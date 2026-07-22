"""AlertPermissionMixin 策略权限根规格测试。"""

from types import SimpleNamespace

import pytest

from apps.core.utils.current_team_scope import CurrentTeamDataScope
from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.models.monitor_policy import MonitorPolicy, PolicyOrganization
from apps.monitor.views.monitor_alert import AlertPermissionMixin, MonitorAlertViewSet, MonitorEventViewSet

pytestmark = pytest.mark.django_db


def _policy(name, organization):
    monitor_object = MonitorObject.objects.create(name=f"{name}-object", level="base")
    policy = MonitorPolicy.objects.create(
        monitor_object=monitor_object,
        name=name,
        algorithm="max",
        query_condition={},
        source={},
        group_by=[],
    )
    PolicyOrganization.objects.create(
        policy=policy,
        organization=organization,
    )
    return policy


def _request(*, is_superuser=False):
    return SimpleNamespace(
        user=SimpleNamespace(
            username="actor",
            domain="domain.com",
            is_superuser=is_superuser,
        ),
        COOKIES={"current_team": "1", "include_children": "0"},
    )


def _scope(*teams):
    return CurrentTeamDataScope(
        current_team=1,
        data_team_ids=frozenset(teams),
        include_children=False,
        username="actor",
        domain="domain.com",
        is_superuser=False,
    )


def test_alert_and_event_views_share_permission_mixin():
    assert issubclass(MonitorAlertViewSet, AlertPermissionMixin)
    assert issubclass(MonitorEventViewSet, AlertPermissionMixin)
    assert "get_accessible_policy_queryset" not in MonitorAlertViewSet.__dict__
    assert "get_accessible_policy_queryset" not in MonitorEventViewSet.__dict__


def test_superuser_policy_queryset_stays_in_current_team(mocker):
    current = _policy("mixin-current", 1)
    _policy("mixin-sibling", 2)
    mixin = AlertPermissionMixin()
    mocker.patch(
        "apps.monitor.views.monitor_alert.resolve_current_team_data_scope",
        return_value=_scope(1),
    )

    queryset = mixin.get_accessible_policy_queryset(_request(is_superuser=True))

    assert set(queryset.values_list("id", flat=True)) == {current.id}


def test_normal_user_policy_queryset_intersects_object_permission_and_scope(mocker):
    allowed = _policy("mixin-allowed", 1)
    blocked = _policy("mixin-blocked", 1)
    _policy("mixin-sibling", 2)
    mixin = AlertPermissionMixin()
    mocker.patch(
        "apps.monitor.views.monitor_alert.resolve_current_team_data_scope",
        return_value=_scope(1),
    )
    mocker.patch(
        "apps.monitor.views.monitor_alert.get_permissions_rules",
        return_value={
            "data": {
                str(allowed.monitor_object_id): {
                    "team": [],
                    "instance": [{"id": allowed.id, "permission": ["View"]}],
                },
                str(blocked.monitor_object_id): {
                    "team": [],
                    "instance": [],
                },
            },
            "team": [1],
        },
    )

    queryset = mixin.get_accessible_policy_queryset(_request())

    assert set(queryset.values_list("id", flat=True)) == {allowed.id}


def test_operate_queryset_rejects_view_only_permission(mocker):
    policy = _policy("mixin-view-only", 1)
    mixin = AlertPermissionMixin()
    mocker.patch(
        "apps.monitor.views.monitor_alert.resolve_current_team_data_scope",
        return_value=_scope(1),
    )
    mocker.patch(
        "apps.monitor.views.monitor_alert.get_permissions_rules",
        return_value={
            "data": {
                str(policy.monitor_object_id): {
                    "team": [],
                    "instance": [{"id": policy.id, "permission": ["View"]}],
                }
            },
            "team": [1],
        },
    )

    queryset = mixin.get_accessible_policy_queryset(
        _request(),
        require_operate=True,
    )

    assert not queryset.exists()
