from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

EVAL_NONE = "none"
EVAL_FIRE = "fire"
EVAL_RESOLVE = "resolve"

SEVERITY_NONE = ""
SEVERITY_WARNING = "warning"
SEVERITY_CRITICAL = "critical"


@dataclass
class EvalState:
    breaching_since: datetime | None = None
    recovering_since: datetime | None = None


def compare(op: str, value: float, threshold: float) -> bool:
    if op == ">":
        return value > threshold
    if op == "<":
        return value < threshold
    if op == "<=":
        return value <= threshold
    return value >= threshold  # ">=" and empty


def breached(op: str, value: float, warn: float, critical: float) -> str:
    down = op in {"<", "<="}
    critical_hit = critical > 0 and compare(op, value, critical)
    warn_hit = warn > 0 and compare(op, value, warn)
    if down:
        if critical_hit:
            return SEVERITY_CRITICAL
        if warn_hit:
            return SEVERITY_WARNING
        return SEVERITY_NONE
    if critical_hit:
        return SEVERITY_CRITICAL
    if warn_hit:
        return SEVERITY_WARNING
    return SEVERITY_NONE


def advance(
    state: EvalState,
    is_breached: bool,
    has_open: bool,
    for_duration: timedelta,
    now: datetime,
) -> str:
    if is_breached:
        state.recovering_since = None
        if has_open:
            state.breaching_since = None
            return EVAL_NONE
        if state.breaching_since is None:
            state.breaching_since = now
            if for_duration.total_seconds() > 0:
                return EVAL_NONE
        if for_duration.total_seconds() <= 0 or now - state.breaching_since >= for_duration:
            state.breaching_since = None
            return EVAL_FIRE
        return EVAL_NONE

    state.breaching_since = None
    if not has_open:
        state.recovering_since = None
        return EVAL_NONE
    if state.recovering_since is None:
        state.recovering_since = now
        if for_duration.total_seconds() > 0:
            return EVAL_NONE
    if for_duration.total_seconds() <= 0 or now - state.recovering_since >= for_duration:
        state.recovering_since = None
        return EVAL_RESOLVE
    return EVAL_NONE


def should_renotify(
    last_notified_at: datetime | None,
    renotify_minutes: int | None,
    now: datetime,
) -> bool:
    if renotify_minutes is None or renotify_minutes <= 0:
        return False
    if last_notified_at is None:
        return True
    return now - last_notified_at >= timedelta(minutes=renotify_minutes)
