import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from agents.webhookd.mlops.docker.tests.serve_test_support import (
    DockerServingTestCase,
)


WATCHDOG_PATH = Path(__file__).resolve().parents[1] / "startup_cleanup_watchdog.py"


class StartupCleanupWatchdogContractTest(DockerServingTestCase):
    def test_parent_sigkill_with_slow_rm_stays_within_rollback_budget(self):
        parent = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        self.addCleanup(lambda: parent.poll() is None and parent.kill())
        cid_file = self.temp_path / "missing.cid"
        commit_file = self.temp_path / "committed"
        handled_file = self.temp_path / "handled"
        failure_file = self.temp_path / "cleanup-failed"
        ready_file = self.temp_path / "ready"
        self.container_state.touch()
        env = os.environ.copy()
        env.update(
            {
                "PATH": f"{self.bin_path}:{env['PATH']}",
                "FAKE_DOCKER_LOG": str(self.docker_log),
                "FAKE_CONTAINER_STATE_FILE": str(self.container_state),
                "FAKE_LABEL_QUERY_COUNT_FILE": str(self.label_query_count),
                "FAKE_REMOVE_ATTEMPT_COUNT_FILE": str(self.remove_attempt_count),
                "FAKE_DOCKER_REMOVE_DELAY_SECONDS": "10",
            }
        )
        watchdog = subprocess.Popen(
            [
                sys.executable,
                str(WATCHDOG_PATH),
                str(parent.pid),
                str(cid_file),
                "slow-rm-instance",
                str(commit_file),
                str(handled_file),
                str(failure_file),
                str(ready_file),
                "1",
            ],
            env=env,
        )
        for _ in range(100):
            if ready_file.exists():
                break
            time.sleep(0.01)
        self.assertTrue(ready_file.exists())

        started_at = time.monotonic()
        os.kill(parent.pid, signal.SIGKILL)
        parent.wait(timeout=1)
        watchdog_status = watchdog.wait(timeout=2)
        elapsed = time.monotonic() - started_at

        self.assertLess(elapsed, 1.5)
        self.assertEqual(watchdog_status, 1)
        self.assertTrue(self.container_state.exists())
        self.assertEqual(cid_file.read_text(encoding="utf-8"), "fake-container-id\n")
        failure_detail = failure_file.read_text(encoding="utf-8")
        self.assertIn("containers=fake-container-id", failure_detail)
        self.assertIn("docker rm timed out", failure_detail)
        self.assertIn(
            "rm -f fake-container-id",
            self.docker_log.read_text(encoding="utf-8"),
        )
