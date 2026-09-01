"""PC 快照元数据跨 Stargazer、NATS、VM 和 CMDB 的完整流程测试。

普通 Server 虚拟环境没有 Stargazer 的 Sanic/Influx 依赖，因此该用例在常规
Server 单测中跳过；使用实施文档记录的组合环境命令执行。
"""

# flake8: noqa: E402

from __future__ import annotations

import asyncio
import importlib
import json
import sys
import time

import pytest

pytest.importorskip("sanic", reason="cross-service test requires Stargazer dependencies")
pytest.importorskip("influxdb_client", reason="cross-service test requires Stargazer dependencies")

from core.collection.contracts import StructuredMetricsPayload, TargetCollectionResult
from core.collection.result_publisher import NatsResultPublisher
from core.collection.round_metadata import RedisRoundMetadataStore, round_metadata_key
from core.collection.runtime import CollectionRequest, RunLease
from core.infra import nats as nats_module
from enterprise.plugins.inputs.pc import pc_inventory
from enterprise.plugins.inputs.winsphere import winsphere_info
from service.collection_service import CollectionService
from tasks.utils.nats_helper import convert_structured_metrics_to_influx

from apps.cmdb.collection.round_metadata import RoundMetadataProtocolError, RoundMetadataReader
from apps.cmdb.constants.constants import CollectDriverTypes, CollectPluginTypes, DataCleanupStrategy
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.tests.test_pc_reconcile_service import InMemoryGraph
from apps.cmdb_enterprise.collect.pc import PCCollectionPlugin
from apps.cmdb_enterprise.collect.winsphere import WinsphereCollectionPlugin

TARGET = "10.0.0.8"
WINSPHERE_TARGET = "10.0.0.10"
PC_INST_NAME = "WIN-4C4C4544-0038-5910-8058-C4C04F433632"
DYNAMIC_LABELS = {
    "collection_result_id",
    "collection_fence",
    "snapshot_id",
    "snapshot_status",
    "snapshot_manifest",
    "software_snapshot_status",
    "software_expected_count",
    "software_error_count",
}


class MemoryRedis:
    def __init__(self):
        self.values = {}

    async def set(self, key, value, *, ex, nx):
        assert ex == 24 * 60 * 60
        assert nx is True
        if key in self.values:
            return False
        self.values[key] = value
        return True

    async def get(self, key):
        return self.values.get(key)

    async def mget(self, keys):
        return [self.values.get(key) for key in keys]


class FakeNatsRegistry:
    service_name = "default_stargazer"

    def register_handler(self, _subject, queue=None):
        return lambda handler: handler


def _raw_snapshot(snapshot_id, software):
    return {
        "snapshot_status": "complete",
        "snapshot_id": snapshot_id,
        "pc": [
            {
                "host_name": "PC01",
                "os_type": "windows",
                "hardware_uuid": "4C4C4544-0038-5910-8058-C4C04F433632",
                "serial_number": "SN001",
                "architecture": "x64",
                "snapshot_id": snapshot_id,
                "software_snapshot_status": "complete",
            }
        ],
        "software": software,
        "software_expected_count": len(software),
        "software_error_count": 0,
    }


def _software(snapshot_id):
    return {
        "pc_inst_name": PC_INST_NAME,
        "snapshot_id": snapshot_id,
        "name": "Chrome",
        "version": "127",
        "publisher": "Google",
        "product_id": "chrome",
        "architecture": "x64",
        "source": "windows_registry",
    }


def _parse_influx_lines(lines):
    rows = []
    for line in lines:
        head, _field, timestamp_ns = line.rsplit(" ", 2)
        measurement, *raw_tags = head.split(",")
        tags = dict(tag.split("=", 1) for tag in raw_tags)
        rows.append(
            {
                "metric": {"__name__": measurement, **tags},
                "value": [int(timestamp_ns) / 1_000_000_000, "1"],
            }
        )
    return {"status": "success", "data": {"resultType": "vector", "result": rows}}


def _load_metadata_handler(monkeypatch, store):
    previous = nats_module._nats_instance
    nats_module._nats_instance = FakeNatsRegistry()
    sys.modules.pop("service.nats_server", None)
    try:
        nats_server = importlib.import_module("service.nats_server")
    finally:
        nats_module._nats_instance = previous
    monkeypatch.setattr(nats_server, "_round_metadata_store", lambda: store)
    return nats_server.get_collection_round_metadata


async def _publish_payload(store, task_id, target, model_id, payload, timestamp_ms):
    lines = []

    async def publish_metrics_batch(entries):
        for _ctx, metrics, params, _task_id in entries:
            lines.extend(convert_structured_metrics_to_influx(metrics, params))
        return {}

    request = CollectionRequest(
        task_id=str(task_id),
        plugin_ref=f"{model_id}.config",
        targets=(target,),
        params={"model_id": model_id, "plugin_family": "configuration"},
    )
    lease = RunLease(
        request.task_id,
        request.digest,
        "pod-a",
        1,
        999999,
        attempt_id=f"attempt-{timestamp_ms}",
    )
    result = TargetCollectionResult(
        target=target,
        status="success",
        attempts=1,
        value=payload,
        publish_timestamp_ms=timestamp_ms,
    )
    outcomes = await NatsResultPublisher(
        metrics_publish_batch=publish_metrics_batch,
        round_metadata_store=store,
    ).publish_batch(((request, result, lease),))

    assert list(outcomes.values()) == [None]
    vm_response = _parse_influx_lines(lines)
    for row in vm_response["data"]["result"]:
        assert DYNAMIC_LABELS.isdisjoint(row["metric"])
    return vm_response


async def _publish_pc_round(
    monkeypatch,
    store,
    task_id,
    raw_snapshot,
    timestamp_ms,
):
    async def ansible_adhoc(**_kwargs):
        return {
            "success": True,
            "result": [{"host": TARGET, "stdout": json.dumps(raw_snapshot)}],
        }

    monkeypatch.setattr(pc_inventory, "ansible_adhoc", ansible_adhoc)
    payload = await CollectionService(
        {
            "plugin_name": "pc_info",
            "model_id": "pc",
            "executor_type": "job",
            "host": TARGET,
            "os_type": "windows",
            "node_id": "node-1",
            "username": "collector",
            "password": "must-not-leak",
            "_runtime_structured_metrics": True,
        }
    ).collect()
    assert isinstance(payload, StructuredMetricsPayload)
    assert payload.error == ""
    return await _publish_payload(
        store,
        task_id,
        TARGET,
        "pc",
        payload,
        timestamp_ms,
    )


async def _publish_winsphere_round(monkeypatch, store, task_id, timestamp_ms):
    class FakeClient:
        optional_unavailable_paths = set()

        def __init__(self, **_kwargs):
            pass

        def list_pools(self):
            return [{"id": "pool-1", "name": "pool"}]

        def list_clusters(self):
            return [{"id": "cluster-1", "name": "cluster", "poolId": "pool-1"}]

        def list_hosts(self):
            return [{"id": "host-1", "name": "host", "clusterId": "cluster-1"}]

        def list_domains(self):
            return [{"id": "vm-1", "name": "vm", "hostId": "host-1"}]

        def list_storage_pools(self):
            return [{"id": "storage-1", "name": "storage"}]

        def list_standard_switches(self):
            return []

        def list_standard_port_groups(self):
            return []

        def list_distributed_switches(self):
            return [{"id": "dvs-1", "name": "switch"}]

        def list_distributed_switch_hosts(self, _switch_id):
            return [{"id": "host-1"}]

        def list_distributed_port_groups(self, _switch_id):
            return [{"id": "pg-1", "name": "port-group"}]

    monkeypatch.setattr(winsphere_info, "WinSphereClient", FakeClient)
    payload = await CollectionService(
        {
            "plugin_name": "winsphere_info",
            "model_id": "winsphere",
            "executor_type": "protocol",
            "host": WINSPHERE_TARGET,
            "user": "collector",
            "password": "must-not-leak",
            "_runtime_structured_metrics": True,
        }
    ).collect()
    assert isinstance(payload, StructuredMetricsPayload)
    assert payload.error == ""
    return await _publish_payload(
        store,
        task_id,
        WINSPHERE_TARGET,
        "winsphere",
        payload,
        timestamp_ms,
    )


def _consume_round(task, vm_response, handler):
    class HandlerRpc:
        def __init__(self, instance_id=None):
            assert instance_id == "default_stargazer"

        def get_collection_round_metadata(self, payload, timeout=3):
            assert timeout == 3
            return {
                "success": True,
                **asyncio.run(handler(payload)),
            }

    class Reader(RoundMetadataReader):
        def __init__(self, collect_task):
            super().__init__(collect_task, rpc_factory=HandlerRpc)

    plugin = PCCollectionPlugin(
        inst_name="pc-task",
        inst_id=f"cmdb_{task.id}",
        task_id=task.id,
        collect_inst=task,
    )
    plugin.round_metadata_reader_factory = Reader
    plugin.format_data(vm_response["data"])
    plugin.format_metrics()
    return plugin.result[PCCollectionPlugin.TASK_FORMAT_DATA_KEY]


@pytest.mark.django_db
def test_pc_snapshot_full_flow_keeps_series_stable_and_fails_closed_before_delete(monkeypatch):
    """采集→标签编码→metadata Redis/NATS→CMDB 对账，覆盖丢 metadata 与安全删除。"""
    redis = MemoryRedis()
    store = RedisRoundMetadataStore(redis)
    handler = _load_metadata_handler(monkeypatch, store)
    graph = InMemoryGraph()
    monkeypatch.setattr(
        "apps.cmdb.services.pc_discovery.GraphClient",
        lambda *args, **kwargs: graph,
    )
    task = CollectModels.objects.create(
        name="pc-cross-service-e2e",
        task_type=CollectPluginTypes.HOST,
        driver_type=CollectDriverTypes.JOB,
        model_id="pc",
        cycle_value_type="cycle",
        team=[7],
        data_cleanup_strategy=DataCleanupStrategy.IMMEDIATELY,
    )

    first_snapshot_id = "snapshot-round-1"
    first_ts = 1780000000123
    first_vm = asyncio.run(
        _publish_pc_round(
            monkeypatch,
            store,
            task.id,
            _raw_snapshot(first_snapshot_id, [_software(first_snapshot_id)]),
            first_ts,
        )
    )
    first_result = _consume_round(task, first_vm, handler)
    first_pc_labels = next(row["metric"] for row in first_vm["data"]["result"] if row["metric"]["__name__"] == "pc_info")

    assert first_result["pc_summary"]["software_added"] == 1
    software_names = {name for name, entity in graph.store.items() if entity.get("model_id") == "pc_software"}
    assert len(software_names) == 1

    missing_metadata_snapshot_id = "snapshot-round-2"
    missing_metadata_ts = first_ts + 60_000
    missing_metadata_vm = asyncio.run(
        _publish_pc_round(
            monkeypatch,
            store,
            task.id,
            _raw_snapshot(missing_metadata_snapshot_id, []),
            missing_metadata_ts,
        )
    )
    redis.values.pop(round_metadata_key(str(task.id), TARGET, missing_metadata_ts))

    with pytest.raises(RoundMetadataProtocolError, match="metadata_unavailable"):
        _consume_round(task, missing_metadata_vm, handler)
    assert software_names <= set(graph.store)

    final_snapshot_id = "snapshot-round-3"
    final_ts = missing_metadata_ts + 60_000
    final_vm = asyncio.run(
        _publish_pc_round(
            monkeypatch,
            store,
            task.id,
            _raw_snapshot(final_snapshot_id, []),
            final_ts,
        )
    )
    final_result = _consume_round(task, final_vm, handler)
    final_pc_labels = next(row["metric"] for row in final_vm["data"]["result"] if row["metric"]["__name__"] == "pc_info")

    assert first_pc_labels == final_pc_labels
    assert final_result["pc_summary"]["software_deleted"] == 1
    assert software_names.isdisjoint(graph.store)


@pytest.mark.django_db
def test_winsphere_snapshot_full_flow_keeps_all_eight_model_series_stable(monkeypatch):
    """企业插件→VM→metadata RPC→八模型校验，并锁定跨轮 series 稳定性。"""
    redis = MemoryRedis()
    store = RedisRoundMetadataStore(redis)
    handler = _load_metadata_handler(monkeypatch, store)
    task = CollectModels.objects.create(
        name="winsphere-cross-service-e2e",
        task_type=CollectPluginTypes.CLOUD,
        driver_type=CollectDriverTypes.PROTOCOL,
        model_id="winsphere",
        cycle_value_type="cycle",
        team=[7],
        data_cleanup_strategy=DataCleanupStrategy.IMMEDIATELY,
    )

    def consume(vm_response):
        class HandlerRpc:
            def __init__(self, instance_id=None):
                assert instance_id == "default_stargazer"

            def get_collection_round_metadata(self, payload, timeout=3):
                assert timeout == 3
                return {"success": True, **asyncio.run(handler(payload))}

        class Reader(RoundMetadataReader):
            def __init__(self, collect_task):
                super().__init__(collect_task, rpc_factory=HandlerRpc)

        plugin = WinsphereCollectionPlugin(
            inst_name="winsphere-prod",
            inst_id=f"cmdb_{task.id}",
            task_id=task.id,
            collect_inst=task,
        )
        plugin.round_metadata_reader_factory = Reader
        plugin.format_data(vm_response["data"])
        plugin.format_metrics()
        return plugin.result

    first_ts = int(time.time() * 1000)
    first_vm = asyncio.run(_publish_winsphere_round(monkeypatch, store, task.id, first_ts))
    second_vm = asyncio.run(_publish_winsphere_round(monkeypatch, store, task.id, first_ts + 60_000))
    expected_metric_names = set(WinsphereCollectionPlugin.metric_names)
    assert {row["metric"]["__name__"] for row in first_vm["data"]["result"]} == expected_metric_names
    first_result = consume(first_vm)
    second_result = consume(second_vm)

    first_series = {frozenset(row["metric"].items()) for row in first_vm["data"]["result"]}
    second_series = {frozenset(row["metric"].items()) for row in second_vm["data"]["result"]}
    assert first_series == second_series
    assert len(first_series) == len(first_vm["data"]["result"])
    assert set(first_result) == set(WinsphereCollectionPlugin.MODEL_ORDER)
    assert set(second_result) == set(WinsphereCollectionPlugin.MODEL_ORDER)
    assert first_result["winsphere_vm"][0]["resource_id"] == "vm-1"
    assert first_result["winsphere_port_group"][0]["assos"][0]["model_asst_id"] == "winsphere_port_group_group_winsphere_vswitch"
