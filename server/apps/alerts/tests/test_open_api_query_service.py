import datetime
from types import SimpleNamespace

import pytest
from django.utils import timezone

from apps.alerts.constants.constants import SessionStatus
from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Alert, Event
from apps.alerts.open_api.auth import AlertsOpenAPIContext
from apps.alerts.open_api.errors import AlertsOpenAPIError
from apps.alerts.open_api.services import AlertsOpenAPIService


def _context(*, team_id=1, is_superuser=True, permissions=None):
    alarm_perms = {"Alarms-View"} if permissions is None else permissions
    user = SimpleNamespace(
        username="api-user",
        group_list=[{"id": team_id}],
        permission={"alarm": set(alarm_perms)},
        is_superuser=is_superuser,
        locale="zh-CN",
        domain="default",
    )
    return AlertsOpenAPIContext(user=user, team_id=team_id)


def _service(*, team_id=1, is_superuser=True, permissions=None):
    return AlertsOpenAPIService(_context(team_id=team_id, is_superuser=is_superuser, permissions=permissions))


def _create_alert(*, alert_id, team=None, session_status=""):
    return Alert.objects.create(
        alert_id=alert_id,
        level="0",
        title=f"title-{alert_id}",
        content="content",
        fingerprint=f"fp-{alert_id}",
        team=team if team is not None else [1],
        session_status=session_status,
    )


@pytest.mark.django_db
def test_list_alerts_filters_by_team():
    _create_alert(alert_id="A-team-1", team=[1])
    _create_alert(alert_id="A-team-2", team=[2])

    result = _service(team_id=1).list_alerts({})

    assert result["count"] == 1
    assert result["items"][0]["alert_id"] == "A-team-1"


@pytest.mark.django_db
def test_list_alerts_does_not_include_operator_assigned_other_team():
    alert = _create_alert(alert_id="A-mine-other-team", team=[2])
    Alert.objects.filter(pk=alert.pk).update(operator=["api-user"])

    result = _service(team_id=1).list_alerts({})
    ids = {item["alert_id"] for item in result["items"]}

    assert "A-mine-other-team" not in ids


@pytest.mark.django_db
def test_get_alert_other_team_not_found_even_if_operator_matches():
    alert = _create_alert(alert_id="A-other-operator", team=[2])
    Alert.objects.filter(pk=alert.pk).update(operator=["api-user"])

    with pytest.raises(AlertsOpenAPIError) as exc:
        _service(team_id=1).get_alert("A-other-operator")

    assert exc.value.code == "alerts.alert.not_found"
    assert exc.value.status_code == 404


@pytest.mark.django_db
def test_list_alerts_excludes_no_confirmed_session_status():
    _create_alert(alert_id="A-visible", session_status="")
    _create_alert(alert_id="A-observing", session_status=SessionStatus.OBSERVING)
    _create_alert(alert_id="A-recovered", session_status=SessionStatus.RECOVERED)

    result = _service().list_alerts({})

    assert result["count"] == 1
    assert result["items"][0]["alert_id"] == "A-visible"


@pytest.mark.django_db
def test_get_alert_other_team_not_found():
    _create_alert(alert_id="A-other", team=[2])

    with pytest.raises(AlertsOpenAPIError) as exc:
        _service(team_id=1).get_alert("A-other")

    assert exc.value.code == "alerts.alert.not_found"
    assert exc.value.status_code == 404


@pytest.mark.django_db
def test_list_alert_events_returns_events():
    alert = _create_alert(alert_id="A-events")
    source = AlertSource.objects.create(
        name="test-source",
        source_id="src-1",
        source_type="restful",
        secret="x",
    )
    now = timezone.now()
    event1 = Event.objects.create(
        source=source,
        raw_data={},
        title="event-1",
        level="0",
        start_time=now,
        event_id="E-1",
    )
    event2 = Event.objects.create(
        source=source,
        raw_data={},
        title="event-2",
        level="0",
        start_time=now,
        event_id="E-2",
    )
    Event.objects.filter(pk=event1.pk).update(received_at=now - datetime.timedelta(minutes=1))
    Event.objects.filter(pk=event2.pk).update(received_at=now)
    alert.events.add(event1, event2)

    result = _service().list_alert_events("A-events", {})

    assert result["count"] == 2
    assert [item["event_id"] for item in result["items"]] == ["E-2", "E-1"]


@pytest.mark.django_db
def test_get_alert_returns_detail_fields():
    alert = _create_alert(alert_id="A-detail")
    Alert.objects.filter(pk=alert.pk).update(labels={"env": "prod"}, enrichment={"k": "v"})

    data = _service().get_alert("A-detail")

    assert data["alert_id"] == "A-detail"
    assert data["labels"] == {"env": "prod"}
    assert data["enrichment"] == {"k": "v"}


@pytest.mark.django_db
def test_list_alerts_requires_alarms_view():
    with pytest.raises(AlertsOpenAPIError) as exc:
        _service(is_superuser=False, permissions=set()).list_alerts({})

    assert exc.value.code == "alerts.permission.denied"
