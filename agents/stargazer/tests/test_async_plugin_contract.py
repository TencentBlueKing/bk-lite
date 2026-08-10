import asyncio
import importlib
import inspect
import sys
import time
from pathlib import Path

import yaml
import pytest

from core.plugin.executor import PluginExecutor
from core.plugin.yaml_reader import ExecutorConfig


def _registered_collectors():
    plugin_root = Path(__file__).parents[1] / "plugins" / "inputs"
    for config_path in sorted(plugin_root.glob("*/plugin.yml")):
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        for executor in (config.get("executors") or {}).values():
            collector = (executor or {}).get("collector") or {}
            if collector.get("module") and collector.get("class"):
                yield config_path, collector["module"], collector["class"]


def test_registered_plugin_runtime_entrypoints_are_coroutine_functions():
    violations = []
    for config_path, module_name, class_name in _registered_collectors():
        try:
            collector_class = getattr(importlib.import_module(module_name), class_name)
        except ModuleNotFoundError:
            # 精简测试环境不安装全部厂商 SDK；静态契约测试仍覆盖所有注册项。
            continue
        if not inspect.iscoroutinefunction(
            getattr(collector_class, "list_all_resources")
        ):
            violations.append(
                f"{config_path.parent.name}:{module_name}.{class_name}"
            )

    assert violations == []


def test_every_registered_executor_declares_a_positive_timeout():
    violations = []
    plugin_root = Path(__file__).parents[1] / "plugins" / "inputs"
    for config_path in sorted(plugin_root.glob("*/plugin.yml")):
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        for name, executor in (config.get("executors") or {}).items():
            if float((executor or {}).get("timeout") or 0) <= 0:
                violations.append(f"{config_path.parent.name}:{name}")
    assert violations == []


async def _assert_event_loop_responsive(awaitable, *, minimum_ticks=5):
    ticks = 0

    async def heartbeat():
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0.005)

    heartbeat_task = asyncio.create_task(heartbeat())
    try:
        result = await awaitable
    finally:
        heartbeat_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await heartbeat_task

    assert ticks >= minimum_ticks, "event_loop_stalled"
    return result


@pytest.mark.asyncio
async def test_bad_async_plugin_is_rejected_by_event_loop_contract():
    class BlockingPlugin:
        async def collect(self):
            time.sleep(0.05)
            return "done"

    with pytest.raises(AssertionError, match="event_loop_stalled"):
        await _assert_event_loop_responsive(BlockingPlugin().collect())


@pytest.mark.asyncio
async def test_explicit_sync_plugin_wrapper_does_not_stall_event_loop():
    class WrappedPlugin:
        async def collect(self):
            return await asyncio.to_thread(self._sync_collect)

        def _sync_collect(self):
            time.sleep(0.05)
            return "done"

    assert (
        await _assert_event_loop_responsive(WrappedPlugin().collect())
        == "done"
    )


@pytest.mark.asyncio
async def test_plugin_loading_does_not_stall_event_loop(monkeypatch, tmp_path):
    module_name = "slow_loading_plugin"
    (tmp_path / f"{module_name}.py").write_text(
        """
import asyncio
import time

time.sleep(0.05)

class Collector:
    def __init__(self, params):
        pass

    async def list_all_resources(self):
        await asyncio.sleep(0)
        return {"success": True, "result": {"demo": []}}
""",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop(module_name, None)
    config = ExecutorConfig(
        executor_type="protocol",
        config={"collector": {"module": module_name, "class": "Collector"}},
        plugin_config={"metadata": {}},
    )

    result = await _assert_event_loop_responsive(
        PluginExecutor("demo", config, {}).execute()
    )

    assert result == {"success": True, "result": {"demo": []}}


@pytest.mark.asyncio
async def test_plugin_initialization_does_not_stall_event_loop(
    monkeypatch, tmp_path
):
    module_name = "slow_initializing_plugin"
    (tmp_path / f"{module_name}.py").write_text(
        """
import asyncio
import time

class Collector:
    def __init__(self, params):
        time.sleep(0.05)

    async def list_all_resources(self):
        await asyncio.sleep(0)
        return {"success": True, "result": {"demo": []}}
""",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop(module_name, None)
    config = ExecutorConfig(
        executor_type="protocol",
        config={"collector": {"module": module_name, "class": "Collector"}},
        plugin_config={"metadata": {}},
    )

    result = await _assert_event_loop_responsive(
        PluginExecutor("demo", config, {}).execute()
    )

    assert result == {"success": True, "result": {"demo": []}}
