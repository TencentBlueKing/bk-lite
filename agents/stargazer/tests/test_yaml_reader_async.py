import asyncio
import builtins
import time
from pathlib import Path

import pytest

from core.plugin.yaml_reader import PluginYamlReader


def _write_plugin_config(config_path: Path, timeout: int) -> None:
    config_path.write_text(
        f"""
name: demo
metadata:
  model_id: demo
default_executor: protocol
executors:
  protocol:
    type: protocol
    timeout: {timeout}
    collector:
      module: demo_plugin
      class: DemoCollector
""".strip(),
        encoding="utf-8",
    )


async def _heartbeat_during(awaitable, minimum_ticks: int = 5):
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
async def test_async_executor_resolution_reads_real_yaml_without_stalling(
    tmp_path, monkeypatch
):
    plugin_dir = tmp_path / "demo"
    plugin_dir.mkdir()
    config_path = plugin_dir / "plugin.yml"
    _write_plugin_config(config_path, timeout=30)

    real_open = builtins.open

    def delayed_config_open(file, *args, **kwargs):
        if Path(file) == config_path:
            time.sleep(0.05)
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", delayed_config_open)
    reader = PluginYamlReader(plugins_base_dir=str(tmp_path))

    results = await _heartbeat_during(
        asyncio.gather(
            *(
                reader.get_executor_config_with_resolution_async(
                    "demo", "protocol", prefer_enterprise=False
                )
                for _ in range(20)
            )
        )
    )

    assert len(results) == 20
    assert all(result.executor_config.executor_type == "protocol" for result in results)
    assert all(result.executor_config.get_timeout() == 30 for result in results)
    assert all(result.plugin_resolution.source == "oss" for result in results)


@pytest.mark.asyncio
async def test_clear_cache_makes_updated_yaml_observable(tmp_path):
    plugin_dir = tmp_path / "demo"
    plugin_dir.mkdir()
    config_path = plugin_dir / "plugin.yml"
    _write_plugin_config(config_path, timeout=30)
    reader = PluginYamlReader(plugins_base_dir=str(tmp_path))

    initial = await reader.get_executor_config_with_resolution_async(
        "demo", "protocol", prefer_enterprise=False
    )
    _write_plugin_config(config_path, timeout=99)
    cached = await reader.get_executor_config_with_resolution_async(
        "demo", "protocol", prefer_enterprise=False
    )

    assert initial.executor_config.get_timeout() == 30
    assert cached.executor_config.get_timeout() == 30

    reader.clear_cache()
    refreshed = await reader.get_executor_config_with_resolution_async(
        "demo", "protocol", prefer_enterprise=False
    )

    assert refreshed.executor_config.get_timeout() == 99
