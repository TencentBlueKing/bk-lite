"""日志告警链继承策略权限根的 current_team 回归测试。"""

import json
from types import SimpleNamespace

import pytest
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.log.models import CollectType
from apps.log.models.policy import Alert, AlertSnapshot, Event, EventRawData, Policy, PolicyOrganization
from apps.log.nats import log as log_nats
from apps.log.views import policy as policy_views
from apps.log.views.policy import AlertViewSet, EventRawDataViewSet, EventViewSet

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
    )
    PolicyOrganization.objects.bulk_create([PolicyOrganization(policy=policy, organization=organization) for organization in organizations])
    return policy


def _alert(policy, alert_id, collect_type=None):
    return Alert.objects.create(
        id=alert_id,
        policy=policy,
        collect_type=collect_type,
        source_id=f"source-{alert_id}",
        level="warning",
        status="new",
        start_event_time=timezone.now(),
    )


def _event(policy, alert, event_id):
    return Event.objects.create(
        id=event_id,
        policy=policy,
        alert=alert,
        source_id=alert.source_id,
        event_time=timezone.now(),
        level="warning",
    )


def _request(user, method="get", path="/api/v1/log/", data=None):
    factory = APIRequestFactory()
    request = getattr(factory, method)(path, data=data, format="json")
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=user)
    return request


def _patch_http_scope(mocker, scoped_ids, permission_data=None):
    mocker.patch(
        "apps.core.utils.current_team_scope.SystemMgmt.get_authorized_groups_scoped",
        return_value={"result": True, "data": list(scoped_ids)},
    )
    if permission_data is None:
        permission_data = {"all": {"team": [1, 2]}}
    return mocker.patch(
        "apps.log.views.policy.get_permissions_rules",
        return_value={"data": permission_data, "team": [1, 2]},
    )


@pytest.fixture
def scoped_superuser(authenticated_user, mocker):
    authenticated_user.is_superuser = True
    authenticated_user.save(update_fields=["is_superuser"])
    _patch_http_scope(mocker, [1])
    return authenticated_user


def test_superuser_alert_list_inherits_policy_current_team(scoped_superuser):
    current_policy = _policy("alert-current", [1])
    sibling_policy = _policy("alert-sibling", [2])
    current_alert = _alert(current_policy, "alert-current")
    _alert(sibling_policy, "alert-sibling")

    response = AlertViewSet.as_view({"get": "list"})(_request(scoped_superuser, path="/api/v1/log/alert/?page_size=100"))

    assert response.status_code == 200
    assert {item["id"] for item in json.loads(response.content)["data"]["items"]} == {current_alert.id}


def test_shared_policy_alert_projects_organizations_to_current_team(scoped_superuser):
    shared_policy = _policy("alert-shared", [1, 2])
    _alert(shared_policy, "alert-shared")

    response = AlertViewSet.as_view({"get": "list"})(_request(scoped_superuser, path="/api/v1/log/alert/?page_size=100"))

    assert response.status_code == 200
    [result] = json.loads(response.content)["data"]["items"]
    assert result["organizations"] == [1]


def test_regular_user_policy_scope_intersects_object_permission(authenticated_user, mocker):
    allowed = _policy("regular-allowed", [1])
    _policy("regular-denied", [1])
    _patch_http_scope(
        mocker,
        [1],
        permission_data={"None": {"instance": [{"id": allowed.id, "permission": ["View"]}]}},
    )
    request = SimpleNamespace(
        COOKIES={"current_team": "1", "include_children": "0"},
        user=authenticated_user,
    )

    helper = getattr(policy_views, "get_accessible_log_policy_queryset", None)
    assert callable(helper)
    assert list(helper(request).values_list("id", flat=True)) == [allowed.id]


def test_policy_scope_invalid_current_team_fails_closed(authenticated_user):
    request = SimpleNamespace(
        COOKIES={"current_team": "not-an-id", "include_children": "0"},
        user=authenticated_user,
    )

    assert not policy_views.get_accessible_log_policy_queryset(request).exists()


def test_foreign_alert_close_is_hidden_with_zero_side_effect(scoped_superuser):
    sibling_policy = _policy("close-sibling", [2])
    alert = _alert(sibling_policy, "close-sibling-alert")

    response = AlertViewSet.as_view({"post": "closed"})(
        _request(
            scoped_superuser,
            method="post",
            path=f"/api/v1/log/alert/{alert.id}/closed/",
        ),
        pk=alert.id,
    )

    assert response.status_code == 404
    alert.refresh_from_db()
    assert alert.status == "new"
    assert alert.operator is None


def test_event_policy_mismatch_with_alert_is_hidden(scoped_superuser):
    current_policy = _policy("event-current", [1])
    sibling_policy = _policy("event-sibling", [2])
    sibling_alert = _alert(sibling_policy, "event-sibling-alert")
    event = _event(current_policy, sibling_alert, "event-mismatch")

    response = EventViewSet.as_view({"get": "retrieve"})(
        _request(scoped_superuser, path=f"/api/v1/log/event/{event.id}/"),
        pk=event.id,
    )

    assert response.status_code == 404


def test_raw_data_policy_mismatch_is_hidden_before_s3_read(scoped_superuser, mocker):
    current_policy = _policy("raw-current", [1])
    sibling_policy = _policy("raw-sibling", [2])
    sibling_alert = _alert(sibling_policy, "raw-sibling-alert")
    event = _event(current_policy, sibling_alert, "raw-mismatch-event")
    mocker.patch(
        "apps.core.fields.s3_json_field.S3JSONField._upload_to_s3",
        return_value="raw-mismatch.json.gz",
    )
    raw_data = EventRawData.objects.create(event=event, data={"secret": "sibling"})
    s3_read = mocker.patch(
        "apps.core.fields.s3_json_field.S3JSONField._load_from_s3",
        return_value={"secret": "sibling"},
    )

    response = EventRawDataViewSet.as_view({"get": "retrieve"})(
        _request(scoped_superuser, path=f"/api/v1/log/event_raw_data/{raw_data.id}/"),
        pk=raw_data.id,
    )

    assert response.status_code == 404
    s3_read.assert_not_called()


def test_snapshot_policy_mismatch_is_hidden_before_s3_read(scoped_superuser, mocker):
    current_policy = _policy("snapshot-current", [1])
    sibling_policy = _policy("snapshot-sibling", [2])
    alert = _alert(current_policy, "snapshot-current-alert")
    mocker.patch(
        "apps.core.fields.s3_json_field.S3JSONField._upload_to_s3",
        return_value="snapshot-mismatch.json.gz",
    )
    AlertSnapshot.objects.create(
        alert=alert,
        policy=sibling_policy,
        source_id=alert.source_id,
        snapshots=[{"secret": "sibling"}],
    )
    s3_read = mocker.patch(
        "apps.core.fields.s3_json_field.S3JSONField._load_from_s3",
        return_value=[{"secret": "sibling"}],
    )

    response = AlertViewSet.as_view({"get": "get_snapshots"})(
        _request(scoped_superuser, path=f"/api/v1/log/alert/snapshots/{alert.id}/"),
        alert_id=alert.id,
    )

    assert response.status_code == 404
    s3_read.assert_not_called()


def test_nats_db_superuser_uses_authenticated_current_team_scope(mocker):
    collect_type = CollectType.objects.create(name="nats-superuser", collector="Vector", icon="")
    current_policy = _policy("nats-current", [1], collect_type)
    _policy("nats-sibling", [2], collect_type)
    mocker.patch(
        "apps.log.nats.log.SystemMgmt.get_authorized_groups_scoped",
        return_value={"result": True, "data": [1], "is_superuser": True},
    )
    mocker.patch("apps.log.nats.log.get_permissions_rules", return_value={"data": {}, "team": []})

    policy_ids, error = log_nats._get_log_policy_ids(
        str(collect_type.id),
        {
            "user": "admin",
            "domain": "domain.com",
            "team": 1,
            "include_children": False,
            "is_superuser": False,
        },
    )

    assert error is None
    assert policy_ids == [current_policy.id]


def test_nats_policy_scope_rejects_non_mapping_actor_context():
    policy_ids, error = log_nats._get_log_policy_ids("1", None)

    assert policy_ids == []
    assert error is not None


def test_nats_forged_sibling_current_team_fails_closed(mocker):
    collect_type = CollectType.objects.create(name="nats-forged", collector="Vector", icon="")
    sibling_policy = _policy("nats-forged-sibling", [2], collect_type)
    scoped_rpc = mocker.patch(
        "apps.log.nats.log.SystemMgmt.get_authorized_groups_scoped",
        return_value={"result": True, "data": [1], "is_superuser": True},
    )
    mocker.patch(
        "apps.log.nats.log.get_permissions_rules",
        return_value={"data": {str(collect_type.id): {"team": [2]}}, "team": [2]},
    )

    policy_ids, error = log_nats._get_log_policy_ids(
        str(collect_type.id),
        {
            "user": "ordinary-user",
            "domain": "domain.com",
            "team": 2,
            "include_children": False,
            "is_superuser": True,
        },
    )

    assert policy_ids == []
    assert error is not None
    assert sibling_policy.id not in policy_ids
    scoped_rpc.assert_called_once()
