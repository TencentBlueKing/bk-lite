import json
import os
import subprocess
from pathlib import Path

import pytest

from apps.mlops.utils.webhook_client import WebhookClient


REPO_ROOT = Path(__file__).resolve().parents[4]
BASE_PAYLOAD = {
    "id": "TimeseriesPredict_Serving_1",
    "mlflow_tracking_uri": "http://mlflow:15000",
    "mlflow_model_uri": "models:/timeseries/1",
    "train_image": "classify-timeseries:latest",
    "device": "cpu",
    "timeseries_predict_timeout_seconds": 75,
}


def _write_executable(path, source):
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)


def _run_serve_script(tmp_path, runtime, payload, mode="success"):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    capture_file = tmp_path / f"{runtime}-capture"
    if runtime == "docker":
        _write_executable(
            bin_dir / "docker",
            """#!/bin/bash
echo "$*" >> "$CAPTURE_FILE"
case "$1 $2" in
  "ps -a")
    if [ "$STUB_MODE" = "existing" ]; then echo "TimeseriesPredict_Serving_1"; fi
    exit 0
    ;;
  "images --format") echo "classify-timeseries:latest"; exit 0 ;;
  "run -d")
    if [ "$STUB_MODE" = "dependency_failure" ]; then echo "docker unavailable" >&2; exit 1; fi
    echo "container-id"
    exit 0
    ;;
  "ps -q") echo "container-id"; exit 0 ;;
esac
exit 0
""",
        )
        _write_executable(bin_dir / "sleep", "#!/bin/bash\nexit 0\n")
        _write_executable(bin_dir / "ss", "#!/bin/bash\nexit 0\n")
        script = REPO_ROOT / "agents/webhookd/mlops/docker/serve.sh"
    else:
        _write_executable(
            bin_dir / "kubectl",
            """#!/bin/bash
if [ "$1 $2" = "get namespace" ]; then exit 0; fi
if [ "$1 $2" = "get deployment" ]; then
  if [ "$STUB_MODE" = "existing" ]; then
    if [[ "$*" == *"jsonpath"* ]]; then echo "1"; fi
    exit 0
  fi
  exit 1
fi
if [ "$1 $2" = "apply -f" ]; then
  cat > "$CAPTURE_FILE"
  if [ "$STUB_MODE" = "dependency_failure" ]; then echo "cluster unavailable" >&2; exit 1; fi
  exit 0
fi
if [ "$1 $2" = "get svc" ]; then echo "31001"; exit 0; fi
exit 0
""",
        )
        script = REPO_ROOT / "agents/webhookd/mlops/kubernetes/serve.sh"

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["CAPTURE_FILE"] = str(capture_file)
    env["STUB_MODE"] = mode
    result = subprocess.run(
        ["bash", str(script), json.dumps(payload)],
        capture_output=True,
        check=False,
        env=env,
        text=True,
    )
    captured = capture_file.read_text(encoding="utf-8") if capture_file.exists() else ""
    return result, captured


def _run_kubernetes_remove_script(tmp_path, mode):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    capture_file = tmp_path / "kubectl-capture"
    deleted_file = tmp_path / "service-deleted"
    _write_executable(
        bin_dir / "kubectl",
        """#!/bin/bash
echo "$*" >> "$CAPTURE_FILE"
if [ "$1 $2" = "get job" ] || [ "$1 $2" = "get deployment" ]; then
  exit 0
fi
if [ "$1 $2" = "get service" ]; then
  if [ ! -f "$DELETED_FILE" ]; then echo "service/orphan-svc"; fi
  exit 0
fi
if [ "$1 $2" = "delete service" ]; then
  if [ "$STUB_MODE" = "delete_failure" ]; then echo "delete failed" >&2; exit 1; fi
  touch "$DELETED_FILE"
  exit 0
fi
exit 0
""",
    )
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["CAPTURE_FILE"] = str(capture_file)
    env["DELETED_FILE"] = str(deleted_file)
    env["STUB_MODE"] = mode
    script = REPO_ROOT / "agents/webhookd/mlops/kubernetes/remove.sh"
    result = subprocess.run(
        ["bash", str(script), json.dumps({"id": "orphan", "namespace": "mlops"})],
        capture_output=True,
        check=False,
        env=env,
        text=True,
    )
    captured = capture_file.read_text(encoding="utf-8") if capture_file.exists() else ""
    return result, captured


def _run_kubernetes_status_script(tmp_path, mode):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_executable(
        bin_dir / "kubectl",
        """#!/bin/bash
if [ "$1 $2" = "get job" ] || [ "$1 $2" = "get deployment" ]; then
  if [ "$STUB_MODE" = "workload_query_failure" ]; then exit 1; fi
  exit 0
fi
if [ "$1 $2" = "get service" ]; then
  if [ "$STUB_MODE" = "orphan_service" ]; then
    echo '{"metadata":{"name":"timeseriespredict-serving-1-svc"}}'
  elif [ "$STUB_MODE" = "query_failure" ]; then
    exit 1
  fi
  exit 0
fi
exit 0
""",
    )
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["STUB_MODE"] = mode
    script = REPO_ROOT / "agents/webhookd/mlops/kubernetes/status.sh"
    result = subprocess.run(
        [
            "bash",
            str(script),
            json.dumps(
                {
                    "id": "TimeseriesPredict_Serving_1",
                    "namespace": "mlops",
                }
            ),
        ],
        capture_output=True,
        check=False,
        env=env,
        text=True,
    )
    return result


def _run_stop_script(tmp_path, runtime, mode, remove=True):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    capture_file = tmp_path / f"{runtime}-stop-capture"
    deleted_file = tmp_path / "service-deleted"
    if runtime == "docker":
        _write_executable(
            bin_dir / "docker",
            """#!/bin/bash
echo "$*" >> "$CAPTURE_FILE"
if [ "$1 $2" = "ps -a" ]; then
  if [ "$STUB_MODE" != "missing" ]; then echo "TimeseriesPredict_Serving_1"; fi
  exit 0
fi
if [ "$1" = "stop" ]; then exit 0; fi
if [ "$1" = "rm" ]; then
  if [ "$STUB_MODE" = "remove_failure" ]; then echo "remove failed" >&2; exit 1; fi
  exit 0
fi
exit 0
""",
        )
        script = REPO_ROOT / "agents/webhookd/mlops/docker/stop.sh"
    else:
        _write_executable(
            bin_dir / "kubectl",
            """#!/bin/bash
echo "$*" >> "$CAPTURE_FILE"
if [ "$1 $2" = "get job" ] || [ "$1 $2" = "get deployment" ]; then
  exit 0
fi
if [ "$1 $2" = "get service" ]; then
  if { [ "$STUB_MODE" = "orphan_service" ] || [ "$STUB_MODE" = "service_delete_failure" ]; } && [ ! -f "$DELETED_FILE" ]; then
    echo "service/orphan-svc"
  fi
  exit 0
fi
if [ "$1 $2" = "delete service" ]; then
  if [ "$STUB_MODE" = "service_delete_failure" ]; then echo "delete failed" >&2; exit 1; fi
  touch "$DELETED_FILE"
  exit 0
fi
exit 0
""",
        )
        script = REPO_ROOT / "agents/webhookd/mlops/kubernetes/stop.sh"

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["CAPTURE_FILE"] = str(capture_file)
    env["DELETED_FILE"] = str(deleted_file)
    env["STUB_MODE"] = mode
    payload = {"id": "TimeseriesPredict_Serving_1", "remove": remove, "namespace": "mlops"}
    result = subprocess.run(
        ["bash", str(script), json.dumps(payload)],
        capture_output=True,
        check=False,
        env=env,
        text=True,
    )
    captured = capture_file.read_text(encoding="utf-8") if capture_file.exists() else ""
    return result, captured


def test_webhook_client_forwards_timeseries_budget(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        WebhookClient,
        "_request",
        staticmethod(lambda endpoint, payload: captured.update(endpoint=endpoint, payload=payload) or {"status": "success"}),
    )

    WebhookClient.serve(
        "TimeseriesPredict_Serving_1",
        "http://mlflow:15000",
        "models:/timeseries/1",
        timeseries_predict_timeout_seconds=75,
    )

    assert captured["endpoint"] == "serve"
    assert captured["payload"]["timeseries_predict_timeout_seconds"] == 75


def test_webhook_client_omits_budget_for_other_services(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        WebhookClient,
        "_request",
        staticmethod(lambda endpoint, payload: captured.update(payload) or {"status": "success"}),
    )

    WebhookClient.serve("Anomaly_Serving_1", "http://mlflow:15000", "models:/anomaly/1")

    assert "timeseries_predict_timeout_seconds" not in captured


@pytest.mark.parametrize("invalid_timeout", [0, 291])
def test_webhook_client_rejects_invalid_budget(monkeypatch, invalid_timeout):
    monkeypatch.setattr(WebhookClient, "_request", staticmethod(lambda endpoint, payload: {"status": "success"}))

    with pytest.raises(ValueError, match="between 1 and 290"):
        WebhookClient.serve(
            "TimeseriesPredict_Serving_1",
            "http://mlflow:15000",
            "models:/timeseries/1",
            timeseries_predict_timeout_seconds=invalid_timeout,
        )


@pytest.mark.parametrize("runtime", ["docker", "kubernetes"])
def test_serve_script_injects_timeseries_budget(tmp_path, runtime):
    result, captured = _run_serve_script(tmp_path, runtime, BASE_PAYLOAD)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "TIMESERIES_PREDICT_TIMEOUT_SECONDS" in captured
    assert "75" in captured


@pytest.mark.parametrize("runtime", ["docker", "kubernetes"])
def test_serve_script_omits_timeseries_budget_for_other_services(tmp_path, runtime):
    payload = {key: value for key, value in BASE_PAYLOAD.items() if key != "timeseries_predict_timeout_seconds"}

    result, captured = _run_serve_script(tmp_path, runtime, payload)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "TIMESERIES_PREDICT_TIMEOUT_SECONDS" not in captured


@pytest.mark.parametrize(
    ("runtime", "expected_code"),
    [
        ("docker", "CONTAINER_ALREADY_EXISTS"),
        ("kubernetes", "DEPLOYMENT_ALREADY_EXISTS"),
    ],
)
def test_serve_script_rejects_existing_resource_without_replacing_it(tmp_path, runtime, expected_code):
    result, captured = _run_serve_script(tmp_path, runtime, BASE_PAYLOAD, mode="existing")

    assert result.returncode == 1
    error = json.loads(result.stdout)
    assert error["code"] == expected_code
    assert "run -d" not in captured
    assert "apiVersion:" not in captured


@pytest.mark.parametrize(
    ("runtime", "expected_code"),
    [
        ("docker", "CONTAINER_START_FAILED"),
        ("kubernetes", "RESOURCE_APPLY_FAILED"),
    ],
)
def test_serve_script_reports_dependency_failure(tmp_path, runtime, expected_code):
    result, _ = _run_serve_script(tmp_path, runtime, BASE_PAYLOAD, mode="dependency_failure")

    assert result.returncode == 1
    error = json.loads(result.stdout)
    assert error["code"] == expected_code


@pytest.mark.parametrize("runtime", ["docker", "kubernetes"])
def test_serve_script_rejects_invalid_budget_before_mutation(tmp_path, runtime):
    result, captured = _run_serve_script(
        tmp_path,
        runtime,
        {**BASE_PAYLOAD, "timeseries_predict_timeout_seconds": 291},
    )

    assert result.returncode == 1
    error = json.loads(result.stdout)
    assert error["code"] == "INVALID_PREDICT_TIMEOUT"
    assert captured == ""


def test_kubernetes_remove_deletes_orphan_service_without_deployment(tmp_path):
    result, captured = _run_kubernetes_remove_script(tmp_path, mode="orphan_service")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "delete service orphan-svc" in captured
    assert "Resources removed successfully: Service" in result.stdout


def test_kubernetes_remove_reports_orphan_service_delete_failure(tmp_path):
    result, _ = _run_kubernetes_remove_script(tmp_path, mode="delete_failure")

    assert result.returncode == 1
    error = json.loads(result.stdout)
    assert error["code"] == "SERVICE_DELETE_FAILED"


def test_kubernetes_status_does_not_report_not_found_for_orphan_service(tmp_path):
    result = _run_kubernetes_status_script(tmp_path, mode="orphan_service")

    assert result.returncode == 0, result.stdout + result.stderr
    runtime_status = json.loads(result.stdout)["results"][0]
    assert runtime_status["state"] == "orphaned"


def test_kubernetes_status_reports_not_found_only_when_all_resources_are_absent(tmp_path):
    result = _run_kubernetes_status_script(tmp_path, mode="absent")

    assert result.returncode == 0, result.stdout + result.stderr
    runtime_status = json.loads(result.stdout)["results"][0]
    assert runtime_status["state"] == "not_found"
    assert "Service" in runtime_status["detail"]


def test_kubernetes_status_does_not_hide_service_query_failure(tmp_path):
    result = _run_kubernetes_status_script(tmp_path, mode="query_failure")

    assert result.returncode == 0, result.stdout + result.stderr
    runtime_status = json.loads(result.stdout)["results"][0]
    assert runtime_status["status"] == "error"
    assert runtime_status["state"] == "unknown"


def test_kubernetes_status_does_not_hide_workload_query_failure(tmp_path):
    result = _run_kubernetes_status_script(tmp_path, mode="workload_query_failure")

    assert result.returncode == 0, result.stdout + result.stderr
    runtime_status = json.loads(result.stdout)["results"][0]
    assert runtime_status["status"] == "error"
    assert runtime_status["state"] == "unknown"


@pytest.mark.parametrize("runtime", ["docker", "kubernetes"])
def test_stop_script_reports_removed_when_runtime_is_already_absent(tmp_path, runtime):
    result, _ = _run_stop_script(tmp_path, runtime, mode="missing")

    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["state"] == "removed"


def test_docker_stop_reports_synchronous_terminal_state(tmp_path):
    result, captured = _run_stop_script(tmp_path, "docker", mode="existing")

    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["state"] == "removed"
    assert "stop --time=5 TimeseriesPredict_Serving_1" in captured
    assert "rm TimeseriesPredict_Serving_1" in captured


def test_docker_stop_without_remove_reports_stopped(tmp_path):
    result, _ = _run_stop_script(tmp_path, "docker", mode="existing", remove=False)

    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["state"] == "stopped"


def test_docker_stop_does_not_claim_removed_when_remove_fails(tmp_path):
    result, _ = _run_stop_script(tmp_path, "docker", mode="remove_failure")

    assert result.returncode == 1
    error = json.loads(result.stdout)
    assert error["code"] == "CONTAINER_REMOVE_FAILED"


def test_kubernetes_stop_deletes_orphan_service_and_reports_terminating(tmp_path):
    result, captured = _run_stop_script(tmp_path, "kubernetes", mode="orphan_service")

    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["state"] == "terminating"
    assert "delete service timeseriespredict-serving-1-svc" in captured


def test_kubernetes_stop_does_not_hide_orphan_service_delete_failure(tmp_path):
    result, _ = _run_stop_script(tmp_path, "kubernetes", mode="service_delete_failure")

    assert result.returncode == 1
    error = json.loads(result.stdout)
    assert error["code"] == "SERVICE_DELETE_FAILED"
