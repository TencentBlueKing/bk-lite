"""apps/log/tasks/policy.py 测试：scan_log_policy_task / compensate_log_notice_task。

LogPolicyScan 整体作为协作边界 mock（其内部逻辑已在 policy_scan 测试覆盖），
聚焦任务编排：启用判断、首次执行、单周期、补偿循环、last_run_time 落库、通知补偿筛选。
S3 边界 stub。
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

import pytest
from django.db import close_old_connections
from django.utils import timezone as dj_timezone

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.log.constants.alert_policy import AlertConstants
from apps.log.models.policy import Alert, Event, Policy
from apps.log.services.alert_lifecycle_notify import LogAlertLifecycleNotifier
from apps.log.tasks.policy import _advance_policy_cursor, _run_policy_window, compensate_log_notice_task, scan_log_policy_task
from apps.system_mgmt.models.channel import Channel

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _stub_s3(mocker):
    mocker.patch("apps.core.fields.s3_json_field.S3JSONField._upload_to_s3", return_value="p.json.gz")
    mocker.patch("apps.core.fields.s3_json_field.S3JSONField._load_from_s3", return_value=[])


def _make_policy(**overrides):
    data = dict(
        name=overrides.pop("name", "task-p"),
        alert_type="keyword",
        alert_name="a",
        alert_level="warning",
        alert_condition={"query": "error"},
        schedule={"type": "min", "value": 5},
        period={"type": "min", "value": 5},
        notice=False,
        enable=True,
        notice_users=[],
    )
    data.update(overrides)
    return Policy.objects.create(**data)


class TestScanLogPolicyTask:
    @pytest.mark.parametrize(
        ("delay_periods", "expected_windows", "expected_cursor_periods"),
        [
            (0.5, [(-0.5, 0.5)], 0.5),
            (1, [(0, 1)], 1),
            (1.5, [(0, 1), (0.5, 1.5)], 1.5),
            (2, [(0, 1), (1, 2)], 2),
        ],
    )
    def test_scan_window_boundaries(self, mocker, delay_periods, expected_windows, expected_cursor_periods):
        period_seconds = 5 * 60
        cursor = datetime(2026, 7, 24, tzinfo=timezone.utc)
        safe_time = cursor + timedelta(seconds=period_seconds * delay_periods)
        policy = _make_policy(last_run_time=cursor)
        mocker.patch("apps.log.tasks.policy.datetime").now.return_value = safe_time + timedelta(seconds=AlertConstants.INGEST_DELAY_SECONDS)
        scan = mocker.patch("apps.log.tasks.policy.LogPolicyScan")

        result = scan_log_policy_task(policy.id)

        assert result["success"] is True
        assert [(call.kwargs["window_start"], call.kwargs["window_end"]) for call in scan.call_args_list] == [
            (
                int(cursor.timestamp() + start_period * period_seconds),
                int(cursor.timestamp() + end_period * period_seconds),
            )
            for start_period, end_period in expected_windows
        ]
        policy.refresh_from_db()
        assert policy.last_run_time == cursor + timedelta(seconds=period_seconds * expected_cursor_periods)

    def test_backfill_overlap_does_not_break_cursor_continuity(self, mocker):
        period_seconds = 5 * 60
        cursor = datetime(2026, 7, 24, tzinfo=timezone.utc)
        policy = _make_policy(last_run_time=cursor)
        safe_time = cursor + timedelta(seconds=period_seconds * 2)
        mocker.patch("apps.log.tasks.policy.datetime").now.return_value = safe_time + timedelta(seconds=AlertConstants.INGEST_DELAY_SECONDS)
        mocker.patch.object(AlertConstants, "WINDOW_OVERLAP_SECONDS", 30)
        scan = mocker.patch("apps.log.tasks.policy.LogPolicyScan")

        result = scan_log_policy_task(policy.id)

        assert result["success"] is True
        assert [(call.kwargs["window_start"], call.kwargs["window_end"]) for call in scan.call_args_list] == [
            (int(cursor.timestamp()) - 30, int(cursor.timestamp()) + period_seconds),
            (int(cursor.timestamp()) + period_seconds - 30, int(cursor.timestamp()) + period_seconds * 2),
        ]
        policy.refresh_from_db()
        assert policy.last_run_time == cursor + timedelta(seconds=period_seconds * 2)

    def test_backfill_tail_respects_24_hour_progress_limit(self, mocker):
        period_seconds = 20 * 3600
        cursor = datetime(2026, 7, 24, tzinfo=timezone.utc)
        safe_time = cursor + timedelta(hours=39)
        policy = _make_policy(
            period={"type": "hour", "value": 20},
            last_run_time=cursor,
        )
        mocker.patch("apps.log.tasks.policy.datetime").now.return_value = safe_time + timedelta(
            seconds=AlertConstants.INGEST_DELAY_SECONDS
        )
        scan = mocker.patch("apps.log.tasks.policy.LogPolicyScan")

        result = scan_log_policy_task(policy.id)

        assert result["success"] is True
        assert [(call.kwargs["window_start"], call.kwargs["window_end"]) for call in scan.call_args_list] == [
            (int(cursor.timestamp()), int(cursor.timestamp()) + period_seconds),
            (
                int(cursor.timestamp()) + 4 * 3600,
                int(cursor.timestamp()) + AlertConstants.MAX_BACKFILL_SECONDS,
            ),
        ]
        policy.refresh_from_db()
        assert policy.last_run_time == cursor + timedelta(seconds=AlertConstants.MAX_BACKFILL_SECONDS)

    def test_backfill_tail_does_not_exceed_window_count_limit(self, mocker):
        period_seconds = 3600
        cursor = datetime(2026, 7, 24, tzinfo=timezone.utc)
        safe_time = cursor + timedelta(hours=AlertConstants.MAX_BACKFILL_COUNT + 0.5)
        policy = _make_policy(
            period={"type": "hour", "value": 1},
            last_run_time=cursor,
        )
        mocker.patch("apps.log.tasks.policy.datetime").now.return_value = safe_time + timedelta(
            seconds=AlertConstants.INGEST_DELAY_SECONDS
        )
        scan = mocker.patch("apps.log.tasks.policy.LogPolicyScan")

        result = scan_log_policy_task(policy.id)

        assert result["success"] is True
        assert scan.call_count == AlertConstants.MAX_BACKFILL_COUNT
        assert scan.call_args_list[-1].kwargs["window_end"] == int(
            cursor.timestamp() + AlertConstants.MAX_BACKFILL_COUNT * period_seconds
        )
        policy.refresh_from_db()
        assert policy.last_run_time == cursor + timedelta(
            seconds=AlertConstants.MAX_BACKFILL_COUNT * period_seconds
        )

    def test_missing_policy_raises(self):
        with pytest.raises(BaseAppException, match="未找到"):
            scan_log_policy_task(999999)

    def test_disabled_policy_skipped(self):
        policy = _make_policy(enable=False)
        result = scan_log_policy_task(policy.id)
        assert result["success"] is True
        assert result["message"] == "策略未启用"

    def test_invalid_period_returns_observable_failure(self, mocker):
        policy = _make_policy(period={"type": "min", "value": 0})
        scan = mocker.patch("apps.log.tasks.policy.LogPolicyScan")

        result = scan_log_policy_task(policy.id)

        assert result["success"] is False
        assert "策略周期配置无效" in result["message"]
        scan.assert_not_called()

    def test_first_run_sets_last_run_time_and_runs(self, mocker):
        policy = _make_policy(last_run_time=None)
        run = mocker.patch("apps.log.tasks.policy.LogPolicyScan")
        result = scan_log_policy_task(policy.id)
        assert result["success"] is True
        run.assert_called_once()
        policy.refresh_from_db()
        assert policy.last_run_time is not None

    def test_first_run_failure_keeps_bounded_retry_window_without_advancing_cursor(self, mocker):
        period_seconds = 5 * 60
        first_safe_time = datetime(2026, 7, 24, tzinfo=timezone.utc)
        retry_safe_time = first_safe_time + timedelta(seconds=period_seconds // 4)
        policy = _make_policy(last_run_time=None)
        Policy.objects.filter(id=policy.id).update(created_at=first_safe_time - timedelta(days=30))
        mocker.patch("apps.log.tasks.policy.datetime").now.side_effect = [
            first_safe_time + timedelta(seconds=AlertConstants.INGEST_DELAY_SECONDS),
            retry_safe_time + timedelta(seconds=AlertConstants.INGEST_DELAY_SECONDS),
        ]
        scan = mocker.patch("apps.log.tasks.policy.LogPolicyScan")
        scan.return_value.run.side_effect = [RuntimeError("worker lost"), None]

        with pytest.raises(RuntimeError, match="worker lost"):
            scan_log_policy_task(policy.id)
        policy.refresh_from_db()
        assert policy.last_run_time is None

        result = scan_log_policy_task(policy.id)

        assert result["success"] is True
        assert [(call.kwargs["window_start"], call.kwargs["window_end"]) for call in scan.call_args_list] == [
            (
                int(first_safe_time.timestamp()) - period_seconds,
                int(first_safe_time.timestamp()),
            ),
            (
                int(retry_safe_time.timestamp()) - period_seconds,
                int(retry_safe_time.timestamp()),
            ),
        ]
        assert scan.call_args_list[0].kwargs["execution_key"] == scan.call_args_list[1].kwargs["execution_key"]
        assert scan.call_args_list[0].kwargs["cursor_time"] is None
        assert scan.call_args_list[1].kwargs["cursor_time"] is None
        policy.refresh_from_db()
        assert policy.last_run_time == retry_safe_time

    def test_single_window_run(self, mocker):
        # last_run_time 接近 now → backfill_count == 0 单周期分支
        recent = datetime.now(timezone.utc) - timedelta(seconds=120)
        policy = _make_policy(last_run_time=recent)
        run = mocker.patch("apps.log.tasks.policy.LogPolicyScan")
        result = scan_log_policy_task(policy.id)
        assert result["success"] is True
        # 单周期：构造一次并 run 一次
        run.assert_called_once()
        _, kwargs = run.call_args
        assert "window_start" in kwargs and "window_end" in kwargs

    def test_one_and_half_period_delay_keeps_window_continuous(self, mocker):
        period_seconds = 5 * 60
        last_run_time = datetime(2026, 7, 24, tzinfo=timezone.utc)
        safe_time = last_run_time + timedelta(seconds=period_seconds * 1.5)
        current_time = safe_time + timedelta(seconds=AlertConstants.INGEST_DELAY_SECONDS)
        policy = _make_policy(last_run_time=last_run_time)
        mocker.patch("apps.log.tasks.policy.datetime").now.return_value = current_time
        scan = mocker.patch("apps.log.tasks.policy.LogPolicyScan")

        result = scan_log_policy_task(policy.id)

        assert result["success"] is True
        assert [(call.kwargs["window_start"], call.kwargs["window_end"]) for call in scan.call_args_list] == [
            (int(last_run_time.timestamp()), int(last_run_time.timestamp()) + period_seconds),
            (
                int(safe_time.timestamp()) - period_seconds,
                int(safe_time.timestamp()),
            ),
        ]
        assert scan.return_value.run.call_count == 2
        policy.refresh_from_db()
        assert policy.last_run_time == safe_time

    def test_failed_partial_window_reuses_cursor_identity_when_safe_time_moves(self, mocker):
        period_seconds = 5 * 60
        cursor = datetime(2026, 7, 24, tzinfo=timezone.utc)
        safe_times = [
            cursor + timedelta(seconds=period_seconds * 0.5),
            cursor + timedelta(seconds=period_seconds * 0.75),
        ]
        policy = _make_policy(last_run_time=cursor)
        mocker.patch("apps.log.tasks.policy.datetime").now.side_effect = [
            safe_time + timedelta(seconds=AlertConstants.INGEST_DELAY_SECONDS) for safe_time in safe_times
        ]
        scan = mocker.patch("apps.log.tasks.policy.LogPolicyScan")
        scan.return_value.run.side_effect = [RuntimeError("worker lost"), None]

        with pytest.raises(RuntimeError, match="worker lost"):
            scan_log_policy_task(policy.id)
        policy.refresh_from_db()
        assert policy.last_run_time == cursor

        result = scan_log_policy_task(policy.id)

        assert result["success"] is True
        assert scan.call_args_list[0].kwargs["execution_key"] == scan.call_args_list[1].kwargs["execution_key"]
        assert [(call.kwargs["window_start"], call.kwargs["window_end"]) for call in scan.call_args_list] == [
            (
                int(safe_times[0].timestamp()) - period_seconds,
                int(safe_times[0].timestamp()),
            ),
            (
                int(safe_times[1].timestamp()) - period_seconds,
                int(safe_times[1].timestamp()),
            ),
        ]
        policy.refresh_from_db()
        assert policy.last_run_time == cursor + timedelta(seconds=period_seconds * 0.75)

    def test_backfill_resumes_from_second_window_after_mid_run_failure(self, mocker):
        period_seconds = 5 * 60
        cursor = datetime(2026, 7, 24, tzinfo=timezone.utc)
        safe_times = [
            cursor + timedelta(seconds=period_seconds * 2),
            cursor + timedelta(seconds=period_seconds * 2.5),
        ]
        policy = _make_policy(last_run_time=cursor)
        mocker.patch("apps.log.tasks.policy.datetime").now.side_effect = [
            safe_time + timedelta(seconds=AlertConstants.INGEST_DELAY_SECONDS) for safe_time in safe_times
        ]
        scan = mocker.patch("apps.log.tasks.policy.LogPolicyScan")
        scan.return_value.run.side_effect = [None, RuntimeError("second window failed"), None, None]

        with pytest.raises(RuntimeError, match="second window failed"):
            scan_log_policy_task(policy.id)
        policy.refresh_from_db()
        assert policy.last_run_time == cursor + timedelta(seconds=period_seconds)

        result = scan_log_policy_task(policy.id)

        assert result["success"] is True
        assert [(call.kwargs["window_start"], call.kwargs["window_end"]) for call in scan.call_args_list] == [
            (int(cursor.timestamp()), int(cursor.timestamp()) + period_seconds),
            (int(cursor.timestamp()) + period_seconds, int(cursor.timestamp()) + period_seconds * 2),
            (int(cursor.timestamp()) + period_seconds, int(cursor.timestamp()) + period_seconds * 2),
            (
                int(safe_times[1].timestamp()) - period_seconds,
                int(safe_times[1].timestamp()),
            ),
        ]
        assert scan.call_args_list[1].kwargs["execution_key"] == scan.call_args_list[2].kwargs["execution_key"]
        policy.refresh_from_db()
        assert policy.last_run_time == safe_times[1]

    def test_cursor_compare_and_swap_converges_to_latest_completed_window(self):
        cursor = datetime(2026, 7, 24, tzinfo=timezone.utc)
        policy = _make_policy(last_run_time=cursor)
        earlier_scan_time = cursor + timedelta(minutes=3)
        later_scan_time = cursor + timedelta(minutes=4)

        _advance_policy_cursor(policy.id, cursor, earlier_scan_time)
        _advance_policy_cursor(policy.id, cursor, later_scan_time)
        _advance_policy_cursor(policy.id, cursor, earlier_scan_time)

        policy.refresh_from_db()
        assert policy.last_run_time == later_scan_time

    def test_local_backfill_sequence_does_not_jump_to_concurrent_db_cursor(self, mocker):
        period_seconds = 5 * 60
        cursor = datetime(2026, 7, 24, tzinfo=timezone.utc)
        safe_time = cursor + timedelta(seconds=period_seconds * 2)
        remote_cursor = cursor + timedelta(seconds=period_seconds * 4)
        policy = _make_policy(last_run_time=cursor)
        mocker.patch("apps.log.tasks.policy.datetime").now.return_value = safe_time + timedelta(
            seconds=AlertConstants.INGEST_DELAY_SECONDS
        )
        scan = mocker.patch("apps.log.tasks.policy.LogPolicyScan")
        run_count = 0

        def advance_remote_cursor():
            nonlocal run_count
            run_count += 1
            if run_count == 1:
                Policy.objects.filter(id=policy.id).update(last_run_time=remote_cursor)

        scan.return_value.run.side_effect = advance_remote_cursor

        result = scan_log_policy_task(policy.id)

        assert result["success"] is True
        assert [call.kwargs["scan_time"] for call in scan.call_args_list] == [
            cursor + timedelta(seconds=period_seconds),
            safe_time,
        ]
        policy.refresh_from_db()
        assert policy.last_run_time == remote_cursor

    @pytest.mark.django_db(transaction=True)
    def test_concurrent_disjoint_windows_keep_side_effects_and_converge_cursor(self, mocker):
        cursor = datetime(2026, 7, 24, tzinfo=timezone.utc)
        policy = _make_policy(last_run_time=cursor)
        scan_times = [
            cursor + timedelta(minutes=3),
            cursor + timedelta(minutes=4),
        ]
        barrier = Barrier(2)
        side_effects = []

        class DisjointSourceScan:
            def __init__(self, policy_obj, *, scan_time, **kwargs):
                self.scan_time = scan_time

            def run(self):
                side_effects.append(f"source-{self.scan_time.minute}")
                barrier.wait(timeout=5)

        mocker.patch("apps.log.tasks.policy.LogPolicyScan", DisjointSourceScan)

        def run_window(scan_time):
            close_old_connections()
            try:
                _run_policy_window(
                    Policy.objects.get(id=policy.id),
                    cursor_time=cursor,
                    scan_time=scan_time,
                    period_seconds=5 * 60,
                    overlap_seconds=0,
                )
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(run_window, scan_time) for scan_time in scan_times]
            [future.result() for future in futures]

        policy.refresh_from_db()
        assert sorted(side_effects) == ["source-3", "source-4"]
        assert policy.last_run_time == max(scan_times)

    def test_backfill_multiple_windows(self, mocker):
        # last_run_time 远早于 now → 多周期补偿
        old = datetime.now(timezone.utc) - timedelta(seconds=3000)  # 50 分钟前, period=5min
        policy = _make_policy(last_run_time=old)
        run = mocker.patch("apps.log.tasks.policy.LogPolicyScan")
        result = scan_log_policy_task(policy.id)
        assert result["success"] is True
        # 多次补偿扫描
        assert run.call_count >= 2
        policy.refresh_from_db()
        assert policy.last_run_time > old

    def test_run_error_propagates(self, mocker):
        recent = datetime.now(timezone.utc) - timedelta(seconds=120)
        policy = _make_policy(last_run_time=recent)
        instance = mocker.MagicMock()
        instance.run.side_effect = RuntimeError("scan fail")
        mocker.patch("apps.log.tasks.policy.LogPolicyScan", return_value=instance)
        with pytest.raises(RuntimeError):
            scan_log_policy_task(policy.id)


class TestCompensateLogNoticeTask:
    @staticmethod
    def _make_channel(name="告警中心", channel_type="nats", method_name="receive_alert_events"):
        config = {"method_name": method_name} if method_name else {}
        return Channel.objects.create(
            name=name,
            channel_type=channel_type,
            config=config,
            description="",
        )

    def _make_event(self, policy, alert, **overrides):
        now = datetime.now(timezone.utc)
        data = dict(
            id=overrides.pop("id", "ev-comp"),
            policy=policy,
            source_id="s",
            alert=alert,
            event_time=now - timedelta(minutes=5),
            level="warning",
            content="c",
            notice_result=[],
            notified=False,
            notice_retry_count=0,
        )
        data.update(overrides)
        ev = Event.objects.create(**data)
        # created_at 必须早于 settle_before(now - MIN_AGE)，回填到很早
        Event.objects.filter(id=ev.id).update(created_at=now - timedelta(seconds=AlertConstants.NOTICE_COMPENSATE_MIN_AGE_SECONDS + 60))
        ev.refresh_from_db()
        return ev

    def test_no_pending_events(self):
        result = compensate_log_notice_task()
        assert result["success"] is True
        assert result["scanned"] == 0
        assert result["compensated"] == 0

    def test_no_notice_users_marks_notified(self, mocker):
        policy = _make_policy(notice=True, enable=True, notice_users=[])
        alert = Alert.objects.create(id="a-c1", policy=policy, source_id="s", level="warning", status="new", start_event_time=dj_timezone.now())
        ev = self._make_event(policy, alert, id="ev-nousers")
        result = compensate_log_notice_task()
        ev.refresh_from_db()
        assert ev.notified is True
        assert result["compensated"] == 0

    def test_alert_center_without_notice_users_is_retried(self, mocker):
        channel = self._make_channel()
        policy = _make_policy(
            notice=True,
            enable=True,
            notice_users=[],
            notice_type="nats",
            notice_type_id=channel.id,
        )
        alert = Alert.objects.create(
            id="a-c-nats",
            policy=policy,
            source_id="s",
            level="warning",
            status="new",
            start_event_time=dj_timezone.now(),
        )
        ev = self._make_event(policy, alert, id="ev-nats-nousers")
        send_notice = mocker.patch(
            "apps.log.tasks.services.policy_scan.LogPolicyScan.send_notice",
            return_value=(True, {"result": True}),
        )

        result = compensate_log_notice_task()

        ev.refresh_from_db()
        assert ev.notified is True
        assert result["compensated"] == 1
        send_notice.assert_called_once_with(ev, max_attempts=1)

    def test_successful_resend_marks_alert(self, mocker):
        policy = _make_policy(notice=True, enable=True, notice_users=["u1"])
        alert = Alert.objects.create(
            id="a-c2", policy=policy, source_id="s", level="warning", status="new", start_event_time=dj_timezone.now(), notice=False
        )
        ev = self._make_event(policy, alert, id="ev-resend")
        mocker.patch(
            "apps.log.tasks.services.policy_scan.LogPolicyScan.send_notice",
            return_value=(True, {"result": True}),
        )
        result = compensate_log_notice_task()
        ev.refresh_from_db()
        alert.refresh_from_db()
        assert ev.notified is True
        assert ev.notice_retry_count == 1
        assert alert.notice is True
        assert result["compensated"] == 1

    def test_failed_resend_increments_retry(self, mocker):
        policy = _make_policy(notice=True, enable=True, notice_users=["u1"])
        alert = Alert.objects.create(
            id="a-c3", policy=policy, source_id="s", level="warning", status="new", start_event_time=dj_timezone.now(), notice=False
        )
        ev = self._make_event(policy, alert, id="ev-fail")
        mocker.patch(
            "apps.log.tasks.services.policy_scan.LogPolicyScan.send_notice",
            return_value=(False, {"result": False, "message": "down"}),
        )
        result = compensate_log_notice_task()
        ev.refresh_from_db()
        assert ev.notified is False
        assert ev.notice_retry_count == 1
        assert result["compensated"] == 0

    def test_late_created_success_does_not_complete_closed_alert(self, mocker):
        policy = _make_policy(notice=True, enable=True, notice_users=["u1"])
        alert = Alert.objects.create(
            id="a-c-closed-race",
            policy=policy,
            source_id="s",
            level="warning",
            status="closed",
            start_event_time=dj_timezone.now() - timedelta(minutes=10),
            end_event_time=dj_timezone.now() - timedelta(minutes=5),
            notice=False,
        )
        self._make_event(policy, alert, id="ev-closed-race")
        mocker.patch(
            "apps.log.tasks.services.policy_scan.LogPolicyScan.send_notice",
            return_value=(True, {"result": True}),
        )

        compensate_log_notice_task()

        alert.refresh_from_db()
        assert alert.notice is False

    def test_closed_alert_success_is_compensated_when_policy_disabled(self, mocker):
        channel = self._make_channel()
        policy = _make_policy(
            notice=True,
            enable=False,
            notice_type="nats",
            notice_type_id=channel.id,
        )
        closed_at = dj_timezone.now() - timedelta(seconds=AlertConstants.NOTICE_COMPENSATE_MIN_AGE_SECONDS + 60)
        alert = Alert.objects.create(
            id="a-closed-compensate",
            policy=policy,
            source_id="s",
            level="warning",
            status="closed",
            start_event_time=closed_at - timedelta(minutes=5),
            end_event_time=closed_at,
            notice=False,
        )
        notify_closed = mocker.patch.object(
            LogAlertLifecycleNotifier,
            "notify_closed",
            return_value=(True, {"result": True}),
        )

        result = compensate_log_notice_task()

        alert.refresh_from_db()
        assert alert.notice is True
        assert result["scanned"] == 1
        assert result["compensated"] == 1
        notify_closed.assert_called_once_with(alert, max_attempts=1)

    def test_closed_alert_failure_stays_pending(self, mocker):
        channel = self._make_channel()
        policy = _make_policy(
            notice=True,
            notice_type="nats",
            notice_type_id=channel.id,
        )
        closed_at = dj_timezone.now() - timedelta(seconds=AlertConstants.NOTICE_COMPENSATE_MIN_AGE_SECONDS + 60)
        alert = Alert.objects.create(
            id="a-closed-fail",
            policy=policy,
            source_id="s",
            level="warning",
            status="closed",
            start_event_time=closed_at - timedelta(minutes=5),
            end_event_time=closed_at,
            notice=False,
        )
        notify_closed = mocker.patch.object(
            LogAlertLifecycleNotifier,
            "notify_closed",
            return_value=(False, {"result": False, "message": "down"}),
        )

        result = compensate_log_notice_task()

        alert.refresh_from_db()
        assert alert.notice is False
        assert result["scanned"] == 1
        assert result["compensated"] == 0
        notify_closed.assert_called_once_with(alert, max_attempts=1)

    def test_closed_compensation_filters_ineligible_alerts(self, mocker):
        alert_center = self._make_channel()
        email = self._make_channel(name="邮件", channel_type="email", method_name=None)
        now = dj_timezone.now()
        eligible_age = now - timedelta(seconds=AlertConstants.NOTICE_COMPENSATE_MIN_AGE_SECONDS + 60)
        outside_window = now - timedelta(seconds=AlertConstants.NOTICE_COMPENSATE_WINDOW_SECONDS + 60)

        cases = [
            ("recent", alert_center, True, now),
            ("outside", alert_center, True, outside_window),
            ("ordinary", email, True, eligible_age),
            ("disabled-notice", alert_center, False, eligible_age),
        ]
        for name, channel, notice, closed_at in cases:
            policy = _make_policy(
                name=f"policy-{name}",
                notice=notice,
                notice_type=channel.channel_type,
                notice_type_id=channel.id,
            )
            Alert.objects.create(
                id=f"alert-{name}",
                policy=policy,
                source_id="s",
                level="warning",
                status="closed",
                start_event_time=closed_at - timedelta(minutes=5),
                end_event_time=closed_at,
                notice=False,
            )
        notify_closed = mocker.patch.object(LogAlertLifecycleNotifier, "notify_closed")

        result = compensate_log_notice_task()

        assert result["scanned"] == 0
        assert result["compensated"] == 0
        notify_closed.assert_not_called()
