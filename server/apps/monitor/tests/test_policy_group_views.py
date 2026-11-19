import json
from types import SimpleNamespace

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.current_team_scope import CurrentTeamDataScope
from apps.monitor.models import (
    Metric,
    MetricGroup,
    MonitorInstance,
    MonitorInstanceOrganization,
    MonitorObject,
    MonitorPlugin,
    MonitorPolicy,
    PolicyGroupDefault,
    PolicyGroupMembership,
    PolicyTemplate,
)
from apps.monitor.services.policy_group import PolicyGroupService
from apps.monitor.views.policy_group import PolicyGroupViewSet
from apps.system_mgmt.models import Group

pytestmark = pytest.mark.django_db


def _object(name):
    return MonitorObject.objects.create(name=name, level="base")


def _plugin(monitor_object, name):
    plugin = MonitorPlugin.objects.create(name=name, collector="Telegraf", collect_type="host")
    plugin.monitor_object.add(monitor_object)
    return plugin


def _template(monitor_object, plugin, name):
    metric_group, _ = MetricGroup.objects.get_or_create(monitor_object=monitor_object, monitor_plugin=plugin, name="os")
    Metric.objects.get_or_create(
        monitor_object=monitor_object,
        monitor_plugin=plugin,
        name="cpu_usage_total",
        defaults={"metric_group": metric_group},
    )
    return PolicyTemplate.objects.create(
        key=f"builtin-{plugin.name}-{name}",
        scope_key="builtin",
        template_type=PolicyTemplate.TYPE_BUILTIN,
        organization=None,
        monitor_object=monitor_object,
        plugin=plugin,
        name=name,
        config={"metric_name": "cpu_usage_total", "threshold": [{"level": "warning", "value": 80, "method": ">="}]},
    )


def _instance(monitor_object, name, organization):
    instance = MonitorInstance.objects.create(id=f"('{name}',)", name=name, monitor_object=monitor_object)
    MonitorInstanceOrganization.objects.create(monitor_instance=instance, organization=organization)
    return instance


def _scope(current, data_ids):
    return CurrentTeamDataScope(
        current_team=current,
        data_team_ids=frozenset(data_ids),
        include_children=set(data_ids) != {current},
        username="ops",
        domain="domain.com",
        is_superuser=False,
    )


def _call(monkeypatch, scope, method, action, path, data=None, params=None):
    import apps.monitor.views.policy_group as views

    monkeypatch.setattr(views, "resolve_current_team_data_scope", lambda request: scope)
    factory = APIRequestFactory()
    if method == "get":
        request = factory.get(path, params or {})
    else:
        request = factory.post(path, data or {}, format="json")
    user = SimpleNamespace(username="ops", domain="domain.com", locale="zh", is_superuser=True, is_authenticated=True)
    force_authenticate(request, user=user)
    return PolicyGroupViewSet.as_view({method: action})(request)


def _data(response):
    body = json.loads(response.content)
    assert body["result"] is True
    return body["data"]


def _world():
    parent = Group.objects.create(name="ParentOrg", parent_id=0)
    child = Group.objects.create(name="ChildOrg", parent_id=parent.id)
    monitor_object = _object("ScopeHost")
    plugin = _plugin(monitor_object, "ScopePlugin")
    template = _template(monitor_object, plugin, "CPU")
    parent_group = PolicyGroupService.create_from_templates(
        organization=parent.id,
        monitor_object=monitor_object,
        name="父组织默认告警",
        templates=[template],
    )
    child_group = PolicyGroupService.create_from_templates(
        organization=child.id,
        monitor_object=monitor_object,
        name="子组织默认告警",
        templates=[template],
    )
    parent_instance = _instance(monitor_object, "parent-host", parent.id)
    child_instance = _instance(monitor_object, "child-host", child.id)
    PolicyGroupService.join(instance=parent_instance, group=parent_group)
    PolicyGroupService.join(instance=child_instance, group=child_group)
    legacy = MonitorPolicy.objects.create(
        monitor_object=monitor_object,
        name="子组织旧策略",
        algorithm="avg",
        enable=True,
        source={"type": "instance", "values": [child_instance.id]},
    )
    return SimpleNamespace(
        parent=parent,
        child=child,
        monitor_object=monitor_object,
        template=template,
        parent_group=parent_group,
        child_group=child_group,
        parent_instance=parent_instance,
        child_instance=child_instance,
        legacy=legacy,
    )


def test_list_reports_when_the_default_group_was_removed(monkeypatch):
    world = _world()
    PolicyGroupDefault.objects.create(organization=world.parent.id, monitor_object=world.monitor_object, policy_group=None)

    removed = _data(
        _call(
            monkeypatch,
            _scope(world.parent.id, [world.parent.id]),
            "get",
            "list",
            "/monitor/api/policy_group/",
            params={"monitor_object_id": world.monitor_object.id, "page": 1, "create_default": "false"},
        )
    )
    assert removed["default_removed"] is True

    PolicyGroupDefault.objects.filter(organization=world.parent.id, monitor_object=world.monitor_object).delete()
    absent = _data(
        _call(
            monkeypatch,
            _scope(world.parent.id, [world.parent.id]),
            "get",
            "list",
            "/monitor/api/policy_group/",
            params={"monitor_object_id": world.monitor_object.id, "page": 1, "create_default": "false"},
        )
    )
    assert absent["default_removed"] is False


def test_current_organization_membership_stays_editable(monkeypatch):
    world = _world()

    response = _call(
        monkeypatch,
        _scope(world.parent.id, [world.parent.id]),
        "get",
        "membership",
        "/monitor/api/policy_group/membership/",
        params={"instance_id": world.parent_instance.id},
    )

    data = _data(response)
    assert data["read_only"] is False
    assert data["state"] == PolicyGroupMembership.STATE_MEMBER
    assert data["group_id"] == world.parent_group.id
    assert data["group_name"] == "父组织默认告警"
    assert data["groups"] == [{"id": world.parent_group.id, "name": "父组织默认告警", "is_default": False}]
    assert data["templates"] == [{"id": world.template.id, "name": "CPU"}]
    assert data["legacy_policies"] == []
    assert "group_organization" not in data
    assert "group_organization_name" not in data


def test_child_membership_is_read_only_when_visible_and_rejected_when_hidden(monkeypatch):
    world = _world()
    visible = _call(
        monkeypatch,
        _scope(world.parent.id, [world.parent.id, world.child.id]),
        "get",
        "membership",
        "/monitor/api/policy_group/membership/",
        params={"instance_id": world.child_instance.id},
    )

    data = _data(visible)
    assert data == {
        "read_only": True,
        "state": PolicyGroupMembership.STATE_MEMBER,
        "group_id": world.child_group.id,
        "group_name": "子组织默认告警",
        "group_organization": world.child.id,
        "group_organization_name": "ChildOrg",
        "groups": [],
        "templates": [],
        "legacy_policies": [{"id": world.legacy.id, "name": "子组织旧策略", "enable": True}],
    }

    with pytest.raises(BaseAppException, match="实例不属于当前组织"):
        _call(
            monkeypatch,
            _scope(world.parent.id, [world.parent.id]),
            "get",
            "membership",
            "/monitor/api/policy_group/membership/",
            params={"instance_id": world.child_instance.id},
        )


def test_child_without_group_returns_empty_organization(monkeypatch):
    world = _world()
    outsider = _instance(world.monitor_object, "child-plain", world.child.id)

    data = _data(
        _call(
            monkeypatch,
            _scope(world.parent.id, [world.parent.id, world.child.id]),
            "get",
            "membership",
            "/monitor/api/policy_group/membership/",
            params={"instance_id": outsider.id},
        )
    )

    assert data["read_only"] is True
    assert data["state"] is None
    assert data["group_id"] is None
    assert data["group_name"] == ""
    assert data["group_organization"] is None
    assert data["group_organization_name"] == ""
    assert data["groups"] == []
    assert data["templates"] == []


def test_instance_groups_marks_child_rows_read_only(monkeypatch):
    world = _world()
    params = {"instance_ids": json.dumps([world.parent_instance.id, world.child_instance.id])}

    hidden = _data(
        _call(
            monkeypatch,
            _scope(world.parent.id, [world.parent.id]),
            "get",
            "instance_groups",
            "/monitor/api/policy_group/instance_groups/",
            params=params,
        )
    )
    assert hidden == [
        {
            "instance_id": world.parent_instance.id,
            "group_id": world.parent_group.id,
            "group_name": "父组织默认告警",
            "group_organization": world.parent.id,
            "read_only": False,
        }
    ]

    visible = _data(
        _call(
            monkeypatch,
            _scope(world.parent.id, [world.parent.id, world.child.id]),
            "get",
            "instance_groups",
            "/monitor/api/policy_group/instance_groups/",
            params=params,
        )
    )
    by_instance = {row["instance_id"]: row for row in visible}
    assert by_instance[world.parent_instance.id] == hidden[0]
    assert by_instance[world.child_instance.id] == {
        "instance_id": world.child_instance.id,
        "group_id": world.child_group.id,
        "group_name": "子组织默认告警",
        "group_organization": world.child.id,
        "read_only": True,
    }


def test_join_still_rejects_child_instance(monkeypatch):
    world = _world()
    before = PolicyGroupMembership.objects.get(monitor_instance=world.child_instance)

    with pytest.raises(BaseAppException, match="实例不属于该策略组的组织"):
        _call(
            monkeypatch,
            _scope(world.parent.id, [world.parent.id, world.child.id]),
            "post",
            "join",
            "/monitor/api/policy_group/join/",
            data={"group_id": world.parent_group.id, "instance_ids": [world.child_instance.id]},
        )

    after = PolicyGroupMembership.objects.get(monitor_instance=world.child_instance)
    assert after.policy_group_id == before.policy_group_id
    assert after.state == before.state
