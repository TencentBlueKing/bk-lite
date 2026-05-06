import pytest
from django.utils import timezone
from rest_framework import status

from apps.log.models.policy import Alert, Event, EventRawData, Policy, PolicyOrganization


def _mock_policy_permission(mocker, policy_id=None, organization=1):
    instance_permissions = []
    if policy_id is not None:
        instance_permissions.append({"id": policy_id, "permission": ["View", "Operate"]})

    mocker.patch(
        "apps.log.views.policy.get_permissions_rules",
        return_value={
            "data": {
                "None": {
                    "instance": instance_permissions,
                }
            },
            "team": [organization],
        },
    )


def _create_policy(name, organization):
    policy = Policy.objects.create(
        name=name,
        alert_type="keyword",
        alert_name=name,
        alert_level="warning",
        alert_condition={"query": "error"},
        schedule={"type": "min", "value": 5},
        period={"type": "min", "value": 5},
    )
    PolicyOrganization.objects.create(policy=policy, organization=organization)
    return policy


def _create_alert_with_event(policy, alert_id, event_id):
    alert = Alert.objects.create(
        id=alert_id,
        policy=policy,
        source_id=f"source-{alert_id}",
        level="warning",
        content="raw log alert",
        start_event_time=timezone.now(),
    )
    Event.objects.create(
        id=event_id,
        policy=policy,
        alert=alert,
        source_id=alert.source_id,
        event_time=timezone.now(),
        level="warning",
        content="raw event content",
    )
    return alert


@pytest.mark.django_db
def test_alert_retrieve_hides_unauthorized_policy_alert(api_client, authenticated_user, mocker):
    policy = _create_policy("denied-policy", organization=2)
    alert = _create_alert_with_event(policy, "alert-denied", "event-denied")
    _mock_policy_permission(mocker, organization=1)

    api_client.cookies["current_team"] = "1"
    response = api_client.get(f"/api/v1/log/alert/{alert.id}/")

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_event_retrieve_hides_unauthorized_policy_event(api_client, authenticated_user, mocker):
    policy = _create_policy("denied-policy", organization=2)
    _create_alert_with_event(policy, "alert-denied", "event-denied")
    _mock_policy_permission(mocker, organization=1)

    api_client.cookies["current_team"] = "1"
    response = api_client.get("/api/v1/log/event/event-denied/")

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_last_event_requires_alert_policy_permission(api_client, authenticated_user, mocker):
    policy = _create_policy("denied-policy", organization=2)
    alert = _create_alert_with_event(policy, "alert-denied", "event-denied")
    _mock_policy_permission(mocker, organization=1)

    api_client.cookies["current_team"] = "1"
    response = api_client.get(f"/api/v1/log/alert/last_event/?alert_id={alert.id}")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["result"] is False


@pytest.mark.django_db
def test_event_raw_data_by_event_id_requires_policy_permission(api_client, authenticated_user, mocker):
    policy = _create_policy("denied-policy", organization=2)
    _create_alert_with_event(policy, "alert-denied", "event-denied")
    EventRawData.objects.create(event_id="event-denied", data="")
    _mock_policy_permission(mocker, organization=1)

    api_client.cookies["current_team"] = "1"
    response = api_client.get("/api/v1/log/event_raw_data/by_event_id/?event_id=event-denied")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["result"] is False


@pytest.mark.django_db
def test_event_retrieve_allows_authorized_policy_event(api_client, authenticated_user, mocker):
    policy = _create_policy("allowed-policy", organization=1)
    _create_alert_with_event(policy, "alert-allowed", "event-allowed")
    _mock_policy_permission(mocker, policy_id=policy.id, organization=1)

    api_client.cookies["current_team"] = "1"
    response = api_client.get("/api/v1/log/event/event-allowed/")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["data"]["id"] == "event-allowed"
