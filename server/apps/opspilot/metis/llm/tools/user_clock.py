"""把工具收到的时间解释成绝对时刻。

带 Z 或 ±HH:MM 的值保持原偏移。没写时区的墙钟时间用当前用户时区，
缺失或非法时回退 Asia/Shanghai。
"""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from langchain_core.runnables import RunnableConfig

from apps.opspilot.metis.llm.tools.date.current_time import resolve_user_timezone

_TIME_PARSE_ERROR = "时间格式无法识别。可以用 2026-10-22 14:28:00，或带偏移的 2026-10-22T06:28:00Z。"


def timezone_name_from_config(config: RunnableConfig | None) -> str:
    configurable: dict[str, Any] = {}
    if isinstance(config, dict):
        raw = config.get("configurable")
        if isinstance(raw, dict):
            configurable = raw
    return resolve_user_timezone(configurable.get("user_timezone"))


def parse_user_wall_time(value: Any, tz_name: str | None) -> datetime:
    """返回带时区的时刻。显式偏移优先，否则贴上用户时区。"""
    zone = ZoneInfo(resolve_user_timezone(tz_name))
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            raise ValueError(_TIME_PARSE_ERROR)
        iso = text.replace("Z", "+00:00")
        if " " in iso and "T" not in iso:
            iso = iso.replace(" ", "T", 1)
        try:
            parsed = datetime.fromisoformat(iso)
        except ValueError as exc:
            raise ValueError(_TIME_PARSE_ERROR) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=zone)
    return parsed
