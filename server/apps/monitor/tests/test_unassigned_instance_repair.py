import json
from types import SimpleNamespace

import pytest

from apps.core.exceptions.base_app_exception import BaseAppException, ForbiddenException
from apps.core.utils.current_team_scope import CurrentTeamDataScope
from apps.monitor.models.monitor_object import MonitorInstance, MonitorInstanceOrganization, MonitorObject
from apps.monitor.services.monitor_object import MonitorObjectService
from apps.monitor.views import monitor_instance as monitor_instance_view
from apps.monitor.views.monitor_instance import MonitorInstanceViewSet, _ensure_operate_instances

pytestmark = pytest.mark.django_db


def _user(*, is_superuser=False):
    return SimpleNamespace(
        username="tester",
        domain="domain.com",
        is_superuser=is_superuser,
        locale="zh-Hans",
        group_list=[{"id": 1, "name": "Team 1"}],
        is_authenticated=True,
    )


def _request(*, is_superuser=False, unassigned=None, data=None):
    query = {"unassigned": "true"} if unassigned else {}
    return SimpleNamespace(
        user=_user(is_superuser=is_superuser),
        COOKIES={"current_team": "1", "include_children": "0"},
        GET=query,
        query_params=query,
        data=data or {},
    )


def _scope(*, is_superuser=False):
    return CurrentTeamDataScope(1, frozenset({1}), False, "tester", "domain.com", is_superuser)


def _object():
    return MonitorObject.objects.create(
        name="UnassignedHost",
        level="base",
        default_metric="up",
        instance_id_keys=["instance_id"],
    )


def _patch_list(monkeypatch, *, is_superuser=False):
    monkeypatch.setattr(
        monitor_instance_view,
        "resolve_current_team_data_scope",
        lambda request: _scope(is_superuser=is_superuser),
    )
    monkeypatch.setattr(
        MonitorObjectService,
        "get_instances_by_metric",
        staticmethod(lambda *args, **kwargs: {}),
    )


def _ids(response):
    payload = json.loads(response.content)
    return [item["instance_id"] for item in payload["data"]["results"]]


def test_superuser_default_list_hides_unassigned_instances(monkeypatch):
    obj = _object()
    assigned = MonitorInstance.objects.create(id="('assigned',)", name="assigned", monitor_object=obj)
    ghost = MonitorInstance.objects.create(id="('ghost',)", name="ghost", monitor_object=obj)
    MonitorInstanceOrganization.objects.create(monitor_instance=assigned, organization=1)
    _patch_list(monkeypatch, is_superuser=True)

    response = MonitorInstanceViewSet().monitor_instance_list(_request(is_superuser=True), str(obj.id))

    assert assigned.id in _ids(response)
    assert ghost.id not in _ids(response)


def test_superuser_unassigned_list_shows_only_zero_org_instances(monkeypatch):
    obj = _object()
    assigned = MonitorInstance.objects.create(id="('assigned-u',)", name="assigned", monitor_object=obj)
    ghost = MonitorInstance.objects.create(id="('ghost-u',)", name="ghost", monitor_object=obj)
    MonitorInstanceOrganization.objects.create(monitor_instance=assigned, organization=1)
    _patch_list(monkeypatch, is_superuser=True)

    response = MonitorInstanceViewSet().monitor_instance_list(
        _request(is_superuser=True, unassigned=True),
        str(obj.id),
    )

    assert _ids(response) == [ghost.id]


def test_non_superuser_unassigned_list_is_forbidden(monkeypatch):
    obj = _object()
    _patch_list(monkeypatch, is_superuser=False)

    with pytest.raises(ForbiddenException):
        MonitorInstanceViewSet().monitor_instance_list(_request(unassigned=True), str(obj.id))


def test_superuser_can_set_organization_on_unassigned_instance(mocker, monkeypatch):
    obj = _object()
    ghost = MonitorInstance.objects.create(id="('ghost-set',)", name="ghost", monitor_object=obj)
    monkeypatch.setattr(
        monitor_instance_view,
        "resolve_current_team_data_scope",
        lambda request: _scope(is_superuser=True),
    )
    mocker.patch(
        "apps.monitor.services.node_mgmt.get_permission_rules",
        return_value={"team": [1], "instance": []},
    )
    mocker.patch(
        "apps.core.utils.current_team_scope.SystemMgmt.get_assignable_groups",
        return_value={"result": True, "data": [1, 2]},
    )

    request = _request(is_superuser=True, data={"instance_ids": [ghost.id], "organizations": [1]})
    MonitorInstanceViewSet().set_instances_organizations(request)

    assert set(ghost.monitorinstanceorganization_set.values_list("organization", flat=True)) == {1}


def test_removing_last_monitor_organization_is_rejected():
    obj = _object()
    inst = MonitorInstance.objects.create(id="('last-org',)", name="last", monitor_object=obj)
    MonitorInstanceOrganization.objects.create(monitor_instance=inst, organization=1)

    with pytest.raises(BaseAppException, match="不能移除最后一个组织"):
        MonitorObjectService.remove_instances_organizations([inst.id], [1])

    assert set(inst.monitorinstanceorganization_set.values_list("organization", flat=True)) == {1}


def test_empty_set_organizations_keeps_existing():
    obj = _object()
    inst = MonitorInstance.objects.create(id="('empty-set-svc',)", name="keep", monitor_object=obj)
    MonitorInstanceOrganization.objects.create(monitor_instance=inst, organization=1)

    with pytest.raises(BaseAppException, match="至少保留一个组织"):
        MonitorObjectService.set_instances_organizations([inst.id], [])

    assert set(inst.monitorinstanceorganization_set.values_list("organization", flat=True)) == {1}


def test_superuser_can_delete_unassigned_instance(mocker, monkeypatch):
    obj = _object()
    ghost = MonitorInstance.objects.create(id="('ghost-del',)", name="ghost", monitor_object=obj)
    monkeypatch.setattr(
        monitor_instance_view,
        "resolve_current_team_data_scope",
        lambda request: _scope(is_superuser=True),
    )
    mocker.patch(
        "apps.monitor.services.node_mgmt.get_permission_rules",
        return_value={"team": [1], "instance": []},
    )
    mocker.patch("apps.monitor.services.monitor_instance_removal.NodeMgmt")
    mocker.patch("apps.monitor.services.monitor_instance_removal.record_lifecycle_events")
    mocker.patch("apps.monitor.services.monitor_instance_removal.AlertLifecycleNotifier")

    request = _request(is_superuser=True, data={"instance_ids": [ghost.id]})
    MonitorInstanceViewSet().remove_monitor_instance(request)

    assert not MonitorInstance.objects.filter(id=ghost.id).exists()


def test_authorized_metric_scope_excludes_unassigned_instances_for_superuser(monkeypatch):
    from apps.monitor.services.node_mgmt import InstanceConfigService

    obj = _object()
    assigned = MonitorInstance.objects.create(id="('metric-assigned',)", name="assigned", monitor_object=obj)
    ghost = MonitorInstance.objects.create(id="('metric-ghost',)", name="ghost", monitor_object=obj)
    MonitorInstanceOrganization.objects.create(monitor_instance=assigned, organization=1)
    monkeypatch.setattr(
        InstanceConfigService,
        "_get_data_scope",
        staticmethod(lambda actor_context: _scope(is_superuser=True)),
    )

    ids = set(
        InstanceConfigService._get_authorized_monitor_instances(
            {
                "is_superuser": True,
                "current_team": 1,
                "include_children": False,
                "data_scope": _scope(is_superuser=True),
            },
            obj.id,
        ).values_list("id", flat=True)
    )

    assert assigned.id in ids
    assert ghost.id not in ids


def test_superuser_can_operate_unassigned_instance(mocker, monkeypatch):
    obj = _object()
    ghost = MonitorInstance.objects.create(id="('ghost-op',)", name="ghost", monitor_object=obj)
    monkeypatch.setattr(
        monitor_instance_view,
        "resolve_current_team_data_scope",
        lambda request: _scope(is_superuser=True),
    )
    mocker.patch(
        "apps.monitor.services.node_mgmt.get_permission_rules",
        return_value={"team": [1], "instance": []},
    )

    assert _ensure_operate_instances(_request(is_superuser=True), [ghost.id]) == [ghost.id]
