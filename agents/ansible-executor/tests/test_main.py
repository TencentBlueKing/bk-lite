import os
import re
import subprocess
import sys
from pathlib import Path

from version_info import current_version_line


def test_importing_main_does_not_initialize_ansible_configuration():
    project_root = Path(__file__).resolve().parent.parent
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root)

    subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import main; assert 'ansible.constants' not in sys.modules",
        ],
        cwd=project_root,
        env=env,
        check=True,
    )


def test_version_and_help_share_one_line_without_ansible_config():
    project_root = Path(__file__).resolve().parent.parent
    line = current_version_line()
    assert re.fullmatch(
        r"ansible-executor git=(?:[0-9a-f]{40}|unknown) built=unknown encode_adhoc_module_args=yes linux_script_delivery=yes",
        line,
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root)
    env["ANSIBLE_COLLECTIONS_PATH"] = str(project_root / "missing-collections")
    commands = (["--version"], ["-h"], ["--help"])
    outputs = []
    for args in commands:
        completed = subprocess.run(
            [sys.executable, "main.py", *args],
            cwd=project_root,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        outputs.append(completed.stdout)
    assert outputs[0].strip() == line
    assert line in outputs[1]
    assert line in outputs[2]
