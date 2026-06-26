from unittest.mock import patch
from apps.alerts.action.engine import ActionEngine


@patch("apps.alerts.tasks.action_tasks.process_alert_actions")
def test_dispatch_async_enqueues_task(mock_task):
    ActionEngine.dispatch_async("A1", "created")
    mock_task.delay.assert_called_once_with("A1", "created")


@patch("apps.alerts.tasks.action_tasks.process_alert_actions")
def test_dispatch_async_swallows_enqueue_error(mock_task):
    mock_task.delay.side_effect = RuntimeError("broker down")
    # 不得抛出——绝不阻塞告警主流程
    ActionEngine.dispatch_async("A1", "created")
