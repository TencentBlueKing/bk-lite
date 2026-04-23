import asyncio
import sys
import zipfile

import pytest

from service.ansible_runner import _safe_extract_zip, _safe_workspace_path, run_command


def test_safe_workspace_path_rejects_path_traversal(tmp_path):
    with pytest.raises(ValueError):
        _safe_workspace_path(tmp_path, "../outside.yml", "file name")

    with pytest.raises(ValueError):
        _safe_workspace_path(tmp_path, "/tmp/outside.yml", "file name")


def test_safe_extract_zip_rejects_path_traversal(tmp_path):
    archive_path = tmp_path / "payload.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../outside.yml", "bad")

    with zipfile.ZipFile(archive_path) as archive:
        with pytest.raises(ValueError):
            _safe_extract_zip(archive, tmp_path / "workspace")


def test_run_command_timeout_returns_124():
    code, output = asyncio.run(
        run_command(
            [
                sys.executable,
                "-c",
                "import time; time.sleep(10)",
            ],
            timeout=1,
        )
    )

    assert code == 124
    assert output == "command timed out"
