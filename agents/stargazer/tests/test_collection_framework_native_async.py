# -*- coding: utf-8 -*-
"""原生异步改造后的配置采集全流程框架测试。

覆盖：PluginExecutor → list_all_resources / ConfigurationCollectionPlugin → collect
在原生异步插件（mock IO）下不阻塞事件循环，并产出成功 CollectOutcome。
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
from pathlib import Path

import pytest
import yaml
from core.collection.contracts import AccessProbeResult, AccessProbeStatus, CollectOutcomeStatus, TargetCollectionContext
from core.collection.plugins import ConfigurationCollectionPlugin
from core.plugin.executor import PluginExecutor
from core.plugin.yaml_reader import ExecutorConfig
from plugins.inputs.influxdb.influxdb_info import InfluxdbInfo
from plugins.inputs.mysql.mysql_info import MysqlInfo
from plugins.inputs.postgresql.postgresql_info import PostgresqlInfo


async def _heartbeat_during(awaitable, minimum_ticks: int = 5):
    ticks = 0

    async def heartbeat():
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0.005)

    task = asyncio.create_task(heartbeat())
    try:
        return await awaitable
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert ticks >= minimum_ticks, "event_loop_stalled"


PLUGIN_ROOT = Path(__file__).parents[1] / "plugins" / "inputs"


def _async_protocol_collectors():
    for config_path in sorted(PLUGIN_ROOT.glob("*/plugin.yml")):
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        protocol = (config.get("executors") or {}).get("protocol") or {}
        if protocol.get("execution_mode") != "async":
            continue
        collector = protocol.get("collector") or {}
        yield config_path.parent.name, collector.get("module"), collector.get("class")


@pytest.mark.asyncio
async def test_plugin_executor_runs_native_mysql_without_stalling(monkeypatch):
    async def fake_list(self):
        await asyncio.sleep(0.05)
        return {"success": True, "result": {"mysql": [{"ip_addr": "10.0.0.8"}]}}

    monkeypatch.setattr(MysqlInfo, "list_all_resources", fake_list)

    executor = PluginExecutor(
        model="mysql",
        executor_config=ExecutorConfig(
            executor_type="protocol",
            config={
                "collector": {
                    "module": "plugins.inputs.mysql.mysql_info",
                    "class": "MysqlInfo",
                },
                "timeout": 30,
            },
            plugin_config={"metadata": {}},
        ),
        params={"host": "10.0.0.8", "user": "u", "password": "p"},
    )

    result = await _heartbeat_during(executor.execute())
    assert result["success"] is True
    assert result["result"]["mysql"][0]["ip_addr"] == "10.0.0.8"


@pytest.mark.asyncio
async def test_configuration_plugin_collect_flow_with_native_influxdb(monkeypatch):
    async def fake_list(self):
        await asyncio.sleep(0.05)
        return {
            "success": True,
            "result": {
                "influxdb": [
                    {
                        "version": "2.7.5",
                        "ip_addr": "influx.local",
                        "port": 8086,
                    }
                ]
            },
        }

    monkeypatch.setattr(InfluxdbInfo, "list_all_resources", fake_list)

    class Service:
        def __init__(self, params):
            self.params = params

        async def collect(self):
            # 模拟 CollectionService：PluginExecutor → list_all_resources
            plugin = InfluxdbInfo(self.params)
            raw = await plugin.list_all_resources()
            assert raw["success"] is True
            return raw["result"]

        async def probe(self):
            return AccessProbeResult(status=AccessProbeStatus.READY)

    outcome = await _heartbeat_during(
        ConfigurationCollectionPlugin(service_factory=Service).collect(
            "influx.local",
            {"token": "operator"},
            TargetCollectionContext(
                task_id="framework-influx",
                plugin_ref="influxdb.config",
                fence=1,
                params={
                    "model_id": "influxdb",
                    "executor_type": "protocol",
                    "port": 8086,
                },
            ),
        )
    )

    assert outcome.status == CollectOutcomeStatus.SUCCESS
    assert outcome.value["influxdb"][0]["version"] == "2.7.5"


@pytest.mark.asyncio
async def test_configuration_plugin_probe_flow_with_native_postgresql(monkeypatch):
    async def fake_probe(self):
        await asyncio.sleep(0.05)
        return AccessProbeResult(
            status=AccessProbeStatus.READY,
            evidence={"server_version": "16.2"},
        )

    monkeypatch.setattr(PostgresqlInfo, "probe", fake_probe)

    class Service:
        def __init__(self, params):
            self.params = params

        async def probe(self):
            return await PostgresqlInfo(self.params).probe()

    result = await _heartbeat_during(
        ConfigurationCollectionPlugin(service_factory=Service).probe(
            "10.0.0.9",
            {"user": "collector", "password": "secret"},
            TargetCollectionContext(
                task_id="framework-pg",
                plugin_ref="postgresql.config",
                fence=1,
                params={"model_id": "postgresql", "executor_type": "protocol"},
            ),
            timeout_seconds=5,
        )
    )
    assert result.status == AccessProbeStatus.READY
    assert result.evidence == {"server_version": "16.2"}


def test_native_protocol_plugins_expose_coroutine_collection_interface():
    violations = []
    discovered = []
    for model, module_name, class_name in _async_protocol_collectors():
        discovered.append(model)
        module = importlib.import_module(module_name)
        collector_class = getattr(module, class_name)
        if not inspect.iscoroutinefunction(collector_class.list_all_resources):
            violations.append(model)

    assert discovered
    assert violations == []
