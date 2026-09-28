import json
from pathlib import Path


def test_workflow_orchestration_is_standalone_app_with_execution_permission():
    payload = json.loads(Path("support-files/system_mgmt/menus/workflow-orchestration.json").read_text(encoding="utf-8"))

    assert payload["client_id"] == "workflow-orchestration"
    assert payload["name"] == "Workflow Orchestration"
    assert payload["url"] == "/workflow-orchestration"
    workflow_menu = payload["menus"][0]["children"][0]
    assert workflow_menu == {
        "id": "workflow",
        "name": "Workflow",
        "operation": ["View", "Add", "Edit", "Execute", "Publish", "Approve", "Manage", "Delete"],
    }
    normal_role = next(role for role in payload["roles"] if role["name"] == "normal")
    assert normal_role["menus"] == [
        "workflow-View",
        "workflow-Add",
        "workflow-Edit",
        "workflow-Execute",
        "workflow-Publish",
        "workflow-Approve",
        "workflow-Manage",
        "workflow-Delete",
    ]
