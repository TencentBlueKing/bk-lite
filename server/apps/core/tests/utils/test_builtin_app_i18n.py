"""内置应用展示名翻译。"""

from apps.core.utils.builtin_app_i18n import translate_builtin_app_display_name
from apps.core.utils.loader import LanguageLoader, clear_language_cache


def _loader(lang: str) -> LanguageLoader:
    clear_language_cache(app="core", lang=lang)
    return LanguageLoader(app="core", default_lang=lang)


def test_zh_translates_screenshot_app_names():
    loader = _loader("zh-Hans")
    cases = {
        "monitor": "监控中心",
        "log": "日志中心",
        "cmdb": "CMDB",
        "alarm": "告警中心",
        "job": "作业管理",
        "ops-analysis": "运营分析",
        "ops-console": "控制台",
        "system-manager": "系统管理",
        "node": "节点管理",
        "opspilot": "OpsPilot",
        "mlops": "MLOps",
    }
    for name, expected in cases.items():
        app = {"is_build_in": True, "name": name, "display_name": name}
        translate_builtin_app_display_name(app, loader)
        assert app["display_name"] == expected


def test_en_uses_product_display_names():
    loader = _loader("en")
    app = {"is_build_in": True, "name": "monitor", "display_name": "Monitor"}
    translate_builtin_app_display_name(app, loader)
    assert app["display_name"] == "Monitor Center"

    app = {"is_build_in": True, "name": "alarm", "display_name": "Alarm"}
    translate_builtin_app_display_name(app, loader)
    assert app["display_name"] == "Alert Center"


def test_custom_app_keeps_stored_display_name():
    loader = _loader("zh-Hans")
    app = {"is_build_in": False, "name": "acme", "display_name": "我的应用"}
    translate_builtin_app_display_name(app, loader)
    assert app["display_name"] == "我的应用"


def test_missing_translation_keeps_original():
    loader = _loader("en")
    app = {"is_build_in": True, "name": "not-a-real-app", "display_name": "Stored"}
    translate_builtin_app_display_name(app, loader)
    assert app["display_name"] == "Stored"
