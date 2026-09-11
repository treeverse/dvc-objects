import filecmp
import os
import re
import stat
from os import fspath

import pytest

from dvc_objects.fs import utils
from dvc_objects.fs.local import LocalFileSystem


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


@pytest.mark.parametrize("api", ["utility", "filesystem"])
@pytest.mark.parametrize("relative", [False, True])
def test_remove_directory_symlink_preserves_target(tmp_path, api, relative):
    target = tmp_path / "target"
    target.mkdir()
    content = target / "data"
    content.write_bytes(b"keep this dataset")
    link = tmp_path / "link"
    link.symlink_to(target.name if relative else target, target_is_directory=True)
    target.chmod(0o555)
    original_mode = stat.S_IMODE(target.stat().st_mode)
    try:
        if api == "utility":
            utils.remove(link)
        else:
            LocalFileSystem().rm_file(fspath(link))

        assert not link.is_symlink()
        assert content.read_bytes() == b"keep this dataset"
        assert stat.S_IMODE(target.stat().st_mode) == original_mode
    finally:
        target.chmod(0o755)


@pytest.mark.parametrize("kind", ["file", "directory", "broken_symlink"])
def test_remove_other_path_types(tmp_path, kind):
    path = tmp_path / "entry"
    if kind == "file":
        path.write_bytes(b"data")
    elif kind == "directory":
        path.mkdir()
        (path / "child").write_bytes(b"data")
    else:
        path.symlink_to(tmp_path / "missing")

    utils.remove(path)

    assert not os.path.lexists(path)
