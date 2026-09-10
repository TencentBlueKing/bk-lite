"""受限的告警通知模板校验与渲染。

模板只支持 ``{{ path.to.value }}`` 取值。这里故意不使用 Jinja：模板内容来自页面，
它不应拥有表达式、调用、循环或过滤器能力。
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from html.parser import HTMLParser
from typing import Any, Mapping

MAX_SOURCE_BYTES = 64 * 1024
MAX_OUTPUT_BYTES = 256 * 1024
MAX_VALUE_BYTES = 64 * 1024
MAX_COLLECTION_ITEMS = 100
MAX_VALUE_DEPTH = 6
MAX_SUBJECT_LENGTH = 200
MAX_PLACEHOLDERS = 200
MISSING_VALUE = "—"

MARKDOWN_CHANNELS = {"enterprise_wechat_bot", "dingtalk_bot", "feishu_bot"}
ALLOWED_ROOTS = {"alert", "labels", "dimensions", "enrichment", "notification", "summary"}
ALERT_FIELDS = {
    "alert_id",
    "title",
    "content",
    "level",
    "level_id",
    "status",
    "source_name",
    "resource_id",
    "resource_name",
    "resource_type",
    "item",
    "created_at",
    "first_event_time",
    "last_event_time",
    "operators",
    "team",
}
NOTIFICATION_FIELDS = {
    "scene",
    "scene_name",
    "receivers",
    "receiver_names",
    "generated_at",
    "action_summary",
    "actor_name",
    "previous_receiver_names",
    "action_time",
}
OPERATION_NOTIFICATION_FIELDS = {
    "action_summary",
    "actor_name",
    "previous_receiver_names",
    "action_time",
}
SUMMARY_FIELDS = {"total", "displayed", "omitted", "alerts"}
PATH_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)*$")
PLACEHOLDER_PATTERN = re.compile(r"{{\s*([^{}]+?)\s*}}")
TEMPLATE_MARKER_PATTERN = re.compile(r"({{|}}|{%|%}|{#|#})")
MARKDOWN_ESCAPE_PATTERN = re.compile(r"([\\`*_{}\[\]()#+\-.!|>~])")


class TemplateValidationError(ValueError):
    """模板源不满足受限语法或格式安全契约。"""


@dataclass(frozen=True)
class TemplateRenderResult:
    value: str
    missing_fields: list[str]


class _EmailHTMLValidator(HTMLParser):
    BLOCKED_TAGS = {
        "script",
        "style",
        "iframe",
        "object",
        "embed",
        "form",
        "input",
        "button",
        "meta",
        "link",
        "base",
        "svg",
        "math",
    }
    URL_ATTRIBUTES = {"href", "src", "action", "formaction", "background", "poster", "xlink:href"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.errors: list[str] = []

    def handle_starttag(self, tag, attrs):
        self._validate_tag(tag, attrs)

    def handle_startendtag(self, tag, attrs):
        self._validate_tag(tag, attrs)

    def _validate_tag(self, tag, attrs):
        normalized_tag = tag.lower()
        if normalized_tag in self.BLOCKED_TAGS:
            self.errors.append(f"不允许使用 HTML 标签 <{normalized_tag}>")
        for raw_name, raw_value in attrs:
            name = (raw_name or "").lower()
            value = (raw_value or "").strip()
            lowered = value.lower()
            if name.startswith("on"):
                self.errors.append(f"不允许使用事件属性 {name}")
            if "{{" in value or "}}" in value:
                self.errors.append("变量只能放在 HTML 文本节点中")
            if name in self.URL_ATTRIBUTES and not self._safe_url(lowered):
                self.errors.append(f"属性 {name} 使用了不安全的 URL")
            if name == "style" and any(token in lowered for token in ("url(", "expression(", "@import", "behavior:")):
                self.errors.append("style 中不允许外部资源或可执行表达式")

    @staticmethod
    def _safe_url(value):
        if not value or value.startswith(("#", "/", "./", "../")):
            return True
        return value.startswith(("https://", "http://", "mailto:"))


def _validate_placeholder(path: str, *, scope: str) -> None:
    if not PATH_PATTERN.fullmatch(path):
        raise TemplateValidationError(f"变量语法不合法: {path}")
    parts = path.split(".")
    if parts[0] not in ALLOWED_ROOTS or any(part.startswith("_") for part in parts):
        raise TemplateValidationError(f"不支持的变量: {path}")
    if len(parts) < 2:
        raise TemplateValidationError(f"变量必须包含字段路径: {path}")
    if parts[0] == "alert" and parts[1] not in ALERT_FIELDS:
        raise TemplateValidationError(f"不支持的告警字段: {path}")
    if parts[0] == "notification" and parts[1] not in NOTIFICATION_FIELDS:
        raise TemplateValidationError(f"不支持的通知字段: {path}")
    if parts[0] == "notification" and parts[1] in OPERATION_NOTIFICATION_FIELDS and scope != "alert_operation":
        raise TemplateValidationError("告警操作变量只能用于告警操作通知模板")
    if parts[0] == "summary" and parts[1] not in SUMMARY_FIELDS:
        raise TemplateValidationError(f"不支持的汇总字段: {path}")
    if scope in {"single_alert", "alert_operation"} and parts[0] == "summary":
        raise TemplateValidationError("单告警模板不能使用 summary 变量")
    if scope == "unassigned_summary" and parts[0] in {"alert", "labels", "dimensions", "enrichment"}:
        raise TemplateValidationError("未分派汇总模板不能使用单告警变量")


def validate_source(source: str, *, channel_type: str, is_subject: bool = False, scope: str = "single_alert") -> list[str]:
    if not isinstance(source, str):
        raise TemplateValidationError("模板内容必须是字符串")
    if len(source.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise TemplateValidationError("模板内容不能超过 64KB")
    if is_subject:
        if "\r" in source or "\n" in source:
            raise TemplateValidationError("标题不能包含换行")
        if len(source) > MAX_SUBJECT_LENGTH:
            raise TemplateValidationError("标题不能超过 200 个字符")
    if any(marker in source for marker in ("{%", "%}", "{#", "#}")):
        raise TemplateValidationError("模板只支持 {{ path }} 变量")

    matches = list(PLACEHOLDER_PATTERN.finditer(source))
    if len(matches) > MAX_PLACEHOLDERS:
        raise TemplateValidationError("模板变量不能超过 200 个")
    paths = []
    for match in matches:
        path = match.group(1).strip()
        _validate_placeholder(path, scope=scope)
        paths.append(path)

    residue = PLACEHOLDER_PATTERN.sub("", source)
    if TEMPLATE_MARKER_PATTERN.search(residue):
        raise TemplateValidationError("存在未闭合或不受支持的模板标记")

    if channel_type == "email" and not is_subject:
        parser = _EmailHTMLValidator()
        try:
            parser.feed(source)
            parser.close()
        except Exception as exc:
            raise TemplateValidationError("HTML 结构无法解析") from exc
        if parser.errors:
            raise TemplateValidationError(parser.errors[0])
    return paths


def _bounded_json_value(value: Any, depth: int = 0):
    if depth > MAX_VALUE_DEPTH:
        raise TemplateValidationError("变量值嵌套层级不能超过 6 层")
    if isinstance(value, Mapping):
        if len(value) > MAX_COLLECTION_ITEMS:
            raise TemplateValidationError("变量对象不能超过 100 个字段")
        return {str(key): _bounded_json_value(item, depth + 1) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        if len(value) > MAX_COLLECTION_ITEMS:
            raise TemplateValidationError("变量列表不能超过 100 项")
        return [_bounded_json_value(item, depth + 1) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat()
    return str(value)


def _serialize_value(value: Any) -> str:
    if value is None or value == "":
        return MISSING_VALUE
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (datetime, date)):
        return value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat()
    if isinstance(value, (dict, list, tuple)):
        serialized = json.dumps(_bounded_json_value(value), ensure_ascii=False, separators=(",", ":"))
    else:
        serialized = str(value)
    if len(serialized.encode("utf-8")) > MAX_VALUE_BYTES:
        raise TemplateValidationError("单个变量值不能超过 64KB")
    return serialized


def _resolve_path(context: Mapping[str, Any], path: str):
    current: Any = context
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None, False
        current = current[part]
    return current, current not in (None, "")


def _escape_markdown(value: str) -> str:
    value = value.replace("@", "@\u200b")
    return MARKDOWN_ESCAPE_PATTERN.sub(r"\\\1", value)


def render_source(
    source: str,
    context: Mapping[str, Any],
    *,
    channel_type: str,
    is_subject: bool = False,
    scope: str = "single_alert",
) -> TemplateRenderResult:
    validate_source(source, channel_type=channel_type, is_subject=is_subject, scope=scope)
    missing_fields: list[str] = []
    replacement_bytes = 0

    def replace(match):
        nonlocal replacement_bytes
        path = match.group(1).strip()
        value, present = _resolve_path(context, path)
        if not present:
            missing_fields.append(path)
        serialized = _serialize_value(value)
        replacement_bytes += len(serialized.encode("utf-8"))
        if replacement_bytes + len(source.encode("utf-8")) > MAX_OUTPUT_BYTES:
            raise TemplateValidationError("模板渲染结果不能超过 256KB")
        if is_subject:
            return serialized
        if channel_type == "email":
            return html.escape(serialized, quote=False)
        if channel_type in MARKDOWN_CHANNELS:
            return _escape_markdown(serialized)
        return serialized

    value = PLACEHOLDER_PATTERN.sub(replace, source)
    if len(value.encode("utf-8")) > MAX_OUTPUT_BYTES:
        raise TemplateValidationError("模板渲染结果不能超过 256KB")
    if is_subject and ("\r" in value or "\n" in value):
        raise TemplateValidationError("标题变量值不能包含换行")
    if is_subject and len(value) > MAX_SUBJECT_LENGTH:
        raise TemplateValidationError("标题渲染结果不能超过 200 个字符")
    return TemplateRenderResult(value=value, missing_fields=list(dict.fromkeys(missing_fields)))


def build_alert_context(
    alert: Any,
    receivers: list[str],
    scene: str,
    *,
    generated_at: datetime | None = None,
    level_display_name: str | None = None,
    notification_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    scene_names = {
        "assignment": "告警分派",
        "reassignment": "告警转派",
        "reminder": "告警提醒",
        "escalation": "告警升级",
        "recovery": "告警恢复",
        "test": "测试发送",
    }
    raw_level = getattr(alert, "level", "")
    alert_data = {
        "alert_id": getattr(alert, "alert_id", ""),
        "title": getattr(alert, "title", ""),
        "content": getattr(alert, "content", ""),
        "level": level_display_name or raw_level,
        "level_id": raw_level,
        "status": getattr(alert, "status", ""),
        "source_name": getattr(alert, "source_name", ""),
        "resource_id": getattr(alert, "resource_id", ""),
        "resource_name": getattr(alert, "resource_name", ""),
        "resource_type": getattr(alert, "resource_type", ""),
        "item": getattr(alert, "item", ""),
        "created_at": getattr(alert, "created_at", None),
        "first_event_time": getattr(alert, "first_event_time", None),
        "last_event_time": getattr(alert, "last_event_time", None),
        "operators": getattr(alert, "operator", None) or [],
        "team": getattr(alert, "team", None) or [],
    }
    operation_notification = {
        key: notification_context[key] for key in OPERATION_NOTIFICATION_FIELDS if notification_context and key in notification_context
    }
    return {
        "alert": alert_data,
        "labels": getattr(alert, "labels", None) or {},
        "dimensions": getattr(alert, "dimensions", None) or {},
        "enrichment": getattr(alert, "enrichment", None) or {},
        "notification": {
            "scene": scene,
            "scene_name": scene_names.get(scene, scene),
            "receivers": receivers,
            "receiver_names": "、".join(str(receiver) for receiver in receivers),
            "generated_at": generated_at or datetime.now().astimezone(),
            **operation_notification,
        },
    }
