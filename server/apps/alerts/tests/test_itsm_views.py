from unittest.mock import patch

import pytest

from apps.alerts.models.action import ActionExecution
from apps.alerts.tests.test_action_execution_views import superuser_client  # noqa: F401
from apps.alerts.tests.test_itsm_service import alert, configure_itsm, itsm_connection, prepare, rule  # noqa: F401

BASE = "/api/v1/alerts/api/action_execution/"


@pytest.fixture(name="itsm_api_client")
def configured_api_client(superuser_client):  # noqa: F811
    return superuser_client


@pytest.mark.django_db
def test_manual_retry_is_accepted_async_and_input_is_private(setup_itsm, itsm_api_client):
    a = alert(status="auto_recovery")
    r = rule()
    link = prepare(a)
    ActionExecution.objects.filter(pk=link.current_execution_id).update(status="failed")
    with patch("requests.Session.request") as http:
        result = itsm_api_client.post(
            BASE + "manual_trigger/", {"alert_id": a.alert_id, "rule_id": r.pk}, format="json", HTTP_IDEMPOTENCY_KEY="retry-key"
        )
        assert result.status_code == 202
        http.assert_not_called()
    detail = itsm_api_client.get(BASE + f"itsm_ticket/?alert_id={a.alert_id}")
    assert detail.status_code == 200
    body = detail.json()["data"]
    assert body["execution_status"] == "pending"
    assert "input_snapshot" not in body and "claim_token" not in body
    history = itsm_api_client.get(BASE).json()["data"]
    assert "input_snapshot" not in str(history)


@pytest.mark.django_db
def test_other_team_cannot_read_retry_or_reconcile(setup_itsm, itsm_api_client):
    a = alert()
    r = rule()
    prepare(a)
    itsm_api_client.cookies["current_team"] = "2"
    with patch("requests.Session.request") as http:
        assert itsm_api_client.get(BASE + f"itsm_ticket/?alert_id={a.alert_id}").status_code == 404
        assert itsm_api_client.post(
            BASE + "manual_trigger/", {"alert_id": a.alert_id, "rule_id": r.pk}, format="json", HTTP_IDEMPOTENCY_KEY="key"
        ).status_code in {400, 403, 404}
        assert (
            itsm_api_client.post(
                BASE + "itsm_reconcile/",
                {"alert_id": a.alert_id, "execution_id": 1, "ticket_id": "123", "evidence": "checked", "confirm": True},
                format="json",
            ).status_code
            == 404
        )
        http.assert_not_called()


@pytest.mark.django_db
def test_itsm_rule_patch_cannot_enable_other_lifecycle_events(setup_itsm, itsm_api_client):
    r = rule()
    result = itsm_api_client.patch(f"/api/v1/alerts/api/action_rule/{r.pk}/", {"trigger_events": ["closed"]}, format="json")
    assert result.status_code == 400


@pytest.mark.django_db
def test_unknown_reconcile_requires_both_permissions(setup_itsm, authenticated_user):
    from rest_framework.test import APIClient

    a = alert()
    rule()
    link = prepare(a)
    ActionExecution.objects.filter(pk=link.current_execution_id).update(status="unknown")
    client = APIClient()
    client.cookies["current_team"] = "1"
    for permission in [{"action_exec-Manual"}, {"action_rule-Edit"}, {"Alarms-View"}, set()]:
        authenticated_user.permission = {"alarm": permission}
        client.force_authenticate(authenticated_user)
        with patch("requests.Session.request") as http:
            result = client.post(
                BASE + "itsm_reconcile/", {"alert_id": a.alert_id, "execution_id": link.current_execution_id, "ticket_id": "123"}, format="json"
            )
            assert result.status_code == 403
            http.assert_not_called()


@pytest.mark.django_db
def test_empty_team_does_not_expose_connections_or_tickets(setup_itsm, itsm_api_client):
    a = alert()
    rule()
    prepare(a)
    del itsm_api_client.cookies["current_team"]
    assert itsm_api_client.get(BASE + f"itsm_ticket/?alert_id={a.alert_id}").status_code == 404
    response = itsm_api_client.get("/api/v1/alerts/api/action_rule/itsm_connections/")
    assert response.json()["data"] == []


@pytest.mark.django_db
def test_invalid_itsm_rule_can_still_be_disabled(itsm_api_client):
    r = rule(action_config={})
    response = itsm_api_client.patch(f"/api/v1/alerts/api/action_rule/{r.pk}/", {"is_active": False}, format="json")
    assert response.status_code == 200
    r.refresh_from_db()
    assert not r.is_active


@pytest.mark.django_db
def test_manual_close_recovery_never_recreates_ticket(setup_itsm, itsm_api_client):
    from apps.alerts.models.outbox import AlertOutbox
    from apps.alerts.tests.test_itsm_sync import linked

    a, _, link = linked()
    before = a.status
    with patch("requests.Session.request") as http:
        response = itsm_api_client.post(BASE + "itsm_retry_close/", {"alert_id": a.alert_id}, format="json", HTTP_IDEMPOTENCY_KEY="retry-close")
        assert response.status_code == 409
        http.assert_not_called()
    a.refresh_from_db()
    link.refresh_from_db()
    assert a.status == before
    assert link.close_result == "unprocessed"
    assert not AlertOutbox.objects.filter(kind="itsm_sync").exists()
