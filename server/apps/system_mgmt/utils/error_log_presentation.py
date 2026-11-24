"""错误日志读出展示。库存行形状不变，展示字段只在读边界计算。"""

import re
from dataclasses import dataclass

from apps.system_mgmt.utils.operation_log_utils import resolve_app_display_name

MASK = "****"
UNRECORDED = "未记录"
STACK_UNRECORDED = "未记录堆栈"

STORED_TO_CONSOLE_APP = {
    "system_mgmt": "system-manager",
}
CONSOLE_TO_STORED_APP = {
    "system-manager": "system_mgmt",
}

_TEMPLATE = re.compile(
    r"^\[(?P<method>[A-Z]+)\] (?P<path>.+)\n" r"错误类型: (?P<exception_type>\S+)\n" r"错误信息: (?P<reason>.*)\Z",
    re.DOTALL,
)
_SENSITIVE_FIELD = re.compile(r"(?i)((?:[^\s=:]*?(?:password|token|secret|api_key|authorization|otp)[^\s=:]*))" r"(\s*[=:]\s*)" r"([^\s&]+)")
_QUERY_STRING = re.compile(r"\?([^#\s]*)")
_PEM_PRIVATE_KEY = re.compile(
    r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----",
    re.DOTALL,
)
_BEARER_TOKEN = re.compile(r"(?i)\bBearer\s+\S+")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
_URL_USERINFO = re.compile(r"(?<=://)[^/\s:]+:[^@\s]+@")


@dataclass(frozen=True)
class ErrorLogPresentation:
    app_name: str
    recorded_text: str
    parsed: bool
    method: str
    path: str
    exception_type: str
    reason: str
    stack_text: str


def request_path_without_query(path):
    if not path:
        return ""
    return path.split("?", 1)[0]


def console_app_id(stored_app):
    return STORED_TO_CONSOLE_APP.get(stored_app, stored_app or "")


def expand_app_filter_values(values):
    expanded = []
    seen = set()
    for value in values:
        aliases = (value, STORED_TO_CONSOLE_APP.get(value), CONSOLE_TO_STORED_APP.get(value))
        for item in aliases:
            if item and item not in seen:
                seen.add(item)
                expanded.append(item)
    return expanded


def apply_display_mask(text):
    if not text:
        return text or ""
    masked = _QUERY_STRING.sub(_mask_query_match, text)
    return _SENSITIVE_FIELD.sub(_mask_field_match, masked)


def apply_export_mask(text):
    masked = apply_display_mask(text)
    if not masked:
        return masked
    masked = _PEM_PRIVATE_KEY.sub(MASK, masked)
    masked = _BEARER_TOKEN.sub(MASK, masked)
    masked = _JWT.sub(MASK, masked)
    return _URL_USERINFO.sub(MASK, masked)


def present_error_log(
    *,
    app,
    error_message,
    stack_trace="",
    mapping=None,
    loader=None,
):
    recorded = apply_display_mask(error_message or "")
    stack_text = apply_display_mask(stack_trace or "")
    parsed = _TEMPLATE.fullmatch(error_message or "")
    if parsed is None:
        method = path = exception_type = reason = ""
    else:
        method = parsed.group("method")
        path = request_path_without_query(parsed.group("path"))
        exception_type = parsed.group("exception_type")
        reason = apply_display_mask(parsed.group("reason"))
    return ErrorLogPresentation(
        app_name=resolve_app_display_name(console_app_id(app), mapping, loader=loader) or (app or ""),
        recorded_text=recorded,
        parsed=parsed is not None,
        method=method,
        path=path,
        exception_type=exception_type,
        reason=reason,
        stack_text=stack_text,
    )


def export_unrecorded(value, empty_label=UNRECORDED):
    if value:
        return value
    return empty_label


def _mask_query_match(match):
    pairs = []
    for item in match.group(1).split("&"):
        if item == "":
            continue
        if "=" in item:
            key, _value = item.split("=", 1)
            pairs.append(f"{key}={MASK}")
        else:
            pairs.append(item)
    return "?" + "&".join(pairs)


def _mask_field_match(match):
    return f"{match.group(1)}{match.group(2)}{MASK}"
