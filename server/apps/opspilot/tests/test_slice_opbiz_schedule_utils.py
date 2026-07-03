"""opspilot-biz 切片: utils/schedule_utils 纯逻辑真实测试。

ScheduleConfigValidator / CrontabGenerator / convert_legacy_config /
get_crontab_next_runs 均为纯函数（croniter 为确定性库），直接断言真实行为。
"""

import pydantic.root_model  # noqa

from datetime import datetime

import pytest

from apps.opspilot.utils.schedule_utils import (
    CrontabGenerator,
    ScheduleConfigValidator,
    convert_legacy_config,
    get_crontab_next_runs,
)


# ---------------------------------------------------------------------------
# ScheduleConfigValidator
# ---------------------------------------------------------------------------


class TestValidator:
    def test_empty_config_raises(self):
        with pytest.raises(ValueError, match="config is required"):
            ScheduleConfigValidator.validate({})

    def test_missing_frequency_raises(self):
        with pytest.raises(ValueError, match="frequency is required"):
            ScheduleConfigValidator.validate({"message": "x"})

    def test_invalid_frequency_raises(self):
        with pytest.raises(ValueError, match="Invalid frequency"):
            ScheduleConfigValidator.validate({"frequency": "yearly"})

    def test_daily_valid(self):
        # 不抛异常即通过
        ScheduleConfigValidator.validate({"frequency": "daily", "time": ["09:00", "18:30"]})

    def test_daily_missing_time(self):
        with pytest.raises(ValueError, match="time is required"):
            ScheduleConfigValidator.validate({"frequency": "daily"})

    def test_time_must_be_list(self):
        with pytest.raises(ValueError, match="time must be a list"):
            ScheduleConfigValidator.validate({"frequency": "daily", "time": "09:00"})

    def test_time_empty_list(self):
        with pytest.raises(ValueError, match="time is required"):
            ScheduleConfigValidator.validate({"frequency": "daily", "time": []})

    def test_time_bad_format(self):
        with pytest.raises(ValueError, match="Must be HH:MM"):
            ScheduleConfigValidator.validate({"frequency": "daily", "time": ["25:00"]})

    def test_time_non_string(self):
        with pytest.raises(ValueError, match="Must be a string"):
            ScheduleConfigValidator.validate({"frequency": "daily", "time": [900]})

    def test_weekly_valid(self):
        ScheduleConfigValidator.validate({"frequency": "weekly", "time": ["09:00"], "weekdays": [1, 3, 5]})

    def test_weekly_missing_weekdays(self):
        with pytest.raises(ValueError, match="weekdays is required"):
            ScheduleConfigValidator.validate({"frequency": "weekly", "time": ["09:00"]})

    def test_weekly_weekday_out_of_range(self):
        with pytest.raises(ValueError, match="Must be 0-6"):
            ScheduleConfigValidator.validate({"frequency": "weekly", "time": ["09:00"], "weekdays": [7]})

    def test_weekly_weekday_non_int(self):
        with pytest.raises(ValueError, match="Must be an integer"):
            ScheduleConfigValidator.validate({"frequency": "weekly", "time": ["09:00"], "weekdays": ["1"]})

    def test_monthly_valid(self):
        ScheduleConfigValidator.validate({"frequency": "monthly", "time": ["09:00"], "days": [1, 15, 31]})

    def test_monthly_missing_days(self):
        with pytest.raises(ValueError, match="days is required"):
            ScheduleConfigValidator.validate({"frequency": "monthly", "time": ["09:00"]})

    def test_monthly_day_out_of_range(self):
        with pytest.raises(ValueError, match="Must be 1-31"):
            ScheduleConfigValidator.validate({"frequency": "monthly", "time": ["09:00"], "days": [32]})

    def test_crontab_valid(self):
        ScheduleConfigValidator.validate({"frequency": "crontab", "crontab_expression": "30 9 * * 1-5"})

    def test_crontab_missing_expression(self):
        with pytest.raises(ValueError, match="crontab_expression is required"):
            ScheduleConfigValidator.validate({"frequency": "crontab"})

    def test_crontab_wrong_field_count(self):
        with pytest.raises(ValueError, match="exactly 5 fields"):
            ScheduleConfigValidator.validate({"frequency": "crontab", "crontab_expression": "30 9 * *"})

    def test_crontab_step_value_valid(self):
        ScheduleConfigValidator.validate({"frequency": "crontab", "crontab_expression": "*/5 * * * *"})

    def test_crontab_bad_step(self):
        with pytest.raises(ValueError, match="Invalid step value"):
            ScheduleConfigValidator.validate({"frequency": "crontab", "crontab_expression": "*/0 * * * *"})

    def test_crontab_list_values(self):
        ScheduleConfigValidator.validate({"frequency": "crontab", "crontab_expression": "0,15,30 * * * *"})

    def test_crontab_range_reversed(self):
        with pytest.raises(ValueError, match="start > end"):
            ScheduleConfigValidator.validate({"frequency": "crontab", "crontab_expression": "0 9-5 * * *"})

    def test_crontab_value_out_of_range(self):
        with pytest.raises(ValueError, match="Must be 0-59"):
            ScheduleConfigValidator.validate({"frequency": "crontab", "crontab_expression": "99 * * * *"})

    def test_crontab_non_digit_field(self):
        with pytest.raises(ValueError, match="Invalid value in minute"):
            ScheduleConfigValidator.validate({"frequency": "crontab", "crontab_expression": "abc * * * *"})


# ---------------------------------------------------------------------------
# CrontabGenerator
# ---------------------------------------------------------------------------


class TestGenerator:
    def test_daily_multi_time(self):
        out = CrontabGenerator.generate({"frequency": "daily", "time": ["09:05", "18:00"]})
        assert out == [
            ("0", {"minute": "5", "hour": "9", "day_of_week": "*", "day_of_month": "*", "month_of_year": "*"}),
            ("1", {"minute": "0", "hour": "18", "day_of_week": "*", "day_of_month": "*", "month_of_year": "*"}),
        ]

    def test_daily_midnight_zero_padding(self):
        # "00:00" 应转为 minute=0 hour=0（lstrip 后空串回退 "0"）
        out = CrontabGenerator.generate({"frequency": "daily", "time": ["00:00"]})
        assert out[0][1]["minute"] == "0"
        assert out[0][1]["hour"] == "0"

    def test_weekly_combines_weekdays_sorted(self):
        out = CrontabGenerator.generate({"frequency": "weekly", "time": ["09:00"], "weekdays": [5, 1, 3]})
        assert out[0][1]["day_of_week"] == "1,3,5"

    def test_monthly_combines_days_sorted(self):
        out = CrontabGenerator.generate({"frequency": "monthly", "time": ["09:00"], "days": [15, 1]})
        assert out[0][1]["day_of_month"] == "1,15"
        assert out[0][1]["day_of_week"] == "*"

    def test_crontab_passthrough(self):
        out = CrontabGenerator.generate({"frequency": "crontab", "crontab_expression": "30 9 * * 1-5"})
        assert out == [("0", {"minute": "30", "hour": "9", "day_of_month": "*", "month_of_year": "*", "day_of_week": "1-5"})]

    def test_unknown_frequency_raises(self):
        with pytest.raises(ValueError, match="Unknown frequency"):
            CrontabGenerator.generate({"frequency": "bogus"})


# ---------------------------------------------------------------------------
# convert_legacy_config
# ---------------------------------------------------------------------------


class TestConvertLegacy:
    def test_no_time_returned_as_is(self):
        cfg = {"frequency": "crontab"}
        assert convert_legacy_config(cfg) is cfg

    def test_list_time_returned_as_is(self):
        cfg = {"frequency": "daily", "time": ["09:00"]}
        assert convert_legacy_config(cfg) is cfg

    def test_string_time_converted_to_list(self):
        cfg = {"frequency": "daily", "time": "09:00", "message": "x"}
        out = convert_legacy_config(cfg)
        assert out["time"] == ["09:00"]
        assert out["message"] == "x"
        # 原 config 不被修改
        assert cfg["time"] == "09:00"

    def test_other_type_returned_as_is(self):
        cfg = {"frequency": "daily", "time": 123}
        assert convert_legacy_config(cfg) is cfg


# ---------------------------------------------------------------------------
# get_crontab_next_runs
# ---------------------------------------------------------------------------


class TestNextRuns:
    def test_returns_n_future_times(self):
        base = datetime(2026, 1, 1, 0, 0, 0)
        out = get_crontab_next_runs("0 0 * * *", count=3, base_time=base)
        assert out == ["2026-01-02 00:00:00", "2026-01-03 00:00:00", "2026-01-04 00:00:00"]

    def test_default_count_is_six(self):
        base = datetime(2026, 1, 1, 0, 0, 0)
        out = get_crontab_next_runs("0 0 * * *", base_time=base)
        assert len(out) == 6

    def test_invalid_expression_raises(self):
        with pytest.raises(ValueError, match="Invalid crontab expression"):
            get_crontab_next_runs("not a cron")

    def test_empty_expression_raises(self):
        with pytest.raises(ValueError, match="required and must be a string"):
            get_crontab_next_runs("")

    def test_non_string_raises(self):
        with pytest.raises(ValueError, match="required and must be a string"):
            get_crontab_next_runs(None)  # type: ignore
