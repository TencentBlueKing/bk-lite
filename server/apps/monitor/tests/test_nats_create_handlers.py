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


def _load_monitor_nats_module(monkeypatch, module_name):
    _install_monitor_nats_dependencies(monkeypatch)
    return _load_module(
        module_name,
        Path(__file__).resolve().parents[1] / "nats" / "monitor.py",
    )


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
        MonitorPolicy=_StubModel,
        MonitorEvent=_StubModel,
        MonitorAlertMetricSnapshot=_StubModel,
        PolicyInstanceBaseline=_StubModel,
        CollectConfig=_StubModel,
        MonitorInstanceOrganization=_StubModel,
        PolicyOrganization=_StubModel,
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
    module = _load_monitor_nats_module(monkeypatch, "monitor_nats_create_handlers_test_module")

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
    module = _load_monitor_nats_module(monkeypatch, "monitor_nats_create_handlers_string_user_test_module")

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


def test_create_monitor_policy_maps_api_create_side_effects(monkeypatch):
    module = _load_monitor_nats_module(monkeypatch, "monitor_nats_create_monitor_policy_test_module")

    captured = {"view_calls": []}

    class StubMonitorPolicySerializer:
        def __init__(self, instance=None, data=None):
            self.instance = instance
            self.input_data = data
            if data is not None:
                captured["payload"] = data
                self.data = {"id": 42, "name": data["name"]}
            else:
                self.data = {"id": instance.id, "name": instance.name}

        def is_valid(self, raise_exception=False):
            captured["raise_exception"] = raise_exception
            return True

        def save(self):
            return types.SimpleNamespace(
                id=42,
                name=self.input_data["name"],
                enable_alerts=["no_data"],
            )

    class StubMonitorPolicyViewSet:
        def update_or_create_task(self, policy_id, schedule):
            captured["view_calls"].append(("task", policy_id, schedule))

        def update_policy_organizations(self, policy_id, organizations):
            captured["view_calls"].append(("organizations", policy_id, organizations))

        def is_no_data_alert_enabled(self, policy):
            return "no_data" in policy.enable_alerts

        def update_policy_baselines(self, policy_id, enable_alerts):
            captured["view_calls"].append(("baselines", policy_id, enable_alerts))

    monkeypatch.setattr(module, "MonitorPolicySerializer", StubMonitorPolicySerializer)
    monkeypatch.setattr(module, "_get_monitor_policy_viewset", StubMonitorPolicyViewSet)

    result = module.create_monitor_policy(
        {
            "name": "cpu policy",
            "schedule": "*/5 * * * *",
            "organizations": [1, 2],
        },
        user_info={"user": "alice", "domain": "tenant-a.com"},
    )

    assert result == {"result": True, "data": {"id": 42, "name": "cpu policy"}, "message": ""}
    assert captured["payload"]["created_by"] == "alice"
    assert captured["payload"]["updated_by"] == "alice"
    assert captured["payload"]["domain"] == "tenant-a.com"
    assert captured["payload"]["updated_by_domain"] == "tenant-a.com"
    assert captured["view_calls"] == [
        ("task", 42, "*/5 * * * *"),
        ("organizations", 42, [1, 2]),
        ("baselines", 42, ["no_data"]),
    ]


def test_create_monitor_policy_requires_schedule(monkeypatch):
    module = _load_monitor_nats_module(monkeypatch, "monitor_nats_create_monitor_policy_schedule_test_module")

    result = module.create_monitor_policy({"name": "cpu policy"}, user_info={"user": "alice"})

    assert result == {"result": False, "data": [], "message": "schedule 不能为空"}


def test_create_monitor_object_payload_generates_derivative_instance_id_keys(monkeypatch):
    module = _load_monitor_nats_module(monkeypatch, "monitor_nats_create_monitor_object_payload_test_module")

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

        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

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


def test_mm_query_range_returns_formatted_values_when_victoriametrics_succeeds(monkeypatch):
    module = _load_monitor_nats_module(monkeypatch, "monitor_nats_mm_query_range_success_test_module")

    class StubVictoriaMetricsAPI:
        def query_range(self, query, start, end, step):
            assert (query, start, end, step) == ("up", 1, 2, "1m")
            return {
                "status": "success",
                "data": {
                    "result": [
                        {
                            "values": [[1, "2"], [2, "3"]],
                        }
                    ]
                },
            }

    monkeypatch.setattr(module, "VictoriaMetricsAPI", StubVictoriaMetricsAPI)

    result = module.mm_query_range("up", [1, 2], step="1m")

    assert result == {
        "result": True,
        "data": [{"name": 1, "value": "2"}, {"name": 2, "value": "3"}],
        "message": "",
    }


def test_mm_query_range_keeps_empty_result_as_success(monkeypatch):
    module = _load_monitor_nats_module(monkeypatch, "monitor_nats_mm_query_range_empty_test_module")

    class StubVictoriaMetricsAPI:
        def query_range(self, query, start, end, step):
            return {"status": "success", "data": {"result": []}}

    monkeypatch.setattr(module, "VictoriaMetricsAPI", StubVictoriaMetricsAPI)

    result = module.mm_query_range("up", [1, 2])

    assert result == {"result": True, "data": [], "message": ""}


def test_mm_query_range_returns_failure_when_victoriametrics_reports_error(monkeypatch):
    module = _load_monitor_nats_module(monkeypatch, "monitor_nats_mm_query_range_failure_test_module")

    class StubVictoriaMetricsAPI:
        def query_range(self, query, start, end, step):
            return {
                "status": "error",
                "errorType": "bad_data",
                "error": "parse error",
            }

    monkeypatch.setattr(module, "VictoriaMetricsAPI", StubVictoriaMetricsAPI)

    result = module.mm_query_range("bad_query", [1, 2])

    assert result == {"result": False, "data": [], "message": "bad_data: parse error"}


def test_mm_query_returns_formatted_single_value_when_victoriametrics_succeeds(monkeypatch):
    module = _load_monitor_nats_module(monkeypatch, "monitor_nats_mm_query_success_test_module")

    class StubVictoriaMetricsAPI:
        def query(self, query, step):
            assert (query, step) == ("up", "30s")
            return {
                "status": "success",
                "data": {
                    "result": [
                        {
                            "value": [123, "9"],
                        }
                    ]
                },
            }

    monkeypatch.setattr(module, "VictoriaMetricsAPI", StubVictoriaMetricsAPI)

    result = module.mm_query("up", step="30s")

    assert result == {
        "result": True,
        "data": [{"name": 123, "value": "9"}],
        "message": "",
    }


def test_mm_query_returns_failure_when_victoriametrics_reports_error_without_details(monkeypatch):
    module = _load_monitor_nats_module(monkeypatch, "monitor_nats_mm_query_failure_test_module")

    class StubVictoriaMetricsAPI:
        def query(self, query, step):
            return {"status": "error"}

    monkeypatch.setattr(module, "VictoriaMetricsAPI", StubVictoriaMetricsAPI)

    result = module.mm_query("up")

    assert result == {"result": False, "data": [], "message": "查询单个指标数据失败"}
