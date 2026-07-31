from datetime import datetime, timezone as dt_timezone

import pytest

from apps.operation_analysis.services.schedule_calculator import (
    SCHEDULE_TYPE_DAILY,
    SCHEDULE_TYPE_MONTHLY,
    SCHEDULE_TYPE_WEEKLY,
    ScheduleSpec,
    next_after,
    next_run,
    validate_iana_timezone,
)


def _utc(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=dt_timezone.utc)


class TestValidateTimezone:
    def test_accepts_iana(self):
        assert validate_iana_timezone("Asia/Shanghai") == "Asia/Shanghai"

    def test_rejects_blank(self):
        with pytest.raises(ValueError):
            validate_iana_timezone("")

    def test_rejects_invalid(self):
        with pytest.raises(ValueError):
            validate_iana_timezone("Not/AZone")


class TestDaily:
    def test_same_day_later(self):
        spec = ScheduleSpec(SCHEDULE_TYPE_DAILY, hour=9, minute=0)
        # 2026-08-01 00:00 UTC = 08:00 Shanghai → 当日 09:00 仍在未来
        result = next_run(
            spec, "Asia/Shanghai", after=_utc(2026, 8, 1, 0, 0)
        )
        assert result.utc == _utc(2026, 8, 1, 1, 0)
        assert result.scheduled_local_time == "2026-08-01 09:00"
        assert result.timezone == "Asia/Shanghai"

    def test_after_todays_slot_goes_tomorrow(self):
        spec = ScheduleSpec(SCHEDULE_TYPE_DAILY, hour=9, minute=0)
        # 2026-08-01 02:00 UTC = 10:00 Shanghai → 明日
        result = next_run(
            spec, "Asia/Shanghai", after=_utc(2026, 8, 1, 2, 0)
        )
        assert result.utc == _utc(2026, 8, 2, 1, 0)
        assert result.scheduled_local_time == "2026-08-02 09:00"

    def test_strictly_after_exact_slot(self):
        spec = ScheduleSpec(SCHEDULE_TYPE_DAILY, hour=9, minute=0)
        result = next_after(
            spec, "Asia/Shanghai", scheduled_time_utc=_utc(2026, 8, 1, 1, 0)
        )
        assert result.utc == _utc(2026, 8, 2, 1, 0)


class TestWeekly:
    def test_next_monday(self):
        # 2026-07-30 是周四；下一周一 08-03 09:00 Shanghai = 01:00 UTC
        spec = ScheduleSpec(
            SCHEDULE_TYPE_WEEKLY, hour=9, minute=0, weekday=0
        )
        result = next_run(
            spec, "Asia/Shanghai", after=_utc(2026, 7, 30, 0, 0)
        )
        assert result.scheduled_local_time == "2026-08-03 09:00"
        assert result.utc == _utc(2026, 8, 3, 1, 0)


class TestMonthly:
    def test_normal_day(self):
        spec = ScheduleSpec(
            SCHEDULE_TYPE_MONTHLY, hour=9, minute=0, day_of_month=15
        )
        result = next_run(
            spec, "Asia/Shanghai", after=_utc(2026, 7, 30, 0, 0)
        )
        assert result.scheduled_local_time == "2026-08-15 09:00"

    def test_day_31_clamps_in_short_month(self):
        spec = ScheduleSpec(
            SCHEDULE_TYPE_MONTHLY, hour=9, minute=0, day_of_month=31
        )
        # after 2026-01-31 10:00 Shanghai → 下一期是 2 月最后一天
        result = next_run(
            spec, "Asia/Shanghai", after=_utc(2026, 1, 31, 2, 0)
        )
        assert result.scheduled_local_time == "2026-02-28 09:00"

    def test_february_29_in_leap_year(self):
        spec = ScheduleSpec(
            SCHEDULE_TYPE_MONTHLY, hour=9, minute=0, day_of_month=31
        )
        result = next_run(
            spec, "Asia/Shanghai", after=_utc(2024, 1, 31, 2, 0)
        )
        assert result.scheduled_local_time == "2024-02-29 09:00"


class TestDstAmericaNewYork:
    def test_spring_forward_nonexistent_uses_first_valid(self):
        # 2026-03-08 美国春天跳时：02:00–02:59 不存在 → 取当日 03:00 EDT
        from zoneinfo import ZoneInfo

        spec = ScheduleSpec(SCHEDULE_TYPE_DAILY, hour=2, minute=30)
        result = next_run(
            spec,
            "America/New_York",
            after=_utc(2026, 3, 8, 5, 0),  # 00:00 EST
        )
        local = result.utc.astimezone(ZoneInfo("America/New_York"))
        assert local.date().isoformat() == "2026-03-08"
        assert (local.hour, local.minute) == (3, 0)
        assert result.scheduled_local_time == "2026-03-08 03:00"
        assert result.utc == _utc(2026, 3, 8, 7, 0)

    def test_fall_back_uses_first_occurrence(self):
        # 2026-11-01 秋天回拨，01:30 出现两次；取第一次（EDT, UTC-4）
        spec = ScheduleSpec(SCHEDULE_TYPE_DAILY, hour=1, minute=30)
        result = next_run(
            spec,
            "America/New_York",
            after=_utc(2026, 11, 1, 0, 0),
        )
        assert result.utc == _utc(2026, 11, 1, 5, 30)
        assert result.scheduled_local_time == "2026-11-01 01:30"


class TestSpecValidation:
    def test_weekly_requires_weekday(self):
        with pytest.raises(ValueError):
            next_run(
                ScheduleSpec(SCHEDULE_TYPE_WEEKLY, hour=9, minute=0),
                "Asia/Shanghai",
                after=_utc(2026, 8, 1, 0, 0),
            )

    def test_rejects_cron_like_type(self):
        with pytest.raises(ValueError):
            next_run(
                ScheduleSpec("cron", hour=9, minute=0),
                "Asia/Shanghai",
                after=_utc(2026, 8, 1, 0, 0),
            )
