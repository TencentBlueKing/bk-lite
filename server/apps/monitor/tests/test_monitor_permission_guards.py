from types import SimpleNamespace

import pytest
from django_celery_beat.models import CrontabSchedule, PeriodicTask

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.models import MonitorAlert, MonitorObjectOrganizationRule
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
from apps.monitor.views.monitor_instance import _ensure_operate_instances
from apps.monitor.views.monitor_policy import MonitorPolicyViewSet
from apps.monitor.views.organization_rule import MonitorObjectOrganizationRuleViewSet

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
    _patch_scope_contract(mocker, teams=[1], assignable=[1])
    mocker.patch(
        "apps.monitor.views.monitor_policy.get_permission_rules",
        return_value={"team": teams or [], "instance": instances or []},
    )
    mocker.patch(
        "apps.monitor.views.monitor_policy.InstanceConfigService._get_actor_scope_groups",
        return_value=teams or [],
    )


def _patch_condition_permission(mocker, *, teams=None, instances=None):
    _patch_scope_contract(mocker, teams=[1], assignable=[1])
    mocker.patch(
        "apps.monitor.views.monitor_condition.get_permission_rules",
        return_value={"team": teams or [], "instance": instances or []},
    )


def _patch_scope_contract(mocker, *, teams=None, assignable=None):
    mocker.patch(
        "apps.core.utils.current_team_scope.SystemMgmt.get_authorized_groups_scoped",
        return_value={"result": True, "data": teams or []},
    )
    mocker.patch(
        "apps.core.utils.current_team_scope.SystemMgmt.get_assignable_groups",
        return_value={"result": True, "data": assignable or []},
    )


class TestMonitorPolicyObjectPermission:
    def test_superuser_queryset_stays_in_current_team(self, mocker):
        obj = _monitor_object("PolicySuperuserScopeObj")
        allowed = _policy(obj, name="superuser-current", org=1)
        blocked = _policy(obj, name="superuser-sibling", org=2)
        _patch_policy_permission(mocker, teams=[1])

        view = MonitorPolicyViewSet()
        view.request = _request(user=_user(is_superuser=True), current_team=1)
        view.action = "retrieve"

        ids = set(view.get_queryset().values_list("id", flat=True))
        assert allowed.id in ids
        assert blocked.id not in ids

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
        allowed = _policy(obj, name="allowed-operate", org=1)
        blocked = _policy(obj, name="blocked-view", org=1)
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
        _patch_scope_contract(mocker, teams=[1], assignable=[1, 2])
        view = MonitorPolicyViewSet()
        view.request = _request(current_team=1)

        with pytest.raises(BaseAppException):
            view._ensure_target_organizations([3])

    def test_allows_assigning_current_object_to_authorized_sibling(self, mocker):
        _patch_policy_permission(mocker, teams=[1])
        _patch_scope_contract(mocker, teams=[1], assignable=[1, 2])
        view = MonitorPolicyViewSet()
        view.request = _request(current_team=1)

        assert view._ensure_target_organizations([2]) is None

    def test_superuser_cannot_assign_unauthorized_organization(self, mocker):
        _patch_policy_permission(mocker, teams=[1])
        _patch_scope_contract(mocker, teams=[1], assignable=[1, 2])
        view = MonitorPolicyViewSet()
        view.request = _request(user=_user(is_superuser=True), current_team=1)

        with pytest.raises(BaseAppException):
            view._ensure_target_organizations([3])

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


class TestMonitorInstanceObjectPermission:
    def test_superuser_cannot_operate_sibling_instance(self, mocker):
        obj = _monitor_object("InstanceSuperuserScopeObj")
        inst = MonitorInstance.objects.create(id="('sibling',)", name="sibling", monitor_object=obj)
        MonitorInstanceOrganization.objects.create(monitor_instance=inst, organization=2)
        _patch_scope_contract(mocker, teams=[1], assignable=[1, 2])
        mocker.patch(
            "apps.monitor.services.node_mgmt.get_permission_rules",
            return_value={"team": [1], "instance": []},
        )
        request = _request(user=_user(is_superuser=True), current_team=1)

        with pytest.raises(BaseAppException):
            _ensure_operate_instances(request, [inst.id])


class TestOrganizationRuleObjectPermission:
    def test_superuser_queryset_stays_in_current_team(self, mocker):
        obj = _monitor_object("RuleSuperuserScopeObj")
        allowed = MonitorObjectOrganizationRule.objects.create(
            monitor_object=obj,
            name="rule-current",
            organizations=[1],
            rule={},
        )
        blocked = MonitorObjectOrganizationRule.objects.create(
            monitor_object=obj,
            name="rule-sibling",
            organizations=[2],
            rule={},
        )
        _patch_scope_contract(mocker, teams=[1], assignable=[1, 2])

        view = MonitorObjectOrganizationRuleViewSet()
        view.request = _request(user=_user(is_superuser=True), current_team=1)
        view.action = "retrieve"

        ids = set(view.get_queryset().values_list("id", flat=True))
        assert allowed.id in ids
        assert blocked.id not in ids

    def test_rule_bound_to_sibling_instance_is_hidden(self, mocker):
        obj = _monitor_object("RuleBoundInstanceScopeObj")
        sibling = MonitorInstance.objects.create(id="('rule-sibling',)", name="sibling", monitor_object=obj)
        MonitorInstanceOrganization.objects.create(monitor_instance=sibling, organization=2)
        rule = MonitorObjectOrganizationRule.objects.create(
            monitor_object=obj,
            monitor_instance_id=sibling.id,
            name="rule-current-org-sibling-instance",
            organizations=[1],
            rule={},
        )
        _patch_scope_contract(mocker, teams=[1], assignable=[1, 2])
        mocker.patch(
            "apps.monitor.services.node_mgmt.get_permission_rules",
            return_value={"team": [1], "instance": []},
        )

        view = MonitorObjectOrganizationRuleViewSet()
        view.request = _request(user=_user(is_superuser=True), current_team=1)
        view.action = "retrieve"

        assert not view.get_queryset().filter(id=rule.id).exists()


class TestMonitorConditionObjectPermission:
    def test_superuser_queryset_stays_in_current_team(self, mocker):
        allowed = _condition(name="condition-superuser-current", org=1)
        blocked = _condition(name="condition-superuser-sibling", org=2)
        _patch_condition_permission(mocker, teams=[1])

        view = MonitorConditionViewSet()
        view.request = _request(user=_user(is_superuser=True), current_team=1)
        view.action = "retrieve"

        ids = set(view.get_queryset().values_list("id", flat=True))
        assert allowed.id in ids
        assert blocked.id not in ids

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
        allowed = _condition(name="condition-operate", org=1)
        blocked = _condition(name="condition-view", org=1)
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
