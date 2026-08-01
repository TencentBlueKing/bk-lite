from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.operation_analysis.models.models import Dashboard, Directory
from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
    DashboardReportExecutionSnapshot,
    DashboardReportRenderSnapshot,
    DashboardReportSubscription,
)
from apps.operation_analysis.services.due_subscription_scanner import (
    DueSubscriptionScanner,
)
from apps.operation_analysis.services.execution_orchestrator import (
    PermissionStep,
    RenderSnapshotStep,
    SnapshotStep,
)
from apps.operation_analysis.services.execution_service import (
    DashboardReportExecutionService,
)
from apps.operation_analysis.services.subscription_service import (
    DashboardSubscriptionService,
    TERMINATION_REASON_DASHBOARD_DELETED,
)
from apps.system_mgmt.models import Channel


pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def grant_feature_permission(authenticated_user):
    authenticated_user.permission = {
        "ops-analysis": {"view-View", "view-DeleteChart"},
    }
    return authenticated_user


@pytest.fixture(autouse=True)
def bind_current_team(api_client):
    api_client.cookies["current_team"] = "1"
    return api_client


@pytest.fixture
def email_channel(db):
    return Channel.objects.create(
        name="生命周期邮件通道",
        channel_type="email",
        config={},
        description="测试",
        team=[1],
    )


@pytest.fixture
def dashboard(authenticated_user):
    directory = Directory.objects.create(name="生命周期目录", groups=[1])
    return Dashboard.objects.create(
        name="生命周期仪表盘",
        directory=directory,
        groups=[1],
        created_by=authenticated_user.username,
        view_sets=[{"id": "w1", "itemType": "chart", "valueConfig": {}}],
    )


@pytest.fixture
def subscription_url():
    return "/api/v1/operation_analysis/api/dashboard_subscription/"


@pytest.fixture
def dashboard_url():
    return "/api/v1/operation_analysis/api/dashboard/"


def grant_dashboard_view(monkeypatch, allowed=True):
    monkeypatch.setattr(
        "apps.operation_analysis.services.subscription_service."
        "DashboardSubscriptionService.can_view_dashboard",
        lambda request, dashboard: allowed,
    )


def _make_due_subscription(authenticated_user, dashboard, email_channel, *, due=True):
    due_at = timezone.now() - timedelta(minutes=1) if due else (
        timezone.now() + timedelta(days=1)
    )
    return DashboardReportSubscription.objects.create(
        dashboard=dashboard,
        creator=authenticated_user.username,
        name="生命周期订阅",
        recipient_email="ops@example.com",
        email_channel=email_channel,
        schedule_type=DashboardReportSubscription.ScheduleType.DAILY,
        schedule_hour=9,
        schedule_minute=0,
        timezone="Asia/Shanghai",
        next_run_at=due_at,
        version=1,
        status=DashboardReportSubscription.Status.ACTIVE,
    )


def _create_input_snapshot(execution, subscription):
    return DashboardReportExecutionSnapshot.objects.create(
        execution=execution,
        dashboard_id=subscription.dashboard_id,
        creator_id=subscription.creator,
        subscription_id=subscription.id,
        subscription_name=subscription.name,
        recipient_email=subscription.recipient_email,
        trigger_type=execution.trigger_type,
        email_channel_id=subscription.email_channel_id,
        scheduled_time_utc=execution.scheduled_time_utc,
        schedule_timezone=subscription.timezone or "Asia/Shanghai",
        scheduled_local_time="",
        subscription_version=subscription.version,
        filter_values={},
    )


# --- A1 soft delete ---


def test_soft_delete_hides_from_api_and_stops_scanner(
    api_client,
    authenticated_user,
    dashboard,
    subscription_url,
    email_channel,
    monkeypatch,
):
    grant_dashboard_view(monkeypatch)
    sub = _make_due_subscription(authenticated_user, dashboard, email_channel)
    monkeypatch.setattr(
        DashboardReportExecutionService,
        "_dispatch_render",
        MagicMock(),
    )

    delete_resp = api_client.delete(f"{subscription_url}{sub.id}/")
    # 项目 CustomRenderer 将 DELETE 204 规范为 200
    assert delete_resp.status_code == 200

    row = DashboardReportSubscription.all_objects.get(pk=sub.id)
    assert row.deleted_at is not None
    assert row.deleted_by == authenticated_user.username
    assert DashboardReportSubscription.objects.filter(pk=sub.id).exists() is False

    list_resp = api_client.get(subscription_url)
    assert list_resp.status_code == 200
    assert all(item["id"] != sub.id for item in list_resp.data)

    detail_resp = api_client.get(f"{subscription_url}{sub.id}/")
    assert detail_resp.status_code == 404

    stats = DueSubscriptionScanner.scan()
    assert stats.scanned == 0
    assert stats.created == 0
    assert not DashboardReportExecution.objects.filter(
        subscription_id=sub.id,
        trigger_type=DashboardReportExecution.TriggerType.SCHEDULED,
    ).exists()


def test_soft_delete_keeps_in_flight_execution_and_history(
    api_client,
    authenticated_user,
    dashboard,
    subscription_url,
    email_channel,
    monkeypatch,
):
    grant_dashboard_view(monkeypatch)
    sub = _make_due_subscription(
        authenticated_user, dashboard, email_channel, due=False
    )
    execution = DashboardReportExecution.objects.create(
        subscription=sub,
        dashboard=dashboard,
        creator=sub.creator,
        trigger_type=DashboardReportExecution.TriggerType.MANUAL_TEST,
        request_id="keep-inflight",
        status=DashboardReportExecution.Status.PENDING,
    )
    snapshot = _create_input_snapshot(execution, sub)

    delete_resp = api_client.delete(f"{subscription_url}{sub.id}/")
    # 项目 CustomRenderer 将 DELETE 204 规范为 200
    assert delete_resp.status_code == 200

    execution.refresh_from_db()
    assert execution.status == DashboardReportExecution.Status.PENDING
    assert execution.subscription_id == sub.id
    assert DashboardReportExecutionSnapshot.objects.filter(
        pk=snapshot.pk
    ).exists()

    exec_resp = api_client.get(
        f"/api/v1/operation_analysis/api/dashboard_execution/{execution.id}/"
    )
    assert exec_resp.status_code == 200
    assert exec_resp.data["id"] == execution.id


# --- A2 dashboard delete → terminated ---


def test_dashboard_delete_terminates_active_subscriptions(
    api_client,
    authenticated_user,
    dashboard,
    dashboard_url,
    email_channel,
    monkeypatch,
):
    grant_dashboard_view(monkeypatch)
    sub = _make_due_subscription(authenticated_user, dashboard, email_channel)
    other = DashboardReportSubscription.objects.create(
        dashboard=dashboard,
        creator=authenticated_user.username,
        name="第二条",
        recipient_email="ops2@example.com",
        email_channel=email_channel,
        status=DashboardReportSubscription.Status.PAUSED,
    )

    resp = api_client.delete(f"{dashboard_url}{dashboard.id}/")
    # 项目 CustomRenderer 将 DELETE 204 规范为 200
    assert resp.status_code == 200
    assert not Dashboard.objects.filter(pk=dashboard.id).exists()

    for item in (sub, other):
        item.refresh_from_db()
        assert item.status == DashboardReportSubscription.Status.TERMINATED
        assert item.terminated_at is not None
        assert item.termination_reason == TERMINATION_REASON_DASHBOARD_DELETED
        assert item.terminated_by == authenticated_user.username
        assert item.next_run_at is None
        assert item.dashboard_id is None

    # terminated 仍可见（非逻辑删除）
    list_resp = api_client.get(
        "/api/v1/operation_analysis/api/dashboard_subscription/"
    )
    ids = {item["id"] for item in list_resp.data}
    assert sub.id in ids
    assert other.id in ids


def test_terminated_subscription_not_scanned_and_not_resumable(
    api_client,
    authenticated_user,
    dashboard,
    subscription_url,
    email_channel,
    monkeypatch,
):
    grant_dashboard_view(monkeypatch)
    sub = _make_due_subscription(authenticated_user, dashboard, email_channel)
    DashboardSubscriptionService.terminate_for_dashboard_deletion(
        dashboard,
        actor=authenticated_user.username,
    )
    sub.refresh_from_db()
    assert sub.status == DashboardReportSubscription.Status.TERMINATED
    # 人为拨回 due，验证 terminated 仍不扫描
    DashboardReportSubscription.all_objects.filter(pk=sub.pk).update(
        next_run_at=timezone.now() - timedelta(minutes=1),
        status=DashboardReportSubscription.Status.TERMINATED,
    )

    monkeypatch.setattr(
        DashboardReportExecutionService,
        "_dispatch_render",
        MagicMock(),
    )
    stats = DueSubscriptionScanner.scan()
    assert stats.created == 0
    assert not DashboardReportExecution.objects.filter(
        subscription_id=sub.id
    ).exists()

    resume = api_client.patch(
        f"{subscription_url}{sub.id}/",
        {"status": "active"},
        format="json",
    )
    assert resume.status_code == 400


def test_dashboard_delete_race_before_render_snapshot_fails_permission(
    authenticated_user,
    dashboard,
    email_channel,
):
    sub = _make_due_subscription(
        authenticated_user, dashboard, email_channel, due=False
    )
    execution = DashboardReportExecution.objects.create(
        subscription=sub,
        dashboard=dashboard,
        creator=sub.creator,
        trigger_type=DashboardReportExecution.TriggerType.SCHEDULED,
        scheduled_time_utc=timezone.now(),
        status=DashboardReportExecution.Status.RUNNING,
    )
    _create_input_snapshot(execution, sub)

    DashboardSubscriptionService.terminate_for_dashboard_deletion(
        dashboard,
        actor="deleter",
    )
    dashboard.delete()
    execution.refresh_from_db()
    assert execution.source_canvas_deleted_during_execution is True
    assert execution.dashboard_id is None

    result = PermissionStep.execute(execution)
    assert result.ok is False
    assert result.error_code == "dashboard_missing"


def test_dashboard_delete_race_after_render_snapshot_continues(
    authenticated_user,
    dashboard,
    email_channel,
    monkeypatch,
):
    set_dashboard_view = monkeypatch
    set_dashboard_view.setattr(
        "apps.operation_analysis.views.view."
        "DashboardModelViewSet.get_has_permission",
        lambda *args, **kwargs: True,
    )
    sub = _make_due_subscription(
        authenticated_user, dashboard, email_channel, due=False
    )
    execution = DashboardReportExecution.objects.create(
        subscription=sub,
        dashboard=dashboard,
        creator=sub.creator,
        trigger_type=DashboardReportExecution.TriggerType.SCHEDULED,
        scheduled_time_utc=timezone.now(),
        status=DashboardReportExecution.Status.RUNNING,
    )
    _create_input_snapshot(execution, sub)
    DashboardReportRenderSnapshot.objects.create(
        execution=execution,
        dashboard_id=dashboard.id,
        dashboard_name=dashboard.name,
        dashboard_updated_at=dashboard.updated_at,
        view_sets=dashboard.view_sets or [],
        filters={},
        other={},
        widget_manifest=[],
    )
    frozen_dashboard_id = dashboard.id

    DashboardSubscriptionService.terminate_for_dashboard_deletion(
        dashboard,
        actor="deleter",
    )
    dashboard.delete()
    execution.refresh_from_db()
    assert execution.source_canvas_deleted_during_execution is True
    assert execution.dashboard_id is None

    perm = PermissionStep.execute(execution)
    assert perm.ok is True
    snap = SnapshotStep.execute(execution)
    assert isinstance(snap, DashboardReportExecutionSnapshot)
    assert snap.subscription_id == sub.id
    render = RenderSnapshotStep.execute(execution)
    assert isinstance(render, DashboardReportRenderSnapshot)
    assert render.dashboard_id == frozen_dashboard_id


# --- A6 pause / resume audit ---


def test_pause_resume_records_audit_and_schedule_semantics(
    api_client,
    authenticated_user,
    dashboard,
    subscription_url,
    email_channel,
    monkeypatch,
):
    grant_dashboard_view(monkeypatch)
    monkeypatch.setattr(
        DashboardReportExecutionService,
        "_dispatch_render",
        MagicMock(),
    )
    created = api_client.post(
        subscription_url,
        {
            "dashboard": dashboard.id,
            "name": "审计订阅",
            "recipient_email": "ops@example.com",
            "email_channel": email_channel.id,
            "schedule_type": "daily",
            "schedule_hour": 9,
            "schedule_minute": 0,
            "timezone": "Asia/Shanghai",
        },
        format="json",
    )
    assert created.status_code == 201
    sub_id = created.data["id"]

    # 拨成已到期，pause 后不得产生新 Execution
    past = timezone.now() - timedelta(hours=2)
    DashboardReportSubscription.objects.filter(pk=sub_id).update(
        next_run_at=past
    )

    pause = api_client.patch(
        f"{subscription_url}{sub_id}/",
        {"status": "paused"},
        format="json",
    )
    assert pause.status_code == 200
    assert pause.data["status"] == "paused"
    assert pause.data["last_lifecycle_action"] == "pause"
    assert pause.data["last_lifecycle_actor"] == authenticated_user.username
    assert pause.data["last_lifecycle_at"] is not None

    stats = DueSubscriptionScanner.scan()
    assert stats.created == 0
    assert not DashboardReportExecution.objects.filter(
        subscription_id=sub_id
    ).exists()

    before_resume = timezone.now()
    resume = api_client.patch(
        f"{subscription_url}{sub_id}/",
        {"status": "active"},
        format="json",
    )
    assert resume.status_code == 200
    assert resume.data["status"] == "active"
    assert resume.data["last_lifecycle_action"] == "resume"
    assert resume.data["last_lifecycle_actor"] == authenticated_user.username
    new_next = parse_datetime(resume.data["next_run_at"])
    assert new_next is not None
    if timezone.is_naive(new_next):
        new_next = timezone.make_aware(new_next)
    assert new_next > before_resume
    # resume 只重算未来周期，不回补 pause 期间的 past next_run_at
    assert new_next > past

    # resume 不立即创建 Execution
    assert not DashboardReportExecution.objects.filter(
        subscription_id=sub_id
    ).exists()
    stats_after = DueSubscriptionScanner.scan(now=before_resume)
    assert stats_after.created == 0


def test_api_cannot_set_terminated_directly(
    api_client,
    authenticated_user,
    dashboard,
    subscription_url,
    email_channel,
    monkeypatch,
):
    grant_dashboard_view(monkeypatch)
    created = api_client.post(
        subscription_url,
        {
            "dashboard": dashboard.id,
            "name": "不可直接终止",
            "recipient_email": "ops@example.com",
            "email_channel": email_channel.id,
        },
        format="json",
    )
    resp = api_client.patch(
        f"{subscription_url}{created.data['id']}/",
        {"status": "terminated"},
        format="json",
    )
    assert resp.status_code == 400
