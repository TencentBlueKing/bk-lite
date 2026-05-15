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


def _load_module(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _install_monitor_nats_dependencies(monkeypatch):
    def register(func):
        return func

    class ValidationError(Exception):
        def __init__(self, detail):
            super().__init__(str(detail))
            self.detail = detail

    class _Logger:
        def exception(self, *args, **kwargs):
            return None

        def info(self, *args, **kwargs):
            return None

        def error(self, *args, **kwargs):
            return None

    class _StubModel:
        objects = types.SimpleNamespace()

    _install_module(monkeypatch, "nats_client", register=register)
    rest_serializers = _install_module(monkeypatch, "rest_framework.serializers", ValidationError=ValidationError)
    _install_module(monkeypatch, "rest_framework", serializers=rest_serializers)
    _install_module(monkeypatch, "django.db.models", Count=lambda *args, **kwargs: None, Q=lambda *args, **kwargs: None)
    _install_module(monkeypatch, "django.db", models=sys.modules["django.db.models"])
    _install_module(monkeypatch, "apps.core.utils.time_util", format_timestamp=lambda value: value)
    _install_module(
        monkeypatch,
        "apps.monitor.models",
        MonitorAlert=_StubModel,
        MonitorInstance=_StubModel,
        MonitorObject=_StubModel,
        MonitorObjectType=_StubModel,
        Metric=_StubModel,
        MetricGroup=_StubModel,
        MonitorPlugin=_StubModel,
    )
    _install_module(
        monkeypatch,
        "apps.monitor.serializers.monitor_metrics",
        MetricGroupSerializer=object,
        MetricSerializer=object,
    )
    _install_module(
        monkeypatch,
        "apps.monitor.serializers.monitor_object",
        MonitorObjectSerializer=object,
        MonitorObjectTypeSerializer=object,
    )
    _install_module(monkeypatch, "apps.monitor.serializers.plugin", MonitorPluginSerializer=object)
    _install_module(monkeypatch, "apps.monitor.serializers.monitor_policy", MonitorPolicySerializer=object)
    _install_module(monkeypatch, "apps.monitor.services.metrics", Metrics=types.SimpleNamespace(parse_step_to_seconds=lambda step: 300))
    _install_module(
        monkeypatch,
        "apps.core.utils.permission_utils",
        check_instance_permission=lambda *args, **kwargs: True,
        get_permission_rules=lambda *args, **kwargs: {},
        get_permissions_rules=lambda *args, **kwargs: {},
        permission_filter=lambda *args, **kwargs: [],
    )
    _install_module(
        monkeypatch,
        "apps.monitor.constants.permission",
        PermissionConstants=types.SimpleNamespace(INSTANCE_MODULE="instance"),
    )
    _install_module(monkeypatch, "apps.monitor.utils.victoriametrics_api", VictoriaMetricsAPI=object)
    _install_module(monkeypatch, "apps.core.logger", nats_logger=_Logger())


def test_create_monitor_object_type_accepts_user_info_and_uses_actor_context(monkeypatch):
    _install_monitor_nats_dependencies(monkeypatch)
    module = _load_module(
        "monitor_nats_create_handlers_test_module",
        Path(__file__).resolve().parents[1] / "nats" / "monitor.py",
    )

    captured = {}

    def fake_create_with_serializer(serializer_class, data, operator="api", domain="domain.com"):
        captured["serializer_class"] = serializer_class
        captured["data"] = data
        captured["operator"] = operator
        captured["domain"] = domain
        return object(), {"id": "host"}

    monkeypatch.setattr(module, "_create_with_serializer", fake_create_with_serializer)

    result = module.create_monitor_object_type(
        {"id": "host", "name": "Host"},
        user_info={"user": types.SimpleNamespace(username="alice", domain="tenant-a.com"), "domain": "tenant-a.com"},
    )

    assert result == {"result": True, "data": {"id": "host"}, "message": ""}
    assert captured["data"] == {"id": "host", "name": "Host"}
    assert captured["operator"] == "alice"
    assert captured["domain"] == "tenant-a.com"


def test_execute_nats_create_uses_domain_from_user_info_for_string_users(monkeypatch):
    _install_monitor_nats_dependencies(monkeypatch)
    module = _load_module(
        "monitor_nats_create_handlers_string_user_test_module",
        Path(__file__).resolve().parents[1] / "nats" / "monitor.py",
    )

    captured = {}

    def fake_create(payload, operator="api", domain="domain.com"):
        captured["payload"] = payload
        captured["operator"] = operator
        captured["domain"] = domain
        return object(), {"id": "metric"}

    result = module._execute_nats_create(
        fake_create,
        {"name": "cpu_usage"},
        user_info={"user": "alice", "domain": "tenant-b.com"},
    )

    assert result == {"result": True, "data": {"id": "metric"}, "message": ""}
    assert captured == {
        "payload": {"name": "cpu_usage"},
        "operator": "alice",
        "domain": "tenant-b.com",
    }


def test_create_monitor_object_payload_generates_derivative_instance_id_keys(monkeypatch):
    _install_monitor_nats_dependencies(monkeypatch)
    module = _load_module(
        "monitor_nats_create_monitor_object_payload_test_module",
        Path(__file__).resolve().parents[1] / "nats" / "monitor.py",
    )

    captured = {}

    class StubMonitorObjectSerializer:
        def __init__(self, data=None):
            captured["payload"] = data
            self.data = data

        def is_valid(self, raise_exception=False):
            return True

        def save(self):
            return types.SimpleNamespace(id=1)

    class StubMonitorObjectModel:
        objects = types.SimpleNamespace(bulk_create=lambda objects: captured.setdefault("children", list(objects)))

    monkeypatch.setattr(module, "MonitorObjectSerializer", StubMonitorObjectSerializer)
    monkeypatch.setattr(module, "MonitorObject", StubMonitorObjectModel)

    module._create_monitor_object_payload(
        {
            "name": "host",
            "children": [{"id": "pod", "name": "Pod"}],
        }
    )

    assert captured["payload"]["instance_id_keys"] == ["instance_id"]
    assert captured["children"][0].instance_id_keys == ["instance_id", "pod"]
