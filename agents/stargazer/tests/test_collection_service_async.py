import asyncio
import time
from pathlib import Path

import pytest

from core.plugin.source_resolver import PluginResolution
from core.collection.contracts import AccessProbeStatus
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
