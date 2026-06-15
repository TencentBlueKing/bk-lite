# Windows WMI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a production-ready `Windows WMI` monitor plugin that lets Stargazer remotely collect Windows host metrics over WMI/DCOM without WinRM, Ansible, target-side probes, or target-side scripts.

**Architecture:** Telegraf triggers a new Stargazer API endpoint with `[[inputs.prometheus]]`. Stargazer queues `monitor_type=windows_wmi`, dispatches to a native `WindowsWmiCollector`, performs read-only WMI queries through a focused client/module layer, converts structured results to Prometheus text, and publishes metrics through the existing NATS path. Server-side plugin templates live under `Telegraf/http/windows_wmi/` with independent `UI.json`, `metrics.json`, and `policy.json`.

**Tech Stack:** Python 3.12, Sanic, ARQ, pytest, Django plugin templates, Jinja2, Telegraf `inputs.prometheus`, WMI/DCOM client library candidate `impacket`.

---

## File Structure

Create Stargazer collector files:

- `agents/stargazer/tasks/collectors/host_wmi_collector.py`: Integrates Windows WMI collection with `BaseCollector`.
- `agents/stargazer/tasks/collectors/host_wmi/__init__.py`: Exports core helper types.
- `agents/stargazer/tasks/collectors/host_wmi/errors.py`: Normalized WMI error classes and `classify_wmi_error`.
- `agents/stargazer/tasks/collectors/host_wmi/modules.py`: Module registry, module selection, and WMI query module implementations.
- `agents/stargazer/tasks/collectors/host_wmi/metrics.py`: Converts normalized WMI results to Prometheus text.
- `agents/stargazer/tasks/collectors/host_wmi/client.py`: WMI client abstraction and `ImpacketWmiClient` implementation boundary.

Modify Stargazer integration files:

- `agents/stargazer/api/monitor.py`: Add `/api/monitor/windows/wmi/metrics`.
- `agents/stargazer/core/worker.py`: Dispatch `monitor_type == "windows_wmi"`.
- `agents/stargazer/tasks/handlers/monitor_handler.py`: Add `collect_windows_wmi_metrics_task`.
- `agents/stargazer/pyproject.toml`: Add WMI client dependency after implementation confirms package name/version.

Create or modify tests:

- `agents/stargazer/tests/test_windows_wmi_collector.py`: Collector, module selection, metric conversion, and logging behavior.
- `agents/stargazer/tests/test_windows_wmi_monitor.py`: API and worker/handler integration behavior.

Create Server plugin files:

- `server/apps/monitor/support-files/plugins/Telegraf/http/windows_wmi/UI.json`
- `server/apps/monitor/support-files/plugins/Telegraf/http/windows_wmi/windows_wmi.child.toml.j2`
- `server/apps/monitor/support-files/plugins/Telegraf/http/windows_wmi/metrics.json`
- `server/apps/monitor/support-files/plugins/Telegraf/http/windows_wmi/policy.json`

Modify Server template support:

- `server/apps/monitor/utils/plugin_controller.py`: Allow any new Jinja variables used by `windows_wmi.child.toml.j2`.
- `server/apps/monitor/tests/test_plugin_service.py`: Add template rendering and plugin metadata tests.

---

### Task 1: Windows WMI API Enqueue Path

**Files:**
- Modify: `agents/stargazer/api/monitor.py`
- Test: `agents/stargazer/tests/test_windows_wmi_monitor.py`

- [ ] **Step 1: Write the failing API enqueue test**

Add this test module:

```python
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
```

- [ ] **Step 2: Run the API test to verify it fails**

Run:

```bash
cd agents/stargazer && uv run pytest tests/test_windows_wmi_monitor.py::test_windows_wmi_metrics_enqueues_task -q
```

Expected: `FAIL` or `AttributeError` because `windows_wmi_metrics` does not exist.

- [ ] **Step 3: Implement the minimal API endpoint**

In `agents/stargazer/api/monitor.py`, add helpers and route near the existing host route:

```python
def _monitor_error_response(monitor_type: str, error: str, status: int = 400):
    current_timestamp = int(time.time() * 1000)
    error_lines = [
        "# HELP monitor_request_error Monitor request error",
        "# TYPE monitor_request_error gauge",
        f'monitor_request_error{{monitor_type="{monitor_type}",error="{error}"}} 1 {current_timestamp}',
    ]
    return response.raw(
        "\n".join(error_lines) + "\n",
        content_type="text/plain; version=0.0.4; charset=utf-8",
        status=status,
    )


@monitor_router.get("/windows/wmi/metrics")
async def windows_wmi_metrics(request):
    logger.info("event=wmi_request_received monitor_type=windows_wmi")

    host = request.headers.get("host")
    username = request.headers.get("username")
    password = request.headers.get("password")
    namespace = request.headers.get("namespace", "root\\cimv2")
    metrics_modules = request.headers.get("metrics_modules", "cpu,mem,disk,net")
    raw_timeout = request.headers.get("timeout", "60")
    instance_id = request.headers.get("instance_id")
    instance_type = request.headers.get("instance_type", "os")
    collect_type = request.headers.get("collect_type", "http")
    config_type = request.headers.get("config_type", "windows_wmi")

    if not host or not username or not password:
        return _monitor_error_response(
            "windows_wmi",
            "missing required headers: host, username, password",
            status=400,
        )

    try:
        timeout = int(raw_timeout)
    except (TypeError, ValueError):
        timeout = 60

    task_params = {
        "monitor_type": "windows_wmi",
        "host": host,
        "username": username,
        "password": password,
        "namespace": namespace,
        "metrics_modules": metrics_modules,
        "timeout": timeout,
        "tags": {
            "instance_id": instance_id,
            "instance_type": instance_type,
            "collect_type": collect_type,
            "config_type": config_type,
        },
    }

    task_queue = get_task_queue()
    task_info = await task_queue.enqueue_collect_task(task_params)

    logger.info(
        "event=wmi_task_queued monitor_type=windows_wmi host=%s task_id=%s",
        host,
        task_info["task_id"],
    )

    current_timestamp = int(time.time() * 1000)
    prometheus_lines = [
        "# HELP monitor_request_accepted Indicates that monitor request was accepted",
        "# TYPE monitor_request_accepted gauge",
        f'monitor_request_accepted{{monitor_type="windows_wmi",host="{host}",task_id="{task_info["task_id"]}",status="queued"}} 1 {current_timestamp}',
    ]

    return response.raw(
        "\n".join(prometheus_lines) + "\n",
        content_type="text/plain; version=0.0.4; charset=utf-8",
        headers={
            "X-Task-ID": task_info["task_id"],
            "X-Job-ID": task_info.get("job_id", ""),
            "X-Monitor-Type": "windows_wmi",
        },
    )
```

- [ ] **Step 4: Run API tests to verify they pass**

Run:

```bash
cd agents/stargazer && uv run pytest tests/test_windows_wmi_monitor.py -q
```

Expected: both tests pass.

- [ ] **Step 5: Commit the API enqueue path**

```bash
git add agents/stargazer/api/monitor.py agents/stargazer/tests/test_windows_wmi_monitor.py
git commit -m "feat: add windows wmi monitor api"
```

---

### Task 2: Worker Dispatch And Handler

**Files:**
- Modify: `agents/stargazer/core/worker.py`
- Modify: `agents/stargazer/tasks/handlers/monitor_handler.py`
- Test: `agents/stargazer/tests/test_windows_wmi_monitor.py`

- [ ] **Step 1: Write the failing worker dispatch test**

Append to `agents/stargazer/tests/test_windows_wmi_monitor.py`:

```python
@pytest.mark.asyncio
async def test_worker_dispatches_windows_wmi(monkeypatch):
    called = {}

    async def fake_handler(ctx, params, task_id):
        called["ctx"] = ctx
        called["params"] = params
        called["task_id"] = task_id
        return {"task_id": task_id, "status": "success", "monitor_type": "windows_wmi"}

    _install_module(monkeypatch, "arq", create_pool=lambda *args, **kwargs: None)
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
```

- [ ] **Step 2: Run the worker test to verify it fails**

Run:

```bash
cd agents/stargazer && uv run pytest tests/test_windows_wmi_monitor.py::test_worker_dispatches_windows_wmi -q
```

Expected: `FAIL` because the worker treats `windows_wmi` as an unknown task type.

- [ ] **Step 3: Write the failing handler test**

Append to `agents/stargazer/tests/test_windows_wmi_monitor.py`:

```python
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
```

- [ ] **Step 4: Run the handler test to verify it fails**

Run:

```bash
cd agents/stargazer && uv run pytest tests/test_windows_wmi_monitor.py::test_windows_wmi_handler_collects_and_publishes -q
```

Expected: `FAIL` because `collect_windows_wmi_metrics_task` does not exist.

- [ ] **Step 5: Implement worker dispatch and handler**

In `agents/stargazer/core/worker.py`, add this branch after the `host` branch:

```python
        elif monitor_type == "windows_wmi":
            from tasks.handlers.monitor_handler import collect_windows_wmi_metrics_task

            result = await collect_windows_wmi_metrics_task(ctx, params, task_id)
```

In `agents/stargazer/tasks/handlers/monitor_handler.py`, add:

```python
async def collect_windows_wmi_metrics_task(
    ctx: Dict, params: Dict[str, Any], task_id: str
) -> Dict[str, Any]:
    logger.info(f"[Windows WMI Task] Processing: {task_id}")

    try:
        from tasks.collectors.host_wmi_collector import WindowsWmiCollector
        from tasks.utils.nats_helper import publish_metrics_to_nats

        collector = WindowsWmiCollector(params)
        metrics_data = await collector.collect()
        await publish_metrics_to_nats(ctx, metrics_data, params, task_id)

        return {
            "task_id": task_id,
            "status": "success",
            "monitor_type": "windows_wmi",
            "data_size": len(metrics_data),
            "completed_at": int(time.time() * 1000),
        }

    except Exception as e:
        logger.error(
            f"[Windows WMI Task] {task_id} failed: {str(e)}\n{traceback.format_exc()}"
        )

        from tasks.utils.nats_helper import publish_metrics_to_nats
        from tasks.utils.metrics_helper import generate_monitor_error_metrics

        error_metrics = generate_monitor_error_metrics(params, e)
        await publish_metrics_to_nats(ctx, error_metrics, params, task_id)

        return {
            "task_id": task_id,
            "status": "failed",
            "error": str(e),
            "monitor_type": "windows_wmi",
            "completed_at": int(time.time() * 1000),
        }
```

- [ ] **Step 6: Run worker and handler tests to verify they pass**

Run:

```bash
cd agents/stargazer && uv run pytest tests/test_windows_wmi_monitor.py -q
```

Expected: all tests in `test_windows_wmi_monitor.py` pass.

- [ ] **Step 7: Commit worker dispatch and handler**

```bash
git add agents/stargazer/core/worker.py agents/stargazer/tasks/handlers/monitor_handler.py agents/stargazer/tests/test_windows_wmi_monitor.py
git commit -m "feat: dispatch windows wmi monitor tasks"
```

---

### Task 3: Module Selection And Error Classification

**Files:**
- Create: `agents/stargazer/tasks/collectors/host_wmi/__init__.py`
- Create: `agents/stargazer/tasks/collectors/host_wmi/errors.py`
- Create: `agents/stargazer/tasks/collectors/host_wmi/modules.py`
- Test: `agents/stargazer/tests/test_windows_wmi_collector.py`

- [ ] **Step 1: Write failing module selection and error tests**

Create `agents/stargazer/tests/test_windows_wmi_collector.py`:

```python
from tasks.collectors.host_wmi.errors import WmiError, classify_wmi_error
from tasks.collectors.host_wmi.modules import resolve_modules


def test_resolve_modules_accepts_comma_separated_values():
    assert resolve_modules("cpu, mem,invalid,disk") == ["cpu", "mem", "disk"]


def test_resolve_modules_accepts_arrays_and_defaults_when_empty():
    assert resolve_modules(["net", "processes", "bad"]) == ["net", "processes"]
    assert resolve_modules("bad,unknown") == ["cpu", "mem", "disk", "net"]


def test_classify_wmi_error_normalizes_common_failures():
    assert classify_wmi_error(PermissionError("access denied")) == "dcom_access_denied"
    assert classify_wmi_error(TimeoutError("timed out")) == "query_timeout"
    assert classify_wmi_error(WmiError("bad namespace", "namespace_not_found")) == "namespace_not_found"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd agents/stargazer && uv run pytest tests/test_windows_wmi_collector.py -q
```

Expected: import failure because `tasks.collectors.host_wmi` does not exist.

- [ ] **Step 3: Implement modules and errors**

Create `agents/stargazer/tasks/collectors/host_wmi/__init__.py`:

```python
from .errors import WmiError, classify_wmi_error
from .modules import DEFAULT_MODULES, VALID_MODULES, resolve_modules

__all__ = [
    "DEFAULT_MODULES",
    "VALID_MODULES",
    "WmiError",
    "classify_wmi_error",
    "resolve_modules",
]
```

Create `agents/stargazer/tasks/collectors/host_wmi/errors.py`:

```python
class WmiError(Exception):
    def __init__(self, message: str, error_type: str = "unknown"):
        super().__init__(message)
        self.error_type = error_type


def classify_wmi_error(error: Exception) -> str:
    if isinstance(error, WmiError):
        return error.error_type
    if isinstance(error, TimeoutError):
        return "query_timeout"

    text = str(error).lower()
    if "access denied" in text or "permission" in text:
        return "dcom_access_denied"
    if "auth" in text or "login" in text or "password" in text:
        return "auth_failed"
    if "network" in text or "unreachable" in text:
        return "network_unreachable"
    if "rpc" in text:
        return "rpc_unavailable"
    if "namespace" in text:
        return "namespace_not_found"
    if "class" in text:
        return "class_unavailable"
    if "timeout" in text or "timed out" in text:
        return "query_timeout"
    return "unknown"
```

Create `agents/stargazer/tasks/collectors/host_wmi/modules.py`:

```python
from typing import Any, Callable

VALID_MODULES = ("cpu", "mem", "disk", "diskio", "net", "processes", "system")
DEFAULT_MODULES = ("cpu", "mem", "disk", "net")


def resolve_modules(raw_modules: Any) -> list[str]:
    if isinstance(raw_modules, (list, tuple)):
        items = raw_modules
    else:
        items = str(raw_modules or "").split(",")

    selected = [str(item).strip() for item in items if str(item).strip() in VALID_MODULES]
    return selected or list(DEFAULT_MODULES)


class WmiModule:
    name: str

    def collect(self, client) -> Any:
        raise NotImplementedError


class CpuModule(WmiModule):
    name = "cpu"

    def collect(self, client):
        rows = client.query_class("Win32_Processor")
        load_values = [float(row.get("LoadPercentage") or 0) for row in rows]
        logical_counts = [int(row.get("NumberOfLogicalProcessors") or 0) for row in rows]
        usage = sum(load_values) / len(load_values) if load_values else 0
        cores = sum(logical_counts) or len(rows)
        return {"usage_percent": round(usage, 2), "core_count": cores}


class MemoryModule(WmiModule):
    name = "mem"

    def collect(self, client):
        rows = client.query_class("Win32_OperatingSystem")
        row = rows[0] if rows else {}
        total = int(row.get("TotalVisibleMemorySize") or 0) * 1024
        free = int(row.get("FreePhysicalMemory") or 0) * 1024
        used = max(total - free, 0)
        used_percent = round((used / total) * 100, 2) if total else 0
        return {
            "total_bytes": total,
            "available_bytes": free,
            "used_bytes": used,
            "used_percent": used_percent,
        }


class DiskModule(WmiModule):
    name = "disk"

    def collect(self, client):
        rows = client.query("SELECT DeviceID, Size, FreeSpace FROM Win32_LogicalDisk WHERE DriveType=3")
        disks = []
        for row in rows:
            total = int(row.get("Size") or 0)
            free = int(row.get("FreeSpace") or 0)
            used = max(total - free, 0)
            disks.append(
                {
                    "device": str(row.get("DeviceID") or ""),
                    "total_bytes": total,
                    "free_bytes": free,
                    "used_bytes": used,
                    "used_percent": round((used / total) * 100, 2) if total else 0,
                }
            )
        return disks


class EmptyModule(WmiModule):
    def __init__(self, name: str):
        self.name = name

    def collect(self, client):
        return []


MODULE_REGISTRY: dict[str, Callable[[], WmiModule]] = {
    "cpu": CpuModule,
    "mem": MemoryModule,
    "disk": DiskModule,
    "diskio": lambda: EmptyModule("diskio"),
    "net": lambda: EmptyModule("net"),
    "processes": lambda: EmptyModule("processes"),
    "system": lambda: EmptyModule("system"),
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd agents/stargazer && uv run pytest tests/test_windows_wmi_collector.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit module selection and errors**

```bash
git add agents/stargazer/tasks/collectors/host_wmi agents/stargazer/tests/test_windows_wmi_collector.py
git commit -m "feat: add windows wmi module primitives"
```

---

### Task 4: Prometheus Metric Conversion

**Files:**
- Create: `agents/stargazer/tasks/collectors/host_wmi/metrics.py`
- Test: `agents/stargazer/tests/test_windows_wmi_collector.py`

- [ ] **Step 1: Write failing metric conversion test**

Append to `agents/stargazer/tests/test_windows_wmi_collector.py`:

```python
from tasks.collectors.host_wmi.metrics import wmi_results_to_prometheus


def test_wmi_results_to_prometheus_emits_host_metrics():
    output = wmi_results_to_prometheus(
        {
            "cpu": {"usage_percent": 12.5, "core_count": 4},
            "mem": {
                "total_bytes": 8589934592,
                "available_bytes": 4294967296,
                "used_bytes": 4294967296,
                "used_percent": 50.0,
            },
            "disk": [
                {
                    "device": "C:",
                    "total_bytes": 1000,
                    "free_bytes": 250,
                    "used_bytes": 750,
                    "used_percent": 75.0,
                }
            ],
        },
        {"instance_id": "region_os_10.0.0.8", "instance_type": "os"},
        host="10.0.0.8",
        timestamp=1700000000000,
    )

    assert 'host_cpu_usage_percent_gauge{instance_id="region_os_10.0.0.8",instance_type="os",host="10.0.0.8"} 12.5 1700000000000' in output
    assert 'host_cpu_core_count_gauge{instance_id="region_os_10.0.0.8",instance_type="os",host="10.0.0.8"} 4 1700000000000' in output
    assert 'host_mem_used_percent_gauge{instance_id="region_os_10.0.0.8",instance_type="os",host="10.0.0.8"} 50.0 1700000000000' in output
    assert 'host_disk_used_percent_gauge{instance_id="region_os_10.0.0.8",instance_type="os",host="10.0.0.8",device="C:"} 75.0 1700000000000' in output
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd agents/stargazer && uv run pytest tests/test_windows_wmi_collector.py::test_wmi_results_to_prometheus_emits_host_metrics -q
```

Expected: import failure because `metrics.py` does not exist.

- [ ] **Step 3: Implement metric conversion**

Create `agents/stargazer/tasks/collectors/host_wmi/metrics.py`:

```python
import time
from typing import Any


def _escape_label(value: Any) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _labels(base_labels: dict[str, Any], extra_labels: dict[str, Any] | None = None) -> str:
    merged = {**base_labels, **(extra_labels or {})}
    return ",".join(f'{key}="{_escape_label(value)}"' for key, value in merged.items() if value is not None)


def _append_gauge(lines: list[str], name: str, labels: dict[str, Any], value: Any, timestamp: int):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return
    if number.is_integer():
        rendered = str(int(number))
    else:
        rendered = str(number)
    lines.append(f"{name}{{{_labels(labels)}}} {rendered} {timestamp}")


def wmi_results_to_prometheus(
    results: dict[str, Any],
    tags: dict[str, Any],
    *,
    host: str,
    timestamp: int | None = None,
) -> str:
    timestamp = timestamp or int(time.time() * 1000)
    base_labels = {
        "instance_id": tags.get("instance_id") or host,
        "instance_type": tags.get("instance_type") or "os",
        "host": host,
    }
    lines: list[str] = []

    cpu = results.get("cpu") or {}
    _append_gauge(lines, "host_cpu_usage_percent_gauge", base_labels, cpu.get("usage_percent"), timestamp)
    _append_gauge(lines, "host_cpu_core_count_gauge", base_labels, cpu.get("core_count"), timestamp)

    mem = results.get("mem") or {}
    _append_gauge(lines, "host_mem_total_bytes_gauge", base_labels, mem.get("total_bytes"), timestamp)
    _append_gauge(lines, "host_mem_available_bytes_gauge", base_labels, mem.get("available_bytes"), timestamp)
    _append_gauge(lines, "host_mem_used_bytes_gauge", base_labels, mem.get("used_bytes"), timestamp)
    _append_gauge(lines, "host_mem_used_percent_gauge", base_labels, mem.get("used_percent"), timestamp)

    for disk in results.get("disk") or []:
        disk_labels = {**base_labels, "device": disk.get("device")}
        _append_gauge(lines, "host_disk_total_bytes_gauge", disk_labels, disk.get("total_bytes"), timestamp)
        _append_gauge(lines, "host_disk_free_bytes_gauge", disk_labels, disk.get("free_bytes"), timestamp)
        _append_gauge(lines, "host_disk_used_bytes_gauge", disk_labels, disk.get("used_bytes"), timestamp)
        _append_gauge(lines, "host_disk_used_percent_gauge", disk_labels, disk.get("used_percent"), timestamp)

    return "\n".join(lines) + ("\n" if lines else "")
```

- [ ] **Step 4: Run metric conversion tests**

Run:

```bash
cd agents/stargazer && uv run pytest tests/test_windows_wmi_collector.py -q
```

Expected: all collector tests pass.

- [ ] **Step 5: Commit metric conversion**

```bash
git add agents/stargazer/tasks/collectors/host_wmi/metrics.py agents/stargazer/tests/test_windows_wmi_collector.py
git commit -m "feat: convert windows wmi metrics"
```

---

### Task 5: WindowsWmiCollector With Logging And Partial Failure

**Files:**
- Create: `agents/stargazer/tasks/collectors/host_wmi_collector.py`
- Create: `agents/stargazer/tasks/collectors/host_wmi/client.py`
- Modify: `agents/stargazer/tests/test_windows_wmi_collector.py`

- [ ] **Step 1: Write failing collector behavior tests**

Append to `agents/stargazer/tests/test_windows_wmi_collector.py`:

```python
import logging

import pytest

from tasks.collectors.host_wmi_collector import WindowsWmiCollector


class FakeWmiClient:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def connect(self):
        return None

    def close(self):
        return None

    def query_class(self, class_name):
        if class_name == "Win32_Processor":
            return [{"LoadPercentage": 25, "NumberOfLogicalProcessors": 8}]
        if class_name == "Win32_OperatingSystem":
            return [{"TotalVisibleMemorySize": 1000, "FreePhysicalMemory": 250}]
        return []

    def query(self, query):
        if "Win32_LogicalDisk" in query:
            return [{"DeviceID": "C:", "Size": 1000, "FreeSpace": 400}]
        return []


@pytest.mark.asyncio
async def test_windows_wmi_collector_collects_selected_modules(monkeypatch):
    monkeypatch.setattr(
        "tasks.collectors.host_wmi_collector.WmiClient",
        FakeWmiClient,
    )
    collector = WindowsWmiCollector(
        {
            "host": "10.0.0.8",
            "username": "EXAMPLE\\monitor",
            "password": "secret",
            "namespace": "root\\cimv2",
            "metrics_modules": "cpu,mem,disk",
            "timeout": 30,
            "tags": {"instance_id": "region_os_10.0.0.8", "instance_type": "os"},
        }
    )

    output = await collector.collect()

    assert "host_cpu_usage_percent_gauge" in output
    assert "host_mem_used_percent_gauge" in output
    assert "host_disk_used_percent_gauge" in output


@pytest.mark.asyncio
async def test_windows_wmi_collector_logs_module_failure_and_continues(monkeypatch, caplog):
    class FailingDiskClient(FakeWmiClient):
        def query(self, query):
            raise RuntimeError("class missing")

    monkeypatch.setattr(
        "tasks.collectors.host_wmi_collector.WmiClient",
        FailingDiskClient,
    )
    collector = WindowsWmiCollector(
        {
            "host": "10.0.0.8",
            "username": "EXAMPLE\\monitor",
            "password": "secret",
            "metrics_modules": "cpu,disk",
            "tags": {"instance_id": "region_os_10.0.0.8", "instance_type": "os"},
        }
    )

    with caplog.at_level(logging.WARNING):
        output = await collector.collect()

    assert "host_cpu_usage_percent_gauge" in output
    assert "host_disk_used_percent_gauge" not in output
    assert "event=wmi_module_failed" in caplog.text
    assert "module=disk" in caplog.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd agents/stargazer && uv run pytest tests/test_windows_wmi_collector.py::test_windows_wmi_collector_collects_selected_modules -q
```

Expected: import failure because `host_wmi_collector.py` does not exist.

- [ ] **Step 3: Implement client abstraction and collector**

Create `agents/stargazer/tasks/collectors/host_wmi/client.py`:

```python
from .errors import WmiError


class WmiClient:
    def __init__(self, host: str, username: str, password: str, namespace: str = "root\\cimv2", timeout: int = 60):
        self.host = host
        self.username = username
        self.password = password
        self.namespace = namespace
        self.timeout = timeout

    def connect(self):
        raise WmiError("WMI client dependency is not configured", "unknown")

    def close(self):
        return None

    def query_class(self, class_name: str):
        return self.query(f"SELECT * FROM {class_name}")

    def query(self, query: str):
        raise WmiError("WMI client dependency is not configured", "unknown")
```

Create `agents/stargazer/tasks/collectors/host_wmi_collector.py`:

```python
import logging
import time
from typing import Any

from .base_collector import BaseCollector
from .host_wmi.client import WmiClient
from .host_wmi.errors import classify_wmi_error
from .host_wmi.metrics import wmi_results_to_prometheus
from .host_wmi.modules import MODULE_REGISTRY, resolve_modules

logger = logging.getLogger("stargazer.windows_wmi")


class WindowsWmiCollector(BaseCollector):
    def _context(self) -> dict[str, Any]:
        tags = self.params.get("tags") or {}
        return {
            "monitor_type": "windows_wmi",
            "host": self.params.get("host"),
            "instance_id": tags.get("instance_id") or self.params.get("host"),
            "modules": ",".join(resolve_modules(self.params.get("metrics_modules"))),
        }

    def _client(self) -> WmiClient:
        return WmiClient(
            host=self.params["host"],
            username=self.params["username"],
            password=self.params["password"],
            namespace=self.params.get("namespace") or "root\\cimv2",
            timeout=int(self.params.get("timeout") or 60),
        )

    async def collect(self) -> str:
        context = self._context()
        modules = resolve_modules(self.params.get("metrics_modules"))
        logger.info("event=wmi_collect_start %s", context)
        started = time.monotonic()
        client = self._client()

        try:
            logger.info("event=wmi_connect_start %s", context)
            client.connect()
            logger.info("event=wmi_connect_success %s", context)
        except Exception as error:
            error_type = classify_wmi_error(error)
            logger.error("event=wmi_connect_failed error_type=%s %s", error_type, context, exc_info=True)
            raise

        results: dict[str, Any] = {}
        try:
            for module_name in modules:
                module_started = time.monotonic()
                logger.info("event=wmi_module_start module=%s %s", module_name, context)
                module = MODULE_REGISTRY[module_name]()
                try:
                    results[module_name] = module.collect(client)
                    duration_ms = int((time.monotonic() - module_started) * 1000)
                    logger.info("event=wmi_module_success module=%s duration_ms=%s %s", module_name, duration_ms, context)
                except Exception as error:
                    duration_ms = int((time.monotonic() - module_started) * 1000)
                    error_type = classify_wmi_error(error)
                    logger.warning(
                        "event=wmi_module_failed module=%s error_type=%s duration_ms=%s %s",
                        module_name,
                        error_type,
                        duration_ms,
                        context,
                        exc_info=True,
                    )
        finally:
            client.close()

        if not results:
            raise RuntimeError("Windows WMI collection returned no module data")

        output = wmi_results_to_prometheus(
            results,
            self.params.get("tags") or {},
            host=self.params["host"],
        )
        duration_ms = int((time.monotonic() - started) * 1000)
        logger.info("event=wmi_collect_success duration_ms=%s %s", duration_ms, context)
        return output
```

- [ ] **Step 4: Run collector tests**

Run:

```bash
cd agents/stargazer && uv run pytest tests/test_windows_wmi_collector.py -q
```

Expected: all collector tests pass.

- [ ] **Step 5: Commit collector behavior**

```bash
git add agents/stargazer/tasks/collectors/host_wmi_collector.py agents/stargazer/tasks/collectors/host_wmi/client.py agents/stargazer/tests/test_windows_wmi_collector.py
git commit -m "feat: add windows wmi collector"
```

---

### Task 6: Real Impacket WMI Client

**Files:**
- Modify: `agents/stargazer/tasks/collectors/host_wmi/client.py`
- Modify: `agents/stargazer/pyproject.toml`
- Test: `agents/stargazer/tests/test_windows_wmi_collector.py`

- [ ] **Step 1: Write failing client behavior tests**

Append to `agents/stargazer/tests/test_windows_wmi_collector.py`:

```python
from tasks.collectors.host_wmi.client import WmiClient
from tasks.collectors.host_wmi.errors import WmiError


def test_wmi_client_reports_missing_dependency(monkeypatch):
    client = WmiClient(
        host="10.0.0.8",
        username="EXAMPLE\\monitor",
        password="secret",
        namespace="root\\cimv2",
        timeout=30,
    )

    monkeypatch.setattr(client, "_load_impacket", lambda: (_ for _ in ()).throw(ImportError("missing")))

    try:
        client.connect()
    except WmiError as error:
        assert error.error_type == "unknown"
        assert "impacket" in str(error).lower()
    else:
        raise AssertionError("expected WmiError")


def test_wmi_client_parses_domain_username():
    client = WmiClient(
        host="10.0.0.8",
        username="EXAMPLE\\monitor",
        password="secret",
    )

    assert client._split_username() == ("EXAMPLE", "monitor")


def test_wmi_client_normalizes_wmi_property_rows():
    rows = WmiClient._normalize_rows(
        [
            {
                "Name": {"value": "CPU0"},
                "LoadPercentage": {"value": 12},
                "Ignored": {"value": None},
            }
        ]
    )

    assert rows == [{"Name": "CPU0", "LoadPercentage": 12, "Ignored": None}]
```

- [ ] **Step 2: Run test to verify it fails for the expected reason**

Run:

```bash
cd agents/stargazer && uv run pytest tests/test_windows_wmi_collector.py::test_wmi_client_reports_missing_dependency tests/test_windows_wmi_collector.py::test_wmi_client_parses_domain_username tests/test_windows_wmi_collector.py::test_wmi_client_normalizes_wmi_property_rows -q
```

Expected: `FAIL` because `_load_impacket`, `_split_username`, or `_normalize_rows` does not exist.

- [ ] **Step 3: Implement the impacket WMI client**

Update `agents/stargazer/tasks/collectors/host_wmi/client.py`:

```python
from .errors import WmiError


class WmiClient:
    def __init__(self, host: str, username: str, password: str, namespace: str = "root\\cimv2", timeout: int = 60):
        self.host = host
        self.username = username
        self.password = password
        self.namespace = namespace
        self.timeout = timeout
        self._dcom = None
        self._services = None

    def _load_impacket(self):
        from impacket.dcerpc.v5.dcomrt import DCOMConnection
        from impacket.dcerpc.v5.dcom import wmi
        from impacket.dcerpc.v5.dtypes import NULL

        return DCOMConnection, wmi, NULL

    def _split_username(self) -> tuple[str, str]:
        username = str(self.username or "")
        if "\\" in username:
            domain, user = username.split("\\", 1)
            return domain, user
        if "@" in username:
            user, domain = username.split("@", 1)
            return domain, user
        return "", username

    @staticmethod
    def _normalize_rows(raw_rows):
        rows = []
        for raw_row in raw_rows:
            row = {}
            for key, value in raw_row.items():
                if isinstance(value, dict) and "value" in value:
                    row[key] = value.get("value")
                else:
                    row[key] = value
            rows.append(row)
        return rows

    def connect(self):
        try:
            DCOMConnection, wmi, NULL = self._load_impacket()
        except ImportError as error:
            raise WmiError("impacket is required for Windows WMI collection", "unknown") from error

        domain, user = self._split_username()
        try:
            self._dcom = DCOMConnection(
                self.host,
                user,
                self.password,
                domain,
                "",
                "",
                oxidResolver=True,
            )
            interface = self._dcom.CoCreateInstanceEx(
                wmi.CLSID_WbemLevel1Login,
                wmi.IID_IWbemLevel1Login,
            )
            login = wmi.IWbemLevel1Login(interface)
            self._services = login.NTLMLogin(f"//./{self.namespace}", NULL, NULL)
            login.RemRelease()
        except Exception as error:
            self.close()
            raise WmiError(f"failed to connect to WMI: {error}", "unknown") from error

    def close(self):
        services = self._services
        self._services = None
        if services and hasattr(services, "RemRelease"):
            try:
                services.RemRelease()
            except Exception:
                pass

        dcom = self._dcom
        self._dcom = None
        if dcom and hasattr(dcom, "disconnect"):
            try:
                dcom.disconnect()
            except Exception:
                pass

    def query_class(self, class_name: str):
        return self.query(f"SELECT * FROM {class_name}")

    def query(self, query: str):
        if self._services is None:
            raise WmiError("WMI query called before connection is ready", "unknown")

        try:
            enumerator = self._services.ExecQuery(query)
            raw_rows = []
            while True:
                try:
                    item = enumerator.Next(0xFFFFFFFF, 1)[0]
                    raw_rows.append(item.getProperties())
                    item.RemRelease()
                except Exception as error:
                    if "S_FALSE" in str(error):
                        break
                    raise
            return self._normalize_rows(raw_rows)
        except Exception as error:
            raise WmiError(f"WMI query failed: {error}", "query_failed") from error
        finally:
            if "enumerator" in locals() and hasattr(enumerator, "RemRelease"):
                try:
                    enumerator.RemRelease()
                except Exception:
                    pass
```

The implementation follows impacket's WMI DCOM pattern:

```text
DCOMConnection -> CoCreateInstanceEx(CLSID_WbemLevel1Login) -> IWbemLevel1Login.NTLMLogin("//./root\\cimv2")
```

It keeps authentication and query logic inside `WmiClient`, while collector tests continue to mock the network boundary.

- [ ] **Step 4: Add the dependency**

Add dependency to `agents/stargazer/pyproject.toml` after `pyghmi`:

```toml
    "impacket>=0.12.0",
```

- [ ] **Step 5: Run client tests**

Run:

```bash
cd agents/stargazer && uv run pytest tests/test_windows_wmi_collector.py -q
```

Expected: tests pass because network behavior is mocked in collector tests and unit tests cover dependency, username parsing, and row normalization.

- [ ] **Step 6: Commit WMI client**

```bash
git add agents/stargazer/tasks/collectors/host_wmi/client.py agents/stargazer/pyproject.toml agents/stargazer/tests/test_windows_wmi_collector.py
git commit -m "feat: add windows wmi client"
```

---

### Task 7: Server Plugin Template And UI

**Files:**
- Create: `server/apps/monitor/support-files/plugins/Telegraf/http/windows_wmi/UI.json`
- Create: `server/apps/monitor/support-files/plugins/Telegraf/http/windows_wmi/windows_wmi.child.toml.j2`
- Create: `server/apps/monitor/support-files/plugins/Telegraf/http/windows_wmi/metrics.json`
- Create: `server/apps/monitor/support-files/plugins/Telegraf/http/windows_wmi/policy.json`
- Modify: `server/apps/monitor/utils/plugin_controller.py`
- Test: `server/apps/monitor/tests/test_plugin_service.py`

- [ ] **Step 1: Write failing template rendering test**

Append to `server/apps/monitor/tests/test_plugin_service.py`:

```python
def test_windows_wmi_template_renders_headers(monkeypatch):
    plugin_controller_module = _load_module(
        "monitor_plugin_controller_windows_wmi_test_module",
        Path(__file__).resolve().parents[1] / "utils" / "plugin_controller.py",
    )

    template_path = Path(__file__).resolve().parents[1] / "support-files" / "plugins" / "Telegraf" / "http" / "windows_wmi" / "windows_wmi.child.toml.j2"
    template_content = template_path.read_text()

    controller = plugin_controller_module.Controller({})
    rendered = controller.render_template(
        template_content,
        {
            "config_id": "cfg1",
            "host": "10.0.0.8",
            "username": "EXAMPLE\\monitor",
            "namespace": "root\\cimv2",
            "metrics_modules": ["cpu", "mem"],
            "timeout": 45,
            "interval": 60,
            "instance_id": "region_os_10.0.0.8",
            "instance_type": "os",
        },
    )

    assert 'urls = ["${STARGAZER_URL}/api/monitor/windows/wmi/metrics"]' in rendered
    assert 'host = "10.0.0.8"' in rendered
    assert 'username = "EXAMPLE\\\\monitor"' in rendered
    assert 'password = "${PASSWORD__cfg1}"' in rendered
    assert 'namespace = "root\\\\cimv2"' in rendered
    assert 'metrics_modules = "cpu,mem"' in rendered
    assert 'config_type = "windows_wmi"' in rendered
```

- [ ] **Step 2: Run template test to verify it fails**

Run:

```bash
cd server && uv run pytest apps/monitor/tests/test_plugin_service.py::test_windows_wmi_template_renders_headers -q
```

Expected: file-not-found failure for `windows_wmi.child.toml.j2`.

- [ ] **Step 3: Create plugin template**

Create `server/apps/monitor/support-files/plugins/Telegraf/http/windows_wmi/windows_wmi.child.toml.j2`:

```toml
[[inputs.prometheus]]
    startup_error_behavior = "retry"
    urls = ["${STARGAZER_URL}/api/monitor/windows/wmi/metrics"]
    interval = "{{ interval | default(60, true) }}s"
    timeout = "{{ timeout | default(60, true) }}s"
    response_timeout = "{{ response_timeout | default(60, true) }}s"

    [inputs.prometheus.http_headers]
        host = "{{ host }}"
        username = "{{ username }}"
        password = "${PASSWORD__{{ config_id }}}"
        namespace = "{{ namespace | default('root\\cimv2', true) }}"
        metrics_modules = "{{ metrics_modules | default('cpu,mem,disk,net', true) }}"
        timeout = "{{ timeout | default(60, true) }}"
        instance_id = "{{ instance_id }}"
        instance_type = "{{ instance_type | default('os', true) }}"
        collect_type = "http"
        config_type = "windows_wmi"
```

If `namespace` is not allowed in `plugin_controller.py`, add it to `_MONITOR_TEMPLATE_ALLOWED_VARIABLES`.

- [ ] **Step 4: Create UI metadata**

Create `server/apps/monitor/support-files/plugins/Telegraf/http/windows_wmi/UI.json`:

```json
{
  "object_name": "Host",
  "instance_type": "os",
  "collect_type": "http",
  "config_type": ["windows_wmi"],
  "collector": "Telegraf",
  "instance_id": "{{cloud_region}}_{{instance_type}}_{{host}}",
  "form_fields": [
    {
      "name": "host",
      "label": "目标主机IP",
      "type": "input",
      "required": true,
      "visible_in": "edit",
      "editable": false,
      "description": "目标 Windows 主机的 IP 地址",
      "widget_props": {"placeholder": "10.0.0.1"},
      "transform_on_edit": {"origin_path": "child.content.config.http_headers.host"}
    },
    {
      "name": "username",
      "label": "用户名",
      "type": "input",
      "required": true,
      "editable": false,
      "description": "WMI 查询账号，支持 domain\\\\user 或 user@domain",
      "widget_props": {"placeholder": "DOMAIN\\\\monitor"},
      "transform_on_edit": {"origin_path": "child.content.config.http_headers.username"}
    },
    {
      "name": "ENV_PASSWORD",
      "label": "密码",
      "type": "password",
      "required": true,
      "editable": false,
      "encrypted": true,
      "description": "WMI 查询账号密码",
      "widget_props": {"placeholder": "密码"},
      "transform_on_edit": {"origin_path": "child.env_config.PASSWORD__{{config_id}}"}
    },
    {
      "name": "namespace",
      "label": "命名空间",
      "type": "input",
      "required": false,
      "default_value": "root\\cimv2",
      "description": "WMI 命名空间，默认 root\\\\cimv2",
      "widget_props": {"placeholder": "root\\\\cimv2"},
      "transform_on_edit": {"origin_path": "child.content.config.http_headers.namespace"}
    },
    {
      "name": "metrics_modules",
      "label": "采集模块",
      "type": "checkbox_group",
      "required": true,
      "editable": false,
      "default_value": ["cpu", "mem", "disk", "net"],
      "description": "选择需要通过 WMI 远程采集的 Windows 主机指标模块",
      "options": [
        {"label": "CPU", "value": "cpu"},
        {"label": "Memory", "value": "mem"},
        {"label": "Disk", "value": "disk"},
        {"label": "Disk IO", "value": "diskio"},
        {"label": "Network", "value": "net"},
        {"label": "Processes", "value": "processes"},
        {"label": "System", "value": "system"}
      ],
      "widget_props": {},
      "transform_on_edit": {
        "origin_path": "child.content.config.http_headers.metrics_modules",
        "to_form": {"array": true}
      }
    },
    {
      "name": "timeout",
      "label": "超时",
      "type": "inputNumber",
      "required": false,
      "default_value": 60,
      "description": "WMI 连接和查询超时时间（秒）",
      "widget_props": {"min": 5, "precision": 0, "addonAfter": "s"},
      "transform_on_edit": {"origin_path": "child.content.config.http_headers.timeout"}
    },
    {
      "name": "interval",
      "label": "采集间隔",
      "type": "inputNumber",
      "required": true,
      "default_value": 60,
      "description": "监控数据采集间隔（秒）",
      "widget_props": {"min": 10, "precision": 0, "addonAfter": "s"},
      "transform_on_edit": {
        "origin_path": "child.content.config.interval",
        "to_form": {"regex": "^(\\d+)s$"},
        "to_api": {"suffix": "s"}
      }
    }
  ],
  "table_columns": [
    {"name": "node_ids", "label": "节点", "type": "select", "required": true, "widget_props": {"placeholder": "请选择节点"}, "enable_row_filter": false},
    {"name": "host", "label": "主机", "type": "input", "required": true, "widget_props": {"placeholder": "主机"}, "change_handler": {"type": "simple", "source_fields": ["host"], "target_field": "instance_name"}},
    {"name": "instance_name", "label": "实例名称", "type": "input", "required": true, "widget_props": {"placeholder": "实例名称"}},
    {"name": "group_ids", "label": "组", "type": "group_select", "required": false, "widget_props": {"placeholder": "请选择组"}}
  ],
  "extra_edit_fields": {}
}
```

- [ ] **Step 5: Create metrics metadata**

Create `server/apps/monitor/support-files/plugins/Telegraf/http/windows_wmi/metrics.json`:

```json
{
  "plugin": "Windows WMI",
  "plugin_desc": "Remote Windows host metrics collection through WMI/DCOM from Stargazer. Requires WMI service, account permission, and WMI/DCOM/RPC network reachability.",
  "status_query": "any({instance_type='os', collect_type='http', config_type='windows_wmi'}) by (instance_id)",
  "node_selector": {"is_container": true},
  "name": "Host",
  "icon": "mm-host_主机",
  "type": "OS",
  "description": "Remote Windows host monitoring through WMI",
  "default_metric": "any({instance_type='os', config_type='windows_wmi'}) by (instance_id)",
  "instance_id_keys": ["instance_id"],
  "supplementary_indicators": ["cpu_usage_total", "mem_used_percent", "disk_used_percent"],
  "display_fields": [
    {"name": "CPU Usage", "sort_order": 0, "metrics": [{"plugin": "Windows WMI", "metric": "cpu_usage_total"}]},
    {"name": "Memory Usage", "sort_order": 1, "metrics": [{"plugin": "Windows WMI", "metric": "mem_used_percent"}]},
    {"name": "Disk Usage", "sort_order": 2, "metrics": [{"plugin": "Windows WMI", "metric": "disk_used_percent"}]}
  ],
  "metrics": [
    {"metric_group": "CPU", "name": "cpu_usage_total", "query": "host_cpu_usage_percent_gauge{instance_type=\"os\", config_type=\"windows_wmi\", __$labels__}", "display_name": "CPU Usage", "data_type": "Number", "unit": "%", "dimensions": [], "instance_id_keys": ["instance_id"], "description": "CPU usage percentage"},
    {"metric_group": "Memory", "name": "mem_used_percent", "query": "host_mem_used_percent_gauge{instance_type=\"os\", config_type=\"windows_wmi\", __$labels__}", "display_name": "Memory Usage", "data_type": "Number", "unit": "%", "dimensions": [], "instance_id_keys": ["instance_id"], "description": "Used memory percentage"},
    {"metric_group": "Disk", "name": "disk_used_percent", "query": "host_disk_used_percent_gauge{instance_type=\"os\", config_type=\"windows_wmi\", __$labels__}", "display_name": "Disk Usage", "data_type": "Number", "unit": "%", "dimensions": ["device"], "instance_id_keys": ["instance_id"], "description": "Disk usage percentage per logical disk"}
  ]
}
```

Create `server/apps/monitor/support-files/plugins/Telegraf/http/windows_wmi/policy.json`:

```json
[]
```

- [ ] **Step 6: Run server plugin tests**

Run:

```bash
cd server && uv run pytest apps/monitor/tests/test_plugin_service.py::test_windows_wmi_template_renders_headers -q
```

Expected: test passes.

- [ ] **Step 7: Commit server plugin template**

```bash
git add server/apps/monitor/support-files/plugins/Telegraf/http/windows_wmi server/apps/monitor/utils/plugin_controller.py server/apps/monitor/tests/test_plugin_service.py
git commit -m "feat: add windows wmi monitor plugin template"
```

---

### Task 8: Final Verification

**Files:**
- Review all files modified by Tasks 1-7.

- [ ] **Step 1: Run Stargazer focused tests**

Run:

```bash
cd agents/stargazer && uv run pytest tests/test_windows_wmi_monitor.py tests/test_windows_wmi_collector.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run existing host collector regression tests**

Run:

```bash
cd agents/stargazer && uv run pytest tests/test_host_collector.py -q
```

Expected: all tests pass.

- [ ] **Step 3: Run Server focused plugin tests**

Run:

```bash
cd server && uv run pytest apps/monitor/tests/test_plugin_service.py -q
```

Expected: all tests pass.

- [ ] **Step 4: Inspect git diff for secrets and accidental churn**

Run:

```bash
git diff --check
git diff --stat
rg -n "secret|password|PASSWORD|PRIVATE_KEY|TOKEN" agents/stargazer server/apps/monitor/support-files/plugins/Telegraf/http/windows_wmi
```

Expected:

- `git diff --check` exits 0.
- No real credential values appear.
- `password` appears only as field names, placeholders, or test dummy strings.

- [ ] **Step 5: Commit any verification-only fixes**

If verification required small fixes, commit them:

```bash
git add <fixed-files>
git commit -m "test: verify windows wmi collection"
```
