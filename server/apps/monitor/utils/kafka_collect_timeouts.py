"""Kafka 采集超时偏序校验：GROUP_METRICS_TIMEOUT 必须小于 interval。"""

from __future__ import annotations

import re
from typing import Any

from apps.core.exceptions.base_app_exception import ValidationAppException

_SECONDS_RE = re.compile(r"^(\d+)(?:s)?$", re.IGNORECASE)


def parse_timeout_seconds(value: Any) -> int | None:
    """解析秒数字面值或带 s 后缀的字符串；无法解析时返回 None。"""
    if value is None or value is False:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        seconds = int(value)
        return seconds if seconds > 0 else None
    text = str(value).strip()
    if not text:
        return None
    match = _SECONDS_RE.fullmatch(text)
    if not match:
        return None
    seconds = int(match.group(1))
    return seconds if seconds > 0 else None


def assert_kafka_group_metrics_timeout_lt_interval(
    group_metrics_timeout: Any,
    interval: Any,
) -> None:
    """
    强制 GROUP_METRICS_TIMEOUT < interval。

    Telegraf child 模板中 timeout/response_timeout 与 interval 一致下发，
    因此消费组采集超时必须严格小于采集间隔，否则 Telegraf 可能先于 exporter 结束。
    """
    group_seconds = parse_timeout_seconds(group_metrics_timeout)
    interval_seconds = parse_timeout_seconds(interval)
    if group_seconds is None or interval_seconds is None:
        return
    if group_seconds >= interval_seconds:
        raise ValidationAppException(
            "消费组采集超时必须小于采集间隔："
            f"GROUP_METRICS_TIMEOUT={group_seconds}s，interval={interval_seconds}s"
        )


def extract_group_metrics_timeout_from_env(env_config: dict | None) -> Any:
    """从 child/base env_config 中取出 GROUP_METRICS_TIMEOUT（兼容带 config_id 后缀）。"""
    if not env_config:
        return None
    if "GROUP_METRICS_TIMEOUT" in env_config:
        return env_config.get("GROUP_METRICS_TIMEOUT")
    for key, value in env_config.items():
        if str(key).startswith("GROUP_METRICS_TIMEOUT"):
            return value
    return None
