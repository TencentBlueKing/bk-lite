"""运营分析用户文案：双语词条对称，并跟随当前请求语言。"""

import re

import pytest
from django.utils import translation

from apps.core.utils.loader import LanguageLoader, clear_language_cache
from apps.operation_analysis.services.user_messages import oa_message

pytestmark = pytest.mark.unit

_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _messages(language: str) -> dict:
    clear_language_cache("operation_analysis", language)
    catalog = LanguageLoader("operation_analysis", language).translations or {}
    messages = catalog.get("messages") or {}
    assert isinstance(messages, dict)
    return messages


def test_user_message_catalogs_are_symmetric():
    en = _messages("en")
    zh = _messages("zh-Hans")
    assert set(en) == set(zh)
    assert en
    for key in en:
        assert isinstance(en[key], str)
        assert isinstance(zh[key], str)
        assert sorted(_PLACEHOLDER.findall(en[key])) == sorted(_PLACEHOLDER.findall(zh[key]))


def test_oa_message_uses_request_language_and_keeps_zh_contract():
    clear_language_cache("operation_analysis")
    with translation.override("en"):
        assert oa_message("messages.yaml_empty", "YAML内容不能为空") == "YAML content cannot be empty"
        rendered = oa_message(
            "messages.yaml_too_large",
            "YAML大小 {content_size} 字节，超过 {limit} 字节限制",
            content_size=3,
            limit=2,
        )
        assert rendered == "YAML size is 3 bytes, which exceeds the 2-byte limit"
        assert "SECRET_SENTINEL" not in rendered
        assert oa_message("messages.share_fixed_param", "参数 {name} 为固定值，不允许修改", name="region") == "Parameter region is fixed and cannot be changed"
        assert oa_message("messages.undeclared_params", "存在未声明参数: {names}", names="extra") == "Undeclared parameters: extra"
        assert oa_message("messages.filter_snapshot_invalid_timezone", "无效时区: {name}", name="Not/AZone") == "Invalid timezone: Not/AZone"
        assert (
            oa_message(
                "messages.prometheus_series_truncated",
                "结果共 {total} 条序列，已截断为 {clamped} 条",
                total=3,
                clamped=1,
            )
            == "The result has 3 series and was truncated to 1"
        )
        assert oa_message("messages.weops_request_failed_detail", "WeOps 请求失败: {detail}", detail="probe down") == "WeOps request failed: probe down"

    with translation.override("zh-hans"):
        assert oa_message("messages.yaml_empty", "fallback") == "YAML内容不能为空"
        assert oa_message("messages.builtin_action_denied", "内置对象不允许{action}", action="编辑") == "内置对象不允许编辑"
        assert oa_message("messages.missing_key_sentinel", "原文保持") == "原文保持"
        assert oa_message("messages.share_fixed_param", "参数 {name} 为固定值，不允许修改", name="region") == "参数 region 为固定值，不允许修改"
        assert oa_message("messages.undeclared_params", "存在未声明参数: {names}", names="extra") == "存在未声明参数: extra"
        assert oa_message("messages.filter_snapshot_invalid_timezone", "无效时区: {name}", name="Not/AZone") == "无效时区: Not/AZone"
        assert (
            oa_message(
                "messages.prometheus_series_truncated",
                "结果共 {total} 条序列，已截断为 {clamped} 条",
                total=3,
                clamped=1,
            )
            == "结果共 3 条序列，已截断为 1 条"
        )
        assert oa_message("messages.weops_request_failed_detail", "WeOps 请求失败: {detail}", detail="probe down") == "WeOps 请求失败: probe down"
