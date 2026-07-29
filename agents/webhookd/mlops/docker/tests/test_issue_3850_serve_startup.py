import json
import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "serve.sh"
REPO_ROOT = Path(__file__).resolve().parents[5]
ALGORITHM_SERVICES = (
    "classify_anomaly_server",
    "classify_image_classification_server",
    "classify_log_server",
    "classify_object_detection_server",
    "classify_timeseries_server",
)


class DockerServingStartupContractTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.temp_path = Path(self.temp_dir.name)
        self.bin_path = self.temp_path / "bin"
        self.bin_path.mkdir()
        self.docker_log = self.temp_path / "docker.log"
        self.curl_log = self.temp_path / "curl.log"
        self.container_state = self.temp_path / "container.state"

        self._write_executable(
            "docker",
            """
            #!/bin/bash
            echo "$*" >> "$FAKE_DOCKER_LOG"
            case "$1" in
                ps)
                    if [ -f "$FAKE_CONTAINER_STATE_FILE" ]; then
                        echo "issue-3850-serving"
                    fi
                    exit 0
                    ;;
                images)
                    echo "test-serving:latest"
                    ;;
                run)
                    if [ -f "$FAKE_CONTAINER_STATE_FILE" ]; then
                        echo "container name already exists" >&2
                        exit 125
                    fi
                    touch "$FAKE_CONTAINER_STATE_FILE"
                    while [ "$#" -gt 0 ]; do
                        if [ "$1" = "--cidfile" ]; then
                            echo "fake-container-id" > "$2"
                            break
                        fi
                        shift
                    done
                    echo "fake-container-id"
                    ;;
                inspect)
                    case "$*" in
                        *State.Status*)
                            echo "${FAKE_DOCKER_STATE:-running}"
                            ;;
                        *State.ExitCode*)
                            echo "${FAKE_DOCKER_EXIT_CODE:-42}"
                            ;;
                        *HostPort*)
                            echo "39000"
                            ;;
                    esac
                    ;;
                logs)
                    echo "model load failed: dependency unavailable"
                    ;;
                update)
                    exit "${FAKE_DOCKER_UPDATE_STATUS:-0}"
                    ;;
                rm)
                    if [ "${FAKE_DOCKER_REMOVE_FAIL:-0}" = "1" ]; then
                        exit 1
                    fi
                    rm -f "$FAKE_CONTAINER_STATE_FILE"
                    ;;
            esac
            """,
        )
        self._write_executable(
            "curl",
            """
            #!/bin/bash
            count=0
            if [ -f "$FAKE_CURL_LOG" ]; then
                count=$(wc -l < "$FAKE_CURL_LOG" | tr -d ' ')
            fi
            count=$((count + 1))
            echo "$*" >> "$FAKE_CURL_LOG"
            if [ "$count" -ge "${FAKE_CURL_SUCCEED_AFTER:-999}" ]; then
                exit 0
            fi
            exit 22
            """,
        )
        self._write_executable("sleep", "#!/bin/bash\nexit 0\n")
        self._write_executable("ss", "#!/bin/bash\nexit 0\n")

    def _write_executable(self, name, content):
        path = self.bin_path / name
        path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
        path.chmod(0o755)

    def _run_serve(self, startup_timeout_seconds=3, **extra_env):
        env = os.environ.copy()
        env.update(
            {
                "PATH": f"{self.bin_path}:{env['PATH']}",
                "FAKE_DOCKER_LOG": str(self.docker_log),
                "FAKE_CURL_LOG": str(self.curl_log),
                "FAKE_CONTAINER_STATE_FILE": str(self.container_state),
            }
        )
        env.update(extra_env)
        payload_data = {
            "id": "issue-3850-serving",
            "mlflow_tracking_uri": "http://mlflow:5000",
            "mlflow_model_uri": "models:/demo/1",
            "train_image": "test-serving:latest",
        }
        if startup_timeout_seconds is not None:
            payload_data["startup_timeout_seconds"] = startup_timeout_seconds
        payload = json.dumps(payload_data)
        return subprocess.run(
            ["bash", str(SCRIPT_PATH), payload],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

    def test_enables_restart_policy_only_after_readiness_succeeds(self):
        result = self._run_serve(
            FAKE_DOCKER_STATE="running",
            FAKE_CURL_SUCCEED_AFTER="2",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            {
                "status": "success",
                "id": "issue-3850-serving",
                "state": "running",
                "port": "39000",
                "detail": "Ready",
            },
        )
        docker_calls = self.docker_log.read_text(encoding="utf-8")
        self.assertIn("--restart no", docker_calls)
        self.assertIn(
            "update --restart unless-stopped fake-container-id",
            docker_calls,
        )
        self.assertNotIn("rm -f fake-container-id", docker_calls)
        self.assertTrue(self.container_state.exists())
        self.assertEqual(
            len(self.curl_log.read_text(encoding="utf-8").splitlines()),
            2,
        )

    def test_reports_model_process_exit_without_enabling_restart_loop(self):
        result = self._run_serve(
            FAKE_DOCKER_STATE="exited",
            FAKE_DOCKER_EXIT_CODE="42",
        )

        self.assertEqual(result.returncode, 1)
        response = json.loads(result.stdout)
        self.assertEqual(response["code"], "CONTAINER_EXITED")
        self.assertIn("42", response["message"])
        docker_calls = self.docker_log.read_text(encoding="utf-8")
        self.assertIn("--restart no", docker_calls)
        self.assertNotIn("update --restart", docker_calls)
        self.assertIn("logs --tail 50 fake-container-id", docker_calls)
        self.assertIn("rm -f fake-container-id", docker_calls)
        self.assertFalse(self.container_state.exists())
        self.assertIn("dependency unavailable", response["detail"])

    def test_reports_not_ready_instead_of_claiming_running(self):
        result = self._run_serve(
            FAKE_DOCKER_STATE="running",
            FAKE_CURL_SUCCEED_AFTER="999",
        )

        self.assertEqual(result.returncode, 1)
        response = json.loads(result.stdout)
        self.assertEqual(response["code"], "CONTAINER_NOT_READY")
        docker_calls = self.docker_log.read_text(encoding="utf-8")
        self.assertNotIn("update --restart", docker_calls)
        self.assertIn("rm -f fake-container-id", docker_calls)
        self.assertFalse(self.container_state.exists())

    def test_failed_startup_can_be_retried_after_rollback(self):
        first_result = self._run_serve(
            FAKE_DOCKER_STATE="exited",
            FAKE_DOCKER_EXIT_CODE="42",
        )
        second_result = self._run_serve(
            FAKE_DOCKER_STATE="running",
            FAKE_CURL_SUCCEED_AFTER="1",
        )

        self.assertEqual(first_result.returncode, 1)
        self.assertEqual(second_result.returncode, 0, second_result.stderr)
        docker_calls = self.docker_log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(sum(call.startswith("run ") for call in docker_calls), 2)
        self.assertEqual(sum(call.startswith("rm -f ") for call in docker_calls), 1)

    def test_existing_container_conflict_is_not_mutated(self):
        self.container_state.touch()

        result = self._run_serve()

        self.assertEqual(result.returncode, 1)
        response = json.loads(result.stdout)
        self.assertEqual(response["code"], "CONTAINER_ALREADY_EXISTS")
        docker_calls = self.docker_log.read_text(encoding="utf-8")
        self.assertNotIn("\nrun ", f"\n{docker_calls}")
        self.assertNotIn("\nrm ", f"\n{docker_calls}")
        self.assertTrue(self.container_state.exists())

    def test_rejects_invalid_startup_timeout(self):
        result = self._run_serve(startup_timeout_seconds=0)

        self.assertEqual(result.returncode, 1)
        response = json.loads(result.stdout)
        self.assertEqual(response["code"], "INVALID_STARTUP_TIMEOUT")
        self.assertFalse(self.docker_log.exists())


class AlgorithmEntrypointContractTest(unittest.TestCase):
    def test_bentoml_exit_code_reaches_container_entrypoint(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bin_path = Path(temp_dir)
            fake_python = bin_path / "python3"
            fake_python.write_text("#!/bin/bash\nexit 42\n", encoding="utf-8")
            fake_python.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = f"{bin_path}:{env['PATH']}"

            for service in ALGORITHM_SERVICES:
                with self.subTest(service=service):
                    startup = (
                        REPO_ROOT
                        / "algorithms"
                        / service
                        / "support-files"
                        / "release"
                        / "startup.sh"
                    )
                    result = subprocess.run(
                        ["bash", str(startup)],
                        check=False,
                        capture_output=True,
                        text=True,
                        env=env,
                    )
                    self.assertEqual(result.returncode, 42)


if __name__ == "__main__":
    unittest.main()
