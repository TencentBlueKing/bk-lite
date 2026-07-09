from types import SimpleNamespace

import pytest
from django_celery_beat.models import CrontabSchedule, PeriodicTask

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.models import MonitorAlert
from apps.monitor.models.monitor_object import (
    MonitorInstance,
    MonitorInstanceOrganization,
    MonitorObject,
)
from apps.monitor.models.monitor_condition import (
    MonitorCondition,
    MonitorConditionOrganization,
)
from apps.monitor.models.monitor_policy import MonitorPolicy, PolicyOrganization
from apps.monitor.views.monitor_condition import MonitorConditionViewSet
from apps.monitor.views.monitor_policy import MonitorPolicyViewSet

pytestmark = pytest.mark.django_db


def _user(username="alice", *, is_superuser=False, groups=None):
    return SimpleNamespace(
        username=username,
        domain="domain.com",
        is_superuser=is_superuser,
        locale="zh-Hans",
        group_list=groups or [{"id": 1, "name": "Team 1"}],
        is_authenticated=True,
    )


def _request(user=None, *, current_team=1, include_children="0"):
    return SimpleNamespace(
        user=user or _user(),
        COOKIES={"current_team": str(current_team), "include_children": include_children},
        query_params={},
        GET={},
        data={},
    )


def _monitor_object(name="PermissionGuardObj"):
    return MonitorObject.objects.create(name=name, level="base")


def _policy(obj, *, name="policy", org=1):
    policy = MonitorPolicy.objects.create(
        monitor_object=obj,
        name=name,
        algorithm="max",
        query_condition={"type": "pmq", "query": "up"},
        source={},
        group_by=[],
        schedule={"type": "min", "value": 5},
    )
    PolicyOrganization.objects.create(policy=policy, organization=org)
    return policy


def _condition(*, name="condition", org=1):
    condition = MonitorCondition.objects.create(name=name, condition={})
    MonitorConditionOrganization.objects.create(monitor_condition=condition, organization=org)
    return condition


def _patch_policy_permission(mocker, *, teams=None, instances=None):
    mocker.patch(
        "apps.monitor.views.monitor_policy.get_permission_rules",
        return_value={"team": teams or [], "instance": instances or []},
    )
    mocker.patch(
        "apps.monitor.views.monitor_policy.InstanceConfigService._get_actor_scope_groups",
        return_value=teams or [],
    )


def _patch_condition_permission(mocker, *, teams=None, instances=None):
    mocker.patch(
        "apps.monitor.views.monitor_condition.get_permission_rules",
        return_value={"team": teams or [], "instance": instances or []},
    )
    mocker.patch(
        "apps.monitor.views.monitor_condition.InstanceConfigService._get_actor_scope_groups",
        return_value=teams or [],
    )


class TestMonitorPolicyObjectPermission:
    def test_read_queryset_returns_only_authorized_team_policies(self, mocker):
        obj = _monitor_object("PolicyReadObj")
        allowed = _policy(obj, name="allowed", org=1)
        blocked = _policy(obj, name="blocked", org=2)
        _patch_policy_permission(mocker, teams=[1])

        view = MonitorPolicyViewSet()
        view.request = _request(current_team=1)
        view.action = "retrieve"

        ids = set(view.get_queryset().values_list("id", flat=True))
        assert allowed.id in ids
        assert blocked.id not in ids

    def test_write_queryset_requires_operate_instance_permission(self, mocker):
        obj = _monitor_object("PolicyOperateObj")
        allowed = _policy(obj, name="allowed-operate", org=9)
        blocked = _policy(obj, name="blocked-view", org=9)
        _patch_policy_permission(
            mocker,
            teams=[],
            instances=[
                {"id": allowed.id, "permission": ["View", "Operate"]},
                {"id": blocked.id, "permission": ["View"]},
            ],
        )

        view = MonitorPolicyViewSet()
        view.request = _request(current_team=1)
        view.action = "update"

        ids = set(view.get_queryset().values_list("id", flat=True))
        assert allowed.id in ids
        assert blocked.id not in ids

    def test_rejects_unauthorized_organizations_before_sync(self, mocker):
        _patch_policy_permission(mocker, teams=[1])
        view = MonitorPolicyViewSet()
        view.request = _request(current_team=1)

        with pytest.raises(BaseAppException):
            view._ensure_target_organizations([1, 2])

    def test_destroy_queryset_blocks_side_effect_targets(self, mocker):
        obj = _monitor_object("PolicyDestroyObj")
        blocked = _policy(obj, name="blocked-destroy", org=2)
        schedule = CrontabSchedule.objects.create(
            minute="*/5",
            hour="*",
            day_of_week="*",
            day_of_month="*",
            month_of_year="*",
        )
        PeriodicTask.objects.create(
            name=f"scan_policy_task_{blocked.id}",
            task="apps.monitor.tasks.monitor_policy.scan_policy_task",
            args=f"[{blocked.id}]",
            crontab=schedule,
        )
        MonitorAlert.objects.create(policy_id=blocked.id, monitor_instance_id="h1", status="new")
        _patch_policy_permission(mocker, teams=[1])

        view = MonitorPolicyViewSet()
        view.request = _request(current_team=1)
        view.action = "destroy"

        assert not view.get_queryset().filter(id=blocked.id).exists()
        assert PeriodicTask.objects.filter(name=f"scan_policy_task_{blocked.id}").exists()
        assert PolicyOrganization.objects.filter(policy_id=blocked.id, organization=2).exists()


class TestMonitorPolicyBulkAssetPermission:
    def test_get_bulk_policy_assets_rejects_cross_team_asset(self, mocker):
        obj = _monitor_object("PolicyBulkObj")
        inst = MonitorInstance.objects.create(id="('h1',)", name="h1", monitor_object=obj)
        MonitorInstanceOrganization.objects.create(monitor_instance=inst, organization=2)
        _patch_policy_permission(mocker, teams=[1])

        view = MonitorPolicyViewSet()
        view.request = _request(current_team=1)
        view.action = "bulk_create_from_templates"

        with pytest.raises(BaseAppException):
            view.get_bulk_policy_assets(obj.id, [inst.id])


class TestMonitorConditionObjectPermission:
    def test_read_queryset_returns_only_authorized_team_conditions(self, mocker):
        allowed = _condition(name="condition-allowed", org=1)
        blocked = _condition(name="condition-blocked", org=2)
        _patch_condition_permission(mocker, teams=[1])

        view = MonitorConditionViewSet()
        view.request = _request(current_team=1)
        view.action = "retrieve"

        ids = set(view.get_queryset().values_list("id", flat=True))
        assert allowed.id in ids
        assert blocked.id not in ids

    def test_write_queryset_requires_operate_instance_permission(self, mocker):
        allowed = _condition(name="condition-operate", org=9)
        blocked = _condition(name="condition-view", org=9)
        _patch_condition_permission(
            mocker,
            teams=[],
            instances=[
                {"id": allowed.id, "permission": ["View", "Operate"]},
                {"id": blocked.id, "permission": ["View"]},
            ],
        )

        view = MonitorConditionViewSet()
        view.request = _request(current_team=1)
        view.action = "update"

        ids = set(view.get_queryset().values_list("id", flat=True))
        assert allowed.id in ids
        assert blocked.id not in ids

    def test_rejects_unauthorized_organizations_before_sync(self, mocker):
        _patch_condition_permission(mocker, teams=[1])
        view = MonitorConditionViewSet()
        view.request = _request(current_team=1)

        with pytest.raises(BaseAppException):
            view._ensure_target_organizations([1, 2])

    def test_destroy_queryset_blocks_side_effect_targets(self, mocker):
        blocked = _condition(name="condition-destroy-blocked", org=2)
        _patch_condition_permission(mocker, teams=[1])

        view = MonitorConditionViewSet()
        view.request = _request(current_team=1)
        view.action = "destroy"

        assert not view.get_queryset().filter(id=blocked.id).exists()
        assert MonitorConditionOrganization.objects.filter(monitor_condition_id=blocked.id, organization=2).exists()
