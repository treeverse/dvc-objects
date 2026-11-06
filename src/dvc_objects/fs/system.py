import ctypes
import errno
import logging
import os
import stat
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import AnyFSPath

logger = logging.getLogger(__name__)


has_link = hasattr(os, "link")


def unlink_readonly(path: "AnyFSPath") -> None:
    """Remove a Windows file without changing attributes shared by hardlinks.

    Raise OSError if the OS or filesystem rejects extended file disposition.
    Clearing the read-only attribute as a fallback would unprotect other links.
    """
    if sys.platform == "win32":
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        create = kernel.CreateFileW
        create.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        create.restype = wintypes.HANDLE
        set_info = kernel.SetFileInformationByHandle
        set_info.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            wintypes.LPVOID,
            wintypes.DWORD,
        ]
        set_info.restype = wintypes.BOOL
        close = kernel.CloseHandle
        close.argtypes = [wintypes.HANDLE]
        close.restype = wintypes.BOOL

        delete_access = 0x00010000
        share_read_write_delete = 0x7
        open_existing = 3
        open_reparse_point = 0x00200000
        handle = create(
            os.fsdecode(path),
            delete_access,
            share_read_write_delete,
            None,
            open_existing,
            open_reparse_point,
            None,
        )
        if handle == wintypes.HANDLE(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            # POSIX deletion removes this name; IGNORE_READONLY leaves the shared
            # attribute intact. Do not fall back to chmod if the OS rejects it.
            disposition_ex = 21
            flags = wintypes.DWORD(0x1 | 0x2 | 0x10)
            if not set_info(
                handle, disposition_ex, ctypes.byref(flags), ctypes.sizeof(flags)
            ):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            if not close(handle) and sys.exc_info()[0] is None:
                raise ctypes.WinError(ctypes.get_last_error())
    else:
        raise OSError(errno.ENOTSUP, "read-only unlink is only supported on Windows")


def hardlink(source: "AnyFSPath", link_name: "AnyFSPath") -> None:
    if not has_link:
        # some Python ports (eg: Termux) don't have os.link()
        # see: https://github.com/treeverse/dvc/issues/10875
        raise OSError(errno.ENOTSUP, "hardlink is not supported")

    # NOTE: we should really be using `os.link()` here with
    # `follow_symlinks=True`, but unfortunately the implementation is
    # buggy across platforms, so until it is fixed, we just dereference
    # the symlink ourselves here.
    #
    # See https://bugs.python.org/issue41355 for more info.
    st = os.lstat(source)
    if stat.S_ISLNK(st.st_mode):
        src = os.path.realpath(source)
    else:
        src = source

    os.link(src, link_name)


def symlink(source: "AnyFSPath", link_name: "AnyFSPath") -> None:
    os.symlink(source, link_name)


def _clonefile():
    def _cdll(name):
        return ctypes.CDLL(name, use_errno=True)

    libc = "libc.dylib"
    libc_fallback = "/usr/lib/libSystem.dylib"
    try:
        clib = _cdll(libc)
    except OSError as exc:
        logger.debug(
            "unable to access '%s' (errno '%d'). Falling back to '%s'.",
            libc,
            exc.errno,
            libc_fallback,
        )
        if exc.errno != errno.ENOENT:
            return None
        # NOTE: trying to bypass System Integrity Protection (SIP)
        clib = _cdll(libc_fallback)

    clonefile = getattr(clib, "clonefile", None)
    if clonefile is None:
        logger.debug("'clonefile' is not supported by the standard library")
        return None

    def errcheck(ret, _func, _args):
        if ret:
            err = ctypes.get_errno()
            msg = os.strerror(err)
            raise OSError(err, msg)
        return ret

    clonefile.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    clonefile.restype = ctypes.c_int
    clonefile.errcheck = errcheck

    return clonefile


# NOTE: reflink may (macos) or may not (linux) clone permissions,
# so the user needs to handle those himself.
if sys.platform == "darwin" and (clonefile := _clonefile()):

    def reflink(src, dst):
        clonefile(
            ctypes.c_char_p(os.fsencode(src)),
            ctypes.c_char_p(os.fsencode(dst)),
            ctypes.c_int(0),
        )

elif sys.platform == "linux":
    import fcntl

    FICLONE = 0x40049409

    def reflink(src, dst):
        src_fd = os.open(src, os.O_RDONLY)

        try:
            dst_fd = os.open(dst, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o666)
        except OSError:
            os.close(src_fd)
            raise

        try:
            fcntl.ioctl(dst_fd, FICLONE, src_fd)
        except OSError:
            os.close(src_fd)
            os.close(dst_fd)
            try:
                os.unlink(dst)
            except OSError:
                pass
            raise
        else:
            os.close(src_fd)
            os.close(dst_fd)

else:

    def reflink(src, dst):
        raise OSError(errno.ENOTSUP, "reflink is not supported")


def inode(path: "AnyFSPath") -> int:
    return os.lstat(path).st_ino


def is_symlink(path: "AnyFSPath") -> bool:
    return os.path.islink(path)


def is_hardlink(path: "AnyFSPath") -> bool:
    return os.stat(path).st_nlink > 1
