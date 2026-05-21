import importlib.util
import sys
import types
from pathlib import Path


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


def test_extract_monitor_object_names_supports_basic_and_compound(monkeypatch):
    _install_module(monkeypatch, "django")
    _install_module(monkeypatch, "django.db", transaction=types.SimpleNamespace(atomic=lambda: None))
    _install_module(monkeypatch, "apps")
    _install_module(monkeypatch, "apps.monitor")
    _install_module(monkeypatch, "apps.monitor.constants")
    _install_module(monkeypatch, "apps.monitor.constants.database", DatabaseConstants=types.SimpleNamespace())
    _install_module(
        monkeypatch,
        "apps.monitor.models",
        MonitorPlugin=types.SimpleNamespace(objects=types.SimpleNamespace(filter=lambda **kwargs: None)),
        MonitorPluginUITemplate=types.SimpleNamespace(objects=types.SimpleNamespace(filter=lambda **kwargs: None)),
    )
    _install_module(monkeypatch, "apps.monitor.models.monitor_metrics", MetricGroup=object, Metric=object)
    _install_module(monkeypatch, "apps.monitor.models.monitor_object", MonitorObject=object, MonitorObjectType=object)
    _install_module(monkeypatch, "apps.monitor.utils")
    _install_module(
        monkeypatch,
        "apps.monitor.utils.instance_id_keys",
        resolve_metric_instance_id_keys=lambda *args, **kwargs: [],
        resolve_monitor_object_instance_id_keys=lambda keys, **kwargs: keys or ["instance_id"],
    )

    plugin_module = _load_module(
        "monitor_plugin_service_test_module",
        Path(__file__).resolve().parents[1] / "services" / "plugin.py",
    )

    basic_names = plugin_module.MonitorPluginService._extract_monitor_object_names({"plugin": "OceanStor", "name": "Storage"})
    compound_names = plugin_module.MonitorPluginService._extract_monitor_object_names(
        {
            "plugin": "OceanStor",
            "is_compound_object": True,
            "objects": [{"name": "Storage"}, {"name": "StoragePool"}],
        }
    )

    assert basic_names == ["Storage"]
    assert compound_names == ["Storage", "StoragePool"]


def test_sync_plugin_monitor_objects_replaces_stale_relations(monkeypatch):
    _install_module(monkeypatch, "django")
    _install_module(monkeypatch, "django.db", transaction=types.SimpleNamespace(atomic=lambda: None))
    _install_module(monkeypatch, "apps")
    _install_module(monkeypatch, "apps.monitor")
    _install_module(monkeypatch, "apps.monitor.constants")
    _install_module(monkeypatch, "apps.monitor.constants.database", DatabaseConstants=types.SimpleNamespace())
    _install_module(
        monkeypatch,
        "apps.monitor.models",
        MonitorPlugin=types.SimpleNamespace(objects=types.SimpleNamespace(filter=lambda **kwargs: None)),
        MonitorPluginUITemplate=types.SimpleNamespace(objects=types.SimpleNamespace(filter=lambda **kwargs: None)),
    )
    _install_module(monkeypatch, "apps.monitor.models.monitor_metrics", MetricGroup=object, Metric=object)
    _install_module(monkeypatch, "apps.monitor.utils")
    _install_module(
        monkeypatch,
        "apps.monitor.utils.instance_id_keys",
        resolve_metric_instance_id_keys=lambda *args, **kwargs: [],
        resolve_monitor_object_instance_id_keys=lambda keys, **kwargs: keys or ["instance_id"],
    )

    class StubMonitorObjectManager:
        def __init__(self):
            self.filter_kwargs = None

        def filter(self, **kwargs):
            self.filter_kwargs = kwargs
            return [types.SimpleNamespace(name="Storage")]

    class StubPluginRelation:
        def __init__(self):
            self.received = None

        def set(self, objs):
            self.received = list(objs)

    relation = StubPluginRelation()
    plugin_obj = types.SimpleNamespace(monitor_object=relation)

    class StubMonitorPluginManager:
        def __init__(self):
            self.filter_kwargs = None

        def filter(self, **kwargs):
            self.filter_kwargs = kwargs
            return types.SimpleNamespace(first=lambda: plugin_obj)

    monitor_object_manager = StubMonitorObjectManager()
    monitor_plugin_manager = StubMonitorPluginManager()

    _install_module(
        monkeypatch,
        "apps.monitor.models.monitor_object",
        MonitorObject=types.SimpleNamespace(objects=monitor_object_manager),
        MonitorObjectType=object,
    )

    plugin_module = _load_module(
        "monitor_plugin_service_sync_test_module",
        Path(__file__).resolve().parents[1] / "services" / "plugin.py",
    )
    plugin_module.MonitorPlugin = types.SimpleNamespace(objects=monitor_plugin_manager)
    plugin_module.MonitorObject = types.SimpleNamespace(objects=monitor_object_manager)

    plugin_module.MonitorPluginService._sync_plugin_monitor_objects("OceanStor", ["Storage"])

    assert monitor_plugin_manager.filter_kwargs == {"name": "OceanStor"}
    assert monitor_object_manager.filter_kwargs == {"name__in": ["Storage"]}
    assert [obj.name for obj in relation.received] == ["Storage"]
