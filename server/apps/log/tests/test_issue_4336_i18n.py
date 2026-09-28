from types import SimpleNamespace

import pytest
from rest_framework.exceptions import ValidationError

from apps.core.utils.loader import LanguageLoader
from apps.log.serializers.policy import AssignHandlersSerializer
from apps.log.serializers.search import LogTopStatsSerializer
from apps.log.services.log_extractor.rules import resolve_type_scope
from apps.log.utils.locale_text import log_text

KEYS = (
    "error.extractor_name_required",
    "error.extractor_instance_locked",
    "error.extractor_type_locked",
    "error.must_be_list",
    "error.list_items_must_be_int",
    "error.log_group_rule_object",
    "error.organization_required",
    "error.search_condition_object",
    "error.search_condition_query_required",
    "error.search_condition_groups_required",
    "error.log_groups_must_be_list",
    "error.log_groups_missing",
    "error.handler_invalid",
    "error.handler_required",
    "error.policy_name_exists",
    "error.topn_unsupported",
    "error.type_extractor_unsupported",
    "error.collect_type_missing",
    "error.instance_rule_limit",
    "error.instance_name_duplicate",
    "error.type_rule_limit",
    "error.type_name_duplicate",
    "error.scope_name_duplicate",
    "error.rule_ids_unique",
    "error.instance_rule_ids_exact",
    "error.type_rule_ids_exact",
    "error.event_object_required",
    "error.rule_out_of_scope",
    "error.collect_instance_required",
    "error.scope_exclusive",
    "error.generation_published",
    "error.channel_query_failed",
)


def _request(locale):
    return SimpleNamespace(user=SimpleNamespace(locale=locale))


def test_determined_error_keys_exist_in_both_locales():
    en = LanguageLoader(app="log", default_lang="en")
    zh = LanguageLoader(app="log", default_lang="zh-Hans")
    for key in KEYS:
        en_value = en.get(key)
        zh_value = zh.get(key)
        assert isinstance(en_value, str) and en_value, key
        assert isinstance(zh_value, str) and zh_value, key
        assert en_value != zh_value


def test_unknown_locale_falls_back_to_chinese_instead_of_key():
    assert log_text("zh-TW", "error.topn_unsupported") == "该字段不支持 TopN 统计"
    assert log_text("ja", "error.instance_rule_limit", count=3) == "单个采集实例最多 3 条规则"


def test_views_hand_request_to_localized_serializers():
    import re
    from pathlib import Path

    views_dir = Path(__file__).resolve().parents[1] / "views"
    localized = ("LogTopStatsSerializer", "AssignHandlersSerializer", "LogExtractorSerializer")
    offenders = []
    for path in views_dir.glob("*.py"):
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if any(f"{name}(" in line for name in localized) and "data=" in line and '"request": request' not in line:
                offenders.append(f"{path.name}:{line_no}")
    assert offenders == []


def test_rule_limit_keeps_the_count():
    assert log_text("en", "error.instance_rule_limit", count=20) == "A collect instance can have at most 20 rules"
    assert log_text("zh-Hans", "error.instance_rule_limit", count=20) == "单个采集实例最多 20 条规则"
    assert log_text(None, "error.channel_query_failed") == "通知通道查询失败"


def test_topn_message_follows_request_locale():
    data = {"attr": "_time", "log_groups": ["default"]}
    english = LogTopStatsSerializer(data=data, context={"request": _request("en")})
    chinese = LogTopStatsSerializer(data=data, context={"request": _request("zh-CN")})

    assert not english.is_valid()
    assert english.errors["attr"][0] == "This field does not support TopN statistics"
    assert not chinese.is_valid()
    assert chinese.errors["attr"][0] == "该字段不支持 TopN 统计"


def test_handler_identifier_follows_request_locale():
    english = AssignHandlersSerializer(data={"handlers": [True]}, context={"request": _request("en-US")})
    assert not english.is_valid()
    assert english.errors["handlers"][0] == "Invalid handler identifier"


def test_type_scope_message_follows_locale():
    with pytest.raises(ValidationError) as exc:
        resolve_type_scope("file", locale="en")
    assert exc.value.detail["collect_type"] == "Only syslog and snmp_trap support type-level extractors"
