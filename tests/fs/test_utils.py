import filecmp
import os
import re
import shutil
from os import fspath

import pytest

from dvc_objects.fs import utils


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


@pytest.mark.parametrize("alias", ["same", "hardlink", "symlink", "directory"])
@pytest.mark.parametrize("fallback", [False, True])
def test_copyfile_same_file_preserves_contents(tmp_path, mocker, alias, fallback):
    src = tmp_path / "source"
    src.write_bytes(b"model checkpoint")
    if alias == "same":
        dest = src
    elif alias == "directory":
        dest = tmp_path
    else:
        dest = tmp_path / "alias"
        if alias == "hardlink":
            os.link(src, dest)
        else:
            dest.symlink_to(src)

    if fallback:
        mocker.patch.object(utils.system, "reflink", side_effect=OSError)
        mocker.patch.object(utils, "COPY_PBAR_MIN_SIZE", 0)

    with pytest.raises(shutil.SameFileError):
        utils.copyfile(src, dest)

    assert src.read_bytes() == b"model checkpoint"


@pytest.mark.parametrize("existing_dest", [False, True])
def test_copyfile_progress_fallback(tmp_path, mocker, existing_dest):
    src = tmp_path / "source"
    dest = tmp_path / "destination"
    src.write_bytes(b"model checkpoint")
    if existing_dest:
        dest.write_bytes(b"old destination content")
    mocker.patch.object(utils.system, "reflink", side_effect=OSError)
    mocker.patch.object(utils, "COPY_PBAR_MIN_SIZE", 0)

    utils.copyfile(src, dest)

    assert src.read_bytes() == dest.read_bytes() == b"model checkpoint"
