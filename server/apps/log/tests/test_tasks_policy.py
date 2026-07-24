"""apps/log/tasks/policy.py 测试：scan_log_policy_task / compensate_log_notice_task。

LogPolicyScan 整体作为协作边界 mock（其内部逻辑已在 policy_scan 测试覆盖），
聚焦任务编排：启用判断、首次执行、单周期、补偿循环、last_run_time 落库、通知补偿筛选。
S3 边界 stub。
"""
from datetime import datetime, timedelta, timezone

import pytest
from django.utils import timezone as dj_timezone

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.log.constants.alert_policy import AlertConstants
from apps.log.models.policy import Alert, Event, Policy
from apps.log.services.alert_lifecycle_notify import LogAlertLifecycleNotifier
from apps.log.tasks.policy import compensate_log_notice_task, scan_log_policy_task
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
        scan.assert_called_once_with(
            mocker.ANY,
            scan_time=last_run_time + timedelta(seconds=period_seconds),
            window_start=int(last_run_time.timestamp()),
            window_end=int(last_run_time.timestamp()) + period_seconds,
        )
        scan.return_value.run.assert_called_once_with()
        policy.refresh_from_db()
        assert policy.last_run_time == last_run_time + timedelta(seconds=period_seconds)

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
        alert = Alert.objects.create(id="a-c2", policy=policy, source_id="s", level="warning", status="new", start_event_time=dj_timezone.now(), notice=False)
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
        alert = Alert.objects.create(id="a-c3", policy=policy, source_id="s", level="warning", status="new", start_event_time=dj_timezone.now(), notice=False)
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
        closed_at = dj_timezone.now() - timedelta(
            seconds=AlertConstants.NOTICE_COMPENSATE_MIN_AGE_SECONDS + 60
        )
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
        closed_at = dj_timezone.now() - timedelta(
            seconds=AlertConstants.NOTICE_COMPENSATE_MIN_AGE_SECONDS + 60
        )
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
