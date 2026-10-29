"""没写时区的工具时间按用户时区解释，显式偏移保持原样。"""

from datetime import datetime
from zoneinfo import ZoneInfo

from apps.opspilot.metis.llm.tools.monitor.utils import to_monitor_epoch_ms
from apps.opspilot.metis.llm.tools.user_clock import parse_user_wall_time


def _ms(year, month, day, hour, minute, zone):
    return int(datetime(year, month, day, hour, minute, tzinfo=ZoneInfo(zone)).timestamp() * 1000)


def test_naive_monitor_time_uses_user_timezone_not_utc():
    shanghai = _ms(2026, 10, 22, 14, 28, "Asia/Shanghai")
    assert to_monitor_epoch_ms("2026-10-22 14:28:00", "Asia/Shanghai") == shanghai
    assert to_monitor_epoch_ms("2026-10-22T14:28:00+08:00") == shanghai
    assert to_monitor_epoch_ms("2026-10-22T06:28:00Z") == shanghai
    assert to_monitor_epoch_ms("2026-10-22 14:28:00", "America/New_York") == _ms(2026, 10, 22, 14, 28, "America/New_York")


def test_missing_timezone_falls_back_to_shanghai():
    wall = parse_user_wall_time("2026-10-22 14:28:00", None)
    assert wall.tzinfo == ZoneInfo("Asia/Shanghai")
    assert wall.hour == 14
