"""cmdb.utils.time_util 纯单元测试。

规格：parse_cmdb_time 将 datetime/date/数字(Excel 序列)/字符串统一为 ISO8601；
空字符串与不支持类型抛 ValueError。excel_serial_to_datetime 基准为 1899-12-30 UTC。
"""

from datetime import date, datetime, timezone

import pytest

from apps.cmdb.utils.time_util import excel_serial_to_datetime, parse_cmdb_time

pytestmark = pytest.mark.unit


class TestExcelSerial:
    def test_零对应基准日(self):
        assert excel_serial_to_datetime(0) == datetime(1899, 12, 30, tzinfo=timezone.utc)

    def test_整数天数(self):
        assert excel_serial_to_datetime(2) == datetime(1900, 1, 1, tzinfo=timezone.utc)


class TestParseCmdbTime:
    def test_datetime_原样isoformat(self):
        dt = datetime(2025, 11, 27, 10, 31, 44)
        assert parse_cmdb_time(dt) == dt.isoformat()

    def test_date_补全为零点(self):
        assert parse_cmdb_time(date(2025, 1, 1)) == "2025-01-01T00:00:00"

    def test_iso字符串(self):
        assert parse_cmdb_time("2025-11-27T10:31:44") == "2025-11-27T10:31:44"

    def test_空格分隔字符串(self):
        assert parse_cmdb_time("2025-11-27 10:31:44") == "2025-11-27T10:31:44"

    def test_斜杠日期格式(self):
        assert parse_cmdb_time("2025/11/27") == "2025-11-27T00:00:00"

    def test_数字按excel序列(self):
        assert parse_cmdb_time(0) == "1899-12-30T00:00:00+00:00"

    def test_空字符串抛错(self):
        with pytest.raises(ValueError):
            parse_cmdb_time("")

    def test_无法解析抛错(self):
        with pytest.raises(ValueError):
            parse_cmdb_time("不是时间")

    def test_不支持类型抛错(self):
        with pytest.raises(ValueError):
            parse_cmdb_time([1, 2, 3])
