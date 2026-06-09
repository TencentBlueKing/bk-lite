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
