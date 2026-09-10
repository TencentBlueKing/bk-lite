"""日志告警组织在生成时快照，策略删除后仍按快照可见。"""

import json

import pytest
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.log.models.policy import Alert, Event, Policy, PolicyOrganization
from apps.log.views.policy import AlertViewSet, PolicyViewSet
from apps.log.tasks.services.policy_scan import LogPolicyScan

pytestmark = pytest.mark.django_db


def _policy(name, organizations, collect_type=None):
    policy = Policy.objects.create(
        name=name,
        collect_type=collect_type,
        alert_type="keyword",
        alert_name=name,
        alert_level="warning",
        alert_condition={"query": "error"},
        schedule={"type": "min", "value": 5},
        period={"type": "min", "value": 5},
        notice=False,
    )
    PolicyOrganization.objects.bulk_create(
        [PolicyOrganization(policy=policy, organization=organization) for organization in organizations]
    )
    return policy


def _request(user, method="get", path="/api/v1/log/alert/", data=None):
    factory = APIRequestFactory()
    request = getattr(factory, method)(path, data=data, format="json")
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=user)
    return request


@pytest.fixture
def grant_all(authenticated_user, mocker):
    authenticated_user.is_superuser = True
    authenticated_user.save(update_fields=["is_superuser"])
    mocker.patch(
        "apps.core.utils.current_team_scope.SystemMgmt.get_authorized_groups_scoped",
        return_value={"result": True, "data": [1]},
    )
    mocker.patch(
        "apps.log.views.policy.get_permissions_rules",
        return_value={"data": {"all": {"team": [1]}}, "team": [1]},
    )
    return authenticated_user


def test_new_log_alert_snapshots_policy_organizations():
    policy = _policy("snap-policy", [1, 4])
    scan = LogPolicyScan(policy, scan_time=timezone.now())
    assert scan.organizations == [1, 4]


def test_deleted_policy_log_alert_remains_visible(grant_all):
    policy = _policy("keep-alert", [1])
    alert = Alert.objects.create(
        id="keep-alert-1",
        policy=policy,
        source_id="src-1",
        level="warning",
        status="new",
        start_event_time=timezone.now(),
        organizations=[1],
    )
    Event.objects.create(
        id="keep-event-1",
        policy=policy,
        alert=alert,
        source_id=alert.source_id,
        event_time=timezone.now(),
        level="warning",
    )

    request = _request(grant_all, method="delete", path=f"/api/v1/log/policy/{policy.id}/")
    response = PolicyViewSet.as_view({"delete": "destroy"})(request, pk=policy.id)
    assert response.status_code == 204

    alert.refresh_from_db()
    assert alert.policy_id is None
    assert alert.status == "closed"
    assert alert.organizations == [1]

    list_request = _request(grant_all)
    listed = AlertViewSet.as_view({"get": "list"})(list_request)
    assert listed.status_code == 200
    items = json.loads(listed.content)["data"]["items"]
    assert {item["id"] for item in items} == {alert.id}
    assert items[0]["organizations"] == [1]
    assert items[0]["policy_name"] == ""
    closed_events = list(Event.objects.filter(alert=alert, action="closed"))
    assert len(closed_events) == 1
    assert grant_all.username in closed_events[0].content
