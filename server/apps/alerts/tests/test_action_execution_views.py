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
    superuser_client.cookies["current_team"] = "1"
    alert = Alert.objects.create(alert_id="A1", fingerprint="f", title="t", content="c", level="1", team=[1])
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


@pytest.mark.django_db
def test_execution_list_is_scoped_by_alert_team(superuser_client):
    rule = ActionRule.objects.create(name="r", team=[1, 2])
    alert_1 = Alert.objects.create(
        alert_id="A-team-1", fingerprint="f1", title="t1", content="c", level="1", team=[1]
    )
    alert_2 = Alert.objects.create(
        alert_id="A-team-2", fingerprint="f2", title="t2", content="c", level="1", team=[2]
    )
    ActionExecution.objects.create(rule=rule, alert=alert_1, trigger_event="manual", idempotency_key="k-team-1")
    ActionExecution.objects.create(rule=rule, alert=alert_2, trigger_event="manual", idempotency_key="k-team-2")
    superuser_client.cookies["current_team"] = "1"

    response = superuser_client.get("/api/v1/alerts/api/action_execution/")

    assert response.status_code == 200
    data = response.json().get("data", response.json())
    items = data.get("items", data) if isinstance(data, dict) else data
    assert {item["alert"] for item in items} == {alert_1.id}
