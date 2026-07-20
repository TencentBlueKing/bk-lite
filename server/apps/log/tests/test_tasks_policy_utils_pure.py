"""apps/log/tasks/utils/policy.py 纯函数测试：period_to_seconds / format_period。

无 DB/IO，覆盖全部分支与异常路径。
"""
import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.log.tasks.utils.policy import format_period, period_to_seconds


class TestPeriodToSeconds:
    def test_min_converts_to_seconds(self):
        assert period_to_seconds({"type": "min", "value": 5}) == 300

    def test_hour_converts_to_seconds(self):
        assert period_to_seconds({"type": "hour", "value": 2}) == 7200

    def test_day_converts_to_seconds(self):
        assert period_to_seconds({"type": "day", "value": 1}) == 86400

    def test_empty_period_raises(self):
        with pytest.raises(BaseAppException, match="period.type"):
            period_to_seconds({})

    def test_none_period_raises(self):
        with pytest.raises(BaseAppException, match="period must be an object"):
            period_to_seconds(None)

    def test_missing_type_raises(self):
        with pytest.raises(BaseAppException, match="period.type"):
            period_to_seconds({"value": 5})

    def test_missing_value_raises(self):
        with pytest.raises(BaseAppException, match="period.value"):
            period_to_seconds({"type": "min"})

    def test_unknown_type_raises(self):
        with pytest.raises(BaseAppException, match="period.type"):
            period_to_seconds({"type": "week", "value": 1})

    def test_value_zero_raises(self):
        with pytest.raises(BaseAppException, match="period.value"):
            period_to_seconds({"type": "min", "value": 0})


class TestFormatPeriod:
    def test_min_format(self):
        assert format_period({"type": "min", "value": 5}) == "5m"

    def test_hour_format(self):
        assert format_period({"type": "hour", "value": 3}) == "3h"

    def test_day_format(self):
        assert format_period({"type": "day", "value": 7}) == "7d"

    def test_empty_raises(self):
        with pytest.raises(BaseAppException, match="policy period is empty"):
            format_period(None)

    def test_missing_fields_raises(self):
        with pytest.raises(BaseAppException, match="invalid period format"):
            format_period({"type": "min"})

    def test_unknown_type_raises(self):
        with pytest.raises(BaseAppException, match="invalid period type: month"):
            format_period({"type": "month", "value": 1})
