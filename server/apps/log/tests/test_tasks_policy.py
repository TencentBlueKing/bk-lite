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
from apps.log.tasks.policy import compensate_log_notice_task, scan_log_policy_task

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
        # last_run_time 接近 now → backfill_count <= 1 单周期分支
        recent = datetime.now(timezone.utc) - timedelta(seconds=120)
        policy = _make_policy(last_run_time=recent)
        run = mocker.patch("apps.log.tasks.policy.LogPolicyScan")
        result = scan_log_policy_task(policy.id)
        assert result["success"] is True
        # 单周期：构造一次并 run 一次
        run.assert_called_once()
        _, kwargs = run.call_args
        assert "window_start" in kwargs and "window_end" in kwargs

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
