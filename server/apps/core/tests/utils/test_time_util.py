"""core.utils.time_util 纯单元测试。

规格来源：各函数 docstring 定义的输入/输出契约。
- format_time_iso: "YYYY-MM-DD HH:MM:SS" -> ISO8601 毫秒 + Z
- format_timestamp: "YYYY-MM-DD HH:MM:SS" -> 秒级时间戳字符串
- get_crontab_next_runs: 合法 crontab -> 接下来 N 次执行时间；非法 -> ValueError
"""

from datetime import datetime

import pytest

from apps.core.utils.time_util import (
    format_time_iso,
    format_timestamp,
    get_crontab_next_runs,
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
