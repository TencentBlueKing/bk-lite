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

from core.collection.contracts import (
    AccessProbeResult,
    AccessProbeStatus,
    CollectOutcomeStatus,
    TargetCollectionContext,
)
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


NATIVE_PROTOCOL_MODULES = {
    "mysql": "plugins.inputs.mysql.mysql_info",
    "postgresql": "plugins.inputs.postgresql.postgresql_info",
    "oracle": "plugins.inputs.oracle.oracle_info",
    "mssql": "plugins.inputs.mssql.mssql_info",
    "influxdb": "plugins.inputs.influxdb.influxdb_info",
    "oceanstor": "plugins.inputs.oceanstor.oceanstor_info",
    "fusioninsight": "plugins.inputs.fusioninsight.fusioninsight_info",
    "network": "plugins.inputs.network.snmp_facts",
    "network_topo": "plugins.inputs.network_topo.snmp_topo",
}

WRAPPED_PROTOCOL_MODULES = {
    "aliyun": "plugins.inputs.aliyun.aliyun_info",
    "qcloud": "plugins.inputs.qcloud.qcloud_info",
    "hwcloud": "plugins.inputs.hwcloud.huaweicloud_info",
    "vmware_vc": "plugins.inputs.vmware_vc.vmware_info",
    "network_config_file": "plugins.inputs.network_config_file.network_config_file_info",
}


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


def test_native_protocol_plugins_have_no_to_thread_wrappers():
    missing = []
    still_wrapped = []
    for model, module_name in NATIVE_PROTOCOL_MODULES.items():
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError:
            missing.append(model)
            continue
        source = inspect.getsource(module)
        if "asyncio.to_thread" in source:
            still_wrapped.append(model)
    assert missing == []
    assert still_wrapped == [], f"still using to_thread: {still_wrapped}"


def test_wrapped_protocol_plugins_still_use_explicit_to_thread():
    """云/VMware/netmiko 短期保留合规包装异步。"""
    missing_wrapper = []
    for model, module_name in WRAPPED_PROTOCOL_MODULES.items():
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError:
            # 精简环境可能缺厂商 SDK；跳过
            continue
        source = inspect.getsource(module)
        if "asyncio.to_thread" not in source:
            missing_wrapper.append(model)
    assert missing_wrapper == []


def test_registered_async_matrix_snapshot():
    """盘点注册插件：原生 / 包装 / job(NATS)。"""
    plugin_root = Path(__file__).parents[1] / "plugins" / "inputs"
    native, wrapped, job, unknown = [], [], [], []

    for config_path in sorted(plugin_root.glob("*/plugin.yml")):
        model = config_path.parent.name
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        default = config.get("default_executor") or "protocol"
        executors = config.get("executors") or {}
        executor = executors.get(default) or next(iter(executors.values()), {})
        executor_type = (executor or {}).get("type")
        collector = (executor or {}).get("collector") or {}
        module_name = collector.get("module")
        if executor_type == "job" or module_name == "plugins.script_executor":
            job.append(model)
            continue
        if not module_name:
            unknown.append(model)
            continue
        try:
            module = importlib.import_module(module_name)
            source = inspect.getsource(module)
        except Exception:
            unknown.append(model)
            continue
        if "asyncio.to_thread" in source:
            wrapped.append(model)
        else:
            native.append(model)

    # 本轮改造目标至少进入 native
    for expected in (
        "mysql",
        "postgresql",
        "oracle",
        "mssql",
        "influxdb",
        "oceanstor",
        "fusioninsight",
        "network",
        "network_topo",
        "gbase8a",
        "greenplum",
        "kingbase",
        "opengauss",
        "vastbase",
    ):
        assert expected in native or expected in job, f"{expected} not native yet: native={native}"

    # 合规包装残留
    for expected in ("aliyun", "qcloud", "hwcloud", "vmware_vc", "network_config_file"):
        assert expected in wrapped or expected in unknown, f"{expected} should remain wrapped"

    # 产出可人工验收的摘要（断言侧也保留结构）
    assert len(job) >= 30
    assert len(native) >= 10
