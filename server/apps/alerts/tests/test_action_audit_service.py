"""
ActionEngine audit test — 每次 _dispatch 成功后应写入 OperatorLog。
"""
import pytest
from unittest.mock import patch

from apps.alerts.models.action import ActionRule, ActionExecution
from apps.alerts.models.models import Alert
from apps.alerts.models.operator_log import OperatorLog
from apps.alerts.action.engine import ActionEngine


def _alert(aid="AUDIT-1"):
    return Alert.objects.create(
        alert_id=aid, fingerprint=f"fp-{aid}", title="disk full",
        content="c", level="1", status="unassigned",
        labels={"ip": "10.0.0.5"}, team=[1],
    )


def _rule(name="audit-rule", events=None):
    return ActionRule.objects.create(
        name=name, is_active=True, team=[1],
        trigger_events=events or ["created"],
        match_rules=[[{"key": "level", "operator": "eq", "value": "1"}]],
        action_type="job",
        action_config={"script_id": 1},
    )


@pytest.mark.django_db
@patch("apps.alerts.action.engine.get_handler")
def test_dispatch_writes_operator_log(mock_get):
    """evaluate() 命中规则后，OperatorLog 中应有一条 target_id=alert_id 的记录。"""
    alert = _alert()
    rule = _rule()
    ActionEngine().evaluate(alert, "created")

    # 确认 execution 已创建（验证 dispatch 确实执行了）
    assert ActionExecution.objects.filter(alert=alert).exists()

    # 核心断言：OperatorLog 中应有对应记录
    logs = OperatorLog.objects.filter(target_id=alert.alert_id)
    assert logs.exists(), (
        f"期望存在 target_id={alert.alert_id} 的 OperatorLog，"
        f"但实际记录数为 {OperatorLog.objects.count()}"
    )
    log = logs.first()
    assert log.target_type == "alert"
    # overview 应提及规则名称
    assert rule.name in (log.overview or ""), (
        f"期望 overview 包含规则名 '{rule.name}'，实际为 '{log.overview}'"
    )
    # operator_object 应提及 "告警处理"
    assert "告警处理" in (log.operator_object or ""), (
        f"期望 operator_object 包含 '告警处理'，实际为 '{log.operator_object}'"
    )


@pytest.mark.django_db
@patch("apps.alerts.action.engine.get_handler")
def test_dispatch_no_match_no_operator_log(mock_get):
    """规则条件不命中时，不应产生 OperatorLog 记录。"""
    alert = _alert(aid="AUDIT-2")
    _rule(events=["resolved"])  # 事件不匹配 "created"
    ActionEngine().evaluate(alert, "created")
    assert OperatorLog.objects.count() == 0


@pytest.mark.django_db
@patch("apps.alerts.action.engine.get_handler")
def test_audit_failure_does_not_break_dispatch(mock_get):
    """即使 record_operator_log 抛出异常，dispatch 也不应中断（handler 仍被调用）。"""
    alert = _alert(aid="AUDIT-3")
    _rule()
    with patch("apps.alerts.action.engine.record_operator_log", side_effect=Exception("mirror down")):
        ActionEngine().evaluate(alert, "created")
    # handler 仍然被调用
    mock_get.return_value.execute.assert_called_once()
    # execution 仍然创建
    assert ActionExecution.objects.filter(alert=alert).exists()
