import json
import runpy
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import release_policy

HOOK = Path(__file__).resolve().parents[1] / "release_runtime_hook.py"


def test_normal_start_does_not_run_release_diagnostics():
    with (
        patch.object(sys, "argv", ["ansible-executor", "--config", "config.yml"]),
        patch.object(release_policy, "runtime_info") as info,
        patch.object(release_policy, "verify_manifest") as verify,
    ):
        runpy.run_path(str(HOOK))
        info.assert_not_called()
        verify.assert_not_called()


@pytest.mark.parametrize("flag", ["--build-info", "--verify-release"])
def test_diagnostics_exit_before_application_start(flag, tmp_path, capsys):
    value = {"openssl": "3.5.9", "cryptography_openssl": "3.5.9"}
    with (
        patch.object(sys, "argv", ["ansible-executor", flag]),
        patch.object(sys, "_MEIPASS", str(tmp_path / "_internal"), create=True),
        patch.object(release_policy, "runtime_info", return_value=value),
        patch.object(release_policy, "verify_manifest", return_value=value) as verify,
    ):
        with pytest.raises(SystemExit) as caught:
            runpy.run_path(str(HOOK))
        assert caught.value.code == 0
        if flag == "--verify-release":
            verify.assert_called_once_with(tmp_path)
    assert json.loads(capsys.readouterr().out) == value


def test_integrity_failure_is_not_suppressed(tmp_path):
    with (
        patch.object(sys, "argv", ["ansible-executor", "--verify-release"]),
        patch.object(sys, "_MEIPASS", str(tmp_path / "_internal"), create=True),
        patch.object(release_policy, "verify_manifest", side_effect=RuntimeError("corrupt")),
    ):
        with pytest.raises(RuntimeError, match="corrupt"):
            runpy.run_path(str(HOOK))
