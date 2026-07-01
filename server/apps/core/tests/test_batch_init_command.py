import importlib.util
import io
import sys
import types
from pathlib import Path

import pytest


@pytest.fixture
def settings():
    return types.SimpleNamespace(CACHES={}, MIDDLEWARE=())


class _BaseCommand:
    class _Style:
        @staticmethod
        def SUCCESS(message):
            return message

        @staticmethod
        def ERROR(message):
            return message

        @staticmethod
        def WARNING(message):
            return message

    def __init__(self):
        self.stdout = types.SimpleNamespace(write=lambda message: None)
        self.style = self._Style()


def _install_module(monkeypatch, name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def _load_module(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_command(monkeypatch):
    calls = []

    def call_command(name, *args, **kwargs):
        calls.append((name, args, kwargs))
        if name == "plugin_init":
            raise RuntimeError("plugin init failed")

    _install_module(monkeypatch, "django.core.management", call_command=call_command)
    _install_module(monkeypatch, "django.core.management.base", BaseCommand=_BaseCommand)
    _install_module(
        monkeypatch,
        "apps.core.utils.loader",
        preload_language_cache=lambda: {"loaded": ["zh-Hans"], "skipped": [], "failed": []},
    )

    module = _load_module(
        "batch_init_command_test_module",
        Path(__file__).resolve().parents[1] / "management" / "commands" / "batch_init.py",
    )
    command = module.Command()
    output = io.StringIO()
    command.stdout = types.SimpleNamespace(write=lambda message: output.write(f"{message}\n"))
    return command, output, calls


def test_batch_init_raises_on_non_system_mgmt_failure_by_default(monkeypatch):
    command, output, calls = _load_command(monkeypatch)

    with pytest.raises(RuntimeError, match="plugin init failed"):
        command.handle(apps="monitor,node_mgmt", continue_on_error=False)

    assert calls == [("plugin_init", (), {})]
    assert "初始化 monitor 失败: plugin init failed" in output.getvalue()
    assert "初始化节点管理" not in output.getvalue()
    assert "批量初始化完成" not in output.getvalue()


def test_batch_init_continue_on_error_runs_remaining_apps_and_reports_failures(monkeypatch):
    command, output, calls = _load_command(monkeypatch)

    command.handle(apps="monitor,node_mgmt", continue_on_error=True)

    assert calls == [("plugin_init", (), {}), ("node_init", (), {})]
    assert "初始化 monitor 失败: plugin init failed" in output.getvalue()
    assert "批量初始化完成，失败模块: monitor: plugin init failed" in output.getvalue()
