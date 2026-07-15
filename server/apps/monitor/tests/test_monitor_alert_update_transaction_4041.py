"""Issue #4041: MonitorAlertViewSet.update() 关闭 no_data 告警时基线
delete/refresh 与 perform_update 必须在同一事务中,否则 perform_update
失败时 baseline 已删/已刷,下次扫描会再次 new 一模一样的告警。

覆盖:
a) 正常路径:perform_update 成功 → baseline + alert status 都更新
b) 异常路径:perform_update 抛 IntegrityError → baseline 也回滚
c) 非 no_data alert:不触发事务包裹路径,baseline 不动
d) update_baseline=True vs False 两条路径都覆盖
"""

import pytest

from django.db import IntegrityError, transaction

from apps.monitor.models import (
    MonitorAlert,
    PolicyInstanceBaseline,
)
from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.models.monitor_policy import MonitorPolicy

pytestmark = pytest.mark.django_db


BASE = "/api/v1/monitor"


@pytest.fixture
def grant_all(mocker):
    """放行权限检查,绕过 RPC 权限校验"""
    mocker.patch(
        "apps.monitor.views.monitor_alert.get_permissions_rules",
        return_value={"data": {"all": True}, "team": [1]},
    )
    mocker.patch(
        "apps.monitor.views.monitor_alert.check_instance_permission",
        return_value=True,
    )


@pytest.fixture
def stub_notifier(mocker):
    """stub AlertLifecycleNotifier,避免 NATS 推送依赖"""
    return mocker.patch("apps.monitor.views.monitor_alert.AlertLifecycleNotifier")


@pytest.fixture
def stub_refresh(mocker):
    """stub PolicyBaselineService.refresh,避免触发 VM scan"""
    return mocker.patch("apps.monitor.views.monitor_alert.PolicyBaselineService")


def _make_policy():
    obj = MonitorObject.objects.create(name="AlertCloseObj", level="base")
    return MonitorPolicy.objects.create(
        monitor_object=obj,
        name="p_4041",
        algorithm="max",
        query_condition={},
        source={},
        group_by=[],
    )


class TestCloseNoDataAlertTransaction:
    """正常路径:perform_update 成功 → baseline 与 alert status 都更新"""

    def test_close_no_data_alert_with_update_baseline_true(
        self, api_client, grant_all, stub_notifier, stub_refresh
    ):
        api_client.cookies["current_team"] = "1"
        policy = _make_policy()
        alert = MonitorAlert.objects.create(
            policy_id=policy.id,
            monitor_instance_id="h1",
            metric_instance_id="m1",
            alert_type="no_data",
            status="new",
        )
        PolicyInstanceBaseline.objects.create(
            policy=policy, monitor_instance_id="h1", metric_instance_id="m1"
        )
        PolicyInstanceBaseline.objects.create(
            policy=policy, monitor_instance_id="h1", metric_instance_id="m2"
        )

        resp = api_client.patch(
            f"{BASE}/api/monitor_alert/{alert.id}/",
            {"status": "closed", "update_baseline": True},
            format="json",
        )
        assert resp.status_code == 200
        alert.refresh_from_db()
        assert alert.status == "closed"
        # refresh() 已被调用一次
        stub_refresh.assert_called_once()
        stub_refresh.return_value.refresh.assert_called_once()
        stub_notifier.return_value.notify_alerts.assert_called_once()

    def test_close_no_data_alert_with_update_baseline_false(
        self, api_client, grant_all, stub_notifier
    ):
        api_client.cookies["current_team"] = "1"
        policy = _make_policy()
        alert = MonitorAlert.objects.create(
            policy_id=policy.id,
            monitor_instance_id="h1",
            metric_instance_id="m1",
            alert_type="no_data",
            status="new",
        )
        # 同实例的 baseline 行 (会被删)
        target = PolicyInstanceBaseline.objects.create(
            policy=policy, monitor_instance_id="h1", metric_instance_id="m1"
        )
        # 异实例的 baseline 行 (不应被删)
        other = PolicyInstanceBaseline.objects.create(
            policy=policy, monitor_instance_id="h2", metric_instance_id="m2"
        )

        resp = api_client.patch(
            f"{BASE}/api/monitor_alert/{alert.id}/",
            {"status": "closed", "update_baseline": False},
            format="json",
        )
        assert resp.status_code == 200
        alert.refresh_from_db()
        assert alert.status == "closed"
        # m1 行已删,m2 行保留
        assert not PolicyInstanceBaseline.objects.filter(id=target.id).exists()
        assert PolicyInstanceBaseline.objects.filter(id=other.id).exists()


class TestRollbackOnPerformUpdateFailure:
    """异常路径:perform_update 抛异常 → baseline 必须回滚"""

    def test_perform_update_failure_rolls_back_baseline_delete(
        self, api_client, grant_all, stub_notifier, monkeypatch
    ):
        """update_baseline=False 路径:perform_update 抛 IntegrityError → baseline 行不应被删"""
        api_client.cookies["current_team"] = "1"
        policy = _make_policy()
        alert = MonitorAlert.objects.create(
            policy_id=policy.id,
            monitor_instance_id="h1",
            metric_instance_id="m1",
            alert_type="no_data",
            status="new",
        )
        baseline = PolicyInstanceBaseline.objects.create(
            policy=policy, monitor_instance_id="h1", metric_instance_id="m1"
        )

        # 在事务内拦截 perform_update,人为抛 IntegrityError
        from apps.monitor.views import monitor_alert as alert_view_mod

        def fake_perform_update(self, serializer):
            raise IntegrityError("simulated perform_update failure")

        monkeypatch.setattr(
            alert_view_mod.MonitorAlertViewSet,
            "perform_update",
            fake_perform_update,
        )

        response = api_client.patch(
            f"{BASE}/api/monitor_alert/{alert.id}/",
            {"status": "closed", "update_baseline": False},
            format="json",
        )
        assert response.status_code == 500

        # baseline 必须回滚(行数不变)
        assert PolicyInstanceBaseline.objects.filter(id=baseline.id).exists()
        # alert 状态必须回滚(仍为 new,不是 closed)
        alert.refresh_from_db()
        assert alert.status == "new"
        # notifier 不应被调用(perform_update 失败时整个事务回滚)
        stub_notifier.return_value.notify_alerts.assert_not_called()

    def test_perform_update_failure_rolls_back_baseline_refresh(
        self, api_client, grant_all, stub_notifier, monkeypatch
    ):
        """update_baseline=True 路径:perform_update 抛 IntegrityError →
        PolicyBaselineService.refresh 已执行(delete+bulk_create)的事务也必须回滚"""
        api_client.cookies["current_team"] = "1"
        policy = _make_policy()
        alert = MonitorAlert.objects.create(
            policy_id=policy.id,
            monitor_instance_id="h1",
            metric_instance_id="m1",
            alert_type="no_data",
            status="new",
        )
        original = PolicyInstanceBaseline.objects.create(
            policy=policy, monitor_instance_id="h1", metric_instance_id="m1"
        )

        # 用真实的 refresh,但包裹一个异常注入
        from apps.monitor.views import monitor_alert as alert_view_mod

        # 保留原 refresh,但用一个 fake PolicyBaselineService 在 refresh() 中"清空再补一行"
        # 来模拟 refresh 改变了 baseline 集合的副作用
        class FakeBaselineService:
            def __init__(self, policy):
                self.policy = policy

            def refresh(self):
                # 模拟 refresh 删除全部旧 baseline,然后 bulk_create 新行
                with transaction.atomic():
                    PolicyInstanceBaseline.objects.filter(policy_id=self.policy.id).delete()
                    PolicyInstanceBaseline.objects.create(
                        policy=self.policy,
                        monitor_instance_id="REFRESHED",
                        metric_instance_id="REFRESHED",
                    )

        monkeypatch.setattr(
            alert_view_mod,
            "PolicyBaselineService",
            FakeBaselineService,
        )

        def fake_perform_update(self, serializer):
            raise IntegrityError("simulated perform_update failure")

        monkeypatch.setattr(
            alert_view_mod.MonitorAlertViewSet,
            "perform_update",
            fake_perform_update,
        )

        response = api_client.patch(
            f"{BASE}/api/monitor_alert/{alert.id}/",
            {"status": "closed", "update_baseline": True},
            format="json",
        )
        assert response.status_code == 500

        # refresh 内部的 delete + bulk_create 必须整体回滚:
        # 原 m1 行应存在,且不应有 REFRESHED 行
        assert PolicyInstanceBaseline.objects.filter(id=original.id).exists()
        assert not PolicyInstanceBaseline.objects.filter(
            metric_instance_id="REFRESHED"
        ).exists()
        # alert 状态必须回滚
        alert.refresh_from_db()
        assert alert.status == "new"
        stub_notifier.return_value.notify_alerts.assert_not_called()


class TestNonNoDataAlertDoesNotTouchBaseline:
    """非 no_data alert 不走 baseline 路径,事务包裹也不应触发"""

    def test_close_regular_alert_does_not_touch_baseline(
        self, api_client, grant_all, stub_notifier, stub_refresh
    ):
        api_client.cookies["current_team"] = "1"
        policy = _make_policy()
        alert = MonitorAlert.objects.create(
            policy_id=policy.id,
            monitor_instance_id="h1",
            metric_instance_id="m1",
            alert_type="alert",
            status="new",
        )
        baseline = PolicyInstanceBaseline.objects.create(
            policy=policy, monitor_instance_id="h1", metric_instance_id="m1"
        )

        resp = api_client.patch(
            f"{BASE}/api/monitor_alert/{alert.id}/",
            {"status": "closed", "update_baseline": True},
            format="json",
        )
        assert resp.status_code == 200
        # baseline 完全未被触动
        assert PolicyInstanceBaseline.objects.filter(id=baseline.id).exists()
        # refresh 没被调用(非 no_data)
        stub_refresh.assert_not_called()
        # 但 notifier 仍正常触发
        stub_notifier.return_value.notify_alerts.assert_called_once()


class TestNoDataAlertNoMetricInstanceId:
    """no_data 但无 metric_instance_id 时,baseline 路径不走"""

    def test_close_no_data_without_metric_instance_id(
        self, api_client, grant_all, stub_notifier, stub_refresh
    ):
        api_client.cookies["current_team"] = "1"
        policy = _make_policy()
        alert = MonitorAlert.objects.create(
            policy_id=policy.id,
            monitor_instance_id="h1",
            metric_instance_id="",  # 空
            alert_type="no_data",
            status="new",
        )
        resp = api_client.patch(
            f"{BASE}/api/monitor_alert/{alert.id}/",
            {"status": "closed", "update_baseline": True},
            format="json",
        )
        assert resp.status_code == 200
        stub_refresh.assert_not_called()
        stub_notifier.return_value.notify_alerts.assert_called_once()
