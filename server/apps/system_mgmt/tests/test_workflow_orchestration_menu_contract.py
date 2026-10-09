import json
from pathlib import Path

from apps.core.utils.loader import LanguageLoader, clear_language_cache


def test_workflow_orchestration_is_standalone_app_with_execution_permission():
    payload = json.loads(Path("support-files/system_mgmt/menus/workflow-orchestration.json").read_text(encoding="utf-8"))

    assert payload["client_id"] == "workflow-orchestration"
    assert payload["name"] == "Workflow Orchestration"
    assert payload["url"] == "/workflow-orchestration"
    assert payload["description"] == "app.workflow-orchestration"
    assert payload["tags"] == [
        "tag.workflow_design",
        "tag.workflow_execution",
        "tag.automation",
        "tag.approval",
    ]
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


def test_workflow_orchestration_system_mgmt_language_covers_get_client_detail():
    """get_client_detail / AppSerializer 走 system_mgmt 语言包，需与菜单 key 对齐。"""
    clear_language_cache(app="system_mgmt", lang="zh-Hans")
    clear_language_cache(app="system_mgmt", lang="en")
    zh = LanguageLoader(app="system_mgmt", default_lang="zh-Hans")
    en = LanguageLoader(app="system_mgmt", default_lang="en")
    assert zh.get("app_name.workflow-orchestration") == "编排中心"
    assert en.get("app_name.workflow-orchestration") == "Workflow Orchestration"
    assert zh.get("app.workflow-orchestration")
    assert en.get("app.workflow-orchestration")
