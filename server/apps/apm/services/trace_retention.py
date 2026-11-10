"""VictoriaTraces 明细保留期。健康检查与 SLO 回退共用同一解析。"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta

_DURATION_RE = re.compile(r"^(?P<amount>[1-9]\d*)(?P<unit>[dh])$")
_DEFAULT_TRACE_RETENTION = "35d"
TRACE_RETENTION_TOO_SHORT = "明细保留期不足"
TRACE_RETENTION_INVALID = "明细保留期配置无效"


def retention_days(value: str) -> float | None:
    match = _DURATION_RE.fullmatch(value.strip())
    if match is None:
        return None
    amount = int(match.group("amount"))
    return float(amount) if match.group("unit") == "d" else amount / 24


def trace_retention_setting() -> str:
    """返回 `APM_TRACE_RETENTION` 的原始时长，例如 `35d` 或 `168h`。未设置时为 `35d`。"""

    return os.getenv("APM_TRACE_RETENTION", _DEFAULT_TRACE_RETENTION)


def trace_retention_block_reason(started_at: datetime, ended_at: datetime) -> str | None:
    """VictoriaTraces 回退不能给出可信达成率时返回原因。

    未设置环境变量时与健康检查一样按 35 天解析。值写了但无法解析时，健康检查记为
    degraded（victoria_traces_retention_invalid），这里同样不查询、不套用默认天数。
    """

    days = retention_days(trace_retention_setting())
    if days is None:
        return TRACE_RETENTION_INVALID
    if ended_at - started_at > timedelta(days=days):
        return TRACE_RETENTION_TOO_SHORT
    return None
