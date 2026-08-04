"""core.utils.time_util 纯单元测试。

规格来源：各函数 docstring 定义的输入/输出契约。
- format_time_iso: "YYYY-MM-DD HH:MM:SS" -> ISO8601 毫秒 + Z
- format_timestamp: "YYYY-MM-DD HH:MM:SS" -> 秒级时间戳字符串
- get_crontab_next_runs: 合法 crontab -> 接下来 N 次执行时间；非法 -> ValueError
"""

import os
import time
from datetime import datetime

import pytest

from apps.core.utils.time_util import (
    format_rfc3339_utc,
    format_time_iso,
    format_timestamp,
    get_crontab_next_runs,
    parse_rfc3339_range_utc,
    parse_rfc3339_utc,
    rfc3339_to_timestamp,
)

pytestmark = pytest.mark.unit


class TestFormatTimeIso:
    def test_转换为_iso8601_毫秒并带_z(self):
        assert format_time_iso("2023-10-05 14:30:00") == "2023-10-05T14:30:00.000Z"

    def test_非法格式抛_valueerror(self):
        with pytest.raises(ValueError):
            format_time_iso("2023/10/05 14:30:00")


class TestFormatTimestamp:
    def test_转换为秒级时间戳字符串(self):
        # 用本地时区无关的方式校验：解析回来应等于原始时间
        ts = format_timestamp("2023-10-05 14:30:00")
        assert ts.isdigit()
        assert datetime.fromtimestamp(int(ts)) == datetime(2023, 10, 5, 14, 30, 0)

    def test_非法格式抛_valueerror(self):
        with pytest.raises(ValueError):
            format_timestamp("not-a-time")


class TestRfc3339Time:
    def test_explicit_offset_is_normalized_to_utc(self):
        assert format_rfc3339_utc("2026-08-03T12:17:25.885+08:00") == "2026-08-03T04:17:25.885Z"

    def test_timezone_less_value_is_rejected(self):
        with pytest.raises(ValueError, match="explicit timezone"):
            parse_rfc3339_utc("2026-08-03 12:17:25")

    @pytest.mark.parametrize(
        "value",
        ["20260803T121725+08:00", "2026-08-03T12:17:25+0800", "2026-08-03+08:00"],
    )
    def test_non_rfc3339_iso_variants_are_rejected(self, value):
        with pytest.raises(ValueError, match="RFC3339"):
            parse_rfc3339_utc(value)

    def test_unix_timestamp_is_independent_of_process_timezone(self):
        original_tz = os.environ.get("TZ")
        try:
            timestamps = []
            for process_tz in ("UTC", "Asia/Shanghai"):
                os.environ["TZ"] = process_tz
                time.tzset()
                timestamps.append(rfc3339_to_timestamp("2026-01-01T00:00:00Z"))
        finally:
            if original_tz is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = original_tz
            time.tzset()

        assert timestamps == ["1767225600", "1767225600"]

    def test_time_range_is_normalized_and_ordered(self):
        start, end = parse_rfc3339_range_utc(["2026-08-03T12:00:00+08:00", "2026-08-03T05:00:00Z"])

        assert start.isoformat() == "2026-08-03T04:00:00+00:00"
        assert end.isoformat() == "2026-08-03T05:00:00+00:00"

    @pytest.mark.parametrize(
        "value",
        [
            None,
            [],
            ["2026-08-03T04:00:00Z"],
            ["2026-08-03 04:00:00", "2026-08-03T05:00:00Z"],
            ["2026-08-03T05:00:00Z", "2026-08-03T04:00:00Z"],
        ],
    )
    def test_invalid_time_range_is_rejected(self, value):
        with pytest.raises(ValueError, match="time range"):
            parse_rfc3339_range_utc(value)


class TestGetCrontabNextRuns:
    BASE = datetime(2024, 1, 1, 0, 0, 0)  # 周一

    def test_每分钟_返回默认_6_次且严格递增(self):
        runs = get_crontab_next_runs("* * * * *", base_time=self.BASE)
        assert runs == [
            "2024-01-01 00:01:00",
            "2024-01-01 00:02:00",
            "2024-01-01 00:03:00",
            "2024-01-01 00:04:00",
            "2024-01-01 00:05:00",
            "2024-01-01 00:06:00",
        ]

    def test_count_控制返回条数(self):
        runs = get_crontab_next_runs("0 0 * * *", count=3, base_time=self.BASE)
        assert runs == [
            "2024-01-02 00:00:00",
            "2024-01-03 00:00:00",
            "2024-01-04 00:00:00",
        ]

    def test_非法表达式抛_valueerror(self):
        with pytest.raises(ValueError):
            get_crontab_next_runs("not a cron", base_time=self.BASE)

    @pytest.mark.parametrize("bad", ["", None, 123])
    def test_空或非字符串抛_valueerror(self, bad):
        with pytest.raises(ValueError):
            get_crontab_next_runs(bad, base_time=self.BASE)
