import importlib.util
import sys
import types
from pathlib import Path

import pytest


def _load_module(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _install_module(monkeypatch, name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)
    return module


class FakeHeaders(dict):
    def get(self, key, default=None):
        return super().get(key, default)


class FakeRequest:
    def __init__(self, headers):
        self.headers = FakeHeaders(headers)
        self.args = {}


@pytest.mark.asyncio
async def test_windows_wmi_metrics_enqueues_task(monkeypatch):
    captured = {}

    class FakeQueue:
        async def enqueue_collect_task(self, params):
            captured["params"] = params
            return {"task_id": "task-wmi-1", "job_id": "job-wmi-1"}

    _install_module(monkeypatch, "core")
    _install_module(monkeypatch, "core.task_queue", get_task_queue=lambda: FakeQueue())

    monitor_module = _load_module(
        "stargazer_monitor_windows_wmi_test_module",
        Path(__file__).resolve().parents[1] / "api" / "monitor.py",
    )

    response = await monitor_module.windows_wmi_metrics(
        FakeRequest(
            {
                "host": "10.0.0.8",
                "username": "EXAMPLE\\monitor",
                "password": "secret",
                "namespace": "root\\cimv2",
                "metrics_modules": "cpu,mem,disk",
                "timeout": "45",
                "instance_id": "region_os_10.0.0.8",
                "instance_type": "os",
                "collect_type": "http",
                "config_type": "windows_wmi",
            }
        )
    )

    assert response.status == 200
    assert captured["params"]["monitor_type"] == "windows_wmi"
    assert captured["params"]["host"] == "10.0.0.8"
    assert captured["params"]["username"] == "EXAMPLE\\monitor"
    assert captured["params"]["password"] == "secret"
    assert captured["params"]["namespace"] == "root\\cimv2"
    assert captured["params"]["metrics_modules"] == "cpu,mem,disk"
    assert captured["params"]["timeout"] == 45
    assert captured["params"]["tags"] == {
        "instance_id": "region_os_10.0.0.8",
        "instance_type": "os",
        "collect_type": "http",
        "config_type": "windows_wmi",
    }
    assert b'monitor_request_accepted{monitor_type="windows_wmi"' in response.body


@pytest.mark.asyncio
async def test_windows_wmi_metrics_rejects_missing_required_headers(monkeypatch):
    _install_module(monkeypatch, "core")
    _install_module(monkeypatch, "core.task_queue", get_task_queue=lambda: None)

    monitor_module = _load_module(
        "stargazer_monitor_windows_wmi_missing_headers_test_module",
        Path(__file__).resolve().parents[1] / "api" / "monitor.py",
    )

    response = await monitor_module.windows_wmi_metrics(
        FakeRequest({"host": "10.0.0.8", "username": "EXAMPLE\\monitor"})
    )

    assert response.status == 400
    assert b"missing required headers" in response.body
    assert b'monitor_type="windows_wmi"' in response.body


@pytest.mark.asyncio
async def test_worker_dispatches_windows_wmi(monkeypatch):
    called = {}

    async def fake_handler(ctx, params, task_id):
        called["ctx"] = ctx
        called["params"] = params
        called["task_id"] = task_id
        return {"task_id": task_id, "status": "success", "monitor_type": "windows_wmi"}

    async def fake_create_pool(_settings):
        class FakePool:
            async def delete(self, _key):
                return None

            async def close(self):
                return None

        return FakePool()

    _install_module(monkeypatch, "arq", create_pool=fake_create_pool)
    _install_module(monkeypatch, "arq.connections", RedisSettings=lambda **kwargs: kwargs)
    _install_module(monkeypatch, "core")
    _install_module(
        monkeypatch,
        "core.redis_config",
        REDIS_CONFIG={"host": "localhost", "port": 6379, "password": "", "database": 0},
    )
    _install_module(
        monkeypatch,
        "tasks.handlers.monitor_handler",
        collect_windows_wmi_metrics_task=fake_handler,
    )

    worker_module = _load_module(
        "stargazer_worker_windows_wmi_test_module",
        Path(__file__).resolve().parents[1] / "core" / "worker.py",
    )

    result = await worker_module.collect_task(
        {},
        {"monitor_type": "windows_wmi", "host": "10.0.0.8"},
        "task-wmi-1",
    )

    assert result["status"] == "success"
    assert called["params"]["monitor_type"] == "windows_wmi"
    assert called["task_id"] == "task-wmi-1"


@pytest.mark.asyncio
async def test_windows_wmi_handler_collects_and_publishes(monkeypatch):
    published = {}

    class FakeCollector:
        def __init__(self, params):
            self.params = params

        async def collect(self):
            return "windows_wmi_collection_up 1\n"

    async def fake_publish(ctx, metrics_data, params, task_id):
        published["ctx"] = ctx
        published["metrics_data"] = metrics_data
        published["params"] = params
        published["task_id"] = task_id

    _install_module(monkeypatch, "tasks")
    _install_module(monkeypatch, "tasks.collectors")
    _install_module(monkeypatch, "tasks.collectors.host_wmi_collector", WindowsWmiCollector=FakeCollector)
    _install_module(monkeypatch, "tasks.utils")
    _install_module(monkeypatch, "tasks.utils.nats_helper", publish_metrics_to_nats=fake_publish)
    _install_module(
        monkeypatch,
        "tasks.utils.metrics_helper",
        generate_monitor_error_metrics=lambda params, error: f"error {error}\n",
    )

    handler_module = _load_module(
        "stargazer_monitor_handler_windows_wmi_test_module",
        Path(__file__).resolve().parents[1] / "tasks" / "handlers" / "monitor_handler.py",
    )

    result = await handler_module.collect_windows_wmi_metrics_task(
        {},
        {"monitor_type": "windows_wmi", "host": "10.0.0.8"},
        "task-wmi-1",
    )

    assert result["status"] == "success"
    assert result["monitor_type"] == "windows_wmi"
    assert published["metrics_data"] == "windows_wmi_collection_up 1\n"
