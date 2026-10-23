import json
from pathlib import Path

from apps.core.utils.loader import LanguageLoader, clear_language_cache


def test_workflow_is_standalone_app_with_execution_permission():
    payload = json.loads(Path("support-files/system_mgmt/menus/workflow.json").read_text(encoding="utf-8"))

    assert payload["client_id"] == "workflow"
    assert payload["name"] == "Workflow"
    assert payload["url"] == "/workflow"
    assert payload["description"] == "app.workflow"
    assert payload["tags"] == [
        "tag.workflow_design",
        "tag.workflow_execution",
        "tag.automation",
        "tag.approval",
    ]
    menus = {group["name"]: group["children"] for group in payload["menus"]}
    assert menus["Home"] == [{"id": "workflow_home", "name": "Home", "operation": ["View"]}]
    assert menus["Workflow"] == [
        {
            "id": "workflow",
            "name": "Workflow",
            "operation": ["View", "Add", "Edit", "Execute", "Publish", "Manage", "Delete"],
        },
        {"id": "workflow_market", "name": "Template", "operation": ["View", "Add"]},
    ]
    assert menus["Execution"] == [
        {"id": "workflow_execution", "name": "Execution", "operation": ["View", "Execute", "Approve"]},
    ]
    normal_role = next(role for role in payload["roles"] if role["name"] == "normal")
    assert normal_role["menus"] == [
        "workflow_home-View",
        "workflow-View",
        "workflow-Add",
        "workflow-Edit",
        "workflow-Execute",
        "workflow-Publish",
        "workflow-Manage",
        "workflow-Delete",
        "workflow_market-View",
        "workflow_market-Add",
        "workflow_execution-View",
        "workflow_execution-Execute",
        "workflow_execution-Approve",
    ]


def test_workflow_system_mgmt_language_covers_get_client_detail():
    """get_client_detail / AppSerializer 走 system_mgmt 语言包，需与菜单 key 对齐。"""
    clear_language_cache(app="system_mgmt", lang="zh-Hans")
    clear_language_cache(app="system_mgmt", lang="en")
    zh = LanguageLoader(app="system_mgmt", default_lang="zh-Hans")
    en = LanguageLoader(app="system_mgmt", default_lang="en")
    assert zh.get("app_name.workflow") == "编排中心"
    assert en.get("app_name.workflow") == "Workflow"
    assert zh.get("app.workflow")
    assert en.get("app.workflow")
