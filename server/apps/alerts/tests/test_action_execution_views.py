import re
from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient
from apps.alerts.models.action import ActionRule, ActionExecution
from apps.alerts.models.models import Alert
from apps.base.models import User

_PER_ROW_RELATED_SELECT = re.compile(
    r'FROM\s+"alerts_(?:action_rule|alert)"\s+WHERE\s+\(?\s*"alerts_(?:action_rule|alert)"\."id"\s*=',
    re.IGNORECASE,
)


@pytest.fixture
def superuser_client(authenticated_user):
    """api_client with is_superuser=True so HasPermission is bypassed."""
    authenticated_user.is_superuser = True
    authenticated_user.save()
    client = APIClient()
    client.force_authenticate(user=authenticated_user)
    client.cookies["current_team"] = "1"
    return client


@pytest.mark.django_db
def test_list_executions_filtered_by_alert(superuser_client):
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


def _per_row_related_selects(captured):
    return sum(1 for query in captured.captured_queries if _PER_ROW_RELATED_SELECT.search(query["sql"]))


def _response_items(response):
    body = response.json()
    data = body.get("data", body)
    if isinstance(data, dict):
        return data.get("items", [])
    if isinstance(data, list):
        return data
    return []


def _reset_execution_fixtures():
    ActionExecution.objects.all().delete()
    ActionRule.objects.all().delete()
    Alert.objects.all().delete()


def _seed_executions(count):
    _reset_execution_fixtures()
    base = timezone.now()
    ruled = []
    for index in range(count):
        alert = Alert.objects.create(
            alert_id=f"A-{count}-{index}",
            fingerprint=f"f{count}{index}",
            title=f"title-{count}-{index}",
            content="c",
            level="1",
            team=[1],
        )
        rule = ActionRule.objects.create(name=f"rule-{count}-{index}", team=[1])
        execution = ActionExecution.objects.create(
            rule=rule,
            alert=alert,
            trigger_event="created",
            trigger_type="auto",
            idempotency_key=f"k-{count}-{index}",
            status="success",
        )
        created_at = base - timedelta(seconds=index + 1)
        ActionExecution.objects.filter(pk=execution.pk).update(created_at=created_at)
        execution.created_at = created_at
        ruled.append((execution, rule.name, alert.title))

    null_alert = Alert.objects.create(
        alert_id=f"A-{count}-null",
        fingerprint=f"fn{count}",
        title=f"title-{count}-null",
        content="c",
        level="1",
        team=[1],
    )
    null_execution = ActionExecution.objects.create(
        rule=None,
        alert=null_alert,
        trigger_event="created",
        trigger_type="auto",
        idempotency_key=f"k-{count}-null",
        status="success",
    )
    null_created_at = base - timedelta(seconds=count + 2)
    ActionExecution.objects.filter(pk=null_execution.pk).update(created_at=null_created_at)
    null_execution.created_at = null_created_at

    other_alert = Alert.objects.create(
        alert_id=f"A-{count}-other",
        fingerprint=f"fo{count}",
        title="other-org",
        content="c",
        level="1",
        team=[2],
    )
    other_rule = ActionRule.objects.create(name=f"rule-{count}-other", team=[2])
    other_execution = ActionExecution.objects.create(
        rule=other_rule,
        alert=other_alert,
        trigger_event="created",
        trigger_type="auto",
        idempotency_key=f"k-{count}-other",
        status="success",
    )
    ActionExecution.objects.filter(pk=other_execution.pk).update(created_at=base)
    return ruled, null_execution, other_execution


@pytest.mark.django_db
def test_execution_list_rule_and_alert_names_do_not_query_per_row(superuser_client):
    counts = {}
    for count in (10, 50):
        ruled, null_execution, other_execution = _seed_executions(count)
        superuser_client.cookies["current_team"] = "1"
        with CaptureQueriesContext(connection) as captured:
            response = superuser_client.get("/api/v1/alerts/api/action_execution/")

        assert response.status_code == 200
        items = _response_items(response)
        ids = [item["id"] for item in items]
        assert other_execution.id not in ids
        assert null_execution.id in ids
        null_item = next(item for item in items if item["id"] == null_execution.id)
        assert null_item["rule_name"] is None
        assert null_item["alert_title"] == f"title-{count}-null"
        by_id = {item["id"]: item for item in items}
        for execution, rule_name, alert_title in ruled:
            item = by_id[execution.id]
            assert item["rule_name"] == rule_name
            assert item["alert_title"] == alert_title
        visible = [execution for execution, _rule_name, _alert_title in ruled]
        visible.append(null_execution)
        expected = sorted(visible, key=lambda execution: execution.created_at, reverse=True)
        assert ids == [execution.id for execution in expected]
        counts[count] = _per_row_related_selects(captured)

    assert counts == {10: 0, 50: 0}, f"per-row rule/alert PK selects should stay flat: 10={counts[10]} 50={counts[50]}"
