import importlib.util
import asyncio
import sys
import types
from pathlib import Path


def _load_worker_module():
    spec = importlib.util.spec_from_file_location(
        "stargazer_worker_enterprise_dispatch_test_module",
        Path(__file__).resolve().parents[1] / "core" / "worker.py",
    )
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


def _run(coro):
    return asyncio.run(coro)


def test_collect_task_dispatches_optional_enterprise_monitor(monkeypatch):
    captured = {}

    async def fake_enterprise_handler(ctx, params, task_id):
        captured["ctx"] = ctx
        captured["params"] = params
        captured["task_id"] = task_id
        return {"task_id": task_id, "status": "success", "monitor_type": "pure"}

    storage_handler = _install_module(
        monkeypatch,
        "enterprise.tasks.handlers.storage_handler",
        collect_pure_metrics_task=fake_enterprise_handler,
    )
    handlers = _install_module(
        monkeypatch,
        "enterprise.tasks.handlers",
        storage_handler=storage_handler,
    )
    tasks = _install_module(monkeypatch, "enterprise.tasks", handlers=handlers)
    _install_module(monkeypatch, "enterprise", tasks=tasks)
    _install_module(monkeypatch, "arq", create_pool=lambda *args, **kwargs: None)
    _install_module(monkeypatch, "arq.connections", RedisSettings=lambda **kwargs: kwargs)
    _install_module(monkeypatch, "core")
    _install_module(
        monkeypatch,
        "core.redis_config",
        REDIS_CONFIG={"host": "localhost", "port": 6379, "password": "", "database": 0},
    )

    worker = _load_worker_module()

    async def noop(*args, **kwargs):
        return None

    monkeypatch.setattr(worker, "_clear_dedupe_key", noop)
    monkeypatch.setattr(worker, "_clear_running_flag", noop)

    result = _run(
        worker.collect_task(
            {"job_id": "job-1"},
            {"monitor_type": "pure", "host": "10.0.0.2"},
            "task-1",
        )
    )

    assert result["status"] == "success"
    assert captured["params"]["monitor_type"] == "pure"
    assert captured["task_id"] == "task-1"


def test_collect_task_keeps_unknown_monitor_type_unknown(monkeypatch):
    _install_module(monkeypatch, "arq", create_pool=lambda *args, **kwargs: None)
    _install_module(monkeypatch, "arq.connections", RedisSettings=lambda **kwargs: kwargs)
    _install_module(monkeypatch, "core")
    _install_module(
        monkeypatch,
        "core.redis_config",
        REDIS_CONFIG={"host": "localhost", "port": 6379, "password": "", "database": 0},
    )
    worker = _load_worker_module()

    async def noop(*args, **kwargs):
        return None

    monkeypatch.setattr(worker, "_clear_dedupe_key", noop)
    monkeypatch.setattr(worker, "_clear_running_flag", noop)

    result = _run(
        worker.collect_task(
            {}, {"monitor_type": "not_existing_monitor"}, "task-unknown"
        )
    )

    assert result["status"] == "failed"
    assert result["error"] == "Unknown task type"
