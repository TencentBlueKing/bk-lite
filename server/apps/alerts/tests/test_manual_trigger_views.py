import pytest
from unittest.mock import patch
from rest_framework.test import APIClient
from apps.alerts.models.action import ActionRule, ActionExecution
from apps.alerts.models.models import Alert
from apps.base.models import User


@pytest.fixture
def superuser_client(authenticated_user):
    """api_client with is_superuser=True so HasPermission is bypassed."""
    authenticated_user.is_superuser = True
    authenticated_user.save()
    client = APIClient()
    client.force_authenticate(user=authenticated_user)
    return client


@pytest.mark.django_db
@patch("apps.alerts.views.action.get_handler")
def test_manual_trigger_is_idempotent_for_same_client_key(mock_get, superuser_client):
    alert = Alert.objects.create(alert_id="A1", fingerprint="f", title="t", content="c",
                                 level="0", labels={"ip": "10.0.0.5"}, team=[1])
    rule = ActionRule.objects.create(name="r", team=[1], trigger_events=["created"],
                                     match_rules=[[{"key": "level", "operator": "eq", "value": "9"}]],
                                     action_config={"script_id": 1})
    superuser_client.cookies["current_team"] = "1"
    responses = []
    for _ in range(2):
        resp = superuser_client.post("/api/v1/alerts/api/action_execution/manual_trigger/",
                                     data={"alert_id": "A1", "rule_id": rule.id}, format="json",
                                     HTTP_IDEMPOTENCY_KEY="manual-request-1")
        assert resp.status_code in (200, 201)
        responses.append(resp.json()["data"]["execution_id"])
    execs = ActionExecution.objects.filter(alert=alert, trigger_type="manual")
    assert execs.count() == 1
    assert execs.get().idempotency_key
    assert responses[0] == responses[1]
    assert mock_get.return_value.execute.call_count == 1


@pytest.mark.django_db
@patch("apps.alerts.views.action.get_handler")
def test_manual_trigger_reports_synchronous_handler_failure(mock_get, superuser_client):
    alert = Alert.objects.create(alert_id="A2", fingerprint="f2", title="t", content="c",
                                 level="0", team=[1])
    rule = ActionRule.objects.create(name="r", team=[1], action_config={"script_id": 1})
    superuser_client.cookies["current_team"] = "1"

    def mark_failed(_rule, _alert, execution):
        execution.status = "failed"
        execution.result = {"message": "remote rejected"}
        execution.save(update_fields=["status", "result"])

    mock_get.return_value.execute.side_effect = mark_failed
    response = superuser_client.post(
        "/api/v1/alerts/api/action_execution/manual_trigger/",
        data={"alert_id": alert.alert_id, "rule_id": rule.id},
        format="json",
        HTTP_IDEMPOTENCY_KEY="manual-request-2",
    )

    assert response.status_code == 422
    assert response.json()["result"] is False
    assert response.json()["data"]["status"] == "failed"


@pytest.mark.django_db
@patch("apps.alerts.views.action.get_handler")
def test_manual_trigger_cannot_cross_current_team(mock_get, superuser_client):
    alert = Alert.objects.create(alert_id="A3", fingerprint="f3", title="secret", content="c",
                                 level="0", team=[2])
    rule = ActionRule.objects.create(name="r", team=[2], action_config={"script_id": 1})
    superuser_client.cookies["current_team"] = "1"

    response = superuser_client.post(
        "/api/v1/alerts/api/action_execution/manual_trigger/",
        data={"alert_id": alert.alert_id, "rule_id": rule.id},
        format="json",
        HTTP_IDEMPOTENCY_KEY="manual-request-3",
    )

    assert response.status_code == 400
    assert "secret" not in response.content.decode()
    mock_get.return_value.execute.assert_not_called()
