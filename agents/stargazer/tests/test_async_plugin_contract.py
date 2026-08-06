import ast
import asyncio
import importlib
import inspect
import time
from pathlib import Path

import yaml
import pytest

from plugins.async_contract import threaded_collect


def _registered_collectors():
    plugin_root = Path(__file__).parents[1] / "plugins" / "inputs"
    for config_path in sorted(plugin_root.glob("*/plugin.yml")):
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        for executor in (config.get("executors") or {}).values():
            collector = (executor or {}).get("collector") or {}
            if collector.get("module") and collector.get("class"):
                yield config_path, collector["module"], collector["class"]


def test_every_registered_plugin_exposes_an_async_collection_entrypoint():
    violations = []
    for config_path, module_name, class_name in _registered_collectors():
        module_path = Path(__file__).parents[1] / Path(
            *module_name.split(".")
        ).with_suffix(".py")
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        class_node = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == class_name
        )
        method = next(
            (
                node
                for node in class_node.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "list_all_resources"
            ),
            None,
        )
        is_threaded = method is not None and any(
            isinstance(decorator, ast.Name)
            and decorator.id == "threaded_collect"
            for decorator in method.decorator_list
        )
        if not isinstance(method, ast.AsyncFunctionDef) and not is_threaded:
            violations.append(f"{config_path.parent.name}:{module_name}.{class_name}")

    assert violations == []


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


def test_monitor_collectors_isolate_synchronous_sdks():
    collectors = {
        "tasks/collectors/vmware_collector.py": "VmwareCollector",
        "tasks/collectors/qcloud_collector.py": "QCloudCollector",
        "tasks/collectors/oceanstor_collector.py": "OceanStorCollector",
        "tasks/collectors/host_wmi_collector.py": "WindowsWmiCollector",
    }
    violations = []
    for relative_path, class_name in collectors.items():
        module_path = Path(__file__).parents[1] / relative_path
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        class_node = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == class_name
        )
        method = next(
            node
            for node in class_node.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "collect"
        )
        is_threaded = any(
            isinstance(decorator, ast.Name)
            and decorator.id == "threaded_collect"
            for decorator in method.decorator_list
        )
        if not is_threaded:
            violations.append(class_name)

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


@pytest.mark.asyncio
async def test_threaded_sync_plugin_does_not_stall_event_loop():
    ticks = 0

    class WrappedPlugin:
        @threaded_collect
        def collect(self):
            time.sleep(0.05)
            return "done"

    async def heartbeat():
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0.005)

    heartbeat_task = asyncio.create_task(heartbeat())
    try:
        assert await WrappedPlugin().collect() == "done"
    finally:
        heartbeat_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await heartbeat_task

    assert ticks >= 5
