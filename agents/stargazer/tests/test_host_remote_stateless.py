import pytest

import core.collection.host_remote.callback as callback_state
from core.collection.plugins import MonitorCollectionPlugin
from core.collection.contracts import (
    CollectOutcomeStatus,
    TargetCollectionContext,
)
from tasks.collectors.host_collector import HostCollector


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
    )

    first = await plugin.collect(
        "10.10.24.1", {"credential_id": "credential-1"}, context
    )
    second = await plugin.collect(
        "10.10.24.2", {"credential_id": "credential-1"}, context
    )

    assert first.status == second.status == CollectOutcomeStatus.DEFERRED
    assert stored[0][0] != stored[1][0]
    assert stored[0][2] == {
        "owner_id": "pod-a",
        "fence": 6,
        "plugin_ref": "host.monitor",
        "target": "10.10.24.1",
        "collection_task_id": "monitor-host-run",
            "attempt": 6,
            "caller": "node-a",
        }
    assert stored[0][1]["host"] == "10.10.24.1"
    assert "credential_id" not in stored[0][1]
    assert "password" not in stored[0][1]
    assert stored[0][1]["callback_timestamp"] > 0
    assert submitted[0][2]["collection_fence"] == 6
    assert submitted[0][2]["collection_task_id"] == "monitor-host-run"
    assert submitted[0][2]["collection_plugin_ref"] == "host.monitor"
    assert submitted[0][2]["collection_owner"] == "pod-a"
    assert submitted[0][2]["collection_attempt"] == 6


def test_host_remote_callback_rejects_wrong_fence_before_scheduling():
    callback_context = {
            "ctx": {
                "fence": 8,
                "target": "10.10.24.1",
                "collection_task_id": "monitor-host-run",
                "plugin_ref": "host.monitor",
                "owner_id": "pod-a",
                "attempt": 8,
            },
            "params": {"monitor_type": "host"},
            "raw_callback": None,
            "status": {"execution": "waiting_callback"},
        }

    with pytest.raises(RuntimeError, match="fencing token mismatch"):
        callback_state.validate_host_remote_callback_identity(
            {
                "task_id": "remote-id",
                "collection_fence": 7,
                "collection_target": "10.10.24.1",
                "collection_task_id": "monitor-host-run",
                "collection_plugin_ref": "host.monitor",
                "collection_owner": "pod-a",
                "collection_attempt": 8,
            },
            callback_context,
        )


def test_host_remote_callback_rejects_untrusted_responder_caller():
    callback_context = {
        "ctx": {
            "fence": 8,
            "target": "10.10.24.1",
            "collection_task_id": "monitor-host-run",
            "plugin_ref": "host.monitor",
            "owner_id": "pod-a",
            "attempt": 8,
            "caller": "executor-region-a",
        },
        "raw_callback": None,
        "status": {"execution": "waiting_callback"},
    }

    with pytest.raises(RuntimeError, match="caller mismatch"):
        callback_state.validate_host_remote_callback_identity(
            {
                "collection_fence": 8,
                "collection_target": "10.10.24.1",
                "collection_task_id": "monitor-host-run",
                "collection_plugin_ref": "host.monitor",
                "collection_owner": "pod-a",
                "collection_attempt": 8,
                "collection_caller": "executor-region-b",
            },
            callback_context,
        )


@pytest.mark.asyncio
async def test_host_remote_callback_rejects_fence_replaced_by_takeover(
    monkeypatch,
):
    class Redis:
        async def hget(self, key, field):
            assert key.endswith(":run:monitor-host-run")
            assert field == "fence"
            return "9"

    async def get_pool():
        return Redis()

    monkeypatch.setattr(callback_state, "_get_host_remote_callback_pool", get_pool)

    with pytest.raises(RuntimeError, match="token is stale"):
        await callback_state.ensure_host_remote_callback_fence_is_current(
            {
                "ctx": {
                    "fence": 8,
                    "target": "10.10.24.1",
                    "collection_task_id": "monitor-host-run",
                    "plugin_ref": "host.monitor",
                    "owner_id": "pod-a",
                    "attempt": 8,
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
    assert await callback_state.release_host_remote_processing_claim(
        "remote-id", first
    )
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
