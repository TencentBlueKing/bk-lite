from apps.node_mgmt.tasks.action_task import _update_last_running_step


class _TaskNode:
    def __init__(self):
        self.result = {
            "steps": [
                {
                    "action": "execute_command",
                    "status": "running",
                    "message": "Execute collector action",
                }
            ]
        }


def test_collector_action_success_step_does_not_attach_failure_details():
    task_node = _TaskNode()

    _update_last_running_step(
        task_node,
        "success",
        "Collector action completed",
        details={
            "collector_status": 0,
            "operation": "restart",
        },
    )

    latest_step = task_node.result["steps"][-1]
    assert latest_step["status"] == "success"
    assert latest_step["details"]["collector_status"] == 0
    assert "failure" not in latest_step["details"]


def test_collector_action_error_step_attaches_failure_details():
    task_node = _TaskNode()

    _update_last_running_step(
        task_node,
        "error",
        "Collector action failed",
        details={
            "collector_status": 2,
            "operation": "restart",
        },
    )

    latest_step = task_node.result["steps"][-1]
    assert latest_step["status"] == "error"
    assert latest_step["details"]["failure"]["summary"]
