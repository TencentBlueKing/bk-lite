"""Issue #4085: policy and scheduled-task writes must commit atomically."""

import pytest
from django.db import DatabaseError
from django_celery_beat.models import CrontabSchedule, PeriodicTask
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.log.models.policy import Policy, PolicyOrganization
from apps.log.views.policy import PolicyViewSet


def _policy_payload(name, organizations):
    return {
        "name": name,
        "alert_type": "keyword",
        "alert_name": name,
        "alert_level": "warning",
        "alert_condition": {"query": "error"},
        "schedule": {"type": "min", "value": 5},
        "period": {"type": "min", "value": 5},
        "organizations": organizations,
    }


def _allow_policy_operations(mocker, policy_id=None, teams=None):
    instance_permissions = []
    if policy_id is not None:
        instance_permissions.append({"id": policy_id, "permission": ["View", "Operate"]})
    mocker.patch(
        "apps.log.views.policy.get_permissions_rules",
        return_value={
            "data": {"None": {"instance": instance_permissions}},
            "team": teams or [1],
        },
    )
    mocker.patch(
        "apps.core.utils.current_team_scope.SystemMgmt.get_authorized_groups_scoped",
        return_value={"result": True, "data": [1]},
    )
    mocker.patch(
        "apps.core.utils.current_team_scope.SystemMgmt.get_assignable_groups",
        return_value={"result": True, "data": [1, 2]},
    )


def _fail_periodic_task_create(mocker):
    mocker.patch(
        "apps.log.views.policy.PeriodicTask.objects.create",
        side_effect=DatabaseError("injected periodic-task write failure"),
    )


def _call_policy_view(http_method, path, data, user, **kwargs):
    request = getattr(APIRequestFactory(), http_method)(path, data=data, format="json")
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=user)
    action = {"post": "create", "put": "update", "patch": "partial_update"}[http_method]
    view = PolicyViewSet.as_view({http_method: action})
    return view(request, **kwargs)


@pytest.mark.django_db
def test_policy_create_rolls_back_when_periodic_task_write_fails(authenticated_user, mocker):
    _allow_policy_operations(mocker)
    _fail_periodic_task_create(mocker)

    with pytest.raises(DatabaseError, match="injected periodic-task write failure"):
        _call_policy_view(
            "post",
            "/api/v1/log/policy/",
            _policy_payload("atomic-create", [1]),
            authenticated_user,
        )

    assert not Policy.objects.filter(name="atomic-create").exists()
    assert not PolicyOrganization.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize("http_method", ["put", "patch"])
def test_policy_update_rolls_back_when_periodic_task_write_fails(
    authenticated_user,
    mocker,
    http_method,
):
    policy_data = _policy_payload("atomic-update", [1])
    policy_data.pop("organizations")
    policy = Policy.objects.create(**policy_data)
    PolicyOrganization.objects.create(policy=policy, organization=1)
    old_crontab = CrontabSchedule.objects.create(minute="*/1")
    PeriodicTask.objects.create(
        name=f"log_policy_task_{policy.id}",
        task="apps.log.tasks.policy.scan_log_policy_task",
        crontab=old_crontab,
    )
    _allow_policy_operations(mocker, policy.id, teams=[1, 2])
    _fail_periodic_task_create(mocker)

    payload = _policy_payload("atomic-update", [2])
    payload["alert_name"] = "changed-name"

    with pytest.raises(DatabaseError, match="injected periodic-task write failure"):
        _call_policy_view(
            http_method,
            f"/api/v1/log/policy/{policy.id}/",
            payload,
            authenticated_user,
            pk=policy.id,
        )

    policy.refresh_from_db()
    assert policy.alert_name == "atomic-update"
    assert list(policy.policyorganization_set.values_list("organization", flat=True)) == [1]
    restored_task = PeriodicTask.objects.get(name=f"log_policy_task_{policy.id}")
    assert restored_task.crontab_id == old_crontab.id
