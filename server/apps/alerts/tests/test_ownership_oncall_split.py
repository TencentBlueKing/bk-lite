"""告警归属与值班分离：组织列表、我的告警、跨组织分派。

对照 specs/changes/alert-ownership-oncall-split/spec.md。
"""

from unittest.mock import patch

import pytest
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.alerts.constants.constants import AlertStatus
from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Alert, Event
from apps.alerts.views.alert import AlertModelViewSet
from apps.system_mgmt.models.user import User


def _render(response):
    if hasattr(response, "render"):
        response.render()
    try:
        import json

        return json.loads(response.content)
    except Exception:
        return {}


def _alert_ids(payload):
    data = payload.get("data")
    if isinstance(data, dict):
        items = data.get("items") or []
    else:
        items = data or []
    return {item["alert_id"] for item in items}


@pytest.fixture(autouse=True)
def grant_alert_scope(monkeypatch):
    def rules(*args, **kwargs):
        return {"instance": [], "team": [1]}

    monkeypatch.setattr("apps.core.utils.viewset_utils.get_permission_rules", rules)
    monkeypatch.setattr("apps.core.utils.permission_utils.get_permission_rules", rules)


def _build_user(username, group_ids, permissions, *, disabled=False):
    user = User.objects.create(
        username=username,
        display_name=username,
        email=f"{username}@example.com",
        password=make_password("password123"),
        domain="domain.com",
        group_list=[{"id": group_id} for group_id in group_ids],
        disabled=disabled,
    )
    user.permission = {"alarm": set(permissions)}
    user.is_superuser = False
    user.is_authenticated = True
    return user


def _build_alert(*, alert_id, team, operator, status=AlertStatus.UNASSIGNED, event_team=None):
    source, _ = AlertSource.objects.get_or_create(
        source_id="oncall-source",
        defaults={"name": "oncall-source", "source_type": "restful", "secret": "s"},
    )
    event = Event.objects.create(
        source=source,
        raw_data={},
        title=f"event-{alert_id}",
        level="0",
        start_time=timezone.now(),
        event_id=f"event-{alert_id}",
        team=event_team if event_team is not None else team,
    )
    alert = Alert.objects.create(
        alert_id=alert_id,
        level="0",
        title=f"title-{alert_id}",
        content="content",
        fingerprint=f"fp-{alert_id}",
        team=team,
        operator=operator,
        status=status,
    )
    alert.events.add(event)
    return alert


def _get(path, user, team="1"):
    request = APIRequestFactory().get(path)
    request.COOKIES["current_team"] = team
    force_authenticate(request, user=user)
    return request


def _post(path, user, data, team="1"):
    request = APIRequestFactory().post(path, data, format="json")
    request.COOKIES["current_team"] = team
    force_authenticate(request, user=user)
    return request


@pytest.mark.django_db
def test_org_list_includes_owned_or_assigned_to_me():
    viewer = _build_user("org-viewer", [1], ["Alarms-View"])
    owned = _build_alert(alert_id="owned-unassigned", team=[1], operator=[])
    mine_elsewhere = _build_alert(
        alert_id="assigned-elsewhere",
        team=[2],
        operator=["org-viewer"],
        status=AlertStatus.PENDING,
    )
    foreign = _build_alert(alert_id="foreign-hidden", team=[2], operator=["other"])

    response = AlertModelViewSet.as_view({"get": "list"})(_get("/alerts/", viewer))
    ids = _alert_ids(_render(response))

    assert owned.alert_id in ids
    assert mine_elsewhere.alert_id in ids
    assert foreign.alert_id not in ids


@pytest.mark.django_db
def test_org_only_list_hides_foreign_assigned_alert():
    """显式 org_only 只按归属。告警中心页面趋势不再传该参数，与默认列表同过滤。"""
    viewer = _build_user("org-only-viewer", [1], ["Alarms-View"])
    owned = _build_alert(alert_id="owned-org-only", team=[1], operator=[])
    mine_elsewhere = _build_alert(
        alert_id="assigned-elsewhere-org-only",
        team=[2],
        operator=["org-only-viewer"],
        status=AlertStatus.PENDING,
    )

    response = AlertModelViewSet.as_view({"get": "list"})(_get("/alerts/?org_only=1", viewer))
    ids = _alert_ids(_render(response))

    assert owned.alert_id in ids
    assert mine_elsewhere.alert_id not in ids


@pytest.mark.django_db
def test_my_alert_lists_current_operator_across_orgs():
    oncall = _build_user("noc-user", [1], ["Alarms-View"])
    owned_unassigned = _build_alert(alert_id="owned-open", team=[1], operator=[])
    mine = _build_alert(
        alert_id="noc-ticket",
        team=[2],
        operator=["noc-user"],
        status=AlertStatus.PENDING,
    )
    substring_trap = _build_alert(
        alert_id="admin-trap",
        team=[2],
        operator=["noc-user-extra"],
        status=AlertStatus.PENDING,
    )
    other_oncall = _build_alert(
        alert_id="someone-else",
        team=[2],
        operator=["other-noc"],
        status=AlertStatus.PENDING,
    )

    response = AlertModelViewSet.as_view({"get": "list"})(_get("/alerts/?my_alert=1", oncall))
    ids = _alert_ids(_render(response))

    assert mine.alert_id in ids
    assert owned_unassigned.alert_id not in ids
    assert substring_trap.alert_id not in ids
    assert other_oncall.alert_id not in ids


@pytest.mark.django_db
def test_default_list_includes_closed_alert_assigned_to_me_from_other_org():
    oncall = _build_user("noc-history", [1], ["Alarms-View"])
    closed_mine = _build_alert(
        alert_id="closed-elsewhere",
        team=[2],
        operator=["noc-history"],
        status=AlertStatus.CLOSED,
    )
    closed_foreign = _build_alert(
        alert_id="closed-foreign",
        team=[2],
        operator=["other"],
        status=AlertStatus.CLOSED,
    )

    response = AlertModelViewSet.as_view({"get": "list"})(_get("/alerts/", oncall))
    ids = _alert_ids(_render(response))

    assert closed_mine.alert_id in ids
    assert closed_foreign.alert_id not in ids


@pytest.mark.django_db
def test_operator_can_retrieve_and_list_events_for_foreign_owned_alert():
    oncall = _build_user("noc-detail", [1], ["Alarms-View"])
    alert = _build_alert(
        alert_id="foreign-detail",
        team=[2],
        operator=["noc-detail"],
        status=AlertStatus.PENDING,
        event_team=[2],
    )

    retrieve = AlertModelViewSet.as_view({"get": "retrieve"})(
        _get(f"/alerts/{alert.pk}/", oncall),
        pk=str(alert.pk),
    )
    retrieve_payload = _render(retrieve)
    assert retrieve.status_code == 200
    assert retrieve_payload.get("alert_id") == alert.alert_id or retrieve_payload.get("data", {}).get("alert_id") == alert.alert_id

    events = AlertModelViewSet.as_view({"get": "events"})(
        _get(f"/alerts/{alert.pk}/events/", oncall),
        pk=str(alert.pk),
    )
    events_payload = _render(events)
    assert events.status_code == 200
    items = events_payload.get("data") or events_payload
    if isinstance(items, dict):
        items = items.get("items") or items.get("results") or []
    assert any(item.get("event_id") == f"event-{alert.alert_id}" or item.get("title") == f"event-{alert.alert_id}" for item in items)


@pytest.mark.django_db
def test_non_operator_cannot_operate_foreign_unassigned_alert():
    editor = _build_user("org-editor", [1], ["Alarms-Edit", "Alarms-View"])
    alert = _build_alert(alert_id="foreign-unassigned", team=[2], operator=[])

    response = AlertModelViewSet.as_view({"post": "operator"})(
        _post("/alerts/operator/assign/", editor, {"alert_id": [alert.alert_id], "assignee": ["org-editor"]}),
        operator_action="assign",
    )
    payload = _render(response)
    alert.refresh_from_db()
    assert alert.status == AlertStatus.UNASSIGNED
    message = payload.get("data", {}).get(alert.alert_id, {}).get("message", "")
    assert "权限" in message


@pytest.mark.django_db
@patch("apps.alerts.service.alter_operator.AlertOperator.format_notify_data", return_value={})
def test_manual_assign_accepts_user_outside_alert_team(_notify):
    editor = _build_user("assigner", [1], ["Alarms-Edit", "Alarms-View"])
    _build_user("noc-assignee", [2], ["Alarms-View"])
    alert = _build_alert(alert_id="assign-cross", team=[1], operator=[])

    response = AlertModelViewSet.as_view({"post": "operator"})(
        _post(
            "/alerts/operator/assign/",
            editor,
            {"alert_id": [alert.alert_id], "assignee": ["noc-assignee"]},
        ),
        operator_action="assign",
    )
    alert.refresh_from_db()
    assert response.status_code == 200
    assert alert.status == AlertStatus.PENDING
    assert alert.operator == ["noc-assignee"]


@pytest.mark.django_db
def test_manual_assign_rejects_disabled_user():
    editor = _build_user("assigner-disabled", [1], ["Alarms-Edit", "Alarms-View"])
    _build_user("disabled-user", [1], [], disabled=True)
    alert = _build_alert(alert_id="assign-disabled", team=[1], operator=[])

    response = AlertModelViewSet.as_view({"post": "operator"})(
        _post(
            "/alerts/operator/assign/",
            editor,
            {"alert_id": [alert.alert_id], "assignee": ["disabled-user"]},
        ),
        operator_action="assign",
    )
    payload = _render(response)
    alert.refresh_from_db()
    assert alert.status == AlertStatus.UNASSIGNED
    message = payload.get("data", {}).get(alert.alert_id, {}).get("message", "")
    assert "禁用" in message


@pytest.mark.django_db
@patch("apps.alerts.service.alter_operator.AlertOperator.format_notify_data", return_value={})
def test_cross_org_operator_can_acknowledge_and_reassign_then_loses_queue(_notify):
    oncall = _build_user("noc-ack", [1], ["Alarms-Edit", "Alarms-View"])
    next_owner = _build_user("l2-user", [3], ["Alarms-View"])
    alert = _build_alert(
        alert_id="handoff",
        team=[2],
        operator=["noc-ack"],
        status=AlertStatus.PENDING,
    )

    ack = AlertModelViewSet.as_view({"post": "operator"})(
        _post("/alerts/operator/acknowledge/", oncall, {"alert_id": [alert.alert_id]}),
        operator_action="acknowledge",
    )
    assert ack.status_code == 200
    alert.refresh_from_db()
    assert alert.status == AlertStatus.PROCESSING

    reassign = AlertModelViewSet.as_view({"post": "operator"})(
        _post(
            "/alerts/operator/reassign/",
            oncall,
            {"alert_id": [alert.alert_id], "assignee": ["l2-user"]},
        ),
        operator_action="reassign",
    )
    assert reassign.status_code == 200
    alert.refresh_from_db()
    assert alert.operator == ["l2-user"]
    assert alert.status == AlertStatus.PENDING

    mine = AlertModelViewSet.as_view({"get": "list"})(_get("/alerts/?my_alert=1", oncall))
    assert alert.alert_id not in _alert_ids(_render(mine))

    next_mine = AlertModelViewSet.as_view({"get": "list"})(_get("/alerts/?my_alert=1", next_owner, team="3"))
    assert alert.alert_id in _alert_ids(_render(next_mine))


@pytest.mark.django_db
def test_escalated_operators_both_see_my_alert():
    first = _build_user("l1-oncall", [1], ["Alarms-View"])
    second = _build_user("l2-oncall", [3], ["Alarms-View"])
    alert = _build_alert(
        alert_id="escalated-ticket",
        team=[2],
        operator=["l1-oncall", "l2-oncall"],
        status=AlertStatus.PENDING,
    )

    first_mine = AlertModelViewSet.as_view({"get": "list"})(_get("/alerts/?my_alert=1", first))
    second_mine = AlertModelViewSet.as_view({"get": "list"})(_get("/alerts/?my_alert=1", second, team="3"))

    assert alert.alert_id in _alert_ids(_render(first_mine))
    assert alert.alert_id in _alert_ids(_render(second_mine))


@pytest.mark.django_db
def test_related_alerts_stay_in_current_org_for_cross_org_operator():
    oncall = _build_user("noc-related", [1], ["Alarms-View"])
    source = _build_alert(
        alert_id="related-source",
        team=[2],
        operator=["noc-related"],
        status=AlertStatus.PENDING,
    )
    neighbor = _build_alert(
        alert_id="neighbor-same-owner-org",
        team=[2],
        operator=[],
        status=AlertStatus.UNASSIGNED,
    )
    source.dimensions = {"service": "checkout"}
    neighbor.dimensions = {"service": "checkout"}
    source.save(update_fields=["dimensions"])
    neighbor.save(update_fields=["dimensions"])

    response = AlertModelViewSet.as_view({"get": "related"})(
        _get(f"/alerts/{source.pk}/related/", oncall),
        pk=str(source.pk),
    )
    payload = _render(response)
    body = payload.get("data", payload) if isinstance(payload, dict) else payload
    if not isinstance(body, dict):
        body = {}
    items = body.get("items") or []
    ids = {item.get("alert_id") for item in items}

    assert response.status_code == 200
    assert neighbor.alert_id not in ids
