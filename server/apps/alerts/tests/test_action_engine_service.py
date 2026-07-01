import pytest
from unittest.mock import patch
from apps.alerts.models.action import ActionRule, ActionExecution
from apps.alerts.models.models import Alert
from apps.alerts.action.engine import ActionEngine


def _alert(team=[1], aid="A1"):
    return Alert.objects.create(alert_id=aid, fingerprint="fp", title="disk full",
                                content="c", level="1", status="unassigned",
                                labels={"ip": "10.0.0.5"}, team=team)


def _rule(events, match_rules=None, team=[1], active=True):
    return ActionRule.objects.create(name="r", is_active=active, team=team,
                                     trigger_events=events, match_rules=match_rules or [],
                                     action_type="job", action_config={"script_id": 1})


@pytest.mark.django_db
@patch("apps.alerts.action.engine.get_handler")
def test_match_creates_running_execution_and_dispatches(mock_get):
    alert = _alert()
    _rule(events=["created"], match_rules=[[{"key": "level", "operator": "eq", "value": "1"}]])
    ActionEngine().evaluate(alert, "created")
    ex = ActionExecution.objects.get(alert=alert)
    assert ex.trigger_event == "created"
    assert ex.idempotency_key.endswith(":created")
    mock_get.return_value.execute.assert_called_once()


@pytest.mark.django_db
@patch("apps.alerts.action.engine.get_handler")
def test_event_not_in_trigger_events_noop(mock_get):
    alert = _alert()
    _rule(events=["resolved"])
    ActionEngine().evaluate(alert, "created")
    assert ActionExecution.objects.count() == 0
    mock_get.return_value.execute.assert_not_called()


@pytest.mark.django_db
@patch("apps.alerts.action.engine.get_handler")
def test_no_match_noop(mock_get):
    alert = _alert()
    _rule(events=["created"], match_rules=[[{"key": "level", "operator": "eq", "value": "0"}]])
    ActionEngine().evaluate(alert, "created")
    assert ActionExecution.objects.count() == 0


@pytest.mark.django_db
@patch("apps.alerts.action.engine.get_handler")
def test_duplicate_auto_trigger_skipped(mock_get):
    alert = _alert()
    _rule(events=["created"])
    ActionEngine().evaluate(alert, "created")
    ActionEngine().evaluate(alert, "created")
    assert ActionExecution.objects.filter(alert=alert).count() == 1
    assert mock_get.return_value.execute.call_count == 1


@pytest.mark.django_db
@patch("apps.alerts.action.engine.get_handler")
def test_team_isolation(mock_get):
    alert = _alert(team=[1])
    _rule(events=["created"], team=[2])
    ActionEngine().evaluate(alert, "created")
    assert ActionExecution.objects.count() == 0


@pytest.mark.django_db
@patch("apps.alerts.action.engine.get_handler")
def test_inactive_rule_skipped(mock_get):
    alert = _alert()
    _rule(events=["created"], active=False)
    ActionEngine().evaluate(alert, "created")
    assert ActionExecution.objects.count() == 0
