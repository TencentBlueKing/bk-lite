import asyncio
import time
from pathlib import Path

import pytest
import service.collection_service as collection_service_module
from core.collection.contracts import AccessProbeStatus, StructuredMetricsPayload
from core.plugin.source_resolver import PluginResolution
from core.plugin.yaml_reader import ExecutorConfig, ResolvedExecutorConfig
from service.collection_service import CollectionService


@pytest.mark.asyncio
async def test_collection_service_uses_registered_protocol_probe():
    service = CollectionService(
        {
            "plugin_name": "ip_info",
            "model_id": "ip",
            "executor_type": "protocol",
            "host": "10.10.24.0/24",
            "timeout": 5,
        }
    )

    result = await service.probe()

    assert result.status == AccessProbeStatus.READY


@pytest.mark.asyncio
async def test_config_resolution_does_not_stall_event_loop():
    """首次读取 plugin.yml 是文件 IO，不应阻塞 Sanic 事件循环。"""
    ticks = 0
    executor_config = ExecutorConfig(
        executor_type="protocol",
        config={
            "collector": {
                "module": "plugins.inputs.ip.ip_discovery_scanner",
                "class": "IPDiscoveryScanner",
            }
        },
        plugin_config={"metadata": {}},
    )
    resolution = PluginResolution(
        model_id="ip",
        source="oss",
        plugin_path=Path("plugins/inputs/ip/plugin.yml"),
        plugin_root=Path("plugins/inputs/ip"),
    )

    class SlowConfigProvider:
        @staticmethod
        async def get_executor_config_with_resolution_async(*_args, **_kwargs):
            await asyncio.to_thread(time.sleep, 0.05)
            return ResolvedExecutorConfig(
                executor_config=executor_config,
                plugin_resolution=resolution,
                fallback_executor_config=None,
            )

    service = CollectionService(
        {
            "plugin_name": "ip_info",
            "model_id": "ip",
            "executor_type": "protocol",
            "targets": [],
        },
        config_provider=SlowConfigProvider(),
    )

    async def heartbeat():
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0.005)

    heartbeat_task = asyncio.create_task(heartbeat())
    try:
        result = await service.collect()
    finally:
        heartbeat_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await heartbeat_task

    assert 'collect_status="success"' in result
    assert ticks >= 5


def test_initialization_does_not_mutate_request_params():
    params = {
        "plugin_name": "demo_info",
        "model_id": "demo",
        "executor_type": "protocol",
    }

    CollectionService(params)

    assert params["plugin_name"] == "demo_info"


@pytest.mark.asyncio
async def test_collection_service_logs_sanitized_call_chain_for_sampled_exception(monkeypatch):
    class BrokenConfigProvider:
        @staticmethod
        async def get_executor_config_with_resolution_async(*_args, **_kwargs):
            raise RuntimeError("token=must-not-be-logged")

    error_logs = []

    def capture_error(message, *args):
        error_logs.append(message % args if args else message)

    monkeypatch.setattr("service.collection_service.logger.error", capture_error)
    service = CollectionService(
        {
            "plugin_name": "snmp_facts",
            "model_id": "network",
            "executor_type": "protocol",
            "host": "10.3.252.254",
            "collection_task_id": "task-401",
            "collection_plugin_ref": "network.config",
            "_log_plugin_call_chain": True,
        },
        config_provider=BrokenConfigProvider(),
    )

    await service.collect()

    assert len(error_logs) == 1
    assert "event=plugin_exception" in error_logs[0]
    assert "task_id=task-401" in error_logs[0]
    assert "plugin_ref=network.config" in error_logs[0]
    assert "plugin_name=snmp_facts" in error_logs[0]
    assert "target=10.3.252.254" in error_logs[0]
    assert "error_type=RuntimeError" in error_logs[0]
    assert "get_executor_config_with_resolution_async" in error_logs[0]
    assert "must-not-be-logged" not in error_logs[0]


@pytest.mark.asyncio
async def test_job_service_never_performs_legacy_per_target_node_query(monkeypatch):
    executor_config = ExecutorConfig(
        executor_type="job",
        config={"collector": {"module": "unused", "class": "Unused"}},
        plugin_config={"metadata": {}},
    )
    resolution = PluginResolution(
        model_id="host",
        source="oss",
        plugin_path=Path("plugins/inputs/host/plugin.yml"),
        plugin_root=Path("plugins/inputs/host"),
    )

    class ConfigProvider:
        @staticmethod
        async def get_executor_config_with_resolution_async(*_args, **_kwargs):
            return ResolvedExecutorConfig(
                executor_config=executor_config,
                plugin_resolution=resolution,
                fallback_executor_config=None,
            )

    executed_params = []

    class Executor:
        def __init__(self, _model_id, _executor_config, params, **_kwargs):
            executed_params.append(dict(params))

        async def execute(self):
            return {"success": True, "result": {}}

    monkeypatch.setattr("service.collection_service.PluginExecutor", Executor)
    service = CollectionService(
        {
            "plugin_name": "host_info",
            "model_id": "host",
            "executor_type": "job",
            "host": "10.0.0.99",
            "organization_id": "org-42",
            "_runtime_structured_metrics": True,
        },
        config_provider=ConfigProvider(),
    )
    node_query_calls = 0

    async def count_node_query(*_args, **_kwargs):
        nonlocal node_query_calls
        node_query_calls += 1
        return {"success": False, "result": {"nodes": []}}

    monkeypatch.setattr(
        collection_service_module,
        "nats_request",
        count_node_query,
        raising=False,
    )

    await service.collect()

    assert node_query_calls == 0
    assert len(executed_params) == 1
    assert "node_info" not in executed_params[0]


@pytest.mark.asyncio
async def test_failed_plugin_result_is_not_logged_as_success(monkeypatch):
    executor_config = ExecutorConfig(
        executor_type="protocol",
        config={"collector": {"module": "unused", "class": "Unused"}},
        plugin_config={"metadata": {}},
    )
    resolution = PluginResolution(
        model_id="vmware_vc",
        source="oss",
        plugin_path=Path("plugins/inputs/vmware_vc/plugin.yml"),
        plugin_root=Path("plugins/inputs/vmware_vc"),
    )

    class ConfigProvider:
        @staticmethod
        async def get_executor_config_with_resolution_async(*_args, **_kwargs):
            return ResolvedExecutorConfig(
                executor_config=executor_config,
                plugin_resolution=resolution,
                fallback_executor_config=None,
            )

    class FailedExecutor:
        def __init__(self, *_args, **_kwargs):
            pass

        async def execute(self):
            return {
                "success": False,
                "result": {"cmdb_collect_error": "connection failed"},
            }

    info_logs = []
    debug_logs = []
    warning_logs = []

    def capture_info(message, *args):
        info_logs.append(message % args if args else message)

    def capture_warning(message, *args):
        warning_logs.append(message % args if args else message)

    def capture_debug(message, *args):
        debug_logs.append(message % args if args else message)

    monkeypatch.setattr("service.collection_service.PluginExecutor", FailedExecutor)
    monkeypatch.setattr("service.collection_service.logger.info", capture_info)
    monkeypatch.setattr("service.collection_service.logger.debug", capture_debug)
    monkeypatch.setattr("service.collection_service.logger.warning", capture_warning)
    service = CollectionService(
        {
            "plugin_name": "vmware_info",
            "model_id": "vmware_vc",
            "executor_type": "protocol",
            "host": "10.10.16.254",
            "collection_task_id": "vmware-failed-result",
            "_runtime_structured_metrics": True,
        },
        config_provider=ConfigProvider(),
    )

    result = await service.collect()

    assert isinstance(result, StructuredMetricsPayload)
    assert result.error == "connection failed"
    assert warning_logs == []
    assert not any("start collect." in item for item in info_logs)
    assert any("start collect." in item for item in debug_logs)
    assert not any("Starting collection V2" in item for item in info_logs)
    assert not any("Plugin collection completed" in item for item in info_logs)
    assert not any("Collection completed successfully" in item for item in info_logs)
