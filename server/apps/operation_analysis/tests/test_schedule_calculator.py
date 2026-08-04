from datetime import datetime, timezone as dt_timezone

import pytest

from apps.operation_analysis.services.schedule_calculator import (
    SCHEDULE_TYPE_DAILY,
    SCHEDULE_TYPE_MONTHLY,
    SCHEDULE_TYPE_WEEKLY,
    ScheduleSpec,
    catch_up_scheduled_time,
    latest_run_at_or_before,
    next_after,
    next_run,
    next_run_strictly_after_now,
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


class TestCatchUp:
    def test_daily_skips_three_missed_days(self):
        spec = ScheduleSpec(SCHEDULE_TYPE_DAILY, hour=9, minute=0)
        stored = _utc(2026, 8, 1, 1, 0)  # 08-01 09:00 Shanghai
        now = _utc(2026, 8, 4, 2, 0)  # 08-04 10:00 Shanghai
        catch_up = catch_up_scheduled_time(
            spec,
            "Asia/Shanghai",
            stored_next_run_at=stored,
            now=now,
        )
        assert catch_up == _utc(2026, 8, 4, 1, 0)
        latest = latest_run_at_or_before(spec, "Asia/Shanghai", now)
        assert latest.utc == catch_up
        assert latest.scheduled_local_time == "2026-08-04 09:00"
        advanced = next_run_strictly_after_now(
            spec,
            "Asia/Shanghai",
            after_scheduled_time_utc=catch_up,
            now=now,
        )
        assert advanced.utc == _utc(2026, 8, 5, 1, 0)
        assert advanced.utc > now

    def test_weekly_cross_week(self):
        # Monday 09:00；stored=Mon 08-03，now=Thu 08-13 → catch_up=Mon 08-10
        spec = ScheduleSpec(
            SCHEDULE_TYPE_WEEKLY, hour=9, minute=0, weekday=0
        )
        stored = _utc(2026, 8, 3, 1, 0)
        now = _utc(2026, 8, 13, 2, 0)
        catch_up = catch_up_scheduled_time(
            spec,
            "Asia/Shanghai",
            stored_next_run_at=stored,
            now=now,
        )
        assert catch_up == _utc(2026, 8, 10, 1, 0)
        advanced = next_run_strictly_after_now(
            spec,
            "Asia/Shanghai",
            after_scheduled_time_utc=catch_up,
            now=now,
        )
        assert advanced.utc == _utc(2026, 8, 17, 1, 0)

    def test_monthly_day_31_across_short_months(self):
        spec = ScheduleSpec(
            SCHEDULE_TYPE_MONTHLY, hour=9, minute=0, day_of_month=31
        )
        # stored=Jan 31；now=Apr 15 → catch_up=Mar 31（跳过 Feb 28）
        stored = _utc(2026, 1, 31, 1, 0)
        now = _utc(2026, 4, 15, 2, 0)
        catch_up = catch_up_scheduled_time(
            spec,
            "Asia/Shanghai",
            stored_next_run_at=stored,
            now=now,
        )
        assert catch_up == _utc(2026, 3, 31, 1, 0)
        latest = latest_run_at_or_before(spec, "Asia/Shanghai", now)
        assert latest.scheduled_local_time == "2026-03-31 09:00"

    def test_dst_spring_forward_latest(self):
        from zoneinfo import ZoneInfo

        spec = ScheduleSpec(SCHEDULE_TYPE_DAILY, hour=2, minute=30)
        # 停机跨过春天跳时日；恢复于 03-09 10:00 EDT
        stored = _utc(2026, 3, 7, 7, 30)  # 03-07 02:30 EST
        now = _utc(2026, 3, 9, 14, 0)  # 03-09 10:00 EDT
        catch_up = catch_up_scheduled_time(
            spec,
            "America/New_York",
            stored_next_run_at=stored,
            now=now,
        )
        local = catch_up.astimezone(ZoneInfo("America/New_York"))
        assert local.date().isoformat() == "2026-03-09"
        assert (local.hour, local.minute) == (2, 30)

    def test_stored_in_future_returns_stored(self):
        spec = ScheduleSpec(SCHEDULE_TYPE_DAILY, hour=9, minute=0)
        stored = _utc(2026, 8, 5, 1, 0)
        now = _utc(2026, 8, 4, 2, 0)
        assert (
            catch_up_scheduled_time(
                spec,
                "Asia/Shanghai",
                stored_next_run_at=stored,
                now=now,
            )
            == stored
        )
