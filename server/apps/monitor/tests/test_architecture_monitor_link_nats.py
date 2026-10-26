from types import SimpleNamespace

import pytest

from apps.monitor.models.monitor_object import MonitorInstance, MonitorInstanceOrganization, MonitorObject
from apps.monitor.nats import monitor as nm
from apps.monitor.views import monitor_instance as monitor_instance_view

pytestmark = pytest.mark.django_db


def _user_info(*, superuser, team=1, locale="zh-Hans"):
    return {
        "user": "tester",
        "domain": "default",
        "team": team,
        "include_children": False,
        "is_superuser": superuser,
        "locale": locale,
    }


def _patch_scope(monkeypatch, team_id=1, *, is_superuser=False):
    user = SimpleNamespace(username="tester", domain="default")

    def _scope(user_info):
        if not isinstance(user_info, dict):
            return None, None, None, None, None, {"result": False, "data": {}, "message": "缺少用户或组织信息"}
        return user, team_id, False, frozenset({team_id}), is_superuser, None

    monkeypatch.setattr(nm, "_get_nats_actor_scope", _scope)


def _host(instance_id="('app3d-demo-host-01',)", organization=1, name="web-1"):
    monitor_object = MonitorObject.objects.create(name="Host", display_name="主机", instance_id_keys=["instance_id"])
    instance = MonitorInstance.objects.create(id=instance_id, name=name, monitor_object=monitor_object)
    if organization is not None:
        MonitorInstanceOrganization.objects.create(monitor_instance=instance, organization=organization)
    return monitor_object, instance


def test_lookup_finds_tuple_pk_for_superuser_in_org(monkeypatch):
    monitor_object, _instance = _host()
    _patch_scope(monkeypatch, is_superuser=True)
    out = nm.lookup_monitor_instance("app3d-demo-host-01", user_info=_user_info(superuser=False))
    assert out["result"] is True
    assert out["data"]["monitor_object"]["id"] == monitor_object.id
    assert out["data"]["instance"]["instance_id"] == "('app3d-demo-host-01',)"
    assert out["data"]["instance"]["instance_name"] == "web-1"


def test_lookup_hides_other_team(monkeypatch):
    _host(organization=2)
    _patch_scope(monkeypatch, team_id=1)
    out = nm.lookup_monitor_instance("app3d-demo-host-01", user_info=_user_info(superuser=True))
    assert out == {"result": True, "data": None, "message": ""}


def test_lookup_hides_when_object_permission_empty(monkeypatch):
    _host()
    _patch_scope(monkeypatch)
    monkeypatch.setattr(
        monitor_instance_view,
        "get_permission_rules",
        lambda *args, **kwargs: {"team": [], "instance": []},
    )
    out = nm.lookup_monitor_instance("app3d-demo-host-01", user_info=_user_info(superuser=False))
    assert out["data"] is None


def test_lookup_superuser_sees_unassigned_instance(monkeypatch):
    monitor_object, _instance = _host(organization=None)
    _patch_scope(monkeypatch, is_superuser=True)
    out = nm.lookup_monitor_instance("app3d-demo-host-01", user_info=_user_info(superuser=False))
    assert out["data"]["monitor_object"]["id"] == monitor_object.id


def test_lookup_non_superuser_hides_unassigned_instance(monkeypatch):
    _host(organization=None)
    _patch_scope(monkeypatch, is_superuser=False)
    out = nm.lookup_monitor_instance("app3d-demo-host-01", user_info=_user_info(superuser=True))
    assert out["data"] is None


def test_lookup_requires_instance_id_and_user():
    assert nm.lookup_monitor_instance("  ", user_info=_user_info(superuser=True))["result"] is False
    missing = nm.lookup_monitor_instance("app3d-demo-host-01", user_info=None)
    assert missing["result"] is False
    assert missing["message"] == "缺少用户或组织信息"


def test_effective_plugins_allow_derived_instance_without_row(monkeypatch):
    _patch_scope(monkeypatch)
    seen = {}

    class StubService:
        @staticmethod
        def get_effective_plugins(monitor_object_id, instance_id, locale):
            seen["args"] = (monitor_object_id, instance_id, locale)
            return [{"id": 7, "name": "K8sPod", "collect_type": "k8s"}]

    monkeypatch.setattr(monitor_instance_view, "MonitorEffectivePluginService", StubService)
    out = nm.get_monitor_effective_plugins(
        monitor_object_id=19,
        instance_id="derived-pod-x",
        user_info=_user_info(superuser=True, locale="en"),
        locale="en",
    )
    assert seen["args"] == (19, "('derived-pod-x',)", "en")
    assert out["result"] is True
    assert out["data"][0]["collect_type"] == "k8s"


def test_effective_plugins_unauthorized_instance_is_empty(monkeypatch):
    monitor_object, _instance = _host()
    _patch_scope(monkeypatch)
    monkeypatch.setattr(
        "apps.monitor.services.node_mgmt.get_permission_rules",
        lambda *args, **kwargs: {"team": [], "instance": []},
    )
    out = nm.get_monitor_effective_plugins(
        monitor_object_id=monitor_object.id,
        instance_id="app3d-demo-host-01",
        user_info=_user_info(superuser=True),
    )
    assert out == {"result": True, "data": None, "message": ""}


def test_effective_plugins_keeps_multi_dimension_instance_id(monkeypatch):
    _patch_scope(monkeypatch)
    seen = {}

    class StubService:
        @staticmethod
        def get_effective_plugins(monitor_object_id, instance_id, locale):
            seen["instance_id"] = instance_id
            return []

    monkeypatch.setattr(monitor_instance_view, "MonitorEffectivePluginService", StubService)
    monkeypatch.setattr(
        monitor_instance_view,
        "_ensure_operate_instances",
        lambda request, instance_ids, actor_context=None, allow_missing=False: (
            instance_ids if allow_missing else (_ for _ in ()).throw(AssertionError("allow_missing"))
        ),
    )
    out = nm.get_monitor_effective_plugins(
        19,
        "('vcenter-a', 'host-3171')",
        user_info=_user_info(superuser=True),
        locale="zh-Hans",
    )
    assert out["result"] is True
    assert seen["instance_id"] == "('vcenter-a', 'host-3171')"
    assert out["data"] == []
