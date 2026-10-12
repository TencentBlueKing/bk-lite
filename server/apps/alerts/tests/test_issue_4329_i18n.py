"""Issue #4329：告警接口文案和模板目录标签随请求语言切换。"""

import re
from types import SimpleNamespace

import pytest
from rest_framework.exceptions import ValidationError

from apps.alerts.notification_templates.events import EVENT_SCALAR_FIELDS
from apps.alerts.serializers.action import ActionRuleSerializer
from apps.alerts.utils.i18n import alerts_message
from apps.alerts.views.notification_template import NotificationTemplateViewSet
from apps.core.utils.loader import LanguageLoader, clear_language_cache


def _leaf_keys(node, prefix=""):
    keys = set()
    for name, value in node.items():
        path = f"{prefix}.{name}" if prefix else name
        if isinstance(value, dict):
            keys.update(_leaf_keys(value, path))
        else:
            keys.add(path)
    return keys


def _placeholders(template):
    scrubbed = str(template).replace("{{", "").replace("}}", "")
    return set(re.findall(r"\{(\w+)\}", scrubbed))


def test_alert_locale_keys_match_and_format():
    clear_language_cache(app="alerts")
    english = LanguageLoader(app="alerts", default_lang="en")
    chinese = LanguageLoader(app="alerts", default_lang="zh-Hans")
    english_keys = _leaf_keys(english.translations)
    assert english_keys == _leaf_keys(chinese.translations)
    assert english_keys
    for key in sorted(english_keys):
        en_template = english.get(key)
        zh_template = chinese.get(key)
        assert isinstance(en_template, str) and isinstance(zh_template, str)
        values = {name: "1" for name in _placeholders(en_template) | _placeholders(zh_template)}
        en_text = str(en_template).format(**values)
        zh_text = str(zh_template).format(**values)
        assert en_text != zh_text, key
        assert "对象 {" not in en_text or "{provider_param: event_field}" in en_text

    preserved = alerts_message(None, "error.input_binding_must_be_object")
    assert preserved == "入参绑定必须是对象 {provider_param: event_field}"
    assert "{source, as}" in alerts_message("en", "error.output_projection_must_be_list")
    for path in EVENT_SCALAR_FIELDS:
        assert f"catalog.event_field.{path}" in english_keys


def test_action_config_error_follows_request_locale():
    english = ActionRuleSerializer(context={"request": SimpleNamespace(user=SimpleNamespace(locale="en"))})
    with pytest.raises(ValidationError) as english_error:
        english.validate_action_config([])
    english_text = str(english_error.value.detail)
    assert "must be an object" in english_text
    assert "对象" not in english_text

    chinese = ActionRuleSerializer(context={"request": SimpleNamespace(user=SimpleNamespace(locale="zh-CN"))})
    with pytest.raises(ValidationError) as chinese_error:
        chinese.validate_action_config("bad")
    assert "必须是对象" in str(chinese_error.value.detail)


def test_template_catalog_labels_follow_locale():
    view = NotificationTemplateViewSet()
    response = view.catalog(SimpleNamespace(user=SimpleNamespace(locale="en", is_superuser=True)))
    labels = [item["label"] for item in response.data["variables"]]
    assert "Alert title" in labels
    assert "告警标题" not in labels
    orders = {item["value"]: item["label"] for item in response.data["event_block"]["orders"]}
    assert orders["-start_time"] == "Occurrence time, newest first"
    fields = {item["path"]: item["label"] for item in response.data["event_block"]["fields"]}
    assert fields["title"] == "Event title"
    assert "事件标题" not in fields.values()
