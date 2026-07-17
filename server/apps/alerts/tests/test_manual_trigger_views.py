import pytest
from unittest.mock import patch
from rest_framework.test import APIClient
from apps.alerts.models.action import ActionRule, ActionExecution
from apps.alerts.models.models import Alert
from apps.alerts.models.operator_log import OperatorLog
from apps.base.models import User


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


@pytest.mark.django_db
@patch("apps.alerts.views.action.get_handler")
def test_manual_trigger_writes_operator_log_for_change_record_tab(mock_get, superuser_client):
    """手动触发的执行除了写 ActionExecution，还应在 OperatorLog 落库，
    '变更记录' Tab（operator_log 接口）才能跟自动触发的执行记录对齐显示。"""
    mock_get.return_value.execute.return_value = None  # handler 不真跑
    alert = Alert.objects.create(alert_id="A1", fingerprint="f", title="t", content="c",
                                 level="0", labels={"ip": "10.0.0.5"}, team=[1])
    rule = ActionRule.objects.create(name="重启Nginx", team=[1], trigger_events=["created"],
                                     match_rules=[[{"key": "level", "operator": "eq", "value": "0"}]],
                                     action_config={"script_id": 1})

    before = OperatorLog.objects.filter(target_id="A1").count()
    resp = superuser_client.post(
        "/api/v1/alerts/api/action_execution/manual_trigger/",
        data={"alert_id": "A1", "rule_id": rule.id},
        format="json",
    )
    assert resp.status_code in (200, 201)

    # 手动触发应在 OperatorLog 留下 1 条新记录
    new_logs = list(OperatorLog.objects.filter(target_id="A1"))
    assert len(new_logs) == before + 1
    log = new_logs[-1]
    assert log.action == "execute"   # LogAction.EXECUTE
    assert log.target_type == "alert" # LogTargetType.ALERT
    assert log.target_id == "A1"
    assert log.operator == superuser_client.handler._force_user.username
    # overview 至少包含规则名
    assert "重启Nginx" in (log.overview or "")


@pytest.mark.django_db
@patch("apps.alerts.views.action.get_handler")
def test_manual_trigger_rejects_other_team_alert_and_rule(mock_get, superuser_client):
    own_alert = Alert.objects.create(
        alert_id="A-OWN", fingerprint="f-own", title="own", content="c", level="0", team=[1]
    )
    other_alert = Alert.objects.create(
        alert_id="A-OTHER", fingerprint="f-other", title="other", content="c", level="0", team=[2]
    )
    other_rule = ActionRule.objects.create(name="other-rule", team=[2])

    other_alert_resp = superuser_client.post(
        "/api/v1/alerts/api/action_execution/manual_trigger/",
        data={"alert_id": other_alert.alert_id, "rule_id": other_rule.id},
        format="json",
    )
    other_rule_resp = superuser_client.post(
        "/api/v1/alerts/api/action_execution/manual_trigger/",
        data={"alert_id": own_alert.alert_id, "rule_id": other_rule.id},
        format="json",
    )

    assert other_alert_resp.status_code == 400
    assert other_rule_resp.status_code == 400
    assert ActionExecution.objects.count() == 0
    mock_get.assert_not_called()


@pytest.mark.django_db
@patch("apps.alerts.views.action.get_handler")
def test_manual_trigger_allows_global_rule_for_authorized_alert(mock_get, superuser_client):
    mock_get.return_value.execute.return_value = None
    alert = Alert.objects.create(
        alert_id="A-OWN", fingerprint="f-own", title="own", content="c", level="0", team=[1]
    )
    global_rule = ActionRule.objects.create(name="global-rule", team=[])

    resp = superuser_client.post(
        "/api/v1/alerts/api/action_execution/manual_trigger/",
        data={"alert_id": alert.alert_id, "rule_id": global_rule.id},
        format="json",
    )

    assert resp.status_code == 200
    assert ActionExecution.objects.filter(alert=alert, rule=global_rule).exists()
