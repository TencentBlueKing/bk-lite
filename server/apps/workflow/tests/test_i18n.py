from pathlib import Path
from string import Formatter
from types import SimpleNamespace

import yaml

from apps.workflow.services.definitions import DefinitionValidationError
from apps.workflow.services.validation_messages import render_definition_error, render_known_message
from apps.workflow.utils.i18n import workflow_message

LANGUAGE_ROOT = Path(__file__).resolve().parents[1] / "language"


def _flatten(value: dict, prefix: str = "") -> dict[str, object]:
    result = {}
    for key, item in value.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(item, dict):
            result.update(_flatten(item, path))
        else:
            result[path] = item
    return result


def _load(locale: str) -> dict[str, object]:
    with (LANGUAGE_ROOT / f"{locale}.yaml").open(encoding="utf-8") as stream:
        return _flatten(yaml.safe_load(stream) or {})


def _placeholders(value: str) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(value) if name}


def test_language_trees_and_placeholders_are_aligned():
    english = _load("en")
    chinese = _load("zh-Hans")

    assert english.keys() == chinese.keys()
    for key, english_value in english.items():
        chinese_value = chinese[key]
        assert isinstance(english_value, str)
        assert isinstance(chinese_value, str)
        assert _placeholders(english_value) == _placeholders(chinese_value)


def _request(locale: str | None):
    return SimpleNamespace(user=SimpleNamespace(locale=locale))


def _notification_error(**params):
    return DefinitionValidationError(
        "节点 notify 缺少必填输入: channel_id, recipients",
        code="node_missing_required_input",
        node_reference="notify",
        atom_key="bklite_notification",
        field_keys=["channel_id", "recipients"],
        **params,
    )


def _definition():
    return {
        "tasks": [
            {"name": "bklite_notification", "taskReferenceName": "notify", "type": "SIMPLE"},
            {"name": "bklite_notification", "taskReferenceName": "notify_again", "type": "SIMPLE"},
        ]
    }


def test_request_locale_selects_backend_message():
    request = SimpleNamespace(user=SimpleNamespace(locale="en-US"))

    assert workflow_message(request, "message.invalid_current_team", "fallback") == "Missing or invalid current_team"
    assert workflow_message(request, "message.waiting_items", "fallback", count=2) == "and 2 more"
    assert workflow_message(request, "message.report_too_large", "fallback") == "Report file exceeds the download size limit"
    assert workflow_message(request, "error.workflow_disabled", "fallback") == "Workflow is disabled"


def test_missing_required_input_uses_form_labels_in_account_language():
    error = _notification_error()
    definition = _definition()

    chinese = render_definition_error(None, error, definition=definition)
    english = render_definition_error(_request("en"), error, definition=definition)

    assert chinese == "「对外通知 · notify」缺少必填项：通知方式、通知人"
    assert english == '"Notification · notify" is missing required fields: Notification Method, Recipients'
    assert "channel_id" not in chinese
    assert "channel_id" not in english
    assert str(error) == "节点 notify 缺少必填输入: channel_id, recipients"


def test_renamed_node_keeps_the_canvas_title():
    error = DefinitionValidationError(
        "节点 notify 缺少必填输入: channel_id",
        code="node_missing_required_input",
        node_reference="notify",
        atom_key="bklite_notification",
        field_keys=["channel_id"],
    )

    message = render_definition_error(
        None,
        error,
        definition={"tasks": [{"name": "bklite_notification", "taskReferenceName": "notify", "type": "SIMPLE"}]},
        metadata={"node_titles": {"notify": "发送巡检结果"}},
    )

    assert message == "「发送巡检结果」缺少必填项：通知方式"


def test_schema_error_hides_jsonschema_english():
    error = DefinitionValidationError(
        "节点 notify 输入 channel_id 不符合原子 Schema: 1 is not of type 'integer'",
        code="node_input_invalid",
        node_reference="notify",
        atom_key="bklite_notification",
        field_key="channel_id",
    )

    message = render_definition_error(
        _request("en"),
        error,
        definition={"tasks": [{"name": "bklite_notification", "taskReferenceName": "notify", "type": "SIMPLE"}]},
    )

    assert message == '"Notification" has an invalid value for "Notification Method"'
    assert "is not of type" not in message


def test_unclassified_message_and_static_message_stay_safe():
    static = DefinitionValidationError("inputs 必须是 JSON 对象")
    unknown = DefinitionValidationError("某个没登记的句子")
    titled = DefinitionValidationError(
        "节点 notify 缺少必填输入: channel_id",
        code="node_missing_required_input",
        node_reference="notify",
        atom_key="bklite_notification",
        field_keys=["channel_id"],
    )

    assert render_definition_error(_request("en"), static) == "inputs must be a JSON object"
    assert render_definition_error(_request("en"), unknown) == "某个没登记的句子"
    assert render_definition_error(_request("en"), ValueError("调试触发器不存在")) == "Debug trigger not found"
    assert render_known_message(None, "MVP 不支持断点调试") == "MVP 不支持断点调试"
    assert render_known_message(_request("en"), "MVP 不支持断点调试") == "Breakpoint debugging is not supported in the MVP"
    assert render_definition_error(None, ValueError("停用节点 disabled_transform 的输出仍被引用，请先调整下游配置")) == ("停用节点 disabled_transform 的输出仍被引用，请先调整下游配置")
    assert "weekdays" in render_definition_error(None, ValueError("weekdays 必须至少选择一项"))
    assert render_definition_error(_request("en"), ValueError("主机响应超时")) == "主机响应超时"
    assert (
        render_definition_error(
            None,
            titled,
            definition={"tasks": [{"name": "bklite_notification", "taskReferenceName": "notify", "type": "SIMPLE"}]},
            metadata={"node_titles": {"notify": "告警{严重}"}},
        )
        == "「告警{严重}」缺少必填项：通知方式"
    )
