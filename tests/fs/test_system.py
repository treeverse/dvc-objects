import errno
import os
from os import fspath

import pytest

from dvc_objects.fs import system
from dvc_objects.fs.system import hardlink, inode, is_hardlink, is_symlink, symlink


@pytest.mark.skipif(os.name != "nt", reason="Windows deletion API")
@pytest.mark.parametrize("failure", ["open", "disposition", "close", "both"])
def test_unlink_readonly_api_failure(mocker, failure):
    kernel = mocker.Mock()
    kernel.CreateFileW.return_value = (
        system.ctypes.c_void_p(-1).value if failure == "open" else 123
    )
    kernel.SetFileInformationByHandle.return_value = failure not in (
        "disposition",
        "both",
    )
    kernel.CloseHandle.return_value = failure not in ("close", "both")
    mocker.patch.object(system.ctypes, "WinDLL", return_value=kernel)
    last_error = mocker.patch.object(
        system.ctypes, "get_last_error", side_effect=[5, 6]
    )
    with pytest.raises(PermissionError) as error:
        system.unlink_readonly("readonly-file")
    assert error.value.errno == errno.EACCES
    last_error.assert_called_once_with()
    if failure == "open":
        kernel.SetFileInformationByHandle.assert_not_called()
        kernel.CloseHandle.assert_not_called()
    else:
        kernel.CloseHandle.assert_called_once_with(123)


def test_inode(tmp_path):
    file = tmp_path / "foo"
    file.write_text("foo content", encoding="utf8")
    assert inode(fspath(file)) == inode(fspath(file))


def test_symlink(tmp_path):
    (tmp_path / "source").write_bytes(b"source")
    symlink(fspath(tmp_path / "source"), fspath(tmp_path / "dest"))

    assert os.path.islink(tmp_path / "dest")
    assert is_symlink(fspath(tmp_path / "dest"))


def test_hardlink(tmp_path):
    src = tmp_path / "source"
    dest = tmp_path / "dest"
    src.write_bytes(b"source")

    hardlink(fspath(src), fspath(dest))
    assert inode(fspath(src)) == inode(fspath(dest))
    assert is_hardlink(fspath(dest))


def test_hardlink_follows_symlink(tmp_path):
    src = tmp_path / "source"
    inter = tmp_path / "inter"
    dest = tmp_path / "dest"
    src.write_bytes(b"source")

    symlink(fspath(src), fspath(inter))
    hardlink(fspath(inter), fspath(dest))

    assert inode(fspath(src)) == inode(fspath(dest))
    assert is_hardlink(fspath(dest))
