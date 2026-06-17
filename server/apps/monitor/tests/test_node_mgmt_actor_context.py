import importlib.util
import sys
import types
from contextlib import nullcontext
from pathlib import Path

import pytest


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


def _load_node_mgmt_view(monkeypatch):
    class ViewSet:
        pass

    def action(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

    _install_module(monkeypatch, "rest_framework.viewsets", ViewSet=ViewSet)
    _install_module(monkeypatch, "rest_framework.decorators", action=action)
    _install_module(
        monkeypatch,
        "apps.core.exceptions.base_app_exception",
        BaseAppException=Exception,
        ValidationAppException=Exception,
        UnauthorizedException=Exception,
    )
    _install_module(monkeypatch, "apps.core.utils.web_utils", WebUtils=types.SimpleNamespace(response_success=lambda data=None: data))
    _install_module(
        monkeypatch,
        "apps.core.utils.user_group",
        normalize_user_group_ids=lambda groups: [
            int(group.get("id") if isinstance(group, dict) else group)
            for group in groups
            if (group.get("id") if isinstance(group, dict) else group) is not None
        ],
    )
    _install_module(monkeypatch, "apps.monitor.services.node_mgmt", InstanceConfigService=object)
    _install_module(monkeypatch, "apps.rpc.node_mgmt", NodeMgmt=object)
    _install_module(monkeypatch, "apps.core.logger", monitor_logger=types.SimpleNamespace(debug=lambda *args, **kwargs: None))
    _install_module(monkeypatch, "apps.monitor.utils.pagination", parse_page_params=lambda *args, **kwargs: (1, 10))

    return _load_module(
        "monitor_node_mgmt_view_test_module",
        Path(__file__).resolve().parents[1] / "views" / "node_mgmt.py",
    )


def test_build_actor_context_accepts_api_secret_integer_group_list(monkeypatch):
    module = _load_node_mgmt_view(monkeypatch)
    request = types.SimpleNamespace(
        COOKIES={"current_team": "7", "include_children": "1"},
        user=types.SimpleNamespace(
            username="api-user",
            domain="domain.com",
            is_superuser=False,
            group_list=[7],
        ),
    )

    assert module._build_actor_context(request)["group_list"] == [7]


def test_build_actor_context_keeps_token_group_dicts(monkeypatch):
    module = _load_node_mgmt_view(monkeypatch)
    request = types.SimpleNamespace(
        COOKIES={"current_team": "8"},
        user=types.SimpleNamespace(
            username="token-user",
            domain="domain.com",
            is_superuser=False,
            group_list=[{"id": "8", "name": "team-a"}],
        ),
    )

    assert module._build_actor_context(request)["group_list"] == [8]


def test_get_nodes_accepts_api_secret_integer_group_list(monkeypatch):
    captured = {}

    class NodeMgmt:
        def node_list(self, payload):
            captured["payload"] = payload
            return payload

    module = _load_node_mgmt_view(monkeypatch)
    module.NodeMgmt = NodeMgmt

    request = types.SimpleNamespace(
        COOKIES={"current_team": "7"},
        data={},
        user=types.SimpleNamespace(
            username="api-user",
            domain="domain.com",
            is_superuser=False,
            group_list=[7],
        ),
    )

    module.NodeMgmtView().get_nodes(request)

    assert captured["payload"]["organization_ids"] == [7]
    assert captured["payload"]["permission_data"]["current_team"] == 7


def test_get_nodes_keeps_opspilot_guest_group_ids(monkeypatch):
    captured = {}

    class NodeMgmt:
        def node_list(self, payload):
            captured["payload"] = payload
            return payload

    module = _load_node_mgmt_view(monkeypatch)
    module.NodeMgmt = NodeMgmt

    request = types.SimpleNamespace(
        COOKIES={"current_team": "8"},
        data={},
        user=types.SimpleNamespace(
            username="token-user",
            domain="domain.com",
            is_superuser=False,
            group_list=[
                {"id": "8", "name": "team-a"},
                {"id": "10", "name": "OpsPilotGuest"},
            ],
        ),
    )

    module.NodeMgmtView().get_nodes(request)

    assert set(captured["payload"]["organization_ids"]) == {8, 10}


def test_get_nodes_applies_plugin_node_selector(monkeypatch):
    captured = {}

    class NodeMgmt:
        def node_list(self, payload):
            captured["payload"] = payload
            return payload

    class InstanceConfigService:
        @staticmethod
        def _get_plugin_node_selector(plugin_id):
            assert plugin_id == 12
            return {"is_container": True}

    module = _load_node_mgmt_view(monkeypatch)
    module.NodeMgmt = NodeMgmt
    module.InstanceConfigService = InstanceConfigService

    request = types.SimpleNamespace(
        COOKIES={"current_team": "7"},
        data={"monitor_plugin_id": 12},
        user=types.SimpleNamespace(
            username="api-user",
            domain="domain.com",
            is_superuser=False,
            group_list=[7],
        ),
    )

    module.NodeMgmtView().get_nodes(request)

    assert captured["payload"]["is_container"] is True


def test_get_instance_child_config_passes_monitor_plugin_id(monkeypatch):
    captured = {}

    class InstanceConfigService:
        @staticmethod
        def get_instance_configs(instance_id, actor_context=None, monitor_plugin_id=None, collector=None, collect_type=None):
            captured["instance_id"] = instance_id
            captured["actor_context"] = actor_context
            captured["monitor_plugin_id"] = monitor_plugin_id
            captured["collector"] = collector
            captured["collect_type"] = collect_type
            return []

    module = _load_node_mgmt_view(monkeypatch)
    module.InstanceConfigService = InstanceConfigService

    request = types.SimpleNamespace(
        COOKIES={"current_team": "7"},
        data={"instance_id": "inst-a", "monitor_plugin_id": 18},
        user=types.SimpleNamespace(
            username="api-user",
            domain="domain.com",
            is_superuser=False,
            group_list=[7],
        ),
    )

    module.NodeMgmtView().get_instance_child_config(request)

    assert captured["instance_id"] == "inst-a"
    assert captured["monitor_plugin_id"] == 18
    assert captured["collector"] is None
    assert captured["collect_type"] is None
    assert captured["actor_context"]["current_team"] == 7


def test_get_instance_configs_filters_by_monitor_plugin_id(monkeypatch):
    from apps.monitor.services import node_mgmt as module

    class StubConfig:
        def __init__(self, config_id, collect_type, config_type, monitor_plugin_id):
            self.id = config_id
            self.collector = "Telegraf"
            self.collect_type = collect_type
            self.config_type = config_type
            self.monitor_plugin_id = monitor_plugin_id
            self.monitor_instance_id = "inst-a"
            self.is_child = True

    class StubCollectConfigManager:
        def __init__(self, rows):
            self.rows = rows

        def filter(self, **kwargs):
            result = [row for row in self.rows if row.monitor_instance_id == kwargs["monitor_instance_id"]]
            monitor_plugin_id = kwargs.get("monitor_plugin_id")
            if monitor_plugin_id is not None:
                result = [row for row in result if row.monitor_plugin_id == monitor_plugin_id]
            return result

    monkeypatch.setattr(
        module.InstanceConfigService,
        "_ensure_instance_access",
        classmethod(lambda cls, collect_instance_id, actor_context=None, require_operate=False: None),
    )
    monkeypatch.setattr(
        module.CollectConfig,
        "objects",
        StubCollectConfigManager(
            [
                StubConfig("cfg-http", "http", "host", 208),
                StubConfig("cfg-cpu", "host", "cpu", 18),
                StubConfig("cfg-disk", "host", "disk", 18),
            ]
        ),
    )
    monkeypatch.setattr(
        module.InstanceConfigService,
        "get_config_content",
        staticmethod(lambda ids, actor_context=None: {"child": {"id": ids[0]}}),
    )

    items = module.InstanceConfigService.get_instance_configs("inst-a", monitor_plugin_id=18)

    assert [item["monitor_plugin_id"] for item in items] == [18, 18]
    assert [item["collect_type"] for item in items] == ["host", "host"]


def test_prepare_instances_reuses_flow_created_instance_for_new_snmp_config(monkeypatch):
    from apps.monitor.services import node_mgmt as module

    class StubMonitorInstanceQuerySet:
        def values_list(self, *fields):
            return [("('1:switch:10.0.0.12',)", False)]

    class StubMonitorInstanceManager:
        @staticmethod
        def filter(**kwargs):
            assert kwargs == {
                "id__in": ["('1:switch:10.0.0.12',)"],
                "monitor_object_id": 12,
            }
            return StubMonitorInstanceQuerySet()

    class StubCollectConfigQuerySet:
        def values_list(self, *fields):
            return []

    class StubCollectConfigManager:
        @staticmethod
        def filter(**kwargs):
            assert kwargs == {
                "monitor_instance_id__in": ["('1:switch:10.0.0.12',)"],
                "collector": "Telegraf",
                "collect_type": "snmp",
                "config_type__in": {"switch"},
            }
            return StubCollectConfigQuerySet()

    monkeypatch.setattr(module.MonitorInstance, "objects", StubMonitorInstanceManager())
    monkeypatch.setattr(module.CollectConfig, "objects", StubCollectConfigManager())

    new_instances, existing_instances, deleted_ids = module.InstanceConfigService._prepare_instances_for_creation(
        [
            {
                "instance_id": "1:switch:10.0.0.12",
                "instance_name": "Core Switch",
                "group_ids": [7],
            }
        ],
        monitor_object_id=12,
        collect_type="snmp",
        collector="Telegraf",
        configs=[{"type": "switch"}],
    )

    assert new_instances == []
    assert existing_instances == [
        {
            "instance_id": "('1:switch:10.0.0.12',)",
            "instance_name": "Core Switch",
            "group_ids": [7],
        }
    ]
    assert deleted_ids == []


def test_prepare_instances_rejects_same_instance_same_snmp_config(monkeypatch):
    from apps.monitor.services import node_mgmt as module

    class StubMonitorInstanceQuerySet:
        def values_list(self, *fields):
            return [("('1:switch:10.0.0.12',)", False)]

    class StubMonitorInstanceManager:
        @staticmethod
        def filter(**kwargs):
            return StubMonitorInstanceQuerySet()

    class StubCollectConfigQuerySet:
        def values_list(self, *fields):
            return [("('1:switch:10.0.0.12',)", "switch")]

    class StubCollectConfigManager:
        @staticmethod
        def filter(**kwargs):
            return StubCollectConfigQuerySet()

    monkeypatch.setattr(module.MonitorInstance, "objects", StubMonitorInstanceManager())
    monkeypatch.setattr(module.CollectConfig, "objects", StubCollectConfigManager())

    with pytest.raises(module.BaseAppException, match="已存在采集配置"):
        module.InstanceConfigService._prepare_instances_for_creation(
            [
                {
                    "instance_id": "1:switch:10.0.0.12",
                    "instance_name": "Core Switch",
                    "group_ids": [7],
                }
            ],
            monitor_object_id=12,
            collect_type="snmp",
            collector="Telegraf",
            configs=[{"type": "switch"}],
        )


def test_create_monitor_instance_reuses_flow_instance_and_creates_new_snmp_config(monkeypatch):
    from apps.monitor.services import node_mgmt as module

    captured = {}
    logical_id = "MToxMC4wLjAuMTI"
    storage_id = str((logical_id,))
    requested_instance = {
        "instance_id": "1:switch:10.0.0.12",
        "instance_name": "Core Switch",
        "node_ids": ["node-1"],
        "group_ids": [7],
    }
    prepared_instance = {
        **requested_instance,
        "raw_instance_id": "1:switch:10.0.0.12",
        "logical_instance_value": logical_id,
        "storage_instance_key": storage_id,
        "instance_id": storage_id,
    }

    class _MonitorObjectQuerySet:
        @staticmethod
        def only(*args, **kwargs):
            return _MonitorObjectQuerySet()

        @staticmethod
        def first():
            return types.SimpleNamespace(name="Switch")

    class _MonitorObjectManager:
        @staticmethod
        def filter(**kwargs):
            assert kwargs == {"id": 12}
            return _MonitorObjectQuerySet()

    class _Controller:
        def __init__(self, data):
            captured["data"] = data

        def controller(self):
            captured["called"] = True

    def prepare_instances(instances, monitor_object_id, collect_type, collector, configs):
        assert instances == [prepared_instance]
        assert monitor_object_id == 12
        assert collect_type == "snmp"
        assert collector == "Telegraf"
        assert configs == [{"type": "switch"}]
        return [], [prepared_instance], []

    def create_instances(new_instances, existing_instances, deleted_ids, monitor_object_id):
        captured["db_args"] = {
            "new_instances": new_instances,
            "existing_instances": existing_instances,
            "deleted_ids": deleted_ids,
            "monitor_object_id": monitor_object_id,
        }
        return [], []

    monkeypatch.setattr(module.MonitorObject, "objects", _MonitorObjectManager())
    monkeypatch.setattr(module, "Controller", _Controller)
    monkeypatch.setattr(module.transaction, "atomic", lambda: nullcontext())
    monkeypatch.setattr(
        module.InstanceConfigService,
        "_sanitize_instances_for_onboarding",
        staticmethod(lambda instances, actor_context: instances),
    )
    monkeypatch.setattr(
        module.InstanceConfigService,
        "_validate_instances_with_plugin_selector",
        staticmethod(lambda instances, monitor_plugin_id, actor_context: None),
    )
    monkeypatch.setattr(
        module.InstanceConfigService,
        "_prepare_instances_for_creation",
        staticmethod(prepare_instances),
    )
    monkeypatch.setattr(
        module.InstanceConfigService,
        "_create_instances_in_db",
        staticmethod(create_instances),
    )
    monkeypatch.setattr(
        module.InstanceConfigService,
        "_validate_expected_collect_configs",
        staticmethod(lambda instances, configs, monitor_plugin_id, collect_type: None),
    )

    module.InstanceConfigService.create_monitor_instance_by_node_mgmt(
        {
            "collector": "Telegraf",
            "collect_type": "snmp",
            "monitor_object_id": 12,
            "monitor_plugin_id": 301,
            "configs": [{"type": "switch"}],
            "instances": [requested_instance],
        }
    )

    assert captured["called"] is True
    assert captured["db_args"] == {
        "new_instances": [],
        "existing_instances": [prepared_instance],
        "deleted_ids": [],
        "monitor_object_id": 12,
    }
    assert captured["data"]["instances"] == [prepared_instance]
    assert captured["data"]["monitor_plugin_id"] == 301


def test_prepare_network_device_identity_instances_uses_cloud_region_ip_safe_id():
    from apps.monitor.services import node_mgmt as module

    explicit = module.InstanceConfigService._prepare_network_device_identity_instances(
        [
            {
                "instance_id": "1_switch_snmp_10.0.0.12",
                "cloud_region": 1,
                "ip": "10.0.0.12",
                "instance_name": "Core Switch",
            }
        ]
    )[0]
    parsed = module.InstanceConfigService._prepare_network_device_identity_instances(
        [
            {
                "instance_id": "1_switch_snmp_10.0.0.12",
                "instance_name": "Core Switch",
            }
        ]
    )[0]

    assert explicit["logical_instance_value"] == "MToxMC4wLjAuMTI"
    assert explicit["storage_instance_key"] == "('MToxMC4wLjAuMTI',)"
    assert explicit["instance_id"] == "('MToxMC4wLjAuMTI',)"
    assert explicit["raw_instance_id"] == "1_switch_snmp_10.0.0.12"
    assert parsed["instance_id"] == explicit["instance_id"]


def test_create_monitor_instance_does_not_replace_selected_host_remote_node_id(monkeypatch):
    from apps.monitor.services import node_mgmt as module

    captured = {}

    class _MonitorObjectQuerySet:
        @staticmethod
        def only(*args, **kwargs):
            return _MonitorObjectQuerySet()

        @staticmethod
        def first():
            return types.SimpleNamespace(name="Host")

    class _MonitorObjectManager:
        @staticmethod
        def filter(**kwargs):
            return _MonitorObjectQuerySet()

    class _NodeMgmt:
        @staticmethod
        def get_nodes_by_ids(node_ids):
            raise AssertionError("Host Remote should use the selected node_id directly")

    class _Controller:
        def __init__(self, data):
            captured["data"] = data

        def controller(self):
            captured["called"] = True

    monkeypatch.setattr(module.MonitorObject, "objects", _MonitorObjectManager())
    monkeypatch.setattr(module, "NodeMgmt", _NodeMgmt)
    monkeypatch.setattr(module, "Controller", _Controller)
    monkeypatch.setattr(module.transaction, "atomic", lambda: nullcontext())
    monkeypatch.setattr(
        module.InstanceConfigService,
        "_sanitize_instances_for_onboarding",
        staticmethod(lambda instances, actor_context: instances),
    )
    monkeypatch.setattr(
        module.InstanceConfigService,
        "_validate_instances_with_plugin_selector",
        staticmethod(lambda instances, monitor_plugin_id, actor_context: None),
    )
    monkeypatch.setattr(
        module.InstanceConfigService,
        "_prepare_host_identity_instances",
        staticmethod(lambda instances: instances),
    )
    monkeypatch.setattr(
        module.InstanceConfigService,
        "_prepare_instances_for_creation",
        staticmethod(lambda instances, monitor_object_id, collect_type, collector, configs: (instances, [], [])),
    )
    monkeypatch.setattr(
        module.InstanceConfigService,
        "_create_instances_in_db",
        staticmethod(lambda new_instances, existing_instances, deleted_ids, monitor_object_id: (["inst-a"], [])),
    )
    monkeypatch.setattr(
        module.InstanceConfigService,
        "_validate_expected_collect_configs",
        staticmethod(lambda instances, configs, monitor_plugin_id, collect_type: None),
    )

    module.InstanceConfigService.create_monitor_instance_by_node_mgmt(
        {
            "collector": "Telegraf",
            "collect_type": "http",
            "monitor_object_id": 20,
            "monitor_plugin_id": 208,
            "configs": [{"type": "host"}],
            "instances": [
                {
                    "instance_id": "('inst-a',)",
                    "instance_name": "remote-host",
                    "node_ids": ["node-1"],
                    "type": "host",
                }
            ],
        }
    )

    assert captured["called"] is True
    assert "ansible_node_id" not in captured["data"]["instances"][0]


class _MonitorInstanceQuerySet:
    def __init__(self, rows):
        self.rows = rows

    def values(self, *fields):
        return _ValuesResult([{field: row[field] for field in fields} for row in self.rows])


class _ValuesResult(list):
    def first(self):
        return self[0] if self else None


class _AuthorizedInstanceQuerySet:
    def __init__(self, ids):
        self.ids = [str(instance_id) for instance_id in ids]

    def filter(self, **kwargs):
        requested = {str(item) for item in kwargs.get("id__in", [])}
        return _AuthorizedInstanceQuerySet([instance_id for instance_id in self.ids if instance_id in requested])

    def values_list(self, field, flat=False):
        return list(self.ids)


class _MonitorInstanceOrganizationQuerySet:
    def __init__(self, rows):
        self.rows = rows

    def values_list(self, *fields):
        return [tuple(row[field] for field in fields) for row in self.rows]


class _MonitorInstance:
    rows = []

    class objects:
        @staticmethod
        def filter(**kwargs):
            rows = list(_MonitorInstance.rows)
            if "id__in" in kwargs:
                requested = {str(item) for item in kwargs["id__in"]}
                rows = [row for row in rows if str(row["id"]) in requested]
            return _MonitorInstanceQuerySet(rows)


class _MonitorInstanceOrganization:
    rows = []

    class objects:
        @staticmethod
        def filter(**kwargs):
            rows = list(_MonitorInstanceOrganization.rows)
            if "monitor_instance_id__in" in kwargs:
                requested = {str(item) for item in kwargs["monitor_instance_id__in"]}
                rows = [row for row in rows if str(row["monitor_instance_id"]) in requested]
            return _MonitorInstanceOrganizationQuerySet(rows)


class _MonitorObjectOrganizationRuleQuerySet:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return _MonitorObjectOrganizationRuleQuerySet(list(self.rows))

    def select_related(self, *args):
        return self

    def filter(self, **kwargs):
        rows = list(self.rows)
        if "id__in" in kwargs:
            requested = {int(item) for item in kwargs["id__in"]}
            rows = [row for row in rows if int(row.id) in requested]
        if "id" in kwargs:
            rows = [row for row in rows if int(row.id) == int(kwargs["id"])]
        return _MonitorObjectOrganizationRuleQuerySet(rows)

    def none(self):
        return _MonitorObjectOrganizationRuleQuerySet([])

    def first(self):
        return self.rows[0] if self.rows else None

    def __iter__(self):
        return iter(self.rows)


class _MonitorObjectOrganizationRule:
    rows = []

    class objects:
        @staticmethod
        def all():
            return _MonitorObjectOrganizationRuleQuerySet(list(_MonitorObjectOrganizationRule.rows))

        @staticmethod
        def filter(**kwargs):
            return _MonitorObjectOrganizationRule.objects.all().filter(**kwargs)


def _load_monitor_instance_view(monkeypatch, authorized_ids=None, scope_groups=None):
    class ViewSet:
        pass

    def action(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

    class UnauthorizedException(Exception):
        pass

    class InstanceConfigService:
        @staticmethod
        def _get_actor_scope_groups(actor_context):
            return scope_groups if scope_groups is not None else [actor_context["current_team"]]

        @staticmethod
        def _get_authorized_monitor_instances(actor_context, monitor_object_id, require_operate=False):
            return _AuthorizedInstanceQuerySet(authorized_ids or [])

    _install_module(monkeypatch, "rest_framework.viewsets", ViewSet=ViewSet)
    _install_module(monkeypatch, "rest_framework.decorators", action=action)
    _install_module(
        monkeypatch,
        "apps.core.exceptions.base_app_exception",
        BaseAppException=Exception,
        ValidationAppException=Exception,
        UnauthorizedException=UnauthorizedException,
    )
    _install_module(
        monkeypatch,
        "apps.core.logger",
        monitor_logger=types.SimpleNamespace(debug=lambda *args, **kwargs: None),
    )
    _install_module(
        monkeypatch,
        "apps.core.utils.user_group",
        normalize_user_group_ids=lambda groups: [
            int(group.get("id") if isinstance(group, dict) else group)
            for group in groups
            if (group.get("id") if isinstance(group, dict) else group) is not None
        ],
    )
    _install_module(
        monkeypatch,
        "apps.core.utils.permission_utils",
        get_permission_rules=lambda *args, **kwargs: {},
        permission_filter=lambda *args, **kwargs: None,
    )
    _install_module(
        monkeypatch,
        "apps.core.utils.web_utils",
        WebUtils=types.SimpleNamespace(response_success=lambda data=None: data),
    )
    _install_module(
        monkeypatch,
        "apps.monitor.constants.permission",
        PermissionConstants=types.SimpleNamespace(INSTANCE_MODULE="instance", DEFAULT_PERMISSION=["View", "Operate"]),
    )
    _install_module(
        monkeypatch,
        "apps.monitor.models",
        MonitorInstance=_MonitorInstance,
        MonitorInstanceOrganization=_MonitorInstanceOrganization,
        MonitorObject=object,
        CollectConfig=object,
        MonitorObjectOrganizationRule=object,
    )
    _install_module(monkeypatch, "apps.monitor.services.monitor_instance", InstanceSearch=object)
    _install_module(
        monkeypatch,
        "apps.monitor.services.node_mgmt",
        InstanceConfigService=InstanceConfigService,
    )
    _install_module(
        monkeypatch,
        "apps.monitor.services.monitor_object",
        MonitorObjectService=object,
    )
    _install_module(
        monkeypatch,
        "apps.monitor.services.policy_source_cleanup",
        cleanup_policy_sources=lambda *args: None,
    )
    _install_module(monkeypatch, "apps.monitor.services.metrics", Metrics=object)
    _install_module(
        monkeypatch,
        "apps.monitor.utils.pagination",
        parse_page_params=lambda *args, **kwargs: (1, 10),
    )
    _install_module(monkeypatch, "apps.rpc.node_mgmt", NodeMgmt=object)

    return _load_module(
        "monitor_instance_view_test_module",
        Path(__file__).resolve().parents[1] / "views" / "monitor_instance.py",
    )


def _load_organization_rule_view(monkeypatch, authorized_ids=None, scope_groups=None):
    class ModelViewSet:
        queryset = None

        def get_queryset(self):
            return self.queryset.all()

    class StubBaseAppException(Exception):
        pass

    class UnauthorizedException(Exception):
        pass

    class InstanceConfigService:
        @staticmethod
        def _get_actor_scope_groups(actor_context):
            return scope_groups if scope_groups is not None else [actor_context["current_team"]]

        @staticmethod
        def _get_authorized_monitor_instances(actor_context, monitor_object_id, require_operate=False):
            return _AuthorizedInstanceQuerySet(authorized_ids or [])

    def _build_actor_context(request):
        return {
            "username": request.user.username,
            "domain": request.user.domain,
            "current_team": int(request.COOKIES["current_team"]),
            "include_children": request.COOKIES.get("include_children", "0") == "1",
            "is_superuser": request.user.is_superuser,
            "group_list": [int(group) for group in request.user.group_list],
        }

    def _ensure_target_organizations(organizations, actor_context):
        allowed = set(InstanceConfigService._get_actor_scope_groups(actor_context) or [])
        requested = {int(org) for org in organizations if org not in (None, "")}
        if requested - allowed:
            raise UnauthorizedException("无权限关联指定组织")

    def _ensure_operate_instances(request, instance_ids, actor_context=None):
        allowed = {str(instance_id) for instance_id in (authorized_ids or [])}
        requested = {str(instance_id) for instance_id in instance_ids if instance_id not in (None, "")}
        if requested - allowed:
            raise UnauthorizedException("无权限操作指定监控实例")
        return list(requested)

    _install_module(monkeypatch, "rest_framework.viewsets", ModelViewSet=ModelViewSet, ViewSet=ModelViewSet)
    _install_module(
        monkeypatch,
        "apps.core.exceptions.base_app_exception",
        BaseAppException=StubBaseAppException,
        ValidationAppException=StubBaseAppException,
        UnauthorizedException=UnauthorizedException,
    )
    _install_module(
        monkeypatch,
        "apps.core.utils.web_utils",
        WebUtils=types.SimpleNamespace(response_success=lambda data=None: data),
    )
    _install_module(
        monkeypatch,
        "apps.monitor.filters.monitor_object",
        MonitorObjectOrganizationRuleFilter=object,
    )
    _install_module(
        monkeypatch,
        "apps.monitor.models",
        MonitorObjectOrganizationRule=_MonitorObjectOrganizationRule,
        MonitorInstance=_MonitorInstance,
    )
    _install_module(
        monkeypatch,
        "apps.monitor.serializers.monitor_object",
        MonitorObjectOrganizationRuleSerializer=object,
    )
    _install_module(
        monkeypatch,
        "apps.monitor.services.organization_rule",
        OrganizationRule=types.SimpleNamespace(del_organization_rule=lambda **kwargs: kwargs),
    )
    _install_module(
        monkeypatch,
        "apps.monitor.services.node_mgmt",
        InstanceConfigService=InstanceConfigService,
    )
    _install_module(
        monkeypatch,
        "apps.monitor.views.monitor_instance",
        _build_actor_context=_build_actor_context,
        _ensure_operate_instances=_ensure_operate_instances,
        _ensure_target_organizations=_ensure_target_organizations,
    )
    _install_module(monkeypatch, "config.drf.pagination", CustomPageNumberPagination=object)

    return _load_module(
        "monitor_organization_rule_view_test_module",
        Path(__file__).resolve().parents[1] / "views" / "organization_rule.py",
    )


def _monitor_request(current_team="7"):
    return types.SimpleNamespace(
        COOKIES={"current_team": current_team},
        user=types.SimpleNamespace(
            username="operator",
            domain="domain.com",
            is_superuser=False,
            group_list=[int(current_team)],
        ),
    )


def test_monitor_instance_actor_context_keeps_node_mgmt_shape(monkeypatch):
    module = _load_monitor_instance_view(monkeypatch)

    actor_context = module._build_actor_context(_monitor_request())

    assert actor_context == {
        "username": "operator",
        "domain": "domain.com",
        "current_team": 7,
        "include_children": False,
        "is_superuser": False,
        "group_list": [7],
    }


def test_monitor_instance_operate_guard_rejects_unauthorized_instance(monkeypatch):
    _MonitorInstance.rows = [{"id": "inst-a", "monitor_object_id": 1}]
    _MonitorInstanceOrganization.rows = [{"monitor_instance_id": "inst-a", "organization": 7}]
    module = _load_monitor_instance_view(monkeypatch, authorized_ids=[])

    with pytest.raises(module.UnauthorizedException):
        module._ensure_operate_instances(_monitor_request(), ["inst-a"])


def test_monitor_instance_operate_guard_accepts_authorized_instance(monkeypatch):
    _MonitorInstance.rows = [{"id": "inst-a", "monitor_object_id": 1}]
    _MonitorInstanceOrganization.rows = [{"monitor_instance_id": "inst-a", "organization": 7}]
    module = _load_monitor_instance_view(monkeypatch, authorized_ids=["inst-a"])

    assert module._ensure_operate_instances(_monitor_request(), ["inst-a", "inst-a"]) == ["inst-a"]


def test_monitor_instance_scope_guard_rejects_cross_org_instance(monkeypatch):
    _MonitorInstance.rows = [{"id": "inst-a", "monitor_object_id": 1}]
    _MonitorInstanceOrganization.rows = [
        {"monitor_instance_id": "inst-a", "organization": 7},
        {"monitor_instance_id": "inst-a", "organization": 9},
    ]
    module = _load_monitor_instance_view(monkeypatch, authorized_ids=["inst-a"], scope_groups=[7])

    with pytest.raises(module.UnauthorizedException):
        module._ensure_operate_instances(_monitor_request(), ["inst-a"])


def test_monitor_instance_target_organization_guard_rejects_out_of_scope_org(monkeypatch):
    module = _load_monitor_instance_view(monkeypatch, scope_groups=[7])
    actor_context = module._build_actor_context(_monitor_request())

    with pytest.raises(module.UnauthorizedException):
        module._ensure_target_organizations([9], actor_context)


def test_query_by_instance_fails_closed_when_effective_instance_keys_missing(monkeypatch):
    class ViewSet:
        pass

    def action(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

    class StubBaseAppException(Exception):
        pass

    class StubMetricQuerySet:
        def __init__(self, metric):
            self.metric = metric

        def select_related(self, *args):
            return self

        def first(self):
            return self.metric

    class StubMetricManager:
        def __init__(self, metric):
            self.metric = metric

        def filter(self, **kwargs):
            return StubMetricQuerySet(self.metric)

    class StubAuthorizedQuerySet:
        @staticmethod
        def filter(**kwargs):
            return StubAuthorizedQuerySet()

        @staticmethod
        def exists():
            return True

    metric = types.SimpleNamespace(query="cpu{__$labels__}", dimensions=[], unit="", monitor_object=types.SimpleNamespace(instance_id_keys=[]))

    class StubMetricsService:
        query_called = False

        @staticmethod
        def get_effective_metric_instance_id_keys(metric_obj):
            raise StubBaseAppException("指标未配置有效的 instance_id_keys，无法按实例查询")

        @staticmethod
        def query_metric_by_instance(**kwargs):
            StubMetricsService.query_called = True
            return {"status": "success"}

    _install_module(monkeypatch, "rest_framework.viewsets", ViewSet=ViewSet)
    _install_module(monkeypatch, "rest_framework.decorators", action=action)
    _install_module(
        monkeypatch,
        "apps.core.exceptions.base_app_exception",
        BaseAppException=StubBaseAppException,
        ValidationAppException=StubBaseAppException,
        UnauthorizedException=StubBaseAppException,
    )
    _install_module(
        monkeypatch,
        "apps.core.utils.web_utils",
        WebUtils=types.SimpleNamespace(response_success=lambda data=None: data),
    )
    _install_module(monkeypatch, "apps.core.logger", monitor_logger=types.SimpleNamespace(warning=lambda *args, **kwargs: None))
    _install_module(
        monkeypatch,
        "apps.core.utils.permission_utils",
        get_permission_rules=lambda *args, **kwargs: {},
        permission_filter=lambda *args, **kwargs: StubAuthorizedQuerySet(),
    )
    _install_module(
        monkeypatch,
        "apps.monitor.models.monitor_metrics",
        Metric=types.SimpleNamespace(objects=StubMetricManager(metric)),
    )
    _install_module(monkeypatch, "apps.monitor.models", MonitorInstance=object)
    _install_module(monkeypatch, "apps.monitor.services.metrics", Metrics=StubMetricsService)
    _install_module(monkeypatch, "apps.monitor.utils.unit_converter", UnitConverter=types.SimpleNamespace())

    module = _load_module(
        "metrics_instance_view_test_module",
        Path(__file__).resolve().parents[1] / "views" / "metrics_instance.py",
    )

    request = types.SimpleNamespace(
        COOKIES={"current_team": "7"},
        GET={
            "monitor_object_id": "1",
            "metric_id": "2",
            "instance_id": "('host-1',)",
        },
        user=types.SimpleNamespace(
            username="operator",
            domain="domain.com",
            is_superuser=False,
            group_list=[7],
        ),
    )

    with pytest.raises(StubBaseAppException, match="instance_id_keys"):
        module.MetricsInstanceViewSet().query_by_instance(request)

    assert StubMetricsService.query_called is False


def test_organization_rule_queryset_hides_cross_org_rules(monkeypatch):
    _MonitorObjectOrganizationRule.rows = [
        types.SimpleNamespace(id=1, monitor_object_id=1, organizations=[7], monitor_instance_id="inst-a"),
        types.SimpleNamespace(id=2, monitor_object_id=1, organizations=[9], monitor_instance_id="inst-a"),
    ]
    _MonitorInstance.rows = [{"id": "inst-a", "monitor_object_id": 1}]
    module = _load_organization_rule_view(monkeypatch, authorized_ids=["inst-a"], scope_groups=[7])

    view = module.MonitorObjectOrganizationRuleViewSet()
    view.request = _monitor_request()
    view.action = "list"

    assert [rule.id for rule in view.get_queryset()] == [1]


def test_organization_rule_queryset_requires_operate_permission_for_destroy(monkeypatch):
    _MonitorObjectOrganizationRule.rows = [
        types.SimpleNamespace(id=1, monitor_object_id=1, organizations=[7], monitor_instance_id="inst-a"),
    ]
    _MonitorInstance.rows = [{"id": "inst-a", "monitor_object_id": 1}]
    module = _load_organization_rule_view(monkeypatch, authorized_ids=[], scope_groups=[7])

    view = module.MonitorObjectOrganizationRuleViewSet()
    view.request = _monitor_request()
    view.action = "destroy"

    assert list(view.get_queryset()) == []


def test_organization_rule_payload_rejects_mismatched_monitor_object(monkeypatch):
    _MonitorInstance.rows = [{"id": "inst-a", "monitor_object_id": 1}]
    module = _load_organization_rule_view(monkeypatch, authorized_ids=["inst-a"], scope_groups=[7])

    with pytest.raises(module.BaseAppException):
        module._validate_rule_payload(_monitor_request(), module._build_actor_context(_monitor_request()), 2, "inst-a", [7])


def test_organization_rule_payload_rejects_out_of_scope_organization(monkeypatch):
    _MonitorInstance.rows = [{"id": "inst-a", "monitor_object_id": 1}]
    module = _load_organization_rule_view(monkeypatch, authorized_ids=["inst-a"], scope_groups=[7])

    with pytest.raises(module.UnauthorizedException):
        module._validate_rule_payload(_monitor_request(), module._build_actor_context(_monitor_request()), 1, "inst-a", [9])
