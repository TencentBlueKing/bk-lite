import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


COMMON_SH = Path(__file__).resolve().parents[1] / "common.sh"


class GpuProbePolicyContractTest(unittest.TestCase):
    def test_training_call_without_runner_keeps_on_demand_pull_behavior(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            docker_log = temp_path / "docker.log"
            fake_docker = temp_path / "docker"
            fake_docker.write_text(
                textwrap.dedent(
                    """
                    #!/bin/bash
                    echo "$*" >> "$FAKE_DOCKER_LOG"
                    exit 0
                    """
                ).lstrip(),
                encoding="utf-8",
            )
            fake_docker.chmod(0o755)
            env = os.environ.copy()
            env.update(
                {
                    "PATH": f"{temp_path}:{env['PATH']}",
                    "FAKE_DOCKER_LOG": str(docker_log),
                }
            )

            result = subprocess.run(
                [
                    "bash",
                    "-c",
                    f'source "{COMMON_SH}"; setup_device_args gpu; printf "%s" "$DEVICE_ARGS"',
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "--gpus all")
            docker_call = docker_log.read_text(encoding="utf-8")
            self.assertIn("run --rm --gpus all", docker_call)
            self.assertNotIn("image inspect", docker_call)
            self.assertNotIn("--pull never", docker_call)


if __name__ == "__main__":
    unittest.main()
