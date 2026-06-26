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
def test_manual_trigger_bypasses_match_and_idempotency(mock_get, superuser_client):
    alert = Alert.objects.create(alert_id="A1", fingerprint="f", title="t", content="c",
                                 level="0", labels={"ip": "10.0.0.5"}, team=[1])
    rule = ActionRule.objects.create(name="r", team=[1], trigger_events=["created"],
                                     match_rules=[[{"key": "level", "operator": "eq", "value": "9"}]],
                                     action_config={"script_id": 1})
    for _ in range(2):
        resp = superuser_client.post("/api/v1/alerts/api/action_execution/manual_trigger/",
                                     data={"alert_id": "A1", "rule_id": rule.id}, format="json")
        assert resp.status_code in (200, 201)
    execs = ActionExecution.objects.filter(alert=alert, trigger_type="manual")
    assert execs.count() == 2
    assert all(e.idempotency_key is None for e in execs)
    assert mock_get.return_value.execute.call_count == 2
