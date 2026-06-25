import importlib.util
import sys
import types
from pathlib import Path


def _install_module(monkeypatch, name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def _load_policy_service_module(monkeypatch, rows):
    class _QuerySet:
        def filter(self, **kwargs):
            return rows

        def values_list(self, *args, **kwargs):
            return []

    _install_module(
        monkeypatch,
        "apps.monitor.models",
        PolicyTemplate=types.SimpleNamespace(objects=types.SimpleNamespace(select_related=lambda *args: _QuerySet())),
        MonitorPlugin=object,
        MonitorObject=object,
    )

    spec = importlib.util.spec_from_file_location(
        "policy_service_templates_module",
        Path(__file__).resolve().parents[1] / "services" / "policy.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_get_policy_templates_adds_default_trigger_count_and_preserves_explicit_value(monkeypatch):
    monitor_object = types.SimpleNamespace(id=1, name="Host", display_name="主机")
    plugin = types.SimpleNamespace(id=9, name="Telegraf", display_name="Telegraf", collector="Telegraf")
    row = types.SimpleNamespace(
        id=7,
        monitor_object_id=1,
        monitor_object=monitor_object,
        plugin_id=9,
        plugin=plugin,
        templates=[
            {"name": "CPU", "metric_name": "cpu_usage"},
            {"name": "Memory", "metric_name": "memory_usage", "trigger_count": 2},
        ],
    )
    module = _load_policy_service_module(monkeypatch, [row])

    templates = module.PolicyService.get_policy_templates("Host")

    assert templates[0]["trigger_count"] == 1
    assert templates[1]["trigger_count"] == 2
