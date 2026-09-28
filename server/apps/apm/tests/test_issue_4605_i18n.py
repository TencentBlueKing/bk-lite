from types import SimpleNamespace

from apps.apm.serializers.control_plane import ApmAlertAssignSerializer, InstanceCatalogListQuerySerializer
from apps.apm.utils.locale_text import apm_text
from apps.core.utils.loader import LanguageLoader

KEYS = (
    "error.application_id_exists",
    "error.application_id_invalid",
    "error.unsupported_instance_query",
    "error.otlp_endpoint_server_resolved",
    "error.probe_artifact_missing",
    "error.cloud_region_config_unavailable",
    "error.channel_requires_recipients",
    "error.service_invisible",
    "error.policy_target_limit",
    "error.handler_invalid",
)


def _request(locale):
    return SimpleNamespace(user=SimpleNamespace(locale=locale))


def test_determined_error_keys_exist_in_both_locales():
    en = LanguageLoader(app="apm", default_lang="en")
    zh = LanguageLoader(app="apm", default_lang="zh-Hans")
    for key in KEYS:
        en_value = en.get(key)
        zh_value = zh.get(key)
        assert isinstance(en_value, str) and en_value, key
        assert isinstance(zh_value, str) and zh_value, key
        assert en_value != zh_value


def test_missing_locale_stays_chinese():
    assert apm_text(None, "error.application_id_exists") == "该应用 ID 已存在。"


def test_unknown_locale_falls_back_to_chinese_instead_of_key():
    assert apm_text("zh-TW", "error.application_id_exists") == "该应用 ID 已存在。"
    assert apm_text("ja", "error.channel_requires_recipients", name="Mail") == "渠道 Mail 必须配置接收人。"


def test_views_hand_request_to_serializers():
    import re
    from pathlib import Path

    views_dir = Path(__file__).resolve().parents[1] / "views"
    offenders = []
    for path in views_dir.glob("*.py"):
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"(Serializer|serializer_class)\(data=", line) and '"request":' not in line:
                offenders.append(f"{path.name}:{line_no}")
    assert offenders == []


def test_unsupported_query_follows_request_locale():
    english = InstanceCatalogListQuerySerializer(data={"unknown": 1}, context={"request": _request("en")})
    chinese = InstanceCatalogListQuerySerializer(data={"unknown": 1}, context={"request": _request("zh-CN")})

    assert not english.is_valid()
    assert list(english.errors.values())[0][0] == "Unsupported instance query parameters: unknown"
    assert not chinese.is_valid()
    assert list(chinese.errors.values())[0][0] == "不支持的实例查询参数: unknown"


def test_handler_identifier_follows_request_locale():
    english = ApmAlertAssignSerializer(data={"handlers": [True]}, context={"request": _request("en-US")})
    assert not english.is_valid()
    assert english.errors["handlers"][0] == "Invalid handler identifier"


def test_channel_message_keeps_the_name():
    assert apm_text("en", "error.channel_requires_recipients", name="Mail") == "Channel Mail requires recipients."
    assert apm_text("zh-Hans", "error.policy_target_limit", count=40) == "指定版本模式下，端点与版本组合数不能超过 40。"
