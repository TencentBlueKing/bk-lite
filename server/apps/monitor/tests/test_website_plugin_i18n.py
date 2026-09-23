from pathlib import Path

import pytest
import yaml

from apps.core.utils.loader import LanguageLoader


PLUGIN_LANGUAGE_DIR = (
    Path(__file__).resolve().parents[1]
    / "support-files"
    / "plugins"
    / "Telegraf"
    / "web"
    / "web"
    / "language"
)
ZH_RESULT_CODE_ENUM = {
    "0": "成功",
    "1": "内容不匹配",
    "2": "响应体读取失败",
    "3": "连接失败",
    "4": "超时",
    "5": "DNS 错误",
    "6": "状态码不匹配",
}


def _load_plugin_language(lang: str) -> dict:
    return yaml.safe_load((PLUGIN_LANGUAGE_DIR / f"{lang}.yaml").read_text(encoding="utf-8"))


def _leaf_key_paths(value, prefix: str = "") -> set[str]:
    if not isinstance(value, dict):
        return {prefix} if prefix else set()
    paths: set[str] = set()
    for key, child in value.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(child, dict):
            paths |= _leaf_key_paths(child, path)
        else:
            paths.add(path)
    return paths


def _result_code_metric(language: dict) -> dict:
    return language["monitor_object_metric"]["Website"]["http_response_result_code"]


@pytest.fixture(scope="module")
def plugin_languages() -> dict:
    return {
        "zh-Hans": _load_plugin_language("zh-Hans"),
        "en": _load_plugin_language("en"),
    }


@pytest.fixture(scope="module")
def locale_languages() -> dict:
    return {
        lang: LanguageLoader("monitor", lang).translations
        for lang in ("zh-Hans", "en")
    }


@pytest.mark.unit
def test_website_result_code_language_leaf_keys_are_symmetric(plugin_languages):
    zh_metric = _result_code_metric(plugin_languages["zh-Hans"])
    en_metric = _result_code_metric(plugin_languages["en"])

    assert _leaf_key_paths(zh_metric) == _leaf_key_paths(en_metric)


@pytest.mark.unit
def test_website_result_code_zh_enum_covers_0_to_6(plugin_languages, locale_languages):
    zh_enum = _result_code_metric(plugin_languages["zh-Hans"]).get("enum") or {}
    locale_enum = _result_code_metric(locale_languages["zh-Hans"]).get("enum") or {}

    assert all(isinstance(key, str) for key in zh_enum)
    assert zh_enum == ZH_RESULT_CODE_ENUM
    assert locale_enum == ZH_RESULT_CODE_ENUM
