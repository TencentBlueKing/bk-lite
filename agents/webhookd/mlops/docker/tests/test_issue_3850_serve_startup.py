import json
import os
import signal
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
                image)
                    [ "$2" = "inspect" ] && exit 0
                    exit 1
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
                    if [ -n "${FAKE_DOCKER_RUN_DELAY_SECONDS:-}" ]; then
                        /bin/sleep "$FAKE_DOCKER_RUN_DELAY_SECONDS"
                    fi
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
                    if [ -n "${FAKE_DOCKER_LOGS_DELAY_SECONDS:-}" ]; then
                        /bin/sleep "$FAKE_DOCKER_LOGS_DELAY_SECONDS"
                    fi
                    message="${FAKE_DOCKER_LOG_MESSAGE:-model load failed: dependency unavailable}"
                    echo "$message"
                    ;;
                update)
                    exit "${FAKE_DOCKER_UPDATE_STATUS:-0}"
                    ;;
                rm)
                    if [ -n "${FAKE_DOCKER_REMOVE_DELAY_SECONDS:-}" ]; then
                        /bin/sleep "$FAKE_DOCKER_REMOVE_DELAY_SECONDS"
                    fi
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
            if [ -n "${FAKE_CURL_DELAY_SECONDS:-}" ]; then
                /bin/sleep "$FAKE_CURL_DELAY_SECONDS"
            fi
            count=0
            if [ -f "$FAKE_CURL_LOG" ]; then
                count=$(wc -l < "$FAKE_CURL_LOG" | tr -d ' ')
            fi
            count=$((count + 1))
            echo "$*" >> "$FAKE_CURL_LOG"
            if [ "$count" -ge "${FAKE_CURL_SUCCEED_AFTER:-999}" ]; then
                instance_id="${FAKE_CURL_INSTANCE_ID:-$SERVING_INSTANCE_ID}"
                printf '{"status":"healthy","startup_instance_id":"%s"}\n' "$instance_id"
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

    def _run_serve(
        self,
        startup_timeout_seconds=3,
        network_mode=None,
        port=None,
        **extra_env,
    ):
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
        if network_mode is not None:
            payload_data["network_mode"] = network_mode
        if port is not None:
            payload_data["port"] = port
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
        self.assertIn("-e BENTOML_CONTAINERIZED=true", docker_calls)
        self.assertIn("-e SERVING_INSTANCE_ID=", docker_calls)
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

    def test_startup_timeout_uses_wall_clock_deadline(self):
        result = self._run_serve(
            startup_timeout_seconds=2,
            FAKE_DOCKER_STATE="running",
            FAKE_CURL_DELAY_SECONDS="2",
            FAKE_CURL_SUCCEED_AFTER="999",
        )

        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            json.loads(result.stdout)["code"],
            "CONTAINER_NOT_READY",
        )
        self.assertEqual(
            len(self.curl_log.read_text(encoding="utf-8").splitlines()),
            1,
        )

    def test_host_network_uses_requested_unique_readiness_port(self):
        result = self._run_serve(
            network_mode="host",
            port=39001,
            FAKE_DOCKER_STATE="running",
            FAKE_CURL_SUCCEED_AFTER="1",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["port"], "39001")
        docker_calls = self.docker_log.read_text(encoding="utf-8")
        self.assertIn("--network host", docker_calls)
        self.assertIn("-e BENTOML_PORT=39001", docker_calls)
        self.assertNotIn(" -p ", f" {docker_calls} ")
        self.assertIn(
            "http://127.0.0.1:39001/health",
            self.curl_log.read_text(encoding="utf-8"),
        )

    def test_host_network_allocates_unique_readiness_port_when_unspecified(self):
        result = self._run_serve(
            network_mode="host",
            FAKE_DOCKER_STATE="running",
            FAKE_CURL_SUCCEED_AFTER="1",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        port = json.loads(result.stdout)["port"]
        self.assertNotEqual(port, "3000")
        docker_calls = self.docker_log.read_text(encoding="utf-8")
        self.assertIn(f"-e BENTOML_PORT={port}", docker_calls)
        self.assertIn(
            f"http://127.0.0.1:{port}/health",
            self.curl_log.read_text(encoding="utf-8"),
        )

    def test_host_network_rejects_health_from_another_instance(self):
        result = self._run_serve(
            startup_timeout_seconds=1,
            network_mode="host",
            port=39002,
            FAKE_DOCKER_STATE="running",
            FAKE_CURL_SUCCEED_AFTER="1",
            FAKE_CURL_INSTANCE_ID="another-serving-instance",
        )

        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["code"], "CONTAINER_NOT_READY")
        self.assertFalse(self.container_state.exists())
        self.assertNotIn(
            "update --restart",
            self.docker_log.read_text(encoding="utf-8"),
        )

    def test_slow_docker_run_is_bounded_and_created_container_is_rolled_back(self):
        started_at = __import__("time").monotonic()
        result = self._run_serve(
            startup_timeout_seconds=2,
            FAKE_DOCKER_RUN_DELAY_SECONDS="4",
        )
        elapsed = __import__("time").monotonic() - started_at

        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["code"], "CONTAINER_START_FAILED")
        self.assertLess(elapsed, 4)
        self.assertFalse(self.container_state.exists())

    def test_slow_rollback_is_bounded_and_reported(self):
        started_at = __import__("time").monotonic()
        result = self._run_serve(
            startup_timeout_seconds=1,
            FAKE_DOCKER_STATE="exited",
            FAKE_DOCKER_REMOVE_DELAY_SECONDS="3",
            SERVING_ROLLBACK_TIMEOUT_SECONDS="1",
        )
        elapsed = __import__("time").monotonic() - started_at

        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["code"], "CONTAINER_ROLLBACK_FAILED")
        self.assertLess(elapsed, 4)
        self.assertTrue(self.container_state.exists())

    def test_slow_log_collection_cannot_consume_container_removal_budget(self):
        started_at = __import__("time").monotonic()
        result = self._run_serve(
            startup_timeout_seconds=2,
            FAKE_DOCKER_STATE="exited",
            FAKE_DOCKER_LOGS_DELAY_SECONDS="3",
            SERVING_ROLLBACK_TIMEOUT_SECONDS="2",
        )
        elapsed = __import__("time").monotonic() - started_at

        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["code"], "CONTAINER_EXITED")
        self.assertLess(elapsed, 3)
        self.assertFalse(self.container_state.exists())

    def test_interrupted_startup_rolls_back_created_container(self):
        env = os.environ.copy()
        env.update(
            {
                "PATH": f"{self.bin_path}:{env['PATH']}",
                "FAKE_DOCKER_LOG": str(self.docker_log),
                "FAKE_CURL_LOG": str(self.curl_log),
                "FAKE_CONTAINER_STATE_FILE": str(self.container_state),
                "FAKE_DOCKER_RUN_DELAY_SECONDS": "10",
            }
        )
        payload = json.dumps(
            {
                "id": "issue-3850-serving",
                "mlflow_tracking_uri": "http://mlflow:5000",
                "mlflow_model_uri": "models:/demo/1",
                "train_image": "test-serving:latest",
                "startup_timeout_seconds": 10,
            }
        )
        process = subprocess.Popen(
            ["bash", str(SCRIPT_PATH), payload],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            start_new_session=True,
        )
        for _ in range(50):
            if self.container_state.exists():
                break
            __import__("time").sleep(0.05)
        self.assertTrue(self.container_state.exists())

        os.killpg(process.pid, signal.SIGTERM)
        process.communicate(timeout=5)

        self.assertNotEqual(process.returncode, 0)
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

    def test_reports_rollback_failure_without_claiming_success(self):
        result = self._run_serve(
            FAKE_DOCKER_STATE="exited",
            FAKE_DOCKER_EXIT_CODE="42",
            FAKE_DOCKER_REMOVE_FAIL="1",
        )

        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            json.loads(result.stdout)["code"],
            "CONTAINER_ROLLBACK_FAILED",
        )
        self.assertTrue(self.container_state.exists())

    def test_restart_policy_update_failure_rolls_back(self):
        result = self._run_serve(
            FAKE_DOCKER_STATE="running",
            FAKE_CURL_SUCCEED_AFTER="1",
            FAKE_DOCKER_UPDATE_STATUS="1",
        )

        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            json.loads(result.stdout)["code"],
            "RESTART_POLICY_UPDATE_FAILED",
        )
        self.assertFalse(self.container_state.exists())

    def test_container_logs_are_returned_as_valid_json(self):
        result = self._run_serve(
            FAKE_DOCKER_STATE="exited",
            FAKE_DOCKER_EXIT_CODE="42",
            FAKE_DOCKER_LOG_MESSAGE='loader failed at C:\\models\\bad "format"',
        )

        self.assertEqual(result.returncode, 1)
        response = json.loads(result.stdout)
        self.assertEqual(response["code"], "CONTAINER_EXITED")
        self.assertIn(r'C:\models\bad "format"', response["detail"])

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
