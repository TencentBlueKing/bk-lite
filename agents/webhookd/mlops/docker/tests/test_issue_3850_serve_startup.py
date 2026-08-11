import json
import os
import signal
import subprocess
import time
import unittest
from agents.webhookd.mlops.docker.tests.serve_test_support import (
    DockerServingTestCase,
    SCRIPT_PATH,
)


class DockerServingStartupContractTest(DockerServingTestCase):

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

    def test_json_preflight_consumes_request_entry_budget(self):
        result = self._run_serve(
            startup_timeout_seconds=1,
            FAKE_JQ_DELAY_SECONDS="0.15",
            FAKE_DOCKER_STATE="running",
            FAKE_CURL_SUCCEED_AFTER="1",
        )

        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["code"], "DOCKER_CHECK_FAILED")
        self.assertFalse(self.docker_log.exists())

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
            startup_timeout_seconds=2,
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

    def test_bridge_accepts_legacy_image_during_identity_rollout(self):
        result = self._run_serve(
            startup_timeout_seconds=2,
            FAKE_DOCKER_STATE="running",
            FAKE_LEGACY_HEALTH="1",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        curl_calls = self.curl_log.read_text(encoding="utf-8")
        self.assertIn("/health", curl_calls)
        self.assertIn("/readyz", curl_calls)

    def test_strict_identity_policy_rejects_legacy_bridge_image(self):
        result = self._run_serve(
            startup_timeout_seconds=2,
            FAKE_DOCKER_STATE="running",
            FAKE_LEGACY_HEALTH="1",
            SERVING_REQUIRE_INSTANCE_ID="true",
        )

        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["code"], "CONTAINER_NOT_READY")
        self.assertFalse(self.container_state.exists())

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

    def test_gpu_probe_uses_total_budget_without_implicit_pull(self):
        started_at = __import__("time").monotonic()
        result = self._run_serve(
            startup_timeout_seconds=2,
            device="gpu",
            FAKE_GPU_PROBE_DELAY_SECONDS="4",
            FAKE_GPU_AVAILABLE="0",
        )
        elapsed = __import__("time").monotonic() - started_at

        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["code"], "DEVICE_SETUP_FAILED")
        self.assertLess(elapsed, 4)
        docker_calls = self.docker_log.read_text(encoding="utf-8")
        self.assertIn("image inspect nvidia/cuda:11.0-base", docker_calls)
        self.assertIn("--pull never", docker_calls)
        self.assertFalse(self.container_state.exists())

    def test_missing_gpu_probe_image_is_explicitly_pulled(self):
        result = self._run_serve(
            device="gpu",
            FAKE_GPU_IMAGE_PRESENT="0",
            FAKE_GPU_AVAILABLE="0",
            FAKE_DOCKER_STATE="running",
            FAKE_CURL_SUCCEED_AFTER="1",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        docker_calls = self.docker_log.read_text(encoding="utf-8")
        self.assertIn("pull nvidia/cuda:11.0-base", docker_calls)
        self.assertIn("--pull never", docker_calls)

    def test_slow_gpu_image_pull_is_bounded(self):
        started_at = time.monotonic()
        result = self._run_serve(
            startup_timeout_seconds=2,
            device="gpu",
            FAKE_GPU_IMAGE_PRESENT="0",
            FAKE_GPU_PULL_DELAY_SECONDS="4",
        )
        elapsed = time.monotonic() - started_at

        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["code"], "DEVICE_SETUP_FAILED")
        self.assertLess(elapsed, 4)
        docker_calls = self.docker_log.read_text(encoding="utf-8")
        self.assertIn("pull nvidia/cuda:11.0-base", docker_calls)
        self.assertFalse(self.container_state.exists())

    def test_auto_device_adds_gpu_only_after_successful_bounded_probe(self):
        result = self._run_serve(
            device="auto",
            FAKE_GPU_AVAILABLE="0",
            FAKE_DOCKER_STATE="running",
            FAKE_CURL_SUCCEED_AFTER="1",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        main_run = next(
            call
            for call in self.docker_log.read_text(encoding="utf-8").splitlines()
            if call.startswith("run ") and "--name issue-3850-serving" in call
        )
        self.assertIn("--gpus all", main_run)

    def test_slow_rollback_is_bounded_and_reported(self):
        started_at = __import__("time").monotonic()
        result = self._run_serve(
            startup_timeout_seconds=3,
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
                "FAKE_LABEL_QUERY_COUNT_FILE": str(self.label_query_count),
                "FAKE_REMOVE_ATTEMPT_COUNT_FILE": str(self.remove_attempt_count),
                "FAKE_DOCKER_RUN_DELAY_SECONDS": "10",
                "REAL_JQ_PATH": self.real_jq_path,
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
        for _ in range(200):
            if self.container_state.exists():
                break
            time.sleep(0.05)
        self.assertTrue(self.container_state.exists())

        os.killpg(process.pid, signal.SIGTERM)
        process.communicate(timeout=5)

        self.assertNotEqual(process.returncode, 0)
        self.assertFalse(self.container_state.exists())

    def test_outer_sigkill_rolls_back_created_container(self):
        env = os.environ.copy()
        env.update(
            {
                "PATH": f"{self.bin_path}:{env['PATH']}",
                "FAKE_DOCKER_LOG": str(self.docker_log),
                "FAKE_CURL_LOG": str(self.curl_log),
                "FAKE_CONTAINER_STATE_FILE": str(self.container_state),
                "FAKE_LABEL_QUERY_COUNT_FILE": str(self.label_query_count),
                "FAKE_REMOVE_ATTEMPT_COUNT_FILE": str(self.remove_attempt_count),
                "FAKE_DOCKER_RUN_DELAY_SECONDS": "10",
                "FAKE_SKIP_CIDFILE": "1",
                "FAKE_LABEL_VISIBLE_AFTER": "2",
                "FAKE_DOCKER_REMOVE_FAILS_BEFORE": "1",
                "REAL_JQ_PATH": self.real_jq_path,
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
        for _ in range(100):
            if self.container_state.exists():
                break
            time.sleep(0.02)
        self.assertTrue(self.container_state.exists())

        os.killpg(process.pid, signal.SIGKILL)
        process.communicate(timeout=5)

        for _ in range(100):
            if not self.container_state.exists():
                break
            time.sleep(0.02)
        self.assertFalse(self.container_state.exists())
        self.assertIn(
            "rm -f fake-container-id",
            self.docker_log.read_text(encoding="utf-8"),
        )
        self.assertGreaterEqual(
            int(self.label_query_count.read_text(encoding="utf-8")),
            2,
        )
        self.assertGreaterEqual(
            int(self.remove_attempt_count.read_text(encoding="utf-8")),
            2,
        )

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


if __name__ == "__main__":
    unittest.main()
