"""monitor 任务 + template_access_guide + infra 服务规格测试。"""

from datetime import datetime, timedelta, timezone

import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.constants.alert_policy import AlertConstants
from apps.monitor.models import MonitorAlert
from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.models.monitor_policy import MonitorPolicy
from apps.monitor.services.infra import InfraService
from apps.monitor.services.template_access_guide import TemplateAccessGuideService
from apps.monitor.tasks.monitor_policy import retry_alert_center_lifecycle_notify_task, scan_policy_task

pytestmark = pytest.mark.django_db


def _make_policy(**kwargs):
    obj = MonitorObject.objects.create(name=kwargs.pop("obj_name", "TaskObj"), level="base")
    base = dict(
        monitor_object=obj,
        name="p",
        algorithm="max",
        query_condition={"type": "pmq", "query": "up"},
        source={},
        group_by=["instance_id"],
        enable=True,
        period={"type": "min", "value": 5},
    )
    base.update(kwargs)
    return MonitorPolicy.objects.create(**base)


class TestScanPolicyTask:
    def test_missing_policy_raises(self):
        with pytest.raises(BaseAppException):
            scan_policy_task(999999)

    def test_disabled_policy_skipped(self, mocker):
        policy = _make_policy(enable=False)
        scan = mocker.patch("apps.monitor.tasks.monitor_policy.MonitorPolicyScan")
        out = scan_policy_task(policy.id)
        assert out["success"] is True and out["message"] == "策略未启用"
        scan.assert_not_called()

    def test_first_run_records_watermark(self, mocker):
        policy = _make_policy(last_run_time=None)
        scan = mocker.patch("apps.monitor.tasks.monitor_policy.MonitorPolicyScan")
        out = scan_policy_task(policy.id)
        assert out["success"] is True
        policy.refresh_from_db()
        assert policy.last_run_time is not None
        scan.return_value.run.assert_called_once()

    def test_recent_run_single_scan(self, mocker):
        recent = datetime.now(timezone.utc) - timedelta(seconds=60)
        policy = _make_policy(last_run_time=recent)
        scan = mocker.patch("apps.monitor.tasks.monitor_policy.MonitorPolicyScan")
        out = scan_policy_task(policy.id)
        assert out["success"] is True
        # gap < period(300s) → 单次扫描
        assert scan.return_value.run.call_count == 1

    def test_backfill_is_chunked_per_task_and_watermark_advances(self, mocker, caplog):
        """落后 10 个周期时，一次任务只补 MAX_BACKFILL_PER_TASK 个窗口，其余留给下次调度（issue #5777）。"""
        import logging

        behind = datetime.now(timezone.utc) - timedelta(minutes=5 * 10 + 1)
        policy = _make_policy(last_run_time=behind)
        scan = mocker.patch("apps.monitor.tasks.monitor_policy.MonitorPolicyScan")
        with caplog.at_level(logging.INFO, logger="celery"):
            out = scan_policy_task(policy.id)

        assert out["success"] is True
        assert scan.return_value.run.call_count == AlertConstants.MAX_BACKFILL_PER_TASK
        policy.refresh_from_db()
        assert policy.last_run_time == behind + timedelta(minutes=5 * AlertConstants.MAX_BACKFILL_PER_TASK)

        planned = next(r for r in caplog.records if "event=policy_backfill_planned" in r.getMessage())
        assert planned.args == (policy.id, 10, AlertConstants.MAX_BACKFILL_PER_TASK)
        deferred = next(r for r in caplog.records if "event=policy_backfill_deferred" in r.getMessage())
        assert deferred.getMessage() == (
            f"event=policy_backfill_deferred policy_id={policy.id} "
            f"completed={AlertConstants.MAX_BACKFILL_PER_TASK} remaining={10 - AlertConstants.MAX_BACKFILL_PER_TASK}"
        )

        # 下一次调度从推进后的水位继续，不重扫已完成窗口
        windows = []
        scan.reset_mock()
        scan.side_effect = lambda policy_obj: windows.append(policy_obj.last_run_time) or scan.return_value
        scan_policy_task(policy.id)
        assert windows[0] == behind + timedelta(minutes=5 * (AlertConstants.MAX_BACKFILL_PER_TASK + 1))

    def test_backfill_stops_opening_new_windows_after_soft_time_limit(self, mocker):
        behind = datetime.now(timezone.utc) - timedelta(minutes=5 * 6 + 1)
        policy = _make_policy(last_run_time=behind)
        scan = mocker.patch("apps.monitor.tasks.monitor_policy.MonitorPolicyScan")
        clock = iter([0.0, 0.0, 100.0, 100.0, 100.0, 100.0])
        mocker.patch("apps.monitor.tasks.monitor_policy.time.time", side_effect=lambda: next(clock, 100.0))

        out = scan_policy_task(policy.id)

        assert out["success"] is True
        # 第一个窗口总会执行，第二个窗口前发现已超软时限 → 停止
        assert scan.return_value.run.call_count == 1
        policy.refresh_from_db()
        assert policy.last_run_time == behind + timedelta(minutes=5)

    def test_backfill_failure_keeps_watermark_at_last_success(self, mocker):
        behind = datetime.now(timezone.utc) - timedelta(minutes=5 * 6 + 1)
        policy = _make_policy(last_run_time=behind)
        scan = mocker.patch("apps.monitor.tasks.monitor_policy.MonitorPolicyScan")
        scan.return_value.run.side_effect = [None, RuntimeError("vm down")]

        with pytest.raises(RuntimeError):
            scan_policy_task(policy.id)

        policy.refresh_from_db()
        assert policy.last_run_time == behind + timedelta(minutes=5)


class TestRetryAlertCenterNotify:
    def test_no_alerts(self):
        out = retry_alert_center_lifecycle_notify_task()
        assert out["success"] is True
        assert out["message"] == "no alerts to retry"

    def test_retries_and_marks_success(self, mocker):
        alert = MonitorAlert.objects.create(
            policy_id=1,
            monitor_instance_id="h1",
            status="recovered",
            alert_center_notified=False,
            alert_center_retry_count=0,
        )
        notifier = mocker.patch("apps.monitor.services.alert_lifecycle_notify.AlertLifecycleNotifier")
        inst = notifier.return_value
        inst.push_to_alert_center_only.return_value = [(alert, True)]
        out = retry_alert_center_lifecycle_notify_task()
        assert out["succeeded"] == 1
        inst._mark_alert_center_notified.assert_called_once_with([alert.id])

    def test_failure_increments_retry_count(self, mocker):
        alert = MonitorAlert.objects.create(
            policy_id=1,
            monitor_instance_id="h1",
            status="closed",
            alert_center_notified=False,
            alert_center_retry_count=0,
        )
        notifier = mocker.patch("apps.monitor.services.alert_lifecycle_notify.AlertLifecycleNotifier")
        notifier.return_value.push_to_alert_center_only.return_value = [(alert, False)]
        out = retry_alert_center_lifecycle_notify_task()
        assert out["failed"] == 1
        alert.refresh_from_db()
        assert alert.alert_center_retry_count == 1

    def test_group_exception_treated_as_failure(self, mocker):
        MonitorAlert.objects.create(
            policy_id=1,
            monitor_instance_id="h1",
            status="recovered",
            alert_center_notified=False,
            alert_center_retry_count=0,
        )
        notifier = mocker.patch("apps.monitor.services.alert_lifecycle_notify.AlertLifecycleNotifier")
        notifier.return_value.push_to_alert_center_only.side_effect = RuntimeError("boom")
        out = retry_alert_center_lifecycle_notify_task()
        assert out["failed"] == 1


class TestTemplateAccessGuide:
    def test_get_required_instance_id_keys_default(self):
        obj = MonitorObject.objects.create(name="TAGObj", level="base", instance_id_keys=[])
        assert TemplateAccessGuideService.get_required_instance_id_keys(obj) == ["instance_id"]

    def test_get_required_instance_id_keys_custom(self):
        obj = MonitorObject.objects.create(name="TAGObj2", level="base", instance_id_keys=["a", None, "b"])
        assert TemplateAccessGuideService.get_required_instance_id_keys(obj) == ["a", "b"]

    def test_resolve_required_int(self):
        assert TemplateAccessGuideService.resolve_required_int("5", "x") == 5

    def test_resolve_required_int_empty_raises(self):
        with pytest.raises(BaseAppException):
            TemplateAccessGuideService.resolve_required_int("", "x")

    def test_resolve_required_int_invalid_raises(self):
        with pytest.raises(BaseAppException):
            TemplateAccessGuideService.resolve_required_int("abc", "x")

    def test_telegraf_endpoint_builds_url(self, mocker):
        node = mocker.patch("apps.monitor.services.template_access_guide.NodeMgmt")
        node.return_value.get_cloud_region_public_config.return_value = {"NODE_SERVER_URL": "https://node.example.com:8080/foo"}
        url = TemplateAccessGuideService.get_telegraf_listener_endpoint(1)
        assert url == "https://node.example.com:8080/telegraf/api"

    def test_telegraf_endpoint_missing_url_raises(self, mocker):
        node = mocker.patch("apps.monitor.services.template_access_guide.NodeMgmt")
        node.return_value.get_cloud_region_public_config.return_value = {}
        with pytest.raises(BaseAppException):
            TemplateAccessGuideService.get_telegraf_listener_endpoint(1)

    def test_telegraf_endpoint_bad_url_raises(self, mocker):
        node = mocker.patch("apps.monitor.services.template_access_guide.NodeMgmt")
        node.return_value.get_cloud_region_public_config.return_value = {"NODE_SERVER_URL": "not-a-url"}
        with pytest.raises(BaseAppException):
            TemplateAccessGuideService.get_telegraf_listener_endpoint(1)


@pytest.fixture
def locmem_cache(settings):
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    from django.core.cache import cache

    cache.clear()
    return cache


class TestInfraService:
    def test_generate_and_validate_token(self, locmem_cache):
        token = InfraService.generate_install_token("c1", "5")
        assert isinstance(token, str)
        data = InfraService.validate_and_get_token_data(token)
        assert data["cluster_name"] == "c1"
        assert data["cloud_region_id"] == "5"
        assert data["image_registry_prefix"] == "bk-lite.tencentcloudcr.com/bklite"
        assert data["remaining_usage"] >= 0

    def test_validate_empty_token_raises(self, locmem_cache):
        with pytest.raises(BaseAppException):
            InfraService.validate_and_get_token_data("")

    def test_validate_unknown_token_raises(self, locmem_cache):
        with pytest.raises(BaseAppException):
            InfraService.validate_and_get_token_data("does-not-exist")

    def test_token_usage_limit(self, locmem_cache):
        token = InfraService.generate_install_token("c1", "5")
        # 连续使用至超限（max_usage 次）
        from apps.monitor.constants.infra import InfraConstants

        for _ in range(InfraConstants.TOKEN_MAX_USAGE):
            InfraService.validate_and_get_token_data(token)
        with pytest.raises(BaseAppException):
            InfraService.validate_and_get_token_data(token)

    def test_custom_image_registry_is_bound_to_token(self, locmem_cache):
        token = InfraService.generate_install_token("c1", "5", "harbor.internal/bklite")

        data = InfraService.validate_and_get_token_data(token)

        assert data["image_registry_prefix"] == "harbor.internal/bklite"

    def test_stale_payload_cannot_reuse_exhausted_counter(self, locmem_cache):
        from apps.core.exceptions.base_app_exception import BaseAppException
        from apps.monitor.constants.infra import InfraConstants
        from apps.monitor.services import infra as infra_mod

        token = InfraService.generate_install_token("c1", "5")
        payload_key = f"infra_install_token:{token}"
        payload = infra_mod.cache.get(payload_key)
        payload["usage_count"] = InfraConstants.TOKEN_MAX_USAGE - 1
        infra_mod.cache.set(payload_key, payload, timeout=InfraConstants.TOKEN_EXPIRE_TIME)
        infra_mod.cache.set(f"{payload_key}:usage_count", InfraConstants.TOKEN_MAX_USAGE, timeout=InfraConstants.TOKEN_EXPIRE_TIME)

        with pytest.raises(BaseAppException, match="exceeded maximum usage limit"):
            InfraService.validate_and_get_token_data(token)

    def test_last_quota_is_atomic_under_concurrency(self, monkeypatch):
        import copy
        import threading
        from concurrent.futures import ThreadPoolExecutor

        from apps.core.exceptions.base_app_exception import BaseAppException
        from apps.monitor.constants.infra import InfraConstants

        class RaceyCache:
            def __init__(self):
                self._data = {}
                self._lock = threading.Lock()

            def get(self, key, default=None):
                value = self._data.get(key, default)
                if isinstance(key, str) and key.startswith("infra_install_token:") and ":usage_count" not in key:
                    threading.Event().wait(0.01)
                return copy.deepcopy(value)

            def set(self, key, value, timeout=None):
                self._data[key] = copy.deepcopy(value)

            def add(self, key, value, timeout=None):
                with self._lock:
                    if key in self._data:
                        return False
                    self._data[key] = copy.deepcopy(value)
                    return True

            def incr(self, key, delta=1):
                with self._lock:
                    if key not in self._data:
                        raise ValueError("Key not found")
                    self._data[key] += delta
                    return self._data[key]

            def delete(self, key):
                self._data.pop(key, None)

        monkeypatch.setattr("apps.monitor.services.infra.cache", RaceyCache())
        token = InfraService.generate_install_token("c1", "5")

        def consume():
            try:
                InfraService.validate_and_get_token_data(token)
                return True
            except BaseAppException:
                return False

        workers = InfraConstants.TOKEN_MAX_USAGE * 2
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(lambda _: consume(), range(workers)))

        assert results.count(True) == InfraConstants.TOKEN_MAX_USAGE
