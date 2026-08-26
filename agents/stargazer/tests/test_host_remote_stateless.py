import hashlib
import importlib
import json
import sys
from unittest.mock import AsyncMock, Mock

import core.collection.host_remote.callback as callback_state
import pytest
from core.collection.contracts import CollectOutcomeStatus, TargetCollectionContext
from core.collection.plugins import MonitorCollectionPlugin
from tasks.collectors.host_collector import HostCollector


@pytest.fixture(autouse=True)
def host_remote_v2_settings(monkeypatch):
    monkeypatch.setenv("HOST_REMOTE_CALLBACK_V2_ENABLED", "true")
    monkeypatch.setenv(
        "HOST_REMOTE_CALLBACK_TOKEN_SECRET",
        "issue-4280-test-token-secret-with-32-bytes",
    )


def _generation_snapshot(generation=None, active_run=None, latest_generation=None):
    generation_json = json.dumps(generation) if generation else ""
    latest_generation = latest_generation or active_run or generation or {}
    active_values = ["", "", "", 0]
    if active_run:
        active_values = [
            str(active_run["fence"]),
            active_run["attempt"],
            active_run["owner_id"],
            1,
        ]
    return [
        generation_json,
        *active_values,
        str(latest_generation.get("fence") or ""),
        latest_generation.get("attempt") or "",
        latest_generation.get("owner_id") or "",
    ]


@pytest.mark.asyncio
async def test_host_remote_uses_unique_fenced_callback_id_per_target(monkeypatch):
    stored = []
    submitted = []

    async def store(task_id, params, ctx):
        stored.append((task_id, params, ctx))

    async def accepted(task_id):
        return None

    async def submit(self, task_id, subject, payload):
        submitted.append((task_id, subject, payload))
        return {"success": True, "result": {"accepted": True}}

    monkeypatch.setattr(callback_state, "store_host_remote_callback_context", store)
    monkeypatch.setattr(callback_state, "mark_host_remote_submit_accepted", accepted)
    monkeypatch.setattr(HostCollector, "submit_collection", submit)
    plugin = MonitorCollectionPlugin()
    context = TargetCollectionContext(
        task_id="monitor-host-run",
        plugin_ref="host.monitor",
        fence=6,
        params={"monitor_type": "host", "ansible_node_id": "node-a"},
        owner_id="pod-a",
        attempt_id="attempt-a",
    )

    first = await plugin.collect(
        "10.10.24.1", {"credential_id": "credential-1"}, context
    )
    second = await plugin.collect(
        "10.10.24.2", {"credential_id": "credential-1"}, context
    )

    assert first.status == second.status == CollectOutcomeStatus.DEFERRED
    assert stored[0][0] != stored[1][0]
    assert stored[0][0].startswith("remote-v2-")
    trusted_identity = stored[0][2]
    callback_identity = submitted[0][2]["context"]
    assert trusted_identity == {
        "protocol_version": "host_remote.v2",
        "token_hash": hashlib.sha256(
            callback_identity["token"].encode("utf-8")
        ).hexdigest(),
        "owner_id": "pod-a",
        "fence": 6,
        "plugin_ref": "host.monitor",
        "target": "10.10.24.1",
        "collection_task_id": "monitor-host-run",
        "attempt": "attempt-a",
        "caller": "node-a",
    }
    assert stored[0][1]["host"] == "10.10.24.1"
    assert "credential_id" not in stored[0][1]
    assert "password" not in stored[0][1]
    assert stored[0][1]["callback_timestamp"] > 0
    assert callback_identity["fence"] == 6
    assert callback_identity["collection_task_id"] == "monitor-host-run"
    assert callback_identity["plugin_ref"] == "host.monitor"
    assert callback_identity["owner_id"] == "pod-a"
    assert callback_identity["attempt"] == "attempt-a"


@pytest.mark.asyncio
async def test_host_remote_issues_one_time_identity_in_forwarded_context(monkeypatch):
    stored = []
    submitted = []

    async def store(task_id, params, ctx):
        stored.append((task_id, params, ctx))

    async def accepted(task_id):
        return None

    async def submit(self, task_id, subject, payload):
        submitted.append((task_id, subject, payload))
        return {"success": True, "result": {"accepted": True}}

    monkeypatch.setattr(callback_state, "store_host_remote_callback_context", store)
    monkeypatch.setattr(callback_state, "mark_host_remote_submit_accepted", accepted)
    monkeypatch.setattr(HostCollector, "submit_collection", submit)
    context = TargetCollectionContext(
        task_id="monitor-host-run",
        plugin_ref="host.monitor",
        fence=6,
        params={"monitor_type": "host", "ansible_node_id": "node-a"},
        owner_id="pod-a",
        attempt_id="attempt-a",
    )

    result = await MonitorCollectionPlugin().collect(
        "10.10.24.1", {"credential_id": "credential-1"}, context
    )

    assert result.status == CollectOutcomeStatus.DEFERRED
    callback_identity = submitted[0][2]["context"]
    assert callback_identity == {
        "protocol_version": "host_remote.v2",
        "token": callback_identity["token"],
        "fence": 6,
        "target": "10.10.24.1",
        "collection_task_id": "monitor-host-run",
        "plugin_ref": "host.monitor",
        "owner_id": "pod-a",
        "attempt": "attempt-a",
        "caller": "node-a",
    }
    assert len(callback_identity["token"]) >= 32
    assert (
        stored[0][2]["token_hash"]
        == hashlib.sha256(callback_identity["token"].encode("utf-8")).hexdigest()
    )
    assert "token" not in stored[0][2]


@pytest.mark.asyncio
async def test_host_remote_duplicate_submission_reuses_stored_identity(monkeypatch):
    submitted = []

    async def store(task_id, params, ctx):
        return {"ctx": dict(ctx)}

    async def accepted(task_id):
        return None

    async def submit(self, task_id, subject, payload):
        submitted.append((task_id, subject, payload))
        return {"success": True, "result": {"accepted": True, "duplicate": True}}

    monkeypatch.setattr(callback_state, "store_host_remote_callback_context", store)
    monkeypatch.setattr(callback_state, "mark_host_remote_submit_accepted", accepted)
    monkeypatch.setattr(HostCollector, "submit_collection", submit)
    context = TargetCollectionContext(
        task_id="monitor-host-run",
        plugin_ref="host.monitor",
        fence=6,
        params={"monitor_type": "host", "ansible_node_id": "node-a"},
        owner_id="pod-a",
        attempt_id="attempt-a",
    )

    first = await MonitorCollectionPlugin().collect(
        "10.10.24.1", {"credential_id": "credential-1"}, context
    )
    second = await MonitorCollectionPlugin().collect(
        "10.10.24.1", {"credential_id": "credential-1"}, context
    )

    assert first.status == second.status == CollectOutcomeStatus.DEFERRED
    assert submitted[0][2]["context"]["token"] == submitted[1][2]["context"]["token"]


@pytest.mark.asyncio
async def test_v2_can_be_disabled_until_old_executors_are_drained(monkeypatch):
    submitted = []

    async def store(task_id, params, ctx):
        return {"ctx": dict(ctx)}

    async def accepted(task_id):
        return None

    async def submit(self, task_id, subject, payload):
        submitted.append((task_id, subject, payload))
        return {"success": True, "result": {"accepted": True}}

    monkeypatch.setenv("HOST_REMOTE_CALLBACK_V2_ENABLED", "false")
    monkeypatch.setattr(callback_state, "store_host_remote_callback_context", store)
    monkeypatch.setattr(callback_state, "mark_host_remote_submit_accepted", accepted)
    monkeypatch.setattr(HostCollector, "submit_collection", submit)
    context = TargetCollectionContext(
        task_id="monitor-host-run",
        plugin_ref="host.monitor",
        fence=6,
        params={"monitor_type": "host", "ansible_node_id": "node-a"},
        owner_id="pod-a",
        attempt_id="attempt-a",
    )

    result = await MonitorCollectionPlugin().collect(
        "10.10.24.1", {"credential_id": "credential-1"}, context
    )

    assert result.status == CollectOutcomeStatus.DEFERRED
    assert submitted[0][0].startswith("remote-")
    assert not submitted[0][0].startswith("remote-v2-")
    assert "context" not in submitted[0][2]


@pytest.mark.asyncio
async def test_v2_fails_closed_without_independent_token_secret(monkeypatch):
    submitted = AsyncMock()
    monkeypatch.delenv("HOST_REMOTE_CALLBACK_TOKEN_SECRET", raising=False)
    monkeypatch.setattr(HostCollector, "submit_collection", submitted)
    context = TargetCollectionContext(
        task_id="monitor-host-run",
        plugin_ref="host.monitor",
        fence=6,
        params={"monitor_type": "host", "ansible_node_id": "node-a"},
        owner_id="pod-a",
        attempt_id="attempt-a",
    )

    with pytest.raises(RuntimeError, match="must contain at least 32 characters"):
        await MonitorCollectionPlugin().collect(
            "10.10.24.1", {"credential_id": "credential-1"}, context
        )

    submitted.assert_not_awaited()


@pytest.mark.asyncio
async def test_host_remote_failed_retry_keeps_shared_callback_context(monkeypatch):
    cleared = AsyncMock()
    logged = []

    async def store(task_id, params, ctx):
        return {"ctx": ctx}

    async def submit(self, task_id, subject, payload):
        return {"success": False, "result": {"accepted": False}}

    monkeypatch.setattr(callback_state, "store_host_remote_callback_context", store)
    monkeypatch.setattr(callback_state, "clear_host_remote_callback_context", cleared)
    monkeypatch.setattr(
        callback_state,
        "log_host_remote_event",
        lambda event, task_id, **fields: logged.append((event, task_id, fields)),
    )
    monkeypatch.setattr(HostCollector, "submit_collection", submit)
    context = TargetCollectionContext(
        task_id="monitor-host-run",
        plugin_ref="host.monitor",
        fence=6,
        params={"monitor_type": "host", "ansible_node_id": "node-a"},
        owner_id="pod-a",
        attempt_id="attempt-a",
    )

    result = await MonitorCollectionPlugin().collect(
        "10.10.24.1", {"credential_id": "credential-1"}, context
    )

    assert result.status == CollectOutcomeStatus.FAILED
    cleared.assert_not_awaited()
    assert len(logged) == 1
    event, task_id, fields = logged[0]
    assert event == "submit_rejected_context_retained"
    assert task_id.startswith("remote-v2-")
    assert fields == {
        "level": "warning",
        "execution": "waiting_callback",
        "failed_stage": "executor_submit",
        "error_type": "executor_rejected",
    }
    assert "token" not in str(logged)


def test_host_remote_event_uses_lazy_stable_template_without_secret(monkeypatch):
    info = Mock()
    monkeypatch.setattr(callback_state.logger, "info", info)

    callback_state.log_host_remote_event(
        "submit_rejected_context_retained",
        "remote-v2-id",
        failed_stage="executor_submit",
        error_type="executor_rejected",
    )

    template, *arguments = info.call_args.args
    assert template == "[Host Remote] event=%s, task_id=%s, %s"
    assert arguments == [
        "submit_rejected_context_retained",
        "remote-v2-id",
        "failed_stage=executor_submit, error_type=executor_rejected",
    ]
    rendered = template % tuple(arguments)
    assert rendered == (
        "[Host Remote] event=submit_rejected_context_retained, "
        "task_id=remote-v2-id, failed_stage=executor_submit, "
        "error_type=executor_rejected"
    )
    assert "token" not in rendered


@pytest.mark.asyncio
async def test_host_remote_rejects_conflicting_stored_identity(monkeypatch):
    submitted = []

    async def store(task_id, params, ctx):
        persisted = dict(ctx)
        persisted["target"] = "10.10.24.99"
        return {"ctx": persisted}

    async def submit(self, task_id, subject, payload):
        submitted.append((task_id, subject, payload))
        return {"success": True, "result": {"accepted": True}}

    async def accepted(task_id):
        return None

    monkeypatch.setattr(callback_state, "store_host_remote_callback_context", store)
    monkeypatch.setattr(callback_state, "mark_host_remote_submit_accepted", accepted)
    monkeypatch.setattr(HostCollector, "submit_collection", submit)
    context = TargetCollectionContext(
        task_id="monitor-host-run",
        plugin_ref="host.monitor",
        fence=6,
        params={"monitor_type": "host", "ansible_node_id": "node-a"},
        owner_id="pod-a",
        attempt_id="attempt-a",
    )

    with pytest.raises(RuntimeError, match="stored identity conflict"):
        await MonitorCollectionPlugin().collect(
            "10.10.24.1", {"credential_id": "credential-1"}, context
        )

    assert submitted == []


@pytest.mark.asyncio
async def test_store_host_remote_context_keeps_first_identity_atomically(monkeypatch):
    class Redis:
        def __init__(self):
            self.values = {}
            self.run = {
                "owner_id": "pod-a",
                "fence": "8",
                "attempt_id": "attempt-a",
            }

        async def eval(self, script, key_count, *args):
            assert key_count == 3
            (
                run_key,
                generation_key,
                context_key,
                owner_id,
                fence,
                attempt_id,
                generation_json,
                context_json,
                ttl_seconds,
            ) = args
            assert run_key.endswith(":run:parent-task")
            assert ttl_seconds > 0
            if self.run != {
                "owner_id": owner_id,
                "fence": str(fence),
                "attempt_id": attempt_id,
            }:
                return [0, ""]
            self.values[generation_key] = generation_json
            if context_key in self.values:
                return [2, self.values[context_key]]
            self.values[context_key] = context_json
            return [1, context_json]

        async def get(self, key):
            return self.values.get(key)

    redis = Redis()

    async def get_pool():
        return redis

    monkeypatch.setattr(callback_state, "_get_host_remote_callback_pool", get_pool)
    first = await callback_state.store_host_remote_callback_context(
        "remote-v2-id",
        {"monitor_type": "host"},
        {
            "protocol_version": "host_remote.v2",
            "token": "first-token",
            "collection_task_id": "parent-task",
            "owner_id": "pod-a",
            "fence": 8,
            "attempt": "attempt-a",
        },
    )
    second = await callback_state.store_host_remote_callback_context(
        "remote-v2-id",
        {"monitor_type": "host"},
        {
            "protocol_version": "host_remote.v2",
            "token": "second-token",
            "collection_task_id": "parent-task",
            "owner_id": "pod-a",
            "fence": 8,
            "attempt": "attempt-a",
        },
    )

    assert first["ctx"]["token"] == "first-token"
    assert second["ctx"]["token"] == "first-token"


@pytest.mark.asyncio
async def test_store_host_remote_context_rejects_stale_parent_generation(monkeypatch):
    class Redis:
        async def eval(self, script, key_count, *args):
            return [0, ""]

    async def get_pool():
        return Redis()

    monkeypatch.setattr(callback_state, "_get_host_remote_callback_pool", get_pool)

    with pytest.raises(RuntimeError, match="generation is stale"):
        await callback_state.store_host_remote_callback_context(
            "remote-v2-id",
            {"monitor_type": "host"},
            {
                "protocol_version": "host_remote.v2",
                "token": "stale-token",
                "collection_task_id": "parent-task",
                "owner_id": "pod-a",
                "fence": 8,
                "attempt": "attempt-a",
            },
        )


def test_host_remote_callback_accepts_current_nested_identity():
    token = "current-one-time-token"
    callback_context = {
        "ctx": {
            "token_hash": hashlib.sha256(token.encode("utf-8")).hexdigest(),
            "fence": 8,
            "target": "10.10.24.1",
            "collection_task_id": "monitor-host-run",
            "plugin_ref": "host.monitor",
            "owner_id": "pod-a",
            "attempt": "attempt-a",
            "caller": "executor-region-a",
        },
        "raw_callback": None,
        "status": {"execution": "waiting_callback"},
    }
    identity = {
        "protocol_version": "host_remote.v2",
        "token": token,
        "fence": 8,
        "target": "10.10.24.1",
        "collection_task_id": "monitor-host-run",
        "plugin_ref": "host.monitor",
        "owner_id": "pod-a",
        "attempt": "attempt-a",
        "caller": "executor-region-a",
    }

    callback_state.validate_host_remote_callback_identity(
        {"task_id": "remote-id", "callback_context": identity},
        callback_context,
    )


@pytest.mark.asyncio
async def test_legacy_inflight_callback_remains_accepted_within_bounded_ttl(
    monkeypatch,
):
    now_ms = 1_800_000
    monkeypatch.setattr(callback_state, "_now_ms", lambda: now_ms)
    callback_context = {
        "task_id": "remote-legacy-id",
        "ctx": {
            "fence": 8,
            "attempt": 8,
            "owner_id": "pod-a",
            "collection_task_id": "monitor-host-run",
        },
        "status": {"execution": "waiting_callback"},
        "raw_callback": None,
        "created_at": now_ms - 30_000,
        "callback_deadline_at": now_ms + 30_000,
    }
    payload = {"task_id": "remote-legacy-id", "result": {"cpu": 1}}

    callback_state.validate_host_remote_callback_identity(
        payload,
        callback_context,
    )
    await callback_state.ensure_host_remote_callback_fence_is_current(callback_context)


def test_expired_legacy_inflight_callback_is_rejected(monkeypatch):
    now_ms = 7_200_000
    monkeypatch.setattr(callback_state, "_now_ms", lambda: now_ms)
    callback_context = {
        "task_id": "remote-legacy-id",
        "ctx": {
            "fence": 8,
            "attempt": 8,
            "owner_id": "pod-a",
            "collection_task_id": "monitor-host-run",
        },
        "status": {"execution": "waiting_callback"},
        "raw_callback": None,
        "created_at": now_ms - 3_700_000,
        "callback_deadline_at": now_ms + 30_000,
    }

    with pytest.raises(RuntimeError, match="legacy compatibility window expired"):
        callback_state.validate_host_remote_callback_identity(
            {"task_id": "remote-legacy-id", "result": {"cpu": 1}},
            callback_context,
        )


def test_host_remote_callback_rejects_forged_token_before_scheduling():
    callback_context = {
        "ctx": {
            "token_hash": hashlib.sha256(b"current-token").hexdigest(),
            "fence": 8,
            "target": "10.10.24.1",
            "collection_task_id": "monitor-host-run",
            "plugin_ref": "host.monitor",
            "owner_id": "pod-a",
            "attempt": "attempt-a",
            "caller": "executor-region-a",
        },
        "raw_callback": None,
        "status": {"execution": "waiting_callback"},
    }

    with pytest.raises(RuntimeError, match="callback token mismatch"):
        callback_state.validate_host_remote_callback_identity(
            {
                "task_id": "remote-id",
                "callback_context": {
                    "protocol_version": "host_remote.v2",
                    "token": "forged-token",
                    "fence": 8,
                    "target": "10.10.24.1",
                    "collection_task_id": "monitor-host-run",
                    "plugin_ref": "host.monitor",
                    "owner_id": "pod-a",
                    "attempt": "attempt-a",
                    "caller": "executor-region-a",
                },
            },
            callback_context,
        )


@pytest.mark.parametrize(
    ("field", "invalid_value", "error_match"),
    [
        ("protocol_version", "host_remote.v1", "protocol version mismatch"),
        ("token", "forged-token", "token mismatch"),
        ("fence", 9, "fencing token mismatch"),
        ("target", "10.10.24.2", "target mismatch"),
        ("collection_task_id", "other-run", "collection task mismatch"),
        ("plugin_ref", "host.other", "plugin mismatch"),
        ("owner_id", "pod-b", "owner mismatch"),
        ("attempt", "attempt-b", "attempt mismatch"),
        ("caller", "executor-region-b", "caller mismatch"),
        ("_deadline", 1, "callback is expired"),
        ("_status", "execution_finished", "duplicate or out of order"),
        ("_raw", {"result": "first"}, "duplicate or out of order"),
    ],
)
@pytest.mark.asyncio
async def test_host_remote_handler_rejects_invalid_identity_without_side_effects(
    monkeypatch,
    field,
    invalid_value,
    error_match,
):
    import core.infra.nats as nats_module

    def register_handler(*args, **kwargs):
        return lambda handler: handler

    monkeypatch.setattr(nats_module, "register_handler", register_handler)
    monkeypatch.delitem(sys.modules, "service.nats_server", raising=False)
    nats_server = importlib.import_module("service.nats_server")
    callback_context = {
        "ctx": {
            "token_hash": hashlib.sha256(b"current-token").hexdigest(),
            "fence": 8,
            "target": "10.10.24.1",
            "collection_task_id": "monitor-host-run",
            "plugin_ref": "host.monitor",
            "owner_id": "pod-a",
            "attempt": "attempt-a",
            "caller": "executor-region-a",
        },
        "raw_callback": None,
        "status": {"execution": "waiting_callback"},
    }
    load_context = AsyncMock(return_value=callback_context)
    ensure_current = AsyncMock()
    claim_processing = AsyncMock(return_value="claim-token")
    record_payload = AsyncMock()
    clear_running = AsyncMock()
    schedule_processing = AsyncMock()
    monkeypatch.setattr(
        nats_server.host_remote_callback,
        "load_host_remote_callback_context",
        load_context,
    )
    monkeypatch.setattr(
        nats_server.host_remote_callback,
        "ensure_host_remote_callback_fence_is_current",
        ensure_current,
    )
    monkeypatch.setattr(
        nats_server.host_remote_callback,
        "claim_host_remote_processing",
        claim_processing,
    )
    monkeypatch.setattr(
        nats_server.host_remote_callback,
        "record_host_remote_callback_payload",
        record_payload,
    )
    monkeypatch.setattr(
        nats_server,
        "_clear_host_remote_running_flag_best_effort",
        clear_running,
    )
    monkeypatch.setattr(
        nats_server,
        "schedule_host_remote_processing",
        schedule_processing,
    )

    callback_identity = {
        "protocol_version": "host_remote.v2",
        "token": "current-token",
        "fence": 8,
        "target": "10.10.24.1",
        "collection_task_id": "monitor-host-run",
        "plugin_ref": "host.monitor",
        "owner_id": "pod-a",
        "attempt": "attempt-a",
        "caller": "executor-region-a",
    }
    if field == "_deadline":
        callback_context["callback_deadline_at"] = invalid_value
    elif field == "_status":
        callback_context["status"]["execution"] = invalid_value
    elif field == "_raw":
        callback_context["raw_callback"] = invalid_value
    else:
        callback_identity[field] = invalid_value
    with pytest.raises(RuntimeError, match=error_match):
        await nats_server.handle_host_remote_callback(
            {
                "args": [
                    {
                        "task_id": "remote-v2-id",
                        "callback_context": callback_identity,
                    }
                ],
                "kwargs": {},
            }
        )

    ensure_current.assert_not_awaited()
    claim_processing.assert_not_awaited()
    record_payload.assert_not_awaited()
    clear_running.assert_not_awaited()
    schedule_processing.assert_not_awaited()


@pytest.mark.asyncio
async def test_host_remote_handler_stops_when_atomic_record_loses_context(
    monkeypatch,
):
    import core.infra.nats as nats_module

    monkeypatch.setattr(
        nats_module,
        "register_handler",
        lambda *args, **kwargs: lambda handler: handler,
    )
    monkeypatch.delitem(sys.modules, "service.nats_server", raising=False)
    nats_server = importlib.import_module("service.nats_server")
    callback_context = {
        "ctx": {},
        "params": {"monitor_type": "host"},
        "status": {"execution": "waiting_callback"},
        "raw_callback": None,
    }
    release_claim = AsyncMock(return_value=True)
    clear_running = AsyncMock()
    schedule_processing = AsyncMock()
    mark_enqueued = AsyncMock()
    monkeypatch.setattr(
        nats_server.host_remote_callback,
        "load_host_remote_callback_context",
        AsyncMock(return_value=callback_context),
    )
    monkeypatch.setattr(
        nats_server.host_remote_callback,
        "validate_host_remote_callback_identity",
        lambda payload, context: None,
    )
    monkeypatch.setattr(
        nats_server.host_remote_callback,
        "ensure_host_remote_callback_fence_is_current",
        AsyncMock(),
    )
    monkeypatch.setattr(
        nats_server.host_remote_callback,
        "claim_host_remote_processing",
        AsyncMock(return_value="claim-token"),
    )
    monkeypatch.setattr(
        nats_server.host_remote_callback,
        "record_host_remote_callback_payload",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        nats_server.host_remote_callback,
        "release_host_remote_processing_claim",
        release_claim,
    )
    monkeypatch.setattr(
        nats_server,
        "_clear_host_remote_running_flag_best_effort",
        clear_running,
    )
    monkeypatch.setattr(
        nats_server,
        "schedule_host_remote_processing",
        schedule_processing,
    )
    monkeypatch.setattr(
        nats_server.host_remote_callback,
        "mark_host_remote_processing_enqueued",
        mark_enqueued,
    )

    with pytest.raises(RuntimeError, match="context disappeared"):
        await nats_server.handle_host_remote_callback(
            {"args": [{"task_id": "remote-v2-id"}], "kwargs": {}}
        )

    release_claim.assert_awaited_once_with("remote-v2-id", "claim-token")
    clear_running.assert_not_awaited()
    schedule_processing.assert_not_awaited()
    mark_enqueued.assert_not_awaited()


@pytest.mark.asyncio
async def test_atomic_record_rejects_duplicate_status(monkeypatch):
    callback_context = {
        "ctx": {
            "collection_task_id": "monitor-host-run",
            "owner_id": "pod-a",
            "fence": 1,
            "attempt": "attempt-a",
        },
        "status": {"execution": "execution_finished"},
        "raw_callback": {"result": "first"},
    }

    class Redis:
        async def eval(self, *args):
            return [4, json.dumps(callback_context)]

    monkeypatch.setattr(
        callback_state,
        "load_host_remote_callback_context",
        AsyncMock(return_value=callback_context),
    )
    monkeypatch.setattr(
        callback_state,
        "_get_host_remote_callback_pool",
        AsyncMock(return_value=Redis()),
    )

    with pytest.raises(RuntimeError, match="duplicate or out of order"):
        await callback_state.record_host_remote_callback_payload(
            "remote-v2-id",
            {"task_id": "remote-v2-id", "callback_context": {}},
        )


@pytest.mark.asyncio
async def test_submit_accepted_does_not_overwrite_completed_callback(monkeypatch):
    logged = []
    completed = {
        "task_id": "remote-v2-id",
        "ctx": {"token_hash": "digest"},
        "status": {"execution": "execution_finished", "delivery": "not_ready"},
        "raw_callback": {"result": {"cpu": 1}},
    }
    stale_waiting = {
        **completed,
        "ctx": {"token": "plaintext", "token_hash": "digest"},
        "status": {"execution": "waiting_callback", "delivery": "not_ready"},
        "raw_callback": None,
    }

    class Redis:
        async def eval(self, *args):
            return [2, json.dumps(completed)]

        async def set(self, *args, **kwargs):
            return True

    monkeypatch.setattr(
        callback_state,
        "load_host_remote_callback_context",
        AsyncMock(return_value=stale_waiting),
    )
    monkeypatch.setattr(
        callback_state,
        "_get_host_remote_callback_pool",
        AsyncMock(return_value=Redis()),
    )
    monkeypatch.setattr(
        callback_state,
        "log_host_remote_event",
        lambda event, task_id, **fields: logged.append((event, task_id, fields)),
    )

    stored = await callback_state.mark_host_remote_submit_accepted("remote-v2-id")

    assert stored["status"]["execution"] == "execution_finished"
    assert stored["raw_callback"] == {"result": {"cpu": 1}}
    assert "token" not in stored["ctx"]
    assert logged == [
        (
            "submit_ack_after_callback",
            "remote-v2-id",
            {"execution": "execution_finished", "delivery": "not_ready"},
        )
    ]


def test_host_remote_callback_rejects_wrong_fence_before_scheduling():
    token = "current-token"
    callback_context = {
        "ctx": {
            "protocol_version": "host_remote.v2",
            "token_hash": hashlib.sha256(token.encode("utf-8")).hexdigest(),
            "fence": 8,
            "target": "10.10.24.1",
            "collection_task_id": "monitor-host-run",
            "plugin_ref": "host.monitor",
            "owner_id": "pod-a",
            "attempt": "attempt-a",
            "caller": "executor-region-a",
        },
        "params": {"monitor_type": "host"},
        "raw_callback": None,
        "status": {"execution": "waiting_callback"},
    }

    with pytest.raises(RuntimeError, match="fencing token mismatch"):
        callback_state.validate_host_remote_callback_identity(
            {
                "task_id": "remote-id",
                "callback_context": {
                    "protocol_version": "host_remote.v2",
                    "token": token,
                    "fence": 7,
                    "target": "10.10.24.1",
                    "collection_task_id": "monitor-host-run",
                    "plugin_ref": "host.monitor",
                    "owner_id": "pod-a",
                    "attempt": "attempt-a",
                    "caller": "executor-region-a",
                },
            },
            callback_context,
        )


def test_host_remote_callback_rejects_untrusted_responder_caller():
    token = "current-token"
    callback_context = {
        "ctx": {
            "protocol_version": "host_remote.v2",
            "token_hash": hashlib.sha256(token.encode("utf-8")).hexdigest(),
            "fence": 8,
            "target": "10.10.24.1",
            "collection_task_id": "monitor-host-run",
            "plugin_ref": "host.monitor",
            "owner_id": "pod-a",
            "attempt": "attempt-a",
            "caller": "executor-region-a",
        },
        "raw_callback": None,
        "status": {"execution": "waiting_callback"},
    }

    with pytest.raises(RuntimeError, match="caller mismatch"):
        callback_state.validate_host_remote_callback_identity(
            {
                "callback_context": {
                    "protocol_version": "host_remote.v2",
                    "token": token,
                    "fence": 8,
                    "target": "10.10.24.1",
                    "collection_task_id": "monitor-host-run",
                    "plugin_ref": "host.monitor",
                    "owner_id": "pod-a",
                    "attempt": "attempt-a",
                    "caller": "executor-region-b",
                },
            },
            callback_context,
        )


@pytest.mark.asyncio
async def test_host_remote_callback_rejects_fence_replaced_by_takeover(
    monkeypatch,
):
    class Redis:
        async def eval(self, script, key_count, generation_key, run_key, fence_key):
            assert key_count == 3
            assert generation_key.endswith(":current_generation:monitor-host-run")
            assert fence_key.endswith(":fence:monitor-host-run")
            return _generation_snapshot(
                {"fence": 9, "attempt": "attempt-a", "owner_id": "pod-a"}
            )

    async def get_pool():
        return Redis()

    monkeypatch.setattr(callback_state, "_get_host_remote_callback_pool", get_pool)

    with pytest.raises(RuntimeError, match="fencing token is stale"):
        await callback_state.ensure_host_remote_callback_fence_is_current(
            {
                "ctx": {
                    "fence": 8,
                    "target": "10.10.24.1",
                    "collection_task_id": "monitor-host-run",
                    "plugin_ref": "host.monitor",
                    "owner_id": "pod-a",
                    "attempt": "attempt-a",
                }
            }
        )


@pytest.mark.asyncio
async def test_host_remote_callback_rejects_replaced_attempt_with_same_fence(
    monkeypatch,
):
    class Redis:
        async def eval(self, script, key_count, generation_key, run_key, fence_key):
            return _generation_snapshot(
                {"fence": 8, "attempt": "attempt-b", "owner_id": "pod-a"}
            )

    async def get_pool():
        return Redis()

    monkeypatch.setattr(callback_state, "_get_host_remote_callback_pool", get_pool)

    with pytest.raises(RuntimeError, match="attempt is stale"):
        await callback_state.ensure_host_remote_callback_fence_is_current(
            {
                "ctx": {
                    "fence": 8,
                    "collection_task_id": "monitor-host-run",
                    "owner_id": "pod-a",
                    "attempt": "attempt-a",
                }
            }
        )


@pytest.mark.asyncio
async def test_host_remote_callback_rejects_replaced_owner(monkeypatch):
    class Redis:
        async def eval(self, script, key_count, generation_key, run_key, fence_key):
            return _generation_snapshot(
                {"fence": 8, "attempt": "attempt-a", "owner_id": "pod-b"}
            )

    async def get_pool():
        return Redis()

    monkeypatch.setattr(callback_state, "_get_host_remote_callback_pool", get_pool)

    with pytest.raises(RuntimeError, match="owner is stale"):
        await callback_state.ensure_host_remote_callback_fence_is_current(
            {
                "ctx": {
                    "fence": 8,
                    "collection_task_id": "monitor-host-run",
                    "owner_id": "pod-a",
                    "attempt": "attempt-a",
                }
            }
        )


@pytest.mark.asyncio
async def test_host_remote_callback_accepts_generation_after_run_key_finished(
    monkeypatch,
):
    class Redis:
        async def eval(self, script, key_count, generation_key, run_key, fence_key):
            assert key_count == 3
            return _generation_snapshot(
                {"fence": 8, "attempt": "attempt-a", "owner_id": "pod-a"}
            )

    async def get_pool():
        return Redis()

    monkeypatch.setattr(callback_state, "_get_host_remote_callback_pool", get_pool)

    await callback_state.ensure_host_remote_callback_fence_is_current(
        {
            "ctx": {
                "fence": 8,
                "collection_task_id": "monitor-host-run",
                "owner_id": "pod-a",
                "attempt": "attempt-a",
            }
        }
    )


@pytest.mark.asyncio
async def test_old_callback_rejected_after_new_run_acquired_before_context_store(
    monkeypatch,
):
    class Redis:
        async def eval(self, script, key_count, generation_key, run_key, fence_key):
            return _generation_snapshot(
                {"fence": 1, "attempt": "attempt-a", "owner_id": "pod-a"},
                {"fence": 1, "attempt": "attempt-b", "owner_id": "pod-b"},
            )

    async def get_pool():
        return Redis()

    monkeypatch.setattr(callback_state, "_get_host_remote_callback_pool", get_pool)

    with pytest.raises(RuntimeError, match="attempt is stale|owner is stale"):
        await callback_state.ensure_host_remote_callback_fence_is_current(
            {
                "ctx": {
                    "fence": 1,
                    "collection_task_id": "monitor-host-run",
                    "owner_id": "pod-a",
                    "attempt": "attempt-a",
                }
            }
        )


@pytest.mark.asyncio
async def test_old_callback_rejected_after_new_run_finished_before_context_store(
    monkeypatch,
):
    class Redis:
        async def eval(self, script, key_count, *keys):
            generation = {
                "fence": 8,
                "attempt": "attempt-a",
                "owner_id": "pod-a",
            }
            if key_count == 2:
                return _generation_snapshot(generation)
            assert key_count == 3
            assert keys[2].endswith(":fence:monitor-host-run")
            return [
                json.dumps(generation),
                "",
                "",
                "",
                0,
                "8",
                "attempt-b",
                "pod-b",
            ]

    async def get_pool():
        return Redis()

    monkeypatch.setattr(callback_state, "_get_host_remote_callback_pool", get_pool)

    with pytest.raises(RuntimeError, match="latest attempt is stale"):
        await callback_state.ensure_host_remote_callback_fence_is_current(
            {
                "ctx": {
                    "fence": 8,
                    "collection_task_id": "monitor-host-run",
                    "owner_id": "pod-a",
                    "attempt": "attempt-a",
                }
            }
        )


@pytest.mark.asyncio
async def test_host_remote_callback_rejects_expired_generation_pointer(monkeypatch):
    class Redis:
        async def eval(self, script, key_count, generation_key, run_key, fence_key):
            return _generation_snapshot()

    async def get_pool():
        return Redis()

    monkeypatch.setattr(callback_state, "_get_host_remote_callback_pool", get_pool)

    with pytest.raises(RuntimeError, match="generation is stale"):
        await callback_state.ensure_host_remote_callback_fence_is_current(
            {
                "ctx": {
                    "fence": 8,
                    "collection_task_id": "monitor-host-run",
                    "owner_id": "pod-a",
                    "attempt": "attempt-a",
                }
            }
        )


@pytest.mark.asyncio
async def test_host_remote_processing_claim_is_cross_pod_atomic(monkeypatch):
    class Redis:
        def __init__(self):
            self.value = ""

        async def set(self, key, value, **kwargs):
            assert kwargs["nx"] is True
            if self.value:
                return False
            self.value = value
            return True

        async def eval(self, script, key_count, key, token):
            if self.value != token:
                return 0
            self.value = ""
            return 1

    redis = Redis()

    async def get_pool():
        return redis

    monkeypatch.setattr(callback_state, "_get_host_remote_callback_pool", get_pool)

    first = await callback_state.claim_host_remote_processing("remote-id")
    second = await callback_state.claim_host_remote_processing("remote-id")

    assert first
    assert second == ""
    assert not await callback_state.release_host_remote_processing_claim(
        "remote-id", "wrong-token"
    )
    assert await callback_state.release_host_remote_processing_claim("remote-id", first)
    assert await callback_state.claim_host_remote_processing("remote-id")


@pytest.mark.asyncio
async def test_host_remote_processing_claim_renews_only_for_its_owner(monkeypatch):
    class Redis:
        async def eval(self, script, key_count, key, token, ttl):
            assert key_count == 1
            assert key.endswith(":remote-id")
            assert ttl > 0
            return int(token == "owner-token")

    async def get_pool():
        return Redis()

    monkeypatch.setattr(callback_state, "_get_host_remote_callback_pool", get_pool)

    assert await callback_state.renew_host_remote_processing_claim(
        "remote-id", "owner-token"
    )
    assert not await callback_state.renew_host_remote_processing_claim(
        "remote-id", "stale-token"
    )
