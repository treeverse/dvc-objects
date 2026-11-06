import errno
import filecmp
import os
import re
import stat
from os import fspath

import pytest

from dvc_objects.fs import utils


@pytest.mark.skipif(
    os.name != "nt", reason="Windows shares attributes across hardlinks"
)
@pytest.mark.parametrize("directory", [False, True])
def test_remove_preserves_readonly_hardlinks(tmp_path, directory):
    cache = tmp_path / "cache"
    cache.write_text("original", encoding="utf8")
    folder = tmp_path / "workspace"
    folder.mkdir()
    link = folder / "file"
    os.link(cache, link)
    cache.chmod(stat.S_IREAD)
    try:
        utils.remove(folder if directory else link)
        assert not link.exists()
        assert cache.stat().st_file_attributes & stat.FILE_ATTRIBUTE_READONLY
        assert cache.read_text(encoding="utf8") == "original"
        with pytest.raises(PermissionError):
            cache.write_text("modified", encoding="utf8")
    finally:
        cache.chmod(stat.S_IREAD | stat.S_IWRITE)


@pytest.mark.skipif(os.name != "nt", reason="Windows read-only deletion")
@pytest.mark.parametrize("directory", [False, True])
@pytest.mark.parametrize(
    "error",
    [PermissionError("deletion denied"), OSError(errno.ENOTSUP, "unsupported")],
)
def test_remove_readonly_failure_preserves_protection(
    tmp_path, mocker, directory, error
):
    cache = tmp_path / "cache"
    cache.write_text("original", encoding="utf8")
    folder = tmp_path / "workspace"
    folder.mkdir()
    link = folder / "link"
    os.link(cache, link)
    cache.chmod(stat.S_IREAD)
    mocker.patch.object(utils.system, "unlink_readonly", side_effect=error)
    try:
        with pytest.raises(OSError, match=re.escape(str(error))) as raised:
            utils.remove(folder if directory else link)
        assert raised.value is error
        assert link.exists()
        assert cache.stat().st_file_attributes & stat.FILE_ATTRIBUTE_READONLY
        assert cache.read_text(encoding="utf8") == "original"
    finally:
        cache.chmod(stat.S_IREAD | stat.S_IWRITE)


@pytest.mark.skipif(os.name != "nt", reason="Windows read-only deletion")
def test_remove_readonly_file(tmp_path):
    path = tmp_path / "file"
    path.write_text("original", encoding="utf8")
    path.chmod(stat.S_IREAD)
    try:
        utils.remove(path)
        assert not path.exists()
    finally:
        if path.exists():
            path.chmod(stat.S_IREAD | stat.S_IWRITE)


def test_tmp_fname():
    file = os.path.join("path", "to", "file")

    def pattern(path):
        return r"^" + re.escape(path) + r"\.[a-z0-9_-]{22}\.tmp$"

    assert re.search(pattern(file), utils.tmp_fname(file), re.IGNORECASE)
    assert re.search(
        pattern(file),
        utils.tmp_fname(file),
        re.IGNORECASE,
    )


def test_move(tmp_path):
    src = tmp_path / "foo"
    src.write_text("foo content", encoding="utf8")

    dest = tmp_path / "some" / "directory"
    dest.mkdir(parents=True)
    utils.move(fspath(src), fspath(dest))
    assert not os.path.isfile(src)
    assert len(os.listdir(dest)) == 1


def test_copyfile(tmp_path):
    src = tmp_path / "foo"
    src.write_text("foo content", encoding="utf8")
    dest = tmp_path / "bar"

    utils.copyfile(fspath(src), fspath(dest))
    assert filecmp.cmp(src, dest, shallow=False)


def test_copyfile_existing_dir(tmp_path):
    src = tmp_path / "foo"
    src.write_text("foo content", encoding="utf8")
    dest = tmp_path / "dir"
    dest.mkdir()

    utils.copyfile(fspath(src), fspath(dest))
    assert filecmp.cmp(src, dest / "foo", shallow=False)
