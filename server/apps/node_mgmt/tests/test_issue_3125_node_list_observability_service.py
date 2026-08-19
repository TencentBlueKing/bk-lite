"""Issue #3125 legacy node_list 观测首片的跨模块契约测试。"""

import logging
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

import pytest

from apps.alerts.action import target_resolver
from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService
from apps.job_mgmt.services.execution_base_service import ExecutionTaskBaseService
from apps.job_mgmt.views import target as target_views
from apps.node_mgmt.nats import node as nats_node

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("declared_callsite", "expected_callsite"),
    [
        ("job_mgmt.connection_test", "job_mgmt.connection_test"),
        ("forged\nlog-entry", "unknown"),
        (["job_mgmt.connection_test"], "unknown"),
        (None, "unknown"),
    ],
)
def test_legacy_skip_permission_logs_only_normalized_declared_callsite(
    monkeypatch,
    caplog,
    declared_callsite,
    expected_callsite,
):
    expected_result = {"count": 1, "nodes": [{"id": "node-1"}]}
    captured = {}

    def fake_get_node_list(*args):
        captured["args"] = args
        return expected_result

    monkeypatch.setattr(nats_node, "_observed_legacy_node_list_callsites", set(), raising=False)
    monkeypatch.setattr(nats_node.NodeService, "get_node_list", fake_get_node_list)
    query = {"skip_permission": True}
    if declared_callsite is not None:
        query["legacy_callsite"] = declared_callsite

    caplog.set_level(logging.WARNING, logger="node")
    result = nats_node.node_list(query)
    repeated_result = nats_node.node_list(query)

    assert result is expected_result
    assert repeated_result is expected_result
    assert captured["args"][-1] is True
    matching_records = [record for record in caplog.records if "legacy node_list skip_permission" in record.getMessage()]
    assert len(matching_records) == 1
    assert f"declared_callsite={expected_callsite}" in matching_records[0].getMessage()
    assert "forged\nlog-entry" not in caplog.text


def test_legacy_observation_is_bounded_per_normalized_callsite(monkeypatch, caplog):
    monkeypatch.setattr(nats_node, "_observed_legacy_node_list_callsites", set(), raising=False)
    monkeypatch.setattr(nats_node.NodeService, "get_node_list", lambda *args: {"nodes": []})
    caplog.set_level(logging.WARNING, logger="node")

    nats_node.node_list({"skip_permission": True, "legacy_callsite": "job_mgmt.connection_test"})
    nats_node.node_list({"skip_permission": True, "legacy_callsite": "cmdb.node_sync"})
    nats_node.node_list({"skip_permission": True, "legacy_callsite": "forged"})

    messages = [record.getMessage() for record in caplog.records if "legacy node_list skip_permission" in record.getMessage()]
    assert len(messages) == 3
    assert any("declared_callsite=job_mgmt.connection_test" in message for message in messages)
    assert any("declared_callsite=cmdb.node_sync" in message for message in messages)
    assert any("declared_callsite=unknown" in message for message in messages)


def test_legacy_observation_logs_once_under_concurrency(monkeypatch, caplog):
    monkeypatch.setattr(nats_node, "_observed_legacy_node_list_callsites", set(), raising=False)
    monkeypatch.setattr(nats_node.NodeService, "get_node_list", lambda *args: {"nodes": []})
    caplog.set_level(logging.WARNING, logger="node")
    barrier = Barrier(8)

    def call_node_list(_):
        barrier.wait()
        nats_node.node_list({"skip_permission": True, "legacy_callsite": "cmdb.node_sync"})

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(call_node_list, range(8)))

    messages = [record.getMessage() for record in caplog.records if "legacy node_list skip_permission" in record.getMessage()]
    assert messages == [
        "legacy node_list skip_permission used; declared_callsite=cmdb.node_sync authorization_source=untrusted_payload"
    ]


def test_regular_node_list_keeps_behavior_without_legacy_observation(monkeypatch, caplog):
    expected_result = {"count": 0, "nodes": []}
    captured = {}

    def fake_get_node_list(*args):
        captured["args"] = args
        return expected_result

    monkeypatch.setattr(nats_node.NodeService, "get_node_list", fake_get_node_list)
    caplog.set_level(logging.WARNING, logger="node")

    result = nats_node.node_list(
        {
            "permission_data": {"username": "user"},
            "legacy_callsite": "forged\nlog-entry",
        }
    )

    assert result is expected_result
    assert captured["args"][-1] is False
    assert "legacy node_list skip_permission" not in caplog.text
    assert "forged\nlog-entry" not in caplog.text


def test_job_connection_test_declares_legacy_callsite():
    with patch.object(target_views, "NodeMgmt") as node_mgmt:
        node_mgmt.return_value.node_list.return_value = {"nodes": [{"id": "executor-1"}]}

        assert target_views._get_executor_node(3) == "executor-1"

    query = node_mgmt.return_value.node_list.call_args.args[0]
    assert query["legacy_callsite"] == "job_mgmt.connection_test"


def test_job_connection_payload_keeps_legacy_consumer_contract():
    """新生产者可由不识别 legacy_callsite 的旧 handler 按原契约消费。"""
    with patch.object(target_views, "NodeMgmt") as node_mgmt:
        node_mgmt.return_value.node_list.return_value = {"nodes": [{"id": "executor-1"}]}
        target_views._get_executor_node(3)

    query = node_mgmt.return_value.node_list.call_args.args[0]
    with patch.object(nats_node.NodeService, "get_node_list", return_value={"nodes": [{"id": "executor-1"}]}) as service:
        result = nats_node.NodeService.get_node_list(
            query.get("organization_ids"), query.get("cloud_region_id"), query.get("name"), query.get("ip"),
            query.get("os"), query.get("page", 1), query.get("page_size", 10), query.get("is_active"),
            query.get("is_manual"), query.get("is_container"), query.get("permission_data", {}),
            query.get("skip_permission", False),
        )

    assert result == {"nodes": [{"id": "executor-1"}]}
    assert service.call_args.args == (None, 3, None, None, None, 1, 1, None, None, True, {}, True)


def test_job_execution_declares_legacy_callsite():
    with patch("apps.job_mgmt.services.execution_base_service.NodeMgmt") as node_mgmt:
        node_mgmt.return_value.node_list.return_value = {"nodes": [{"id": "executor-2"}]}

        assert ExecutionTaskBaseService._get_ansible_node(4) == "executor-2"

    query = node_mgmt.return_value.node_list.call_args.args[0]
    assert query["legacy_callsite"] == "job_mgmt.execution"


def test_cmdb_sync_declares_legacy_callsite(monkeypatch):
    with patch("apps.cmdb.services.node_mgmt_sync_service.NodeMgmt") as client:
        client.return_value.node_list.return_value = {"count": 0, "nodes": []}
        monkeypatch.setattr(NodeMgmtSyncService, "_node_mgmt_client", classmethod(lambda cls: client.return_value))

        assert NodeMgmtSyncService._fetch_node_mgmt_pages({}) == []

    query = client.return_value.node_list.call_args.args[0]
    assert query["legacy_callsite"] == "cmdb.node_sync"


def test_alert_target_resolver_declares_legacy_callsite():
    with patch.object(target_resolver, "NodeMgmt") as node_mgmt:
        node_mgmt.return_value.node_list.return_value = {
            "nodes": [
                {
                    "id": "node-3",
                    "name": "host",
                    "ip": "10.0.0.3",
                    "operating_system": "linux",
                    "cloud_region": 1,
                }
            ]
        }

        target_resolver.resolve_node_target("10.0.0.3", team=[1])

    query = node_mgmt.return_value.node_list.call_args.args[0]
    assert query["legacy_callsite"] == "alerts.target_resolver"
