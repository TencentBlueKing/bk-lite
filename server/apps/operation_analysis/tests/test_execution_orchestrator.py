import pytest

from apps.operation_analysis.models.models import Dashboard, Directory
from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
    DashboardReportExecutionSnapshot,
    DashboardReportSubscription,
)
from apps.operation_analysis.services.execution_orchestrator import (
    DeliveryStep,
    ExecutionOrchestrator,
    ExecutionStepResult,
    PermissionStep,
    RenderStep,
    SnapshotStep,
)


pytestmark = pytest.mark.django_db


def set_dashboard_view_permission(monkeypatch, allowed):
    monkeypatch.setattr(
        "apps.operation_analysis.views.view."
        "DashboardModelViewSet.get_has_permission",
        lambda self, user, dashboard, team_id, **kwargs: allowed,
    )


@pytest.fixture
def execution(authenticated_user):
    directory = Directory.objects.create(name="编排测试目录", groups=[1])
    dashboard = Dashboard.objects.create(
        name="编排测试仪表盘",
        directory=directory,
        groups=[1],
        created_by=authenticated_user.username,
    )
    subscription = DashboardReportSubscription.objects.create(
        dashboard=dashboard,
        creator=authenticated_user.username,
        name="编排测试订阅",
        recipient_email="ops@example.com",
    )
    execution = DashboardReportExecution.objects.create(
        subscription=subscription,
        dashboard=dashboard,
        creator=authenticated_user.username,
    )
    DashboardReportExecutionSnapshot.objects.create(
        execution=execution,
        dashboard_id=dashboard.id,
        creator_id=authenticated_user.username,
        subscription_id=subscription.id,
        filter_values={"environment": "production"},
    )
    return execution


def test_orchestrator_does_not_succeed_before_render_is_implemented(
    execution,
    monkeypatch,
):
    set_dashboard_view_permission(monkeypatch, True)

    result = ExecutionOrchestrator.execute(execution.id)

    execution.refresh_from_db()
    assert result.id == execution.id
    assert execution.status == DashboardReportExecution.Status.RUNNING
    assert execution.started_at is not None
    assert execution.finished_at is None
    assert execution.failure_stage == ""
    assert execution.error_message == ""


def test_orchestrator_runs_steps_in_order(
    execution,
    monkeypatch,
):
    calls = []

    monkeypatch.setattr(
        PermissionStep,
        "execute",
        lambda current: (
            calls.append("permission"),
            ExecutionStepResult.COMPLETED,
        )[1],
    )

    def snapshot_step(current):
        calls.append("snapshot")
        return current.snapshot

    monkeypatch.setattr(SnapshotStep, "execute", snapshot_step)
    monkeypatch.setattr(
        RenderStep,
        "execute",
        lambda current, snapshot: (
            calls.append("render"),
            ExecutionStepResult.NOT_READY,
        )[1],
    )
    monkeypatch.setattr(
        DeliveryStep,
        "execute",
        lambda current, snapshot: calls.append("delivery"),
    )

    ExecutionOrchestrator.execute(execution.id)

    assert calls == ["permission", "snapshot", "render"]


def test_orchestrator_does_not_succeed_before_delivery_is_implemented(
    execution,
    monkeypatch,
):
    set_dashboard_view_permission(monkeypatch, True)
    monkeypatch.setattr(
        RenderStep,
        "execute",
        lambda current, snapshot: ExecutionStepResult.COMPLETED,
    )

    result = ExecutionOrchestrator.execute(execution.id)

    execution.refresh_from_db()
    assert result.id == execution.id
    assert execution.status == DashboardReportExecution.Status.RUNNING
    assert execution.finished_at is None


def test_orchestrator_fails_when_creator_loses_dashboard_view(
    execution,
    monkeypatch,
):
    set_dashboard_view_permission(monkeypatch, False)
    later_steps = []
    monkeypatch.setattr(
        SnapshotStep,
        "execute",
        lambda current: later_steps.append("snapshot"),
    )
    monkeypatch.setattr(
        RenderStep,
        "execute",
        lambda current, snapshot: later_steps.append("render"),
    )
    monkeypatch.setattr(
        DeliveryStep,
        "execute",
        lambda current, snapshot: later_steps.append("delivery"),
    )

    result = ExecutionOrchestrator.execute(execution.id)

    execution.refresh_from_db()
    assert result.id == execution.id
    assert execution.status == DashboardReportExecution.Status.FAILED
    assert execution.started_at is not None
    assert execution.finished_at is not None
    assert execution.failure_stage == "permission_check"
    assert later_steps == []


def test_orchestrator_fails_when_snapshot_is_missing(
    execution,
    monkeypatch,
):
    set_dashboard_view_permission(monkeypatch, True)
    later_steps = []
    monkeypatch.setattr(
        RenderStep,
        "execute",
        lambda current, snapshot: later_steps.append("render"),
    )
    monkeypatch.setattr(
        DeliveryStep,
        "execute",
        lambda current, snapshot: later_steps.append("delivery"),
    )
    execution.snapshot.delete()

    result = ExecutionOrchestrator.execute(execution.id)

    execution.refresh_from_db()
    assert result.id == execution.id
    assert execution.status == DashboardReportExecution.Status.FAILED
    assert execution.started_at is not None
    assert execution.finished_at is not None
    assert execution.failure_stage == "snapshot"
    assert later_steps == []
