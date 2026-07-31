"""ScheduleCalculator：纯函数计算下一次计划执行时间。

Subscription.timezone 是独立业务配置，不继承 creator_timezone。
scheduled_local_time 仅用于展示/审计，不参与调度计算。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# 与 datetime.weekday() 一致：周一=0 … 周日=6
WEEKDAY_MONDAY = 0
WEEKDAY_SUNDAY = 6

SCHEDULE_TYPE_DAILY = "daily"
SCHEDULE_TYPE_WEEKLY = "weekly"
SCHEDULE_TYPE_MONTHLY = "monthly"
VALID_SCHEDULE_TYPES = frozenset(
    {
        SCHEDULE_TYPE_DAILY,
        SCHEDULE_TYPE_WEEKLY,
        SCHEDULE_TYPE_MONTHLY,
    }
)


@dataclass(frozen=True)
class ScheduleSpec:
    schedule_type: str
    hour: int
    minute: int
    weekday: int | None = None
    day_of_month: int | None = None

    def validate(self) -> None:
        if self.schedule_type not in VALID_SCHEDULE_TYPES:
            raise ValueError(f"不支持的周期类型: {self.schedule_type}")
        if not (0 <= self.hour <= 23):
            raise ValueError("schedule_hour 必须在 0–23")
        if not (0 <= self.minute <= 59):
            raise ValueError("schedule_minute 必须在 0–59")
        if self.schedule_type == SCHEDULE_TYPE_WEEKLY:
            if self.weekday is None or not (
                WEEKDAY_MONDAY <= self.weekday <= WEEKDAY_SUNDAY
            ):
                raise ValueError("weekly 必须指定 weekday（0=周一 … 6=周日）")
        if self.schedule_type == SCHEDULE_TYPE_MONTHLY:
            if self.day_of_month is None or not (
                1 <= self.day_of_month <= 31
            ):
                raise ValueError("monthly 必须指定 day_of_month（1–31）")


@dataclass(frozen=True)
class NextRun:
    """下一次计划执行。

    utc 用于调度比较与持久化 next_run_at / scheduled_time_utc。
    scheduled_local_time / timezone 仅展示与审计，不参与计算。
    """

    utc: datetime
    timezone: str
    scheduled_local_time: str


def validate_iana_timezone(timezone_name: str) -> str:
    if not isinstance(timezone_name, str) or not timezone_name.strip():
        raise ValueError("timezone 必须是有效的 IANA 时区")
    candidate = timezone_name.strip()
    try:
        ZoneInfo(candidate)
    except (ZoneInfoNotFoundError, ValueError, KeyError) as exc:
        raise ValueError(f"无效的 IANA 时区: {candidate}") from exc
    return candidate


def _ensure_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=dt_timezone.utc)
    return value.astimezone(dt_timezone.utc)


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        nxt = date(year + 1, 1, 1)
    else:
        nxt = date(year, month + 1, 1)
    return (nxt - date(year, month, 1)).days


def _clamp_month_day(year: int, month: int, day_of_month: int) -> int:
    return min(day_of_month, _days_in_month(year, month))


def _resolve_local_wall_time(
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int,
    tz: ZoneInfo,
) -> datetime:
    """将本地墙钟时间解析为 aware datetime。

    - 秋季回拨（本地时间重复）：取第一次出现（fold=0）
    - 春季跳时（本地时间不存在）：取该日期第一个有效且不早于目标的墙钟时刻

    通过 UTC 逐分钟探测真实墙钟，避免 zoneinfo 对不存在本地时间的虚假 round-trip。
    """
    target_date = date(year, month, day)
    day_start_utc = datetime(
        year, month, day, 0, 0, tzinfo=tz, fold=0
    ).astimezone(dt_timezone.utc)

    first_at_or_after: datetime | None = None
    exact_first: datetime | None = None

    for offset_minutes in range(36 * 60):
        instant = day_start_utc + timedelta(minutes=offset_minutes)
        local = instant.astimezone(tz)
        if local.date() < target_date:
            continue
        if local.date() > target_date:
            break
        wall = local.replace(second=0, microsecond=0)
        if (wall.hour, wall.minute) == (hour, minute) and exact_first is None:
            exact_first = wall
            break
        if (
            first_at_or_after is None
            and (wall.hour, wall.minute) >= (hour, minute)
        ):
            first_at_or_after = wall

    if exact_first is not None:
        return exact_first
    if first_at_or_after is not None:
        return first_at_or_after

    raise ValueError(
        f"无法解析本地时间 {year:04d}-{month:02d}-{day:02d} "
        f"{hour:02d}:{minute:02d} ({tz})"
    )


def _format_scheduled_local_time(local_aware: datetime) -> str:
    return local_aware.strftime("%Y-%m-%d %H:%M")


def _build_next_run(local_aware: datetime, timezone_name: str) -> NextRun:
    return NextRun(
        utc=local_aware.astimezone(dt_timezone.utc),
        timezone=timezone_name,
        scheduled_local_time=_format_scheduled_local_time(local_aware),
    )


def _iter_candidate_dates(
    spec: ScheduleSpec,
    start_local_date: date,
):
    # 安全上限：约两年的候选日
    if spec.schedule_type == SCHEDULE_TYPE_DAILY:
        current = start_local_date
        for _ in range(800):
            yield current
            current += timedelta(days=1)
        return

    if spec.schedule_type == SCHEDULE_TYPE_WEEKLY:
        assert spec.weekday is not None
        current = start_local_date
        while current.weekday() != spec.weekday:
            current += timedelta(days=1)
        for _ in range(120):
            yield current
            current += timedelta(days=7)
        return

    assert spec.day_of_month is not None
    year = start_local_date.year
    month = start_local_date.month
    for _ in range(30):
        day = _clamp_month_day(year, month, spec.day_of_month)
        candidate = date(year, month, day)
        if candidate >= start_local_date:
            yield candidate
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1


def next_run(
    spec: ScheduleSpec,
    timezone_name: str,
    after: datetime,
) -> NextRun:
    """返回严格晚于 after 的下一次计划时间（UTC）。"""
    spec.validate()
    tz_name = validate_iana_timezone(timezone_name)
    tz = ZoneInfo(tz_name)
    after_utc = _ensure_aware_utc(after)
    after_local = after_utc.astimezone(tz)
    start_date = after_local.date()

    for candidate_date in _iter_candidate_dates(spec, start_date):
        local_aware = _resolve_local_wall_time(
            candidate_date.year,
            candidate_date.month,
            candidate_date.day,
            spec.hour,
            spec.minute,
            tz,
        )
        if local_aware.astimezone(dt_timezone.utc) > after_utc:
            return _build_next_run(local_aware, tz_name)

    raise RuntimeError("无法计算下一次计划时间")


def next_after(
    spec: ScheduleSpec,
    timezone_name: str,
    scheduled_time_utc: datetime,
) -> NextRun:
    """返回某次计划时刻之后的下一期（用于推进 next_run_at）。"""
    return next_run(spec, timezone_name, after=scheduled_time_utc)
