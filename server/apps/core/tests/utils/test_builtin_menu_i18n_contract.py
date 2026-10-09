"""编排中心菜单 i18n key 必须能被 core 语言包解析（与作业管理同一路径）。"""

import json
from pathlib import Path

from apps.core.utils.loader import LanguageLoader, clear_language_cache

MENU_PATH = Path("support-files/system_mgmt/menus/workflow-orchestration.json")


def test_workflow_orchestration_menu_i18n_keys_resolve_in_core_language():
    payload = json.loads(MENU_PATH.read_text(encoding="utf-8"))
    clear_language_cache(app="core", lang="zh-Hans")
    clear_language_cache(app="core", lang="en")
    zh = LanguageLoader(app="core", default_lang="zh-Hans")
    en = LanguageLoader(app="core", default_lang="en")

    assert payload["client_id"] == "workflow-orchestration"
    assert zh.get("app_name.workflow-orchestration") == "编排中心"
    assert en.get("app_name.workflow-orchestration") == "Workflow Orchestration"
    assert zh.get(payload["description"])
    assert en.get(payload["description"])
    for tag in payload["tags"]:
        assert zh.get(tag), f"missing zh {tag}"
        assert en.get(tag), f"missing en {tag}"
    assert zh.get("app_name.job") == "作业管理"
