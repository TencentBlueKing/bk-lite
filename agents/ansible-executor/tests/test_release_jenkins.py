import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

WRAPPER = Path(__file__).resolve().parents[1] / "support-files/jenkins-build-release.sh"


@pytest.mark.parametrize("stale,fail_build", [(False, False), (True, False), (False, True)])
def test_jenkins_layouts_share_new_build_without_overwriting_old_output(tmp_path, stale, fail_build):
    source = tmp_path / "source/support-files"
    source.mkdir(parents=True)
    shutil.copy2(WRAPPER, source / WRAPPER.name)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    dist = tmp_path / "dist"
    fake_python = tmp_path / "python"
    fake_python.write_text(
        "#!"
        + sys.executable
        + "\n"
        + """
import sys
from pathlib import Path
if """
        + repr(fail_build)
        + """:
    raise SystemExit(1)
d = Path(sys.argv[sys.argv.index('--dist-dir') + 1]) / 'ansible-executor'
d.mkdir(parents=True)
(d / '_internal').mkdir()
(d / '_internal/fixture').write_text('new release')
(d / 'ansible-executor').write_text('#!/bin/sh\\n[ "$1" = "--verify-release" ]\\n')
(d / 'ansible-executor').chmod(0o755)
"""
    )
    fake_python.chmod(0o755)
    alias = dist / "linux/ansible-executor-amd64"
    if stale:
        alias.mkdir(parents=True)
        (alias / "old").write_text("preserve")
    result = subprocess.run(
        ["bash", str(source / WRAPPER.name)],
        env=dict(os.environ, FUSION_RELEASE_PYTHON=str(fake_python), WORKSPACE=str(workspace), DIST=str(dist)),
        capture_output=True,
        timeout=10,
    )
    assert (result.returncode == 0) == (not stale and not fail_build)
    if stale:
        assert (alias / "old").read_text() == "preserve"
        assert not (dist / "linux/ansible-executor").exists()
    elif fail_build:
        assert not alias.exists()
    else:
        for name in ["ansible-executor", "_internal/fixture"]:
            assert (alias / name).read_bytes() == (dist / "linux/ansible-executor" / name).read_bytes()
