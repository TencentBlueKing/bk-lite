import importlib.util
import sys
import types
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


class _Q:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def __or__(self, other):
        return self


class _QuerySet:
    def __init__(self, rows, allowed_ids=None):
        self.rows = rows
        self.allowed_ids = allowed_ids

    def filter(self, *args, **kwargs):
        rows = self.rows
        if "monitor_object_id" in kwargs:
            rows = [row for row in rows if row["monitor_object_id"] == kwargs["monitor_object_id"]]
        if self.allowed_ids is not None:
            rows = [row for row in rows if row["id"] in self.allowed_ids]
        return _QuerySet(rows, self.allowed_ids)

    def values(self, *fields):
        return [{field: row[field] for field in fields} for row in self.rows]

    def values_list(self, field, flat=False):
        return [row[field] for row in self.rows]

    def distinct(self):
        return self


class _MonitorInstance:
    rows = []
    allowed_ids = set()

    class objects:
        @staticmethod
        def filter(**kwargs):
            rows = _MonitorInstance.rows
            if "id__in" in kwargs:
                ids = set(kwargs["id__in"])
                rows = [row for row in rows if row["id"] in ids]
            if "monitor_object_id" in kwargs:
                rows = [row for row in rows if row["monitor_object_id"] == kwargs["monitor_object_id"]]
            return _QuerySet(rows, _MonitorInstance.allowed_ids)


def _load_monitor_instance_view(monkeypatch, permission):
    class ViewSet:
        pass

    def action(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

    class UnauthorizedException(Exception):
        pass

    _install_module(monkeypatch, "rest_framework.viewsets", ViewSet=ViewSet)
    _install_module(monkeypatch, "rest_framework.decorators", action=action)
    _install_module(monkeypatch, "django.db.models", Q=_Q)
    _install_module(
        monkeypatch,
        "apps.core.exceptions.base_app_exception",
        BaseAppException=Exception,
        UnauthorizedException=UnauthorizedException,
    )
    _install_module(
        monkeypatch,
        "apps.core.utils.user_group",
        normalize_user_group_ids=lambda groups: [int(item.get("id") if isinstance(item, dict) else item) for item in groups],
    )
    _install_module(
        monkeypatch,
        "apps.core.utils.permission_utils",
        get_permission_rules=lambda *args, **kwargs: permission,
        permission_filter=lambda *args, **kwargs: None,
    )
    _install_module(monkeypatch, "apps.core.utils.web_utils", WebUtils=types.SimpleNamespace(response_success=lambda data=None: data))
    _install_module(
        monkeypatch,
        "apps.monitor.constants.permission",
        PermissionConstants=types.SimpleNamespace(INSTANCE_MODULE="instance", DEFAULT_PERMISSION=["View", "Operate"]),
    )
    _install_module(
        monkeypatch,
        "apps.monitor.models",
        MonitorInstance=_MonitorInstance,
        MonitorObject=object,
        CollectConfig=object,
        MonitorObjectOrganizationRule=object,
    )
    _install_module(monkeypatch, "apps.monitor.services.monitor_instance", InstanceSearch=object)
    _install_module(monkeypatch, "apps.monitor.services.monitor_object", MonitorObjectService=object)
    _install_module(monkeypatch, "apps.monitor.services.policy_source_cleanup", cleanup_policy_sources=lambda *args: None)
    _install_module(monkeypatch, "apps.monitor.services.metrics", Metrics=object)
    _install_module(monkeypatch, "apps.monitor.utils.pagination", parse_page_params=lambda *args, **kwargs: (1, 10))
    _install_module(monkeypatch, "apps.rpc.node_mgmt", NodeMgmt=object)
    _install_module(
        monkeypatch,
        "apps.system_mgmt.utils.group_utils",
        GroupUtils=types.SimpleNamespace(get_user_authorized_child_groups=lambda group_list, current_team, include_children=False: [current_team]),
    )

    return _load_module(
        "monitor_instance_view_test_module",
        Path(__file__).resolve().parents[1] / "views" / "monitor_instance.py",
    )


def _request():
    return types.SimpleNamespace(
        COOKIES={"current_team": "7"},
        user=types.SimpleNamespace(
            username="operator",
            domain="domain.com",
            is_superuser=False,
            group_list=[7],
        ),
    )


def test_operate_guard_rejects_view_only_instance_permission(monkeypatch):
    module = _load_monitor_instance_view(
        monkeypatch,
        {"team": [], "instance": [{"id": "inst-a", "permission": ["View"]}]},
    )
    _MonitorInstance.rows = [{"id": "inst-a", "monitor_object_id": 1}]
    _MonitorInstance.allowed_ids = set()

    with pytest.raises(module.UnauthorizedException):
        module._ensure_operate_instances(_request(), ["inst-a"])


def test_operate_guard_accepts_team_scoped_instance(monkeypatch):
    module = _load_monitor_instance_view(monkeypatch, {"team": [7], "instance": []})
    _MonitorInstance.rows = [{"id": "inst-a", "monitor_object_id": 1}]
    _MonitorInstance.allowed_ids = {"inst-a"}

    assert module._ensure_operate_instances(_request(), ["inst-a"]) == ["inst-a"]


def test_target_organization_guard_rejects_out_of_scope_org(monkeypatch):
    module = _load_monitor_instance_view(monkeypatch, {"team": [7], "instance": []})
    actor_context = module._build_actor_context(_request())

    with pytest.raises(module.UnauthorizedException):
        module._ensure_target_organizations([9], actor_context)
