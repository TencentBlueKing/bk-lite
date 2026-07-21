"""监控告警链继承策略权限根的 current_team 回归测试。"""

from types import SimpleNamespace

import pytest

from apps.monitor.models import MonitorAlert, MonitorAlertMetricSnapshot, MonitorEvent, MonitorEventRawData, PolicyInstanceBaseline
from apps.monitor.models.monitor_object import MonitorInstance, MonitorObject
from apps.monitor.models.monitor_policy import MonitorPolicy, PolicyOrganization
from apps.monitor.nats import monitor as monitor_nats

pytestmark = pytest.mark.django_db

BASE = "/api/v1/monitor"


def _policy(name, organizations):
    monitor_object = MonitorObject.objects.create(name=f"{name}-object", level="base")
    policy = MonitorPolicy.objects.create(
        monitor_object=monitor_object,
        name=name,
        organizations=list(organizations),
        algorithm="max",
        query_condition={"type": "pmq", "query": "up"},
        source={},
        group_by=[],
    )
    PolicyOrganization.objects.bulk_create([PolicyOrganization(policy=policy, organization=organization) for organization in organizations])
    return policy


@pytest.fixture
def scoped_superuser(api_client, authenticated_user, mocker):
    authenticated_user.is_superuser = True
    authenticated_user.save(update_fields=["is_superuser"])
    api_client.cookies["current_team"] = "1"
    mocker.patch(
        "apps.core.utils.current_team_scope.SystemMgmt.get_authorized_groups_scoped",
        return_value={"result": True, "data": [1]},
    )
    mocker.patch(
        "apps.monitor.views.monitor_alert.get_permissions_rules",
        return_value={"data": {"all": {"team": [1]}}, "team": [1]},
    )
    return api_client


def test_superuser_alert_list_inherits_policy_current_team(scoped_superuser):
    current_policy = _policy("current-policy", [1])
    sibling_policy = _policy("sibling-policy", [2])
    current_alert = MonitorAlert.objects.create(
        policy_id=current_policy.id,
        monitor_instance_id="current-instance",
    )
    MonitorAlert.objects.create(
        policy_id=sibling_policy.id,
        monitor_instance_id="sibling-instance",
    )

    response = scoped_superuser.get(f"{BASE}/api/monitor_alert/?page_size=100")

    assert response.status_code == 200
    results = response.json()["data"]["results"]
    assert {item["id"] for item in results} == {current_alert.id}


def test_shared_policy_projection_hides_sibling_organization(scoped_superuser):
    shared_policy = _policy("shared-policy", [1, 2])
    MonitorAlert.objects.create(
        policy_id=shared_policy.id,
        monitor_instance_id="shared-instance",
    )

    response = scoped_superuser.get(f"{BASE}/api/monitor_alert/?page_size=100")

    assert response.status_code == 200
    [result] = response.json()["data"]["results"]
    assert result["policy"]["organizations"] == [1]


def test_foreign_alert_update_is_hidden_and_has_zero_side_effect(scoped_superuser):
    sibling_policy = _policy("sibling-update-policy", [2])
    alert = MonitorAlert.objects.create(
        policy_id=sibling_policy.id,
        monitor_instance_id="sibling-update-instance",
        status="new",
    )

    response = scoped_superuser.patch(
        f"{BASE}/api/monitor_alert/{alert.id}/",
        {"status": "closed"},
        format="json",
    )

    assert response.status_code == 404
    alert.refresh_from_db()
    assert alert.status == "new"
    assert alert.operation_logs == []


def test_snapshot_policy_mismatch_is_hidden_before_s3_read(scoped_superuser, mocker):
    current_policy = _policy("snapshot-current-policy", [1])
    sibling_policy = _policy("snapshot-sibling-policy", [2])
    alert = MonitorAlert.objects.create(
        policy_id=current_policy.id,
        monitor_instance_id="snapshot-instance",
    )
    MonitorAlertMetricSnapshot.objects.create(
        alert=alert,
        policy_id=sibling_policy.id,
        monitor_instance_id=alert.monitor_instance_id,
    )
    s3_read = mocker.patch(
        "apps.core.fields.s3_json_field.S3JSONField._load_from_s3",
        return_value=[{"secret": "sibling"}],
    )

    response = scoped_superuser.get(f"{BASE}/api/monitor_alert/snapshots/{alert.id}/")

    assert response.status_code == 404
    s3_read.assert_not_called()


def test_event_policy_mismatch_is_hidden(scoped_superuser):
    current_policy = _policy("event-current-policy", [1])
    sibling_policy = _policy("event-sibling-policy", [2])
    alert = MonitorAlert.objects.create(
        policy_id=current_policy.id,
        monitor_instance_id="event-instance",
    )
    MonitorEvent.objects.create(
        id="event-policy-mismatch",
        alert=alert,
        policy_id=sibling_policy.id,
        monitor_instance_id=alert.monitor_instance_id,
        level="critical",
    )

    response = scoped_superuser.get(f"{BASE}/api/monitor_event/query/{alert.id}/")

    assert response.status_code == 200
    assert response.json()["data"] == {"count": 0, "results": []}


def test_raw_data_mismatch_is_hidden_before_s3_read(scoped_superuser, mocker):
    current_policy = _policy("raw-current-policy", [1])
    sibling_policy = _policy("raw-sibling-policy", [2])
    sibling_alert = MonitorAlert.objects.create(
        policy_id=sibling_policy.id,
        monitor_instance_id="raw-instance",
    )
    event = MonitorEvent.objects.create(
        id="raw-policy-mismatch",
        alert=sibling_alert,
        policy_id=current_policy.id,
        monitor_instance_id=sibling_alert.monitor_instance_id,
        level="critical",
    )
    MonitorEventRawData.objects.create(event=event)
    s3_read = mocker.patch(
        "apps.core.fields.s3_json_field.S3JSONField._load_from_s3",
        return_value={"secret": "sibling"},
    )

    response = scoped_superuser.get(f"{BASE}/api/monitor_event/raw_data/{event.id}/")

    assert response.status_code == 404
    s3_read.assert_not_called()


def test_nats_statistics_superuser_inherits_policy_current_team(mocker):
    current_policy = _policy("nats-current-policy", [1])
    sibling_policy = _policy("nats-sibling-policy", [2])
    current_alert = MonitorAlert.objects.create(policy_id=current_policy.id)
    sibling_alert = MonitorAlert.objects.create(policy_id=sibling_policy.id)
    MonitorEvent.objects.create(
        id="nats-current-event",
        policy_id=current_policy.id,
        monitor_instance_id="nats-current-instance",
        level="info",
    )
    MonitorEvent.objects.create(
        id="nats-mismatch-event",
        alert=sibling_alert,
        policy_id=current_policy.id,
        monitor_instance_id="nats-current-instance",
        level="info",
    )
    MonitorEvent.objects.create(
        id="nats-sibling-event",
        policy_id=sibling_policy.id,
        monitor_instance_id="nats-sibling-instance",
        level="info",
    )
    mocker.patch(
        "apps.core.fields.s3_json_field.S3JSONField._upload_to_s3",
        return_value="nats-statistics.json.gz",
    )
    MonitorAlertMetricSnapshot.objects.create(
        alert=current_alert,
        policy_id=current_policy.id,
        monitor_instance_id="nats-current-instance",
    )
    MonitorAlertMetricSnapshot.objects.create(
        alert=sibling_alert,
        policy_id=current_policy.id,
        monitor_instance_id="nats-sibling-instance",
    )
    PolicyInstanceBaseline.objects.create(
        policy=current_policy,
        monitor_instance_id="nats-current-instance",
        metric_instance_id="nats-current-metric",
    )
    PolicyInstanceBaseline.objects.create(
        policy=sibling_policy,
        monitor_instance_id="nats-sibling-instance",
        metric_instance_id="nats-sibling-metric",
    )
    mocker.patch(
        "apps.monitor.nats.monitor.get_permissions_rules",
        return_value={"data": {"all": {"team": [1]}}, "team": [1]},
    )

    response = monitor_nats.get_monitor_statistics(
        user_info={
            "user": SimpleNamespace(username="admin", domain="domain.com"),
            "team": 1,
            "is_superuser": True,
            "include_children": False,
        }
    )

    assert response["result"] is True
    assert response["data"]["policy_total"] == 1
    assert response["data"]["alert_history"] == 1
    assert response["data"]["event_total"] == 1
    assert response["data"]["alert_snapshot_total"] == 1
    assert response["data"]["no_data_baseline_total"] == 1


def test_nats_statistics_missing_actor_scope_fails_closed():
    _policy("nats-missing-scope-policy", [1])

    response = monitor_nats.get_monitor_statistics(user_info={})

    assert response["result"] is False
    assert response["data"] == {}


def _patch_nats_alert_permissions(mocker):
    mocker.patch(
        "apps.monitor.nats.monitor.get_permission_rules",
        return_value={"team": [1], "instance": []},
    )
    mocker.patch(
        "apps.monitor.nats.monitor.get_permissions_rules",
        return_value={"data": {"all": {"team": [1]}}, "team": [1]},
    )
    mocker.patch(
        "apps.monitor.nats.monitor.permission_filter",
        side_effect=lambda model, permission, **kwargs: model.objects.all(),
    )
    return {
        "user": SimpleNamespace(username="admin", domain="domain.com"),
        "team": 1,
        "is_superuser": True,
        "include_children": False,
    }


def test_nats_alert_segments_also_inherit_policy_root(mocker):
    from datetime import datetime, timezone

    current_policy = _policy("segment-current-policy", [1])
    sibling_policy = _policy("segment-sibling-policy", [2])
    instance = MonitorInstance.objects.create(
        id="segment-instance",
        name="segment-instance",
        monitor_object=current_policy.monitor_object,
        is_active=True,
    )
    event_time = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    current_alert = MonitorAlert.objects.create(
        policy_id=current_policy.id,
        monitor_instance_id=instance.id,
        start_event_time=event_time,
    )
    MonitorAlert.objects.create(
        policy_id=sibling_policy.id,
        monitor_instance_id=instance.id,
        start_event_time=event_time,
    )
    user_info = _patch_nats_alert_permissions(mocker)

    response = monitor_nats.query_monitor_alert_segments(
        {
            "monitor_obj_id": current_policy.monitor_object_id,
            "start": "2026-01-01 00:00:00",
            "end": "2026-01-02 00:00:00",
        },
        user_info=user_info,
    )

    assert response["result"] is True
    assert response["data"]["count"] == 1
    assert response["data"]["items"][0]["id"] == current_alert.id


def test_nats_latest_alerts_also_inherit_policy_root(mocker):
    current_policy = _policy("latest-current-policy", [1])
    sibling_policy = _policy("latest-sibling-policy", [2])
    instance = MonitorInstance.objects.create(
        id="latest-instance",
        name="latest-instance",
        monitor_object=current_policy.monitor_object,
        is_active=True,
    )
    current_alert = MonitorAlert.objects.create(
        policy_id=current_policy.id,
        monitor_instance_id=instance.id,
        status="new",
    )
    MonitorAlert.objects.create(
        policy_id=sibling_policy.id,
        monitor_instance_id=instance.id,
        status="new",
    )
    user_info = _patch_nats_alert_permissions(mocker)

    response = monitor_nats.query_latest_active_alerts(
        {"monitor_obj_id": current_policy.monitor_object_id},
        user_info=user_info,
    )

    assert response["result"] is True
    assert response["data"]["count"] == 1
    assert response["data"]["items"][0]["id"] == current_alert.id
