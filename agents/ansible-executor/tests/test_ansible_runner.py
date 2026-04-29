import zipfile
from pathlib import Path

import pytest

from service.ansible_runner import _safe_extract_zip, _safe_workspace_path


def test_safe_workspace_path_rejects_parent_escape(tmp_path):
    with pytest.raises(ValueError):
        _safe_workspace_path(tmp_path, "../evil.txt", "file name")


def test_safe_extract_zip_rejects_symlink(tmp_path):
    archive_path = tmp_path / "payload.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        info = zipfile.ZipInfo("link.txt")
        info.create_system = 3
        info.external_attr = 0o120777 << 16
        archive.writestr(info, "target.txt")

    with zipfile.ZipFile(archive_path, "r") as archive:
        with pytest.raises(ValueError):
            _safe_extract_zip(archive, tmp_path / "workspace")


def test_safe_extract_zip_allows_regular_files(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    archive_path = tmp_path / "payload.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("nested/file.txt", "hello")

    with zipfile.ZipFile(archive_path, "r") as archive:
        _safe_extract_zip(archive, workspace)

    assert (workspace / "nested" / "file.txt").read_text(encoding="utf-8") == "hello"
