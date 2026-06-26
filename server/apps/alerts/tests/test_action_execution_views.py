import pytest
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
def test_list_executions_filtered_by_alert(superuser_client):
    alert = Alert.objects.create(alert_id="A1", fingerprint="f", title="t", content="c", level="1")
    rule = ActionRule.objects.create(name="r", team=[1])
    ActionExecution.objects.create(rule=rule, alert=alert, trigger_event="created",
                                   trigger_type="auto", idempotency_key="k1", status="success")
    resp = superuser_client.get("/api/v1/alerts/api/action_execution/?alert_id=A1")
    assert resp.status_code == 200
    body = resp.json()
    # CustomRenderer wraps response as {"result": True, "data": [...]}
    # Pagination (with page_size) returns {"count": N, "items": [...]}
    # Without page_size the data is a plain list
    data = body.get("data", body)
    if isinstance(data, dict):
        count = data.get("count", len(data.get("items", [])))
    else:
        count = len(data) if isinstance(data, list) else 0
    assert count >= 1
