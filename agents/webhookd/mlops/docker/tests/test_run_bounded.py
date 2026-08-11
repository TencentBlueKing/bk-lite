import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


BOUNDED_RUNNER_PATH = Path(__file__).resolve().parents[1] / "run_bounded.py"


class BoundedProcessRunnerContractTest(unittest.TestCase):
    @staticmethod
    def _pid_is_alive(pid: int) -> bool:
        return subprocess.run(
            ["ps", "-p", str(pid)],
            check=False,
            capture_output=True,
        ).returncode == 0

    def test_timeout_includes_term_grace_and_kills_stubborn_descendant(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pid_file = Path(temp_dir) / "child.pid"
            child_code = """
import signal
import subprocess
import sys
import time

child = subprocess.Popen([
    sys.executable,
    "-c",
    "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)",
])
open(sys.argv[1], "w", encoding="utf-8").write(str(child.pid))
signal.signal(signal.SIGTERM, signal.SIG_IGN)
time.sleep(30)
"""
            started_at = time.monotonic()
            result = subprocess.run(
                [
                    sys.executable,
                    str(BOUNDED_RUNNER_PATH),
                    "1",
                    sys.executable,
                    "-c",
                    child_code,
                    str(pid_file),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=3,
            )
            elapsed = time.monotonic() - started_at

            self.assertEqual(result.returncode, 124, result.stderr)
            self.assertLess(elapsed, 1.25)
            child_pid = int(pid_file.read_text(encoding="utf-8"))
            for _ in range(50):
                if not self._pid_is_alive(child_pid):
                    break
                time.sleep(0.02)
            self.assertFalse(self._pid_is_alive(child_pid))

    def test_outer_group_kill_still_reaches_bounded_child(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pid_file = Path(temp_dir) / "child.pid"
            child_code = """
import os
import sys
import time
open(sys.argv[1], "w", encoding="utf-8").write(str(os.getpid()))
time.sleep(30)
"""
            process = subprocess.Popen(
                [
                    sys.executable,
                    str(BOUNDED_RUNNER_PATH),
                    "10",
                    sys.executable,
                    "-c",
                    child_code,
                    str(pid_file),
                ],
                start_new_session=True,
            )
            for _ in range(50):
                if pid_file.exists():
                    break
                time.sleep(0.02)
            self.assertTrue(pid_file.exists())
            child_pid = int(pid_file.read_text(encoding="utf-8"))

            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=3)

            for _ in range(50):
                if not self._pid_is_alive(child_pid):
                    break
                time.sleep(0.02)
            self.assertFalse(self._pid_is_alive(child_pid))


if __name__ == "__main__":
    unittest.main()
