"""告警组织在生成时快照，策略删除后仍按快照可见。"""

import pytest

from apps.monitor.models import MonitorAlert
from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.models.monitor_policy import MonitorPolicy, PolicyOrganization
from apps.monitor.services.alert_access import snapshot_policy_organization_ids
from apps.monitor.tasks.services.policy_scan.event_alert_manager import EventAlertManager

pytestmark = pytest.mark.django_db

BASE = "/api/v1/monitor"


def _policy(organizations=(1,)):
    monitor_object = MonitorObject.objects.create(name="org-snapshot-object", level="base")
    policy = MonitorPolicy.objects.create(
        monitor_object=monitor_object,
        name="org-snapshot-policy",
        organizations=list(organizations),
        algorithm="max",
        query_condition={},
        source={},
        group_by=[],
    )
    PolicyOrganization.objects.bulk_create(
        [PolicyOrganization(policy=policy, organization=organization) for organization in organizations]
    )
    return policy


@pytest.fixture
def grant_all(mocker, api_client):
    api_client.cookies["current_team"] = "1"
    mocker.patch(
        "apps.monitor.views.monitor_alert.get_permissions_rules",
        return_value={"data": {"all": {"team": [1]}}, "team": [1]},
    )
    mocker.patch(
        "apps.core.utils.current_team_scope.SystemMgmt.get_authorized_groups_scoped",
        return_value={"result": True, "data": [1]},
    )
    return api_client


def test_new_alert_snapshots_policy_organizations():
    policy = _policy((1, 3))
    manager = EventAlertManager(policy, {"h1": "host-1"}, [])
    alerts = manager._create_alerts_from_events(
        [
            {
                "monitor_instance_id": "h1",
                "metric_instance_id": "('h1',)",
                "dimensions": {},
                "level": "warning",
                "value": 1,
                "content": "cpu high",
            }
        ]
    )

    assert snapshot_policy_organization_ids(policy) == [1, 3]
    assert alerts[0].organizations == [1, 3]


def test_deleted_policy_alert_remains_visible(grant_all):
    policy = _policy((1,))
    alert = MonitorAlert.objects.create(
        policy_id=policy.id,
        monitor_instance_id="h1",
        status="closed",
        organizations=[1],
    )
    policy_id = policy.id
    PolicyOrganization.objects.filter(policy=policy).delete()
    policy.delete()

    response = grant_all.get(f"{BASE}/api/monitor_alert/?page_size=100")

    assert response.status_code == 200
    results = response.json()["data"]["results"]
    assert {item["id"] for item in results} == {alert.id}
    assert results[0]["policy_id"] == policy_id
    assert results[0]["policy"] is None
    assert results[0]["organizations"] == [1]


def test_sibling_org_snapshot_is_hidden(grant_all):
    MonitorAlert.objects.create(
        policy_id=0,
        monitor_instance_id="foreign",
        status="closed",
        organizations=[2],
    )

    response = grant_all.get(f"{BASE}/api/monitor_alert/?page_size=100")

    assert response.status_code == 200
    assert response.json()["data"]["results"] == []
