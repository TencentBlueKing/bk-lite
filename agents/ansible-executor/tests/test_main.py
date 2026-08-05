import os
import subprocess
import sys
from pathlib import Path


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
