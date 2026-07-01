import importlib.util
import sys
import types
from pathlib import Path

import pandas as pd
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


def test_format_dimension_value_with_display_name_and_empty_value():
    dimension_module = _load_module(
        "dimension_module",
        Path(__file__).resolve().parents[1] / "utils" / "dimension.py",
    )

    dimensions = {"instance_id": "i-1", "agent_id": ""}
    ordered_keys = ["instance_id", "agent_id"]
    name_map = {"instance_id": "实例ID", "agent_id": "节点"}

    result = dimension_module.format_dimension_value(
        dimensions,
        ordered_keys=ordered_keys,
        name_map=name_map,
    )

    assert result == "实例ID:i-1,节点:"


def test_calculate_alerts_should_render_resource_and_dimension_value():
    calculate_module = _load_module(
        "policy_calculate_module",
        Path(__file__).resolve().parents[1] / "tasks" / "utils" / "policy_calculate.py",
    )

    df = pd.DataFrame(
        [
            {
                "instance_id": ("i-1", "a-1"),
                "values": [[1700000000, "92"]],
            }
        ]
    )

    thresholds = [{"method": ">", "value": 80, "level": "warning"}]
    template_context = {
        "monitor_object": "主机",
        "metric_name": "CPU使用率",
        "instances_map": {"('i-1',)": "主机A"},
        "instance_id_keys": ["instance_id", "agent_id"],
        "dimension_name_map": {"instance_id": "实例ID", "agent_id": "节点"},
        "display_unit": "%",
        "enum_value_map": {},
    }

    alert_events, info_events = calculate_module.calculate_alerts(
        "${resource_name}|${dimension_value}|${instance_name}|${value}",
        df,
        thresholds,
        template_context,
    )

    assert len(alert_events) == 1
    assert len(info_events) == 0
    assert alert_events[0]["content"] == "主机A|节点:a-1|主机A - agent_id:a-1|92.00%"


def test_calculate_alerts_uses_highest_level_satisfied_by_all_recent_points():
    calculate_module = _load_module(
        "policy_calculate_highest_level_module",
        Path(__file__).resolve().parents[1] / "tasks" / "utils" / "policy_calculate.py",
    )

    df = pd.DataFrame(
        [
            {
                "instance_id": ("i-1",),
                "values": [[1700000000, "85"], [1700000300, "95"]],
            }
        ]
    )

    thresholds = [
        {"method": ">", "value": 70, "level": "warning"},
        {"method": ">", "value": 80, "level": "error"},
        {"method": ">", "value": 90, "level": "critical"},
    ]

    alert_events, info_events = calculate_module.calculate_alerts(
        "${level}:${value}",
        df,
        thresholds,
        {"instance_id_keys": ["instance_id"], "instances_map": {"i-1": "host-a"}},
        n=2,
    )

    assert len(info_events) == 0
    assert len(alert_events) == 1
    assert alert_events[0]["level"] == "error"
    assert alert_events[0]["content"] == "error:95.00"


def test_resolve_metric_instance_id_keys_inherits_monitor_object_keys():
    instance_id_keys_module = _load_module(
        "instance_id_keys_module",
        Path(__file__).resolve().parents[1] / "utils" / "instance_id_keys.py",
    )

    result = instance_id_keys_module.resolve_metric_instance_id_keys([], ["instance_id", "pod"])

    assert result == ["instance_id", "pod"]


def test_resolve_metric_instance_id_keys_raises_when_no_effective_keys():
    instance_id_keys_module = _load_module(
        "instance_id_keys_module_strict",
        Path(__file__).resolve().parents[1] / "utils" / "instance_id_keys.py",
    )

    with pytest.raises(Exception, match="instance_id_keys"):
        instance_id_keys_module.resolve_metric_instance_id_keys([], [], strict=True)


def test_resolve_monitor_object_instance_id_keys_defaults_for_derivative_object():
    instance_id_keys_module = _load_module(
        "instance_id_keys_module_derivative",
        Path(__file__).resolve().parents[1] / "utils" / "instance_id_keys.py",
    )

    result = instance_id_keys_module.resolve_monitor_object_instance_id_keys([], level="derivative", object_name="pod")

    assert result == ["instance_id", "pod"]


def test_monitor_object_serializer_create_generates_default_instance_id_keys(monkeypatch):
    class StubModelSerializer:
        def __init__(self, instance=None, source=None, read_only=False):
            self.instance = instance

        def validate(self, attrs):
            return attrs

        def create(self, validated_data):
            return validated_data

        def update(self, instance, validated_data):
            for key, value in validated_data.items():
                setattr(instance, key, value)
            return instance

    _install_module(
        monkeypatch,
        "rest_framework.serializers",
        ModelSerializer=StubModelSerializer,
    )
    _install_module(monkeypatch, "rest_framework", serializers=sys.modules["rest_framework.serializers"])
    _install_module(
        monkeypatch,
        "apps.monitor.models.monitor_object",
        MonitorObject=object,
        MonitorObjectOrganizationRule=object,
        MonitorObjectType=object,
    )

    serializer_module = _load_module(
        "monitor_object_serializer_create_module",
        Path(__file__).resolve().parents[1] / "serializers" / "monitor_object.py",
    )

    serializer = serializer_module.MonitorObjectSerializer()

    created = serializer.create(
        {
            "name": "host",
            "level": "base",
        }
    )

    assert created["instance_id_keys"] == ["instance_id"]


def test_monitor_object_serializer_create_generates_derivative_instance_id_keys(monkeypatch):
    class StubModelSerializer:
        def __init__(self, instance=None, source=None, read_only=False):
            self.instance = instance

        def validate(self, attrs):
            return attrs

        def create(self, validated_data):
            return validated_data

    _install_module(
        monkeypatch,
        "rest_framework.serializers",
        ModelSerializer=StubModelSerializer,
    )
    _install_module(monkeypatch, "rest_framework", serializers=sys.modules["rest_framework.serializers"])
    _install_module(
        monkeypatch,
        "apps.monitor.models.monitor_object",
        MonitorObject=object,
        MonitorObjectOrganizationRule=object,
        MonitorObjectType=object,
    )

    serializer_module = _load_module(
        "monitor_object_serializer_derivative_module",
        Path(__file__).resolve().parents[1] / "serializers" / "monitor_object.py",
    )

    serializer = serializer_module.MonitorObjectSerializer()

    created = serializer.create(
        {
            "name": "pod",
            "level": "derivative",
        }
    )

    assert created["instance_id_keys"] == ["instance_id", "pod"]


def test_metric_serializer_validate_inherits_monitor_object_instance_id_keys(monkeypatch):
    class StubModelSerializer:
        def __init__(self, instance=None):
            self.instance = instance

        def validate(self, attrs):
            return attrs

        def to_representation(self, instance):
            return {
                "instance_id_keys": getattr(instance, "instance_id_keys", []),
            }

        def create(self, validated_data):
            return validated_data

        def update(self, instance, validated_data):
            for key, value in validated_data.items():
                setattr(instance, key, value)
            return instance

    class StubValidationError(Exception):
        def __init__(self, detail):
            super().__init__(str(detail))
            self.detail = detail

    class _MetricQuerySet:
        def exclude(self, **kwargs):
            return self

        def exists(self):
            return False

    class _MetricManager:
        def filter(self, **kwargs):
            return _MetricQuerySet()

    class _Metric:
        objects = _MetricManager()

    _install_module(
        monkeypatch,
        "rest_framework.serializers",
        ModelSerializer=StubModelSerializer,
        BooleanField=lambda **kwargs: None,
        ValidationError=StubValidationError,
    )
    _install_module(monkeypatch, "rest_framework", serializers=sys.modules["rest_framework.serializers"])
    _install_module(monkeypatch, "apps.monitor.models.monitor_metrics", MetricGroup=object, Metric=_Metric)

    serializer_module = _load_module(
        "monitor_metric_serializer_module",
        Path(__file__).resolve().parents[1] / "serializers" / "monitor_metrics.py",
    )

    serializer = serializer_module.MetricSerializer()
    monitor_object = types.SimpleNamespace(instance_id_keys=["instance_id", "pod"])

    validated = serializer.validate(
        {
            "monitor_object": monitor_object,
            "monitor_plugin": None,
            "name": "cpu_usage",
            "instance_id_keys": [],
        }
    )

    assert validated["instance_id_keys"] == ["instance_id", "pod"]


def test_metric_serializer_create_persists_monitor_object_instance_id_keys_when_omitted(monkeypatch):
    class StubModelSerializer:
        def __init__(self, instance=None):
            self.instance = instance

        def validate(self, attrs):
            return attrs

        def create(self, validated_data):
            return validated_data

    class StubValidationError(Exception):
        def __init__(self, detail):
            super().__init__(str(detail))
            self.detail = detail

    class _MetricQuerySet:
        def exclude(self, **kwargs):
            return self

        def exists(self):
            return False

    class _MetricManager:
        def filter(self, **kwargs):
            return _MetricQuerySet()

    class _Metric:
        objects = _MetricManager()

    _install_module(
        monkeypatch,
        "rest_framework.serializers",
        ModelSerializer=StubModelSerializer,
        BooleanField=lambda **kwargs: None,
        ValidationError=StubValidationError,
    )
    _install_module(monkeypatch, "rest_framework", serializers=sys.modules["rest_framework.serializers"])
    _install_module(monkeypatch, "apps.monitor.models.monitor_metrics", MetricGroup=object, Metric=_Metric)

    serializer_module = _load_module(
        "monitor_metric_serializer_create_module",
        Path(__file__).resolve().parents[1] / "serializers" / "monitor_metrics.py",
    )

    serializer = serializer_module.MetricSerializer()
    monitor_object = types.SimpleNamespace(instance_id_keys=["instance_id", "pod"])

    created = serializer.create(
        {
            "monitor_object": monitor_object,
            "monitor_plugin": None,
            "name": "cpu_usage",
        }
    )

    assert created["instance_id_keys"] == ["instance_id", "pod"]


def test_metric_serializer_update_preserves_existing_instance_id_keys_when_omitted(monkeypatch):
    class StubModelSerializer:
        def __init__(self, instance=None):
            self.instance = instance

        def validate(self, attrs):
            return attrs

        def update(self, instance, validated_data):
            for key, value in validated_data.items():
                setattr(instance, key, value)
            return instance

    class StubValidationError(Exception):
        def __init__(self, detail):
            super().__init__(str(detail))
            self.detail = detail

    class _MetricQuerySet:
        def exclude(self, **kwargs):
            return self

        def exists(self):
            return False

    class _MetricManager:
        def filter(self, **kwargs):
            return _MetricQuerySet()

    class _Metric:
        objects = _MetricManager()

    _install_module(
        monkeypatch,
        "rest_framework.serializers",
        ModelSerializer=StubModelSerializer,
        BooleanField=lambda **kwargs: None,
        ValidationError=StubValidationError,
    )
    _install_module(monkeypatch, "rest_framework", serializers=sys.modules["rest_framework.serializers"])
    _install_module(monkeypatch, "apps.monitor.models.monitor_metrics", MetricGroup=object, Metric=_Metric)

    serializer_module = _load_module(
        "monitor_metric_serializer_update_module",
        Path(__file__).resolve().parents[1] / "serializers" / "monitor_metrics.py",
    )

    instance = types.SimpleNamespace(
        instance_id_keys=["instance_id", "legacy_key"],
        monitor_object=types.SimpleNamespace(instance_id_keys=["instance_id", "pod"]),
    )
    serializer = serializer_module.MetricSerializer(instance=instance)

    updated = serializer.update(instance, {"display_name": "CPU"})

    assert updated.instance_id_keys == ["instance_id", "legacy_key"]


def test_metrics_service_effective_instance_keys_fallbacks_to_monitor_object(monkeypatch):
    class StubBaseAppException(Exception):
        pass

    class StubLogger:
        def __init__(self):
            self.warning_calls = []

        def warning(self, *args, **kwargs):
            self.warning_calls.append((args, kwargs))

    logger = StubLogger()

    _install_module(monkeypatch, "apps.core.exceptions.base_app_exception", BaseAppException=StubBaseAppException)
    _install_module(monkeypatch, "apps.core.logger", monitor_logger=logger)
    _install_module(monkeypatch, "apps.monitor.models.monitor_metrics", Metric=object)
    _install_module(
        monkeypatch,
        "apps.monitor.models.monitor_object",
        MonitorObject=types.SimpleNamespace(objects=types.SimpleNamespace(filter=lambda **kwargs: None)),
    )
    _install_module(monkeypatch, "apps.monitor.utils.dimension", parse_instance_id=lambda value: (value,))
    _install_module(monkeypatch, "apps.monitor.utils.unit_converter", UnitConverter=object)
    _install_module(monkeypatch, "apps.monitor.utils.victoriametrics_api", VictoriaMetricsAPI=object)

    metrics_module = _load_module(
        "metrics_service_module",
        Path(__file__).resolve().parents[1] / "services" / "metrics.py",
    )

    metric = types.SimpleNamespace(
        id=11,
        monitor_object_id=7,
        instance_id_keys=[],
        monitor_object=types.SimpleNamespace(instance_id_keys=["instance_id", "pod"]),
    )

    keys = metrics_module.Metrics.get_effective_metric_instance_id_keys(metric)

    assert keys == ["instance_id", "pod"]
    assert len(logger.warning_calls) == 1


def test_backfill_metric_instance_id_keys_updates_metrics_from_monitor_object(monkeypatch):
    class _Atomic:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _Style:
        def SUCCESS(self, message):
            return message

        def WARNING(self, message):
            return message

    class _Stdout:
        def __init__(self):
            self.messages = []

        def write(self, message):
            self.messages.append(message)

    class StubBaseCommand:
        def __init__(self):
            self.stdout = _Stdout()
            self.style = _Style()

    class _QuerySet(list):
        def order_by(self, *args, **kwargs):
            return self

    object_bulk_updates = []
    metric_bulk_updates = []

    monitor_object = types.SimpleNamespace(
        id=7,
        name="pod",
        level="base",
        instance_id_keys=["instance_id", "pod"],
    )
    metric = types.SimpleNamespace(
        id=11,
        monitor_object_id=7,
        monitor_object=monitor_object,
        instance_id_keys=[],
    )

    class _MonitorObjectManager:
        def all(self):
            return _QuerySet([monitor_object])

        def bulk_update(self, objects, fields):
            object_bulk_updates.append((list(objects), list(fields)))

    class _MetricManager:
        def select_related(self, *args, **kwargs):
            return self

        def all(self):
            return _QuerySet([metric])

        def bulk_update(self, objects, fields):
            metric_bulk_updates.append((list(objects), list(fields)))

    _install_module(monkeypatch, "django.core.management", BaseCommand=StubBaseCommand)
    _install_module(monkeypatch, "django.db", transaction=types.SimpleNamespace(atomic=lambda: _Atomic()))
    _install_module(
        monkeypatch,
        "apps.monitor.models",
        Metric=types.SimpleNamespace(objects=_MetricManager()),
        MonitorObject=types.SimpleNamespace(objects=_MonitorObjectManager()),
    )

    command_module = _load_module(
        "backfill_metric_instance_id_keys_command_module",
        Path(__file__).resolve().parents[1] / "management" / "commands" / "backfill_metric_instance_id_keys.py",
    )

    command = command_module.Command()
    command.handle(dry_run=False)

    assert metric.instance_id_keys == ["instance_id", "pod"]
    assert object_bulk_updates == []
    assert len(metric_bulk_updates) == 1
    assert metric_bulk_updates[0][1] == ["instance_id_keys"]
    assert "metric updated=1" in command.stdout.messages[0]
