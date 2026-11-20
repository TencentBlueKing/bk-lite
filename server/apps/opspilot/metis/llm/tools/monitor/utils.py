import time
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from langchain_core.runnables import RunnableConfig

from apps.opspilot.metis.llm.common.tool_failure import wrap_tool_error_payload
from apps.opspilot.metis.llm.tools.rpc_identity import configurable_from_config, format_caller_identity_required_error
from apps.opspilot.metis.llm.tools.user_clock import parse_user_wall_time
from apps.opspilot.services.caller_identity import CALLER_IDENTITY_CONFIG_KEY
from apps.rpc.monitor import MonitorOperationAnaRpc

_UNIX_SECONDS_MIN = 1_000_000_000
_UNIX_MS_MIN = 100_000_000_000
_DEFAULT_METRIC_LOOKBACK_MS = 3_600_000


def format_monitor_caller_identity_required_error(config: Optional[RunnableConfig] = None) -> str:
    return format_caller_identity_required_error(config, "监控")


# Backward-compatible constant for imports/tests that still reference the name.
MONITOR_CALLER_IDENTITY_REQUIRED = format_monitor_caller_identity_required_error()


def resolve_monitor_user_info(config: Optional[RunnableConfig]) -> Dict[str, Any]:
    """Build Monitor RPC identity from the validated runtime snapshot only."""

    configurable = configurable_from_config(config)
    if CALLER_IDENTITY_CONFIG_KEY not in configurable:
        raise ValueError(format_monitor_caller_identity_required_error(config))

    identity = configurable[CALLER_IDENTITY_CONFIG_KEY]
    if not isinstance(identity, dict):
        raise ValueError("Monitor caller_identity must be a dictionary")

    username = identity.get("username")
    if not isinstance(username, str) or not username.strip():
        raise ValueError("Monitor caller_identity.username must be a non-empty string")

    domain = identity.get("domain")
    if not isinstance(domain, str) or not domain.strip():
        raise ValueError("Monitor caller_identity.domain must be a non-empty string")

    team_id = identity.get("team_id")
    if type(team_id) is not int or team_id <= 0:
        raise ValueError("Monitor caller_identity.team_id must be a positive integer")

    include_children = identity.get("include_children")
    if type(include_children) is not bool:
        raise ValueError("Monitor caller_identity.include_children must be a boolean")

    return {
        "user": username,
        "domain": domain,
        "team": team_id,
        "include_children": include_children,
    }


def wrap_success(data: Any) -> Dict[str, Any]:
    return {"success": True, "data": data}


def to_monitor_epoch_ms(value: Any, tz_name: str | None = None) -> Any:
    """把工具时间转成监控 RPC 用的毫秒时间戳。没写时区时按用户时区。"""
    if value in (None, ""):
        return value
    if isinstance(value, bool):
        raise ValueError("timestamp must not be a boolean")
    if isinstance(value, datetime):
        dt = value if value.tzinfo else parse_user_wall_time(value, tz_name)
        return int(dt.timestamp() * 1000)
    if isinstance(value, (int, float)):
        number = int(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return value
        if text.isdigit() or (text[0] in "+-" and text[1:].isdigit()):
            number = int(text)
        else:
            return int(parse_user_wall_time(text, tz_name).timestamp() * 1000)
    else:
        raise ValueError("timestamp must be unix seconds, milliseconds, or ISO datetime")
    abs_number = abs(number)
    if abs_number >= _UNIX_MS_MIN:
        return number
    if abs_number >= _UNIX_SECONDS_MIN:
        return number * 1000
    return number


def default_metric_window_ms() -> Tuple[int, int]:
    end_ms = int(time.time() * 1000)
    return end_ms - _DEFAULT_METRIC_LOOKBACK_MS, end_ms


def resolve_metric_window(start: Any, end: Any, tz_name: str | None = None) -> Tuple[int, int]:
    has_start = start not in (None, "")
    has_end = end not in (None, "")
    if not has_start and not has_end:
        return default_metric_window_ms()
    start_ms = to_monitor_epoch_ms(start, tz_name) if has_start else None
    end_ms = to_monitor_epoch_ms(end, tz_name) if has_end else None
    if start_ms is None:
        return int(end_ms) - _DEFAULT_METRIC_LOOKBACK_MS, int(end_ms)
    if end_ms is None:
        return int(start_ms), int(start_ms) + _DEFAULT_METRIC_LOOKBACK_MS
    return int(start_ms), int(end_ms)


def wrap_error(message: str) -> Dict[str, Any]:
    return wrap_tool_error_payload(message)


def call_monitor_rpc(
    method_name: str,
    config: Optional[RunnableConfig],
    **kwargs,
):
    try:
        user_info = resolve_monitor_user_info(config)
        rpc = MonitorOperationAnaRpc()
        method = getattr(rpc, method_name)
        result = method(user_info=user_info, **kwargs)
        if isinstance(result, dict) and result.get("result") is False:
            return wrap_error(result.get("message") or "monitor rpc call failed")
        if isinstance(result, dict) and "data" in result:
            return wrap_success(result.get("data"))
        return wrap_success(result)
    except Exception as exc:
        return wrap_error(str(exc))
