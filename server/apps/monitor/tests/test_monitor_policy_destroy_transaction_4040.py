"""Issue #4040: MonitorPolicyViewSet.destroy() 5 步串行无事务包裹。

def destroy():
    PolicyBaselineService(policy).clear()
    alerts_to_close = list(MonitorAlert.objects.filter(policy_id=policy_id, status="new"))
    self.close_alerts(policy, alerts_to_close, operator, "policy_deleted")  # 内部 bulk_update + NATS
    PeriodicTask.objects.filter(name=...).delete()
    PolicyOrganization.objects.filter(policy_id=policy_id).delete()
    policy.delete()

任一步骤抛异常都会留下半截数据:
- baseline 已清空但 policy/PeriodicTask/PolicyOrganization 还在
- alerts 已 bulk_update 到 closed 但 policy 还在
- PeriodicTask 已删但 policy 还在,扫描会失败
- PolicyOrganization 已删但 policy 还在,产生孤儿 policy

修复模式:在 destroy 内部用 with transaction.atomic(): 包裹所有 DB 写,
NATS 推送(close_alerts 内部 AlertLifecycleNotifier.notify_alerts)挪到
transaction.on_commit 里,保证 DB 整体回滚时 NATS 不会被错误触发。

覆盖:
a) 正常路径:destroy 成功 → policy/PeriodicTask/PolicyOrganization/baseline/alerts 全部清理,NATS 推送 1 次
b) 异常路径:policy.delete() 抛 IntegrityError → 5 步全回滚
c) 异常路径:PolicyOrganization.delete() 抛异常 → 5 步全回滚
d) NATS on_commit:异常路径下 notifier 不应被调用
"""

import pytest

from django.db import IntegrityError, transaction
from django_celery_beat.models import CrontabSchedule, PeriodicTask

from apps.monitor.models import (
    MonitorAlert,
    PolicyInstanceBaseline,
    PolicyOrganization,
)
from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.models.monitor_policy import MonitorPolicy

pytestmark = pytest.mark.django_db


BASE = "/api/v1/monitor"


@pytest.fixture
def superuser_client(db, mocker):
    """Create a superuser-authenticated APIClient to bypass permission rules."""
    from rest_framework.test import APIClient

    from apps.base.models import User

    user = User.objects.create_user(
        username="destroy_tester",
        password="testpass123",
        domain="domain.com",
        locale="en",
        group_list=[{"id": 1, "name": "Default Team"}],
        roles=["admin"],
    )
    user.is_superuser = True
    user.save(update_fields=["is_superuser"])
    mocker.patch(
        "apps.core.utils.current_team_scope.SystemMgmt.get_authorized_groups_scoped",
        return_value={"result": True, "data": [1]},
    )
    client = APIClient()
    client.force_authenticate(user=user)
    client.cookies["current_team"] = "1"
    return client


@pytest.fixture
def stub_notifier(mocker):
    """stub AlertLifecycleNotifier to avoid NATS push side effects."""
    return mocker.patch("apps.monitor.views.monitor_policy.AlertLifecycleNotifier")


@pytest.fixture
def stub_baseline_service(mocker):
    """stub PolicyBaselineService.clear to avoid real VM queries (which is already safe,
    but we still stub to assert call counts)."""
    return mocker.patch("apps.monitor.views.monitor_policy.PolicyBaselineService")


def _make_policy(name="p_4040"):
    obj = MonitorObject.objects.create(name="DestroyObj", level="base")
    return MonitorPolicy.objects.create(
        monitor_object=obj,
        name=name,
        algorithm="max",
        query_condition={},
        source={},
        group_by=[],
    )


def _make_periodic_task(policy_id):
    """Create a real PeriodicTask with a CrontabSchedule (django_celery_beat requires it)."""
    schedule = CrontabSchedule.objects.create(
        minute="*/5",
        hour="*",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
    )
    return PeriodicTask.objects.create(
        name=f"scan_policy_task_{policy_id}",
        task="apps.monitor.tasks.monitor_policy.scan_policy_task",
        args=f"[{policy_id}]",
        crontab=schedule,
    )


class TestDestroySuccessPath:
    """正常路径:destroy 成功 → 所有相关数据清理,NATS 推送 1 次"""

    def test_destroy_policy_clears_all_related_data(
        self, superuser_client, stub_notifier, stub_baseline_service
    ):
        policy = _make_policy()
        # baseline 行
        PolicyInstanceBaseline.objects.create(
            policy=policy, monitor_instance_id="h1", metric_instance_id="m1"
        )
        # new 状态的告警(会被 close)
        alert = MonitorAlert.objects.create(
            policy_id=policy.id,
            monitor_instance_id="h1",
            metric_instance_id="m1",
            alert_type="alert",
            status="new",
        )
        # PeriodicTask
        _make_periodic_task(policy.id)
        # PolicyOrganization
        PolicyOrganization.objects.create(policy=policy, organization=1)
        policy_id = policy.id

        resp = superuser_client.delete(f"{BASE}/api/monitor_policy/{policy_id}/")

        # CustomRenderer 把 DELETE 204 → 200 (config/drf/renderers.py:46)
        assert resp.status_code == 200
        # 业务上 destroy 仍然算成功(返回 result=true 包裹的 null data)
        body = resp.json()
        assert body.get("result") is True
        # policy 已删
        assert not MonitorPolicy.objects.filter(id=policy_id).exists()
        # baseline 已清
        assert not PolicyInstanceBaseline.objects.filter(policy_id=policy_id).exists()
        # PeriodicTask 已删
        assert not PeriodicTask.objects.filter(name=f"scan_policy_task_{policy_id}").exists()
        # PolicyOrganization 已删
        assert not PolicyOrganization.objects.filter(policy_id=policy_id).exists()
        # alert 状态被 close
        alert.refresh_from_db()
        assert alert.status == "closed"
        # baseline service clear 被调用
        stub_baseline_service.assert_called_once()
        stub_baseline_service.return_value.clear.assert_called_once()
        # NATS notifier 在 commit 后被调用
        stub_notifier.return_value.notify_alerts.assert_called_once()
        # 调用参数里包含被 close 的 alert
        call_args = stub_notifier.return_value.notify_alerts.call_args
        closed_alerts = call_args.args[0] if call_args.args else call_args.kwargs.get("alerts")
        assert any(a.id == alert.id for a in closed_alerts)

    def test_destroy_policy_with_no_alerts_and_no_baseline(
        self, superuser_client, stub_notifier, stub_baseline_service
    ):
        """无告警 / 无 baseline / 无 PeriodicTask 的 destroy 仍能成功,
        notifier 不应被调用(无 alert 需要 push)"""
        policy = _make_policy(name="p_4040_empty")
        PolicyOrganization.objects.create(policy=policy, organization=1)
        resp = superuser_client.delete(f"{BASE}/api/monitor_policy/{policy.id}/")
        assert resp.status_code == 200
        assert resp.json().get("result") is True
        assert not MonitorPolicy.objects.filter(id=policy.id).exists()
        stub_notifier.return_value.notify_alerts.assert_not_called()
        stub_baseline_service.return_value.clear.assert_called_once()


class TestDestroyRollbackOnFailure:
    """异常路径:任一步骤抛异常 → 5 步全回滚,NATS 不应被触发"""

    def test_destroy_rolls_back_when_policy_delete_fails(
        self, superuser_client, stub_notifier, stub_baseline_service, monkeypatch
    ):
        """policy.delete() 抛 IntegrityError → 5 步全回滚"""
        policy = _make_policy(name="p_4040_rb1")
        baseline = PolicyInstanceBaseline.objects.create(
            policy=policy, monitor_instance_id="h1", metric_instance_id="m1"
        )
        alert = MonitorAlert.objects.create(
            policy_id=policy.id,
            monitor_instance_id="h1",
            metric_instance_id="m1",
            alert_type="alert",
            status="new",
        )
        periodic = _make_periodic_task(policy.id)
        org = PolicyOrganization.objects.create(policy=policy, organization=1)
        policy_id = policy.id

        from apps.monitor.views import monitor_policy as policy_view_mod

        def fake_policy_delete(self):
            raise IntegrityError("simulated policy.delete failure")

        monkeypatch.setattr(
            policy_view_mod.MonitorPolicy, "delete", fake_policy_delete
        )

        resp = superuser_client.delete(f"{BASE}/api/monitor_policy/{policy_id}/")
        # DRF 把异常转 5xx
        assert resp.status_code == 500

        # 5 步全部回滚:policy/baseline/PeriodicTask/PolicyOrganization 全部还在
        assert MonitorPolicy.objects.filter(id=policy_id).exists()
        assert PolicyInstanceBaseline.objects.filter(id=baseline.id).exists()
        assert PeriodicTask.objects.filter(id=periodic.id).exists()
        assert PolicyOrganization.objects.filter(id=org.id).exists()
        # alert status 必须回滚(若 close_alerts 已经写了 status,事务必须回滚)
        alert.refresh_from_db()
        assert alert.status == "new"
        # notifier 走 on_commit,事务回滚时不会调用
        stub_notifier.return_value.notify_alerts.assert_not_called()

    def test_destroy_rolls_back_when_organization_delete_fails(
        self, superuser_client, stub_notifier, stub_baseline_service, monkeypatch
    ):
        """PolicyOrganization.delete() 抛异常 → 5 步全回滚。
        用 PolicyOrganization.objects 的 _base_manager.filter 返回一个抛异常的 Mock QuerySet
        来模拟 PolicyOrganization.objects.filter(...).delete() 失败。"""
        policy = _make_policy(name="p_4040_rb2")
        PolicyInstanceBaseline.objects.create(
            policy=policy, monitor_instance_id="h1", metric_instance_id="m1"
        )
        alert = MonitorAlert.objects.create(
            policy_id=policy.id,
            monitor_instance_id="h1",
            metric_instance_id="m1",
            alert_type="alert",
            status="new",
        )
        _make_periodic_task(policy.id)
        PolicyOrganization.objects.create(policy=policy, organization=1)
        policy_id = policy.id

        from apps.monitor.views import monitor_policy as policy_view_mod
        from django.db.models.query import QuerySet

        original_filter = policy_view_mod.PolicyOrganization.objects.filter

        def patched_filter(*args, **kwargs):
            qs = original_filter(*args, **kwargs)

            def fail_delete(*dargs, **dkwargs):
                raise IntegrityError("simulated PolicyOrganization.delete failure")

            # 给返回的 QuerySet 注入会抛异常的 delete
            qs.delete = fail_delete
            return qs

        monkeypatch.setattr(
            policy_view_mod.PolicyOrganization.objects, "filter", patched_filter
        )

        resp = superuser_client.delete(f"{BASE}/api/monitor_policy/{policy_id}/")
        # DRF 把 IntegrityError 转 5xx
        assert resp.status_code == 500

        # 5 步全回滚
        assert MonitorPolicy.objects.filter(id=policy_id).exists()
        assert PolicyInstanceBaseline.objects.filter(policy_id=policy_id).exists()
        assert PeriodicTask.objects.filter(
            name=f"scan_policy_task_{policy_id}"
        ).exists()
        assert PolicyOrganization.objects.filter(policy_id=policy_id).exists()
        # alert status 仍为 new(close_alerts 的 bulk_update 也必须回滚)
        alert.refresh_from_db()
        assert alert.status == "new"
        stub_notifier.return_value.notify_alerts.assert_not_called()


class TestDestroyNoAlertsNoNatsPush:
    """destroy 时若没有 new 状态告警 → 不应触发 NATS 推送"""

    def test_destroy_with_only_old_alerts_skips_notifier(
        self, superuser_client, stub_notifier, stub_baseline_service
    ):
        policy = _make_policy(name="p_4040_noalert")
        PolicyOrganization.objects.create(policy=policy, organization=1)
        # alert 已经是 closed(不属于要被 close 的范围)
        MonitorAlert.objects.create(
            policy_id=policy.id,
            monitor_instance_id="h1",
            metric_instance_id="m1",
            alert_type="alert",
            status="closed",
        )

        resp = superuser_client.delete(f"{BASE}/api/monitor_policy/{policy.id}/")
        assert resp.status_code == 200
        stub_notifier.return_value.notify_alerts.assert_not_called()
