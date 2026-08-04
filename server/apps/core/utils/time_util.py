# -- coding: utf-8 --
# @File: time_util.py
# @Time: 2025/8/27 14:53
# @Author: windyzhao

import re
from datetime import datetime, timezone

from croniter import croniter

RFC3339_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")


def parse_rfc3339_utc(value: str | datetime) -> datetime:
    """Parse an RFC3339 timestamp and return the same instant in UTC.

    Timezone-less values are rejected so callers never depend on the process or
    Django timezone to recover an absolute instant.
    """
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("RFC3339 timestamp cannot be empty")
        if not RFC3339_PATTERN.fullmatch(text):
            raise ValueError("timestamp must be RFC3339 with an explicit timezone")
        normalized = f"{text[:-1]}+00:00" if text.endswith("Z") else text
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError("timestamp must be RFC3339 with an explicit timezone") from exc
    else:
        raise ValueError("timestamp must be a string or datetime")

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include Z or an explicit UTC offset")
    return parsed.astimezone(timezone.utc)


def parse_rfc3339_range_utc(value: object) -> tuple[datetime, datetime]:
    """Parse an ordered two-item RFC3339 range and normalize it to UTC."""
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError("time range must contain exactly two RFC3339 timestamps")

    try:
        start = parse_rfc3339_utc(value[0])
        end = parse_rfc3339_utc(value[1])
    except (ValueError, OverflowError) as exc:
        raise ValueError("time range values must be RFC3339 timestamps with explicit timezones") from exc

    if end <= start:
        raise ValueError("time range end must be later than start")
    return start, end


def format_rfc3339_utc(value: str | datetime) -> str:
    """Serialize an aware timestamp as canonical UTC RFC3339 milliseconds."""
    parsed = parse_rfc3339_utc(value)
    return parsed.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def rfc3339_to_timestamp(value: str | datetime) -> str:
    """Convert an RFC3339 timestamp to Unix seconds without process-TZ input."""
    return str(int(parse_rfc3339_utc(value).timestamp()))


def format_time_iso(time_str: str):
    """
    将 "YYYY-MM-DD HH:MM:SS" 格式的时间字符串转换为 ISO 8601 格式，精确到毫秒，并附加 'Z' 表示 UTC 时间。
    例如，"2023-10-05 14:30:00" ->
    "2023-10-05T14:30:00.000Z"
    :param time_str: 输入的时间字符串，格式为 "YYYY-MM-DD HH:MM:SS"
    :return: 转换后的 ISO 8601 格式时间字符串
    """
    # 解析为datetime对象
    dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")

    # 转换为ISO 8601格式（UTC时区，带毫秒和Z后缀）
    iso_format = dt.isoformat(timespec="milliseconds") + "Z"

    return iso_format


def format_timestamp(time_str: str):
    """
    将 "YYYY-MM-DD HH:MM:SS" 格式的时间字符串转换为时间戳（秒级别）。
    例如，"2023-10-05 14:30:00" -> 1696500600
    """
    dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
    timestamp = dt.timestamp()
    formatted_timestamp = str(int(timestamp))
    return formatted_timestamp


def get_crontab_next_runs(
    crontab_expression: str,
    count: int = 6,
    base_time: datetime | None = None,
) -> list[str]:
    """
    Get the next N execution times for a crontab expression.

    Args:
        crontab_expression: 5-field crontab expression (minute hour day month weekday)
        count: Number of next execution times to return (default: 6)
        base_time: Base time to calculate from (default: now)

    Returns:
        List of datetime strings (YYYY-MM-DD HH:MM:SS) for next executions

    Raises:
        ValueError: If crontab expression is invalid
    """
    if not crontab_expression or not isinstance(crontab_expression, str):
        raise ValueError("crontab_expression is required and must be a string")

    expression = crontab_expression.strip()

    if not croniter.is_valid(expression):
        raise ValueError(f"Invalid crontab expression: {expression}")

    if base_time is None:
        base_time = datetime.now()

    try:
        cron = croniter(expression, base_time)
        next_runs = []
        for _ in range(count):
            next_time = cron.get_next(datetime)
            next_runs.append(next_time.strftime("%Y-%m-%d %H:%M:%S"))
        return next_runs
    except Exception as e:
        raise ValueError(f"Failed to calculate next runs: {e}")
