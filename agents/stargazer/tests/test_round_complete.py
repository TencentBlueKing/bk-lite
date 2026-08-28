"""轮次完成标记契约测试。"""

import pytest
from core.collection.round_complete import (
    ROUND_COMPLETE_METRIC,
    build_round_complete_labels,
    build_round_complete_prometheus,
    publish_round_complete_marker,
    resolve_round_marker_identity,
)
from core.collection.runtime import CollectionRequest


def test_build_round_complete_prometheus_uses_stable_labels_and_round_ts():
    payload = build_round_complete_prometheus(
        round_ts=1_700_000_000,
        instance_id="cmdb_12",
        model_id="vmware_vc",
        extra_labels={
            "collection_role": "topology",
            "run_attempt_id": "attempt-1",
            "collection_run_attempt_id": "attempt-1",
        },
    )

    assert f"# TYPE {ROUND_COMPLETE_METRIC} gauge" in payload
    assert 'instance_id="cmdb_12"' in payload
    assert 'model_id="vmware_vc"' in payload
    assert 'collection_role="topology"' in payload
    assert "run_attempt_id" not in payload
    assert "collection_run_attempt_id" not in payload
    assert payload.strip().endswith("1700000000")


def test_build_round_complete_labels_excludes_per_run_attempt_identity():
    labels = build_round_complete_labels(
        {
            "collection_role": "topology",
            "channel_config_version": 7,
            "collect_task_id": 42,
            "run_attempt_id": "attempt-9",
            "collection_run_attempt_id": "attempt-9",
        }
    )

    assert labels == {
        "collection_role": "topology",
        "channel_config_version": 7,
        "collect_task_id": 42,
    }


def test_resolve_round_marker_identity_requires_cmdb_instance():
    assert resolve_round_marker_identity({"model_id": "host"}) is None
    assert resolve_round_marker_identity({"tags": {"instance_id": "monitor_1"}, "model_id": "host"}) is None
    assert resolve_round_marker_identity({"collect_task_id": 9, "model_id": "network", "callback_subject": "cb"}) is None
    assert resolve_round_marker_identity({"tags": {"instance_id": "cmdb_9"}, "model_id": "network"}) == ("cmdb_9", "network")
    assert resolve_round_marker_identity({"collect_task_id": 9, "model_id": "aliyun"}) == ("cmdb_9", "aliyun")


@pytest.mark.asyncio
async def test_publish_round_complete_marker_after_success():
    published = []

    async def fake_publish(ctx, metrics_data, params, task_id):
        published.append((metrics_data, params, task_id))
        return 1

    request = CollectionRequest(
        task_id="run-1",
        plugin_ref="vmware_vc.info",
        targets=("vc.example",),
        params={
            "model_id": "vmware_vc",
            "collection_role": "topology",
            "tags": {"instance_id": "cmdb_42", "instance_type": "cmdb_vmware"},
        },
    )

    ok = await publish_round_complete_marker(request, 1_700_000_111, metrics_publish=fake_publish)

    assert ok is True
    assert len(published) == 1
    metrics_data, params, task_id = published[0]
    assert task_id == "run-1"
    assert params["tags"]["instance_id"] == "cmdb_42"
    assert params["tags"]["collection_role"] == "topology"
    assert "cmdb_round_complete" in metrics_data
    assert "1700000111" in metrics_data


@pytest.mark.asyncio
async def test_publish_round_complete_marker_skips_non_cmdb():
    published = []

    async def fake_publish(*_args, **_kwargs):
        published.append(True)
        return 1

    request = CollectionRequest(
        task_id="run-2",
        plugin_ref="host.monitor",
        targets=("10.0.0.1",),
        params={"model_id": "host", "tags": {"instance_id": "agent-1"}},
    )

    ok = await publish_round_complete_marker(request, 1_700_000_222, metrics_publish=fake_publish)

    assert ok is False
    assert published == []


@pytest.mark.asyncio
async def test_publish_round_complete_marker_swallows_publish_errors():
    async def boom(*_args, **_kwargs):
        raise RuntimeError("nats down")

    request = CollectionRequest(
        task_id="run-3",
        plugin_ref="network.config",
        targets=("10.0.0.2",),
        params={"model_id": "network", "collect_task_id": 7},
    )

    ok = await publish_round_complete_marker(request, 1_700_000_333, metrics_publish=boom)

    assert ok is False
