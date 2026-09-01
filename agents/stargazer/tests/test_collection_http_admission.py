import json
from types import SimpleNamespace

import api.collect as collect_api
import api.health as health_api
import api.monitor as monitor_api
import pytest
from core.collection.enums import WorkloadClass
from core.collection.request_identity import build_request_task_id
from core.collection.runtime import Submission, SubmissionStatus
from core.collection.yaml_target_policy import apply_yaml_target_policy


class Application:
    def __init__(self, status, fence):
        self.status = status
        self.fence = fence
        self.requests = []

    async def submit(self, request):
        self.requests.append(request)
        return Submission(task_id=request.task_id, status=self.status, fence=self.fence)


def _request(*, path="/api/collect/collect_info", query="", headers=None):
    return SimpleNamespace(
        method="GET",
        path=path,
        query_string=query,
        headers=headers or {},
    )


def _collect_request(headers):
    async def receive_body():
        return None

    return SimpleNamespace(
        method="GET",
        path="/api/collect/collect_info",
        query_string="",
        query_args=[],
        headers=headers,
        receive_body=receive_body,
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
async def test_configuration_http_maps_runtime_admission_status(monkeypatch, submission_status, http_status):
    app = Application(submission_status, fence=4)
    monkeypatch.setattr(collect_api, "get_collection_application", lambda: app)

    headers = {
        "x-task-id": "caller-old-id",
        "cmdbplugin_name": "mysql_info",
        "cmdbhosts": "10.10.24.1,10.10.24.2",
    }
    request = _request(headers=headers)
    expected_task_id = build_request_task_id("GET", "/api/collect/collect_info", "", headers)

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
    assert app.requests[0].workload_class is WorkloadClass.CONFIGURATION


@pytest.mark.asyncio
async def test_vmware_legacy_http_headers_use_hostname_not_instance_id(monkeypatch):
    app = Application(SubmissionStatus.ACCEPTED, fence=1)
    monkeypatch.setattr(collect_api, "get_collection_application", lambda: app)

    result = await collect_api.collect(
        _collect_request(
            {
                "cmdbmodel_id": "vmware_vc",
                "cmdbplugin_name": "vmware_info",
                "cmdbexecutor_type": "protocol",
                "cmdbhostname": "10.10.16.254",
                "cmdbport": "443",
                "cmdbssl": "false",
                "cmdbusername": "readonly",
                "cmdbpassword": "not-a-real-secret",
                "instance_id": "cmdb_6",
            }
        )
    )

    request = app.requests[0]
    enriched = apply_yaml_target_policy(request)
    assert result.status == 202
    assert request.targets == ("10.10.16.254",)
    assert request.params["target_is_logical"] is False
    assert enriched.params["preflight_kind"] == "https"
    assert request.credentials[0]["password"] == "not-a-real-secret"
    assert "password" not in request.params


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model_id", "plugin_name", "instance_id"),
    (
        ("qcloud", "qcloud_info", "cmdb_8"),
        ("aliyun", "aliyun_info", "cmdb_7"),
    ),
)
async def test_cloud_http_headers_keep_instance_id_as_logical_target(monkeypatch, model_id, plugin_name, instance_id):
    app = Application(SubmissionStatus.ACCEPTED, fence=1)
    monkeypatch.setattr(collect_api, "get_collection_application", lambda: app)

    result = await collect_api.collect(
        _collect_request(
            {
                "cmdbmodel_id": model_id,
                "cmdbplugin_name": plugin_name,
                "cmdbexecutor_type": "protocol",
                "cmdbhosts": "",
                "cmdbsecret_id": "test-id",
                "cmdbsecret_key": "not-a-real-secret",
                "instance_id": instance_id,
            }
        )
    )

    request = app.requests[0]
    assert result.status == 202
    assert request.targets == (instance_id,)
    assert request.params["target_is_logical"] is True
    assert request.params["preflight_kind"] == "cloud"
    assert "secret_id" not in request.params
    assert "secret_key" not in request.params


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
    expected_task_id = build_request_task_id("GET", "/api/monitor/windows_wmi/metrics", "", headers)

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
    assert app.requests[0].workload_class is WorkloadClass.MONITORING
    assert app.requests[0].task_id != "monitor-task-1"


@pytest.mark.asyncio
async def test_monitor_auth_legacy_mode_preserves_existing_request(monkeypatch):
    app = Application(SubmissionStatus.ACCEPTED, fence=8)
    monkeypatch.setattr(monitor_api, "get_collection_application", lambda: app)
    monkeypatch.delenv("STARGAZER_MONITOR_AUTH_MODE", raising=False)
    monkeypatch.delenv("STARGAZER_MONITOR_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("STARGAZER_MONITOR_AUTH_PREVIOUS_TOKEN", raising=False)

    request = _request(
        path="/api/monitor/host/metrics",
        headers={
            "host": "10.10.24.8",
            "username": "operator",
            "password": "not-a-real-secret",
            "ansible_node_id": "node-1",
        },
    )

    assert await monitor_api.authenticate_monitor_request(request) is None
    result = await monitor_api.host_metrics(request)

    assert result.status == 202
    assert len(app.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "authorization",
    [None, "Bearer wrong-token", "Basic current-token"],
)
async def test_monitor_auth_enforce_rejects_missing_or_invalid_token_without_submit(
    monkeypatch,
    authorization,
):
    app = Application(SubmissionStatus.ACCEPTED, fence=8)
    monkeypatch.setattr(monitor_api, "get_collection_application", lambda: app)
    monkeypatch.setenv("STARGAZER_MONITOR_AUTH_MODE", "enforce")
    monkeypatch.setenv("STARGAZER_MONITOR_AUTH_TOKEN", "current-token")
    headers = {"authorization": authorization} if authorization else {}

    result = await monitor_api.authenticate_monitor_request(_request(path="/api/monitor/host/metrics", headers=headers))

    assert result.status == 401
    assert result.headers["www-authenticate"] == "Bearer"
    assert app.requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize("token", ["current-token", "previous-token"])
async def test_monitor_auth_enforce_accepts_current_and_previous_token(
    monkeypatch,
    token,
):
    monkeypatch.setenv("STARGAZER_MONITOR_AUTH_MODE", "enforce")
    monkeypatch.setenv("STARGAZER_MONITOR_AUTH_TOKEN", "current-token")
    monkeypatch.setenv(
        "STARGAZER_MONITOR_AUTH_PREVIOUS_TOKEN",
        "previous-token",
    )

    result = await monitor_api.authenticate_monitor_request(
        _request(
            path="/api/monitor/host/metrics",
            headers={"authorization": f"Bearer {token}"},
        )
    )

    assert result is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "token"),
    [("enforce", ""), ("unsupported", "current-token")],
)
async def test_monitor_auth_misconfiguration_fails_closed(monkeypatch, mode, token):
    monkeypatch.setenv("STARGAZER_MONITOR_AUTH_MODE", mode)
    monkeypatch.setenv("STARGAZER_MONITOR_AUTH_TOKEN", token)
    monkeypatch.delenv("STARGAZER_MONITOR_AUTH_PREVIOUS_TOKEN", raising=False)

    result = await monitor_api.authenticate_monitor_request(
        _request(
            path="/api/monitor/host/metrics",
            headers={"authorization": "Bearer current-token"},
        )
    )

    assert result.status == 503


@pytest.mark.asyncio
async def test_monitor_auth_rollback_logs_metadata_without_token(monkeypatch):
    messages = []
    monkeypatch.setattr(
        monitor_api.logger,
        "warning",
        lambda template, *args: messages.append(template % args),
    )
    monkeypatch.setenv("STARGAZER_MONITOR_AUTH_MODE", "enforce")
    monkeypatch.setenv("STARGAZER_MONITOR_AUTH_TOKEN", "current-token-secret")
    request = _request(
        path="/api/monitor/host/metrics",
        headers={"authorization": "Bearer rejected-token-secret"},
    )

    assert (await monitor_api.authenticate_monitor_request(request)).status == 401
    monkeypatch.setenv("STARGAZER_MONITOR_AUTH_MODE", "legacy")
    assert await monitor_api.authenticate_monitor_request(request) is None

    assert "current-token-secret" not in str(messages)
    assert "rejected-token-secret" not in str(messages)
    assert any("auth_status=invalid" in message for message in messages)


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
                "max_active_targets": 150,
                "target_task_window": 150,
                "publish_queue_depth": 12,
                "publish_batch_size_p99": 50,
                "run_first_schedule_wait_seconds_p99": 0.02,
                "execution_mode_async_success_total": 119,
                "event_loop_lag_seconds": 0.004,
                "event_loop_lag_p99_seconds": 0.009,
                "plugin_duration_seconds_p99": 0.45,
                "publish_duration_seconds_p99": 0.12,
                "publish_enqueue_duration_seconds_p99": 0.03,
                "thread_count": 24,
                "open_file_descriptors": 88,
                "submissions": {"busy": 2, "conflict": 1},
                "plugin_timeout_total": 4,
                "result_publish_failure_total": 2,
                "lease_takeover_total": 1,
                "job_node_info_lookup_rpc_total": 1,
                "job_node_info_lookup_found_total": 140,
                "job_node_info_lookup_duration_seconds_p99": 0.085,
                "workload_configuration_active": 100,
                "workload_configuration_pending": 40,
                "workload_configuration_borrowed": 20,
                "capacity_group_snmp_active": 80,
                "capacity_group_snmp_pending": 15,
                "capacity_group_snmp_limit": 100,
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
    assert "stargazer_collection_plugin_duration_seconds_p99 0.45" in body
    assert "stargazer_collection_publish_duration_seconds_p99 0.12" in body
    assert "stargazer_collection_publish_enqueue_duration_seconds_p99 0.03" in body
    assert "stargazer_process_threads 24" in body
    assert "stargazer_process_open_file_descriptors 88" in body
    assert "stargazer_collection_submission_rejected_total 3" in body
    assert "stargazer_collection_plugin_timeout_total 4" in body
    assert "stargazer_collection_result_publish_failure_total 2" in body
    assert "stargazer_collection_lease_takeover_total 1" in body
    assert "stargazer_collection_target_task_window 150" in body
    assert "stargazer_collection_publish_queue_depth 12" in body
    assert "stargazer_collection_publish_batch_size_p99 50" in body
    assert "stargazer_collection_run_first_schedule_wait_seconds_p99 0.02" in body
    assert "stargazer_collection_job_node_info_lookup_rpc_total 1" in body
    assert "stargazer_collection_job_node_info_lookup_found_total 140" in body
    assert "stargazer_collection_job_node_info_lookup_duration_seconds_p99 0.085" in body
    assert 'stargazer_collection_execution_mode_success_total{execution_mode="async"} 119' in body
    assert 'stargazer_scheduler_active_targets{workload_class="configuration"} 100' in body
    assert 'stargazer_scheduler_pending_targets{workload_class="configuration"} 40' in body
    assert 'stargazer_scheduler_borrowed_slots{workload_class="configuration"} 20' in body
    assert 'stargazer_capacity_group_active_targets{capacity_group="snmp"} 80' in body
    assert 'stargazer_capacity_group_pending_targets{capacity_group="snmp"} 15' in body
    assert 'stargazer_capacity_group_limit{capacity_group="snmp"} 100' in body


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("redis_ready", "metrics_ready", "expected_status"),
    ((True, True, 200), (True, False, 503), (False, True, 503)),
)
async def test_readiness_requires_redis_and_metrics_transport(
    monkeypatch,
    redis_ready,
    metrics_ready,
    expected_status,
):
    class RuntimeApplication:
        async def readiness(self):
            return {
                "redis": redis_ready,
                "metrics_jetstream": metrics_ready,
                "nats_subscriber": True,
            }

    monkeypatch.setattr(
        health_api,
        "get_collection_application",
        lambda: RuntimeApplication(),
    )

    result = await health_api.readiness_check(_request())
    payload = json.loads(result.body)

    assert result.status == expected_status
    assert payload["ready"] is (expected_status == 200)
    assert payload["checks"]["metrics_jetstream"] == ("connected" if metrics_ready else "disconnected")
    assert payload["checks"]["nats_subscriber"] == "connected"
