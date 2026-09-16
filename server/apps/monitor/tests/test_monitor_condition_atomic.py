"""Issue #5496: 监控条件本体与组织关系必须同一事务提交。"""

import pytest
from django.db import DatabaseError
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.monitor.models.monitor_condition import MonitorCondition, MonitorConditionOrganization
from apps.monitor.views.monitor_condition import MonitorConditionViewSet
from apps.system_mgmt.models import Group

pytestmark = pytest.mark.django_db


def _patch_current_team_scope(mocker, *, teams=(1,), assignable=(1,)):
    Group.objects.get_or_create(id=1, defaults={"name": "Default Team", "parent_id": 0})
    mocker.patch(
        "apps.core.utils.current_team_scope.SystemMgmt.get_authorized_groups_scoped",
        return_value={"result": True, "data": list(teams)},
    )
    mocker.patch(
        "apps.core.utils.current_team_scope.SystemMgmt.get_assignable_groups",
        return_value={"result": True, "data": list(assignable)},
    )


def _fail_organization_bulk_create(mocker):
    mocker.patch(
        "apps.monitor.views.monitor_condition.MonitorConditionOrganization.objects.bulk_create",
        side_effect=DatabaseError("injected organization write failure"),
    )


def _call_condition_view(http_method, path, user, data=None, **kwargs):
    request = getattr(APIRequestFactory(), http_method)(path, data=data or {}, format="json")
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=user)
    action = {"post": "create", "put": "update", "patch": "partial_update", "delete": "destroy"}[http_method]
    view = MonitorConditionViewSet.as_view({http_method: action})
    return view(request, **kwargs)


class TestMonitorConditionAtomic:
    def test_create_rolls_back_condition_when_organization_write_fails(self, authenticated_user, mocker):
        _patch_current_team_scope(mocker, assignable=(1, 3, 4))
        _fail_organization_bulk_create(mocker)

        with pytest.raises(DatabaseError, match="injected organization write failure"):
            _call_condition_view(
                "post",
                "/api/v1/monitor/api/monitor_condition/",
                authenticated_user,
                {"name": "atomic-create", "condition": {"x": 1}, "organizations": [3, 4]},
            )

        assert not MonitorCondition.objects.filter(name="atomic-create").exists()
        assert not MonitorConditionOrganization.objects.filter(organization__in=[3, 4]).exists()

    def test_full_update_keeps_old_organizations_when_write_fails(self, authenticated_user, mocker):
        _patch_current_team_scope(mocker, assignable=(1, 3))
        cond = MonitorCondition.objects.create(name="atomic-update", description="old", condition={})
        MonitorConditionOrganization.objects.create(monitor_condition=cond, organization=1)
        mocker.patch(
            "apps.monitor.views.monitor_condition.get_permission_rules",
            return_value={"team": [1], "instance": []},
        )
        _fail_organization_bulk_create(mocker)

        with pytest.raises(DatabaseError, match="injected organization write failure"):
            _call_condition_view(
                "put",
                f"/api/v1/monitor/api/monitor_condition/{cond.id}/",
                authenticated_user,
                {
                    "name": "atomic-update-changed",
                    "description": "new",
                    "condition": {"y": 2},
                    "organizations": [3],
                },
                pk=cond.id,
            )

        cond.refresh_from_db()
        assert cond.name == "atomic-update"
        assert cond.description == "old"
        orgs = set(
            MonitorConditionOrganization.objects.filter(monitor_condition_id=cond.id).values_list(
                "organization",
                flat=True,
            )
        )
        assert orgs == {1}

    def test_partial_update_keeps_old_organizations_when_write_fails(self, authenticated_user, mocker):
        _patch_current_team_scope(mocker, assignable=(1, 3))
        cond = MonitorCondition.objects.create(name="atomic-patch", description="old", condition={})
        MonitorConditionOrganization.objects.create(monitor_condition=cond, organization=1)
        mocker.patch(
            "apps.monitor.views.monitor_condition.get_permission_rules",
            return_value={"team": [1], "instance": []},
        )
        _fail_organization_bulk_create(mocker)

        with pytest.raises(DatabaseError, match="injected organization write failure"):
            _call_condition_view(
                "patch",
                f"/api/v1/monitor/api/monitor_condition/{cond.id}/",
                authenticated_user,
                {"description": "new", "organizations": [3]},
                pk=cond.id,
            )

        cond.refresh_from_db()
        assert cond.description == "old"
        orgs = set(
            MonitorConditionOrganization.objects.filter(monitor_condition_id=cond.id).values_list(
                "organization",
                flat=True,
            )
        )
        assert orgs == {1}

    def test_destroy_keeps_condition_and_organizations_when_delete_fails(self, authenticated_user, mocker):
        _patch_current_team_scope(mocker)
        cond = MonitorCondition.objects.create(name="atomic-destroy", condition={})
        MonitorConditionOrganization.objects.create(monitor_condition=cond, organization=1)
        mocker.patch(
            "apps.monitor.views.monitor_condition.get_permission_rules",
            return_value={"team": [], "instance": [{"id": cond.id, "permission": ["View", "Operate"]}]},
        )
        mocker.patch.object(MonitorCondition, "delete", side_effect=DatabaseError("injected destroy failure"))

        with pytest.raises(DatabaseError, match="injected destroy failure"):
            _call_condition_view(
                "delete",
                f"/api/v1/monitor/api/monitor_condition/{cond.id}/",
                authenticated_user,
                pk=cond.id,
            )

        assert MonitorCondition.objects.filter(id=cond.id).exists()
        assert MonitorConditionOrganization.objects.filter(monitor_condition_id=cond.id, organization=1).exists()
