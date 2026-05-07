import json

import pytest
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.alerts.constants.constants import (
    AlertStatus,
    AlertsSourceTypes,
    EventAction,
    EventType,
    IncidentStatus,
    LogAction,
    LogTargetType,
)
from apps.alerts.models import Alert, AlertSource, Event, Incident, OperatorLog
from apps.alerts.views.alert import AlertModelViewSet
from apps.alerts.views.incident import IncidentModelViewSet
from apps.alerts.views.event import EventModelViewSet
from apps.alerts.views.operator_log import SystemLogModelViewSet
from apps.system_mgmt.models import Group, User


def _build_user(username, group_list, alarm_permissions):
    user = User.objects.create(
        username=username,
        display_name=username,
        email=f"{username}@example.com",
        password=make_password("password123"),
        domain="domain.com",
        group_list=group_list,
    )
    user.permission = {"alarm": set(alarm_permissions)}
    user.is_superuser = False
    user.is_authenticated = True
    return user


def _ensure_groups(*group_ids):
    for group_id in group_ids:
        Group.objects.get_or_create(id=group_id, defaults={"name": f"group-{group_id}", "parent_id": 0})


def _build_alert(team, operator, suffix):
    source = AlertSource.objects.create(
        name=f"source-{suffix}",
        source_id=f"source-{suffix}",
        source_type=AlertsSourceTypes.WEBHOOK,
    )
    event = Event.objects.create(
        source=source,
        push_source_id="default",
        raw_data={},
        title=f"event-{suffix}",
        description="desc",
        level="warning",
        service="svc",
        event_type=EventType.ALERT,
        tags={},
        location="gz",
        external_id=f"external-{suffix}",
        start_time=timezone.now(),
        labels={},
        action=EventAction.CREATED,
        event_id=f"EVENT-{suffix}",
        item="cpu",
        resource_id=f"resource-{suffix}",
        resource_type="host",
        resource_name=f"host-{suffix}",
        status="received",
        assignee=[],
    )
    alert = Alert.objects.create(
        alert_id=f"ALERT-{suffix}",
        status=AlertStatus.UNASSIGNED,
        level="warning",
        title=f"alert-{suffix}",
        content="content",
        labels={},
        first_event_time=timezone.now(),
        last_event_time=timezone.now(),
        item="cpu",
        resource_id=f"resource-{suffix}",
        resource_name=f"host-{suffix}",
        resource_type="host",
        operate=None,
        operator=operator,
        source_name=source.name,
        fingerprint=f"fp-{suffix}",
        group_by_field="service",
        rule_id=f"rule-{suffix}",
        team=team,
    )
    alert.events.add(event)
    return alert


@pytest.mark.django_db
def test_alert_list_is_scoped_by_operator_and_authorized_team():
    _ensure_groups(1, 2)
    user = _build_user("alert-owner", [1], ["Alarms-View"])
    team_alert = _build_alert([1], [], "team")
    assigned_alert = _build_alert([2], ["alert-owner"], "assigned")
    hidden_alert = _build_alert([2], ["someone-else"], "hidden")

    factory = APIRequestFactory()
    request = factory.get("/api/alert")
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=user)

    response = AlertModelViewSet.as_view({"get": "list"})(request)
    payload = json.loads(response.content)
    returned_alert_ids = {item["alert_id"] for item in payload["data"]}

    assert team_alert.alert_id in returned_alert_ids
    assert assigned_alert.alert_id in returned_alert_ids
    assert hidden_alert.alert_id not in returned_alert_ids


@pytest.mark.django_db
def test_incident_retrieve_rejects_cross_team_access():
    _ensure_groups(1, 2)
    user = _build_user("incident-reader", [1], ["Incidents-View"])
    foreign_alert = _build_alert([2], ["someone-else"], "foreign")
    incident = Incident.objects.create(
        incident_id="INCIDENT-foreign",
        status=IncidentStatus.PENDING,
        level="warning",
        title="foreign-incident",
        content="content",
        note="",
        labels={},
        operator=[],
        fingerprint="incident-fp",
        created_by="system",
        updated_by="system",
        domain="domain.com",
        updated_by_domain="domain.com",
    )
    incident.alert.add(foreign_alert)

    factory = APIRequestFactory()
    request = factory.get(f"/api/incident/{incident.pk}/")
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=user)

    response = IncidentModelViewSet.as_view({"get": "retrieve"})(request, pk=incident.pk)

    assert response.status_code == 404


@pytest.mark.django_db
def test_incident_create_rejects_unscoped_alert_ids():
    _ensure_groups(1, 2)
    user = _build_user("incident-editor", [1], ["Alarms-Edit"])
    hidden_alert = _build_alert([2], ["someone-else"], "hidden-create")

    factory = APIRequestFactory()
    request = factory.post(
        "/api/incident",
        {
            "title": "new-incident",
            "level": "warning",
            "content": "content",
            "note": "",
            "labels": {},
            "operator": [],
            "alert": [hidden_alert.pk],
        },
        format="json",
    )
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=user)

    response = IncidentModelViewSet.as_view({"post": "create"})(request)

    assert response.status_code == 400
    assert Incident.objects.count() == 0


@pytest.mark.django_db
def test_alert_operator_rejects_unscoped_alert_ids():
    _ensure_groups(1, 2)
    user = _build_user("alert-editor", [1], ["Alarms-Edit"])
    hidden_alert = _build_alert([2], ["someone-else"], "hidden-operator")

    factory = APIRequestFactory()
    request = factory.post(
        "/api/alert/operator/assign/",
        {"alert_id": [hidden_alert.alert_id], "assignee": ["alert-editor"]},
        format="json",
    )
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=user)

    response = AlertModelViewSet.as_view({"post": "operator"})(request, operator_action="assign")
    payload = json.loads(response.content)
    hidden_alert.refresh_from_db()

    assert response.status_code == 500
    assert payload["result"] is False
    assert payload["data"][hidden_alert.alert_id]["message"] == "您没有权限操作此告警"
    assert hidden_alert.status == AlertStatus.UNASSIGNED


@pytest.mark.django_db
def test_event_retrieve_rejects_cross_team_access():
    _ensure_groups(1, 2)
    user = _build_user("event-reader", [1], ["Alarms-View"])
    hidden_alert = _build_alert([2], ["someone-else"], "hidden-event")
    hidden_event = hidden_alert.events.first()

    factory = APIRequestFactory()
    request = factory.get(f"/api/events/{hidden_event.pk}/")
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=user)

    response = EventModelViewSet.as_view({"get": "retrieve"})(request, pk=hidden_event.pk)

    assert response.status_code == 404


@pytest.mark.django_db
def test_operator_log_list_hides_cross_team_alert_history():
    _ensure_groups(1, 2)
    user = _build_user("log-reader", [1], ["operation_log-View"])
    visible_alert = _build_alert([1], [], "visible-log")
    hidden_alert = _build_alert([2], ["someone-else"], "hidden-log")
    OperatorLog.objects.create(
        operator="system",
        action=LogAction.MODIFY,
        target_type=LogTargetType.ALERT,
        operator_object="告警处理-关闭",
        target_id=visible_alert.alert_id,
        overview="visible log",
    )
    OperatorLog.objects.create(
        operator="system",
        action=LogAction.MODIFY,
        target_type=LogTargetType.ALERT,
        operator_object="告警处理-关闭",
        target_id=hidden_alert.alert_id,
        overview="hidden log",
    )

    factory = APIRequestFactory()
    request = factory.get("/api/log/")
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=user)

    response = SystemLogModelViewSet.as_view({"get": "list"})(request)
    payload = response.data
    rows = payload["data"] if isinstance(payload, dict) else payload
    returned_overviews = {item["overview"] for item in rows}

    assert "visible log" in returned_overviews
    assert "hidden log" not in returned_overviews
