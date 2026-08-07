from types import SimpleNamespace

import pytest

import api.collect as collect_api
import api.health as health_api
import api.monitor as monitor_api
from core.collection.request_identity import build_request_task_id
from core.collection.runtime import Submission, SubmissionStatus


class Application:
    def __init__(self, status, fence):
        self.status = status
        self.fence = fence
        self.requests = []

    async def submit(self, request):
        self.requests.append(request)
        return Submission(
            task_id=request.task_id, status=self.status, fence=self.fence
        )


def _request(*, path="/api/collect/collect_info", query="", headers=None):
    return SimpleNamespace(
        method="GET",
        path=path,
        query_string=query,
        headers=headers or {},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("submission_status", "http_status"),
    [
        (SubmissionStatus.ACCEPTED, 202),
        (SubmissionStatus.DUPLICATE_ACTIVE, 202),
        (SubmissionStatus.BUSY, 429),
    ],
)
async def test_configuration_http_maps_runtime_admission_status(
    monkeypatch, submission_status, http_status
):
    app = Application(submission_status, fence=4)
    monkeypatch.setattr(collect_api, "get_collection_application", lambda: app)

    headers = {
        "x-task-id": "caller-old-id",
        "cmdbplugin_name": "mysql_info",
        "cmdbhosts": "10.10.24.1,10.10.24.2",
    }
    request = _request(headers=headers)
    expected_task_id = build_request_task_id(
        "GET", "/api/collect/collect_info", "", headers
    )

    result = await collect_api._submit_collection_run(
        request,
        {"model_id": "mysql", "hosts": "10.10.24.1,10.10.24.2"},
        "mysql",
    )

    assert result.status == http_status
    assert result.headers["x-task-id"] == expected_task_id
    assert result.headers["x-task-status"] == submission_status.value
    assert app.requests[0].task_id == expected_task_id
    assert app.requests[0].task_id != "caller-old-id"
    assert app.requests[0].targets == ("10.10.24.1", "10.10.24.2")


@pytest.mark.asyncio
async def test_monitor_http_uses_request_fingerprint_as_task_id(monkeypatch):
    app = Application(SubmissionStatus.DUPLICATE_ACTIVE, fence=7)
    monkeypatch.setattr(monitor_api, "get_collection_application", lambda: app)

    headers = {
        "x-task-id": "monitor-task-1",
        "host": "10.10.24.8",
        "username": "administrator",
        "password": "secret",
    }
    request = _request(path="/api/monitor/windows_wmi/metrics", headers=headers)
    expected_task_id = build_request_task_id(
        "GET", "/api/monitor/windows_wmi/metrics", "", headers
    )

    result = await monitor_api._submit_monitor_request(
        request,
        {
            "monitor_type": "windows_wmi",
            "host": "10.10.24.8",
            "username": "administrator",
            "password": "secret",
        },
    )

    assert result == {
        "task_id": expected_task_id,
        "status": "duplicate_active",
        "fence": 7,
        "http_status": 202,
    }
    assert app.requests[0].plugin_ref == "windows_wmi.monitor"
    assert app.requests[0].task_id != "monitor-task-1"


@pytest.mark.asyncio
async def test_health_metrics_expose_capacity_and_event_loop_lag(monkeypatch):
    class RuntimeApplication:
        async def stats(self):
            return {
                "healthy": True,
                "active_runs": 3,
                "active_targets": 120,
                "target_worker_tasks": 180,
                "max_active_runs": 16,
                "max_active_targets": 200,
                "event_loop_lag_seconds": 0.004,
                "event_loop_lag_p99_seconds": 0.009,
                "submissions": {"busy": 2, "conflict": 1},
                "plugin_timeout_total": 4,
                "result_publish_failure_total": 2,
                "lease_takeover_total": 1,
            }

    monkeypatch.setattr(
        health_api,
        "get_collection_application",
        lambda: RuntimeApplication(),
    )

    result = await health_api.prometheus_metrics(_request())
    body = result.body.decode()

    assert "stargazer_collection_active_targets 120" in body
    assert "stargazer_collection_target_worker_tasks 180" in body
    assert "stargazer_event_loop_lag_p99_seconds 0.009" in body
    assert "stargazer_collection_submission_rejected_total 3" in body
    assert "stargazer_collection_plugin_timeout_total 4" in body
    assert "stargazer_collection_result_publish_failure_total 2" in body
    assert "stargazer_collection_lease_takeover_total 1" in body
