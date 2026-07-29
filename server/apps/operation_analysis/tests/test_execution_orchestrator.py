import pytest
from django.core.exceptions import ValidationError

from apps.operation_analysis.models.models import Dashboard, Directory
from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
    DashboardReportExecutionSnapshot,
    DashboardReportRenderSnapshot,
    DashboardReportSubscription,
)
from apps.operation_analysis.services.execution_orchestrator import (
    DeliveryStep,
    ExecutionOrchestrator,
    ExecutionStepResult,
    PermissionStep,
    RenderSnapshotStep,
    RenderStep,
    SnapshotStep,
)
from apps.operation_analysis.services.execution_service import (
    DashboardReportExecutionService,
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
    assert DashboardReportExecutionService.claim_execution(execution.id)
    execution.refresh_from_db()
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


def test_orchestrator_rejects_unclaimed_execution(execution):
    DashboardReportExecution.objects.filter(pk=execution.id).update(
        status=DashboardReportExecution.Status.PENDING,
        started_at=None,
    )

    with pytest.raises(
        ValidationError,
        match="Execution 必须先由 Worker 成功领取",
    ):
        ExecutionOrchestrator.execute(execution.id)

    execution.refresh_from_db()
    assert execution.status == DashboardReportExecution.Status.PENDING
    assert execution.started_at is None


def test_orchestrator_creates_render_snapshot_from_dashboard(
    execution,
    monkeypatch,
):
    execution.dashboard.view_sets = [
        {
            "id": "group",
            "itemType": "group",
            "subGridOpts": {
                "children": [
                    {
                        "id": "chart-widget",
                        "itemType": "widget",
                        "valueConfig": {
                            "chartType": "line",
                            "dataSource": 17,
                        },
                    }
                ]
            },
        },
        {
            "i": "legacy-static-widget",
            "valueConfig": {"chartType": "single"},
        },
        "invalid-layout-node",
    ]
    execution.dashboard.filters = [{"field": "environment"}]
    execution.dashboard.other = {"title": "运营总览"}
    execution.dashboard.save(
        update_fields=["view_sets", "filters", "other", "updated_at"]
    )
    set_dashboard_view_permission(monkeypatch, True)

    ExecutionOrchestrator.execute(execution.id)

    snapshot = DashboardReportRenderSnapshot.objects.get(
        execution=execution
    )
    assert snapshot.dashboard_id == execution.dashboard_id
    assert snapshot.dashboard_name == execution.dashboard.name
    assert snapshot.dashboard_updated_at == execution.dashboard.updated_at
    assert snapshot.view_sets == execution.dashboard.view_sets
    assert snapshot.filters == execution.dashboard.filters
    assert snapshot.other == execution.dashboard.other
    assert snapshot.widget_manifest == [
        {
            "widget_id": "chart-widget",
            "widget_type": "line",
            "datasource_id": 17,
        },
        {
            "widget_id": "legacy-static-widget",
            "widget_type": "single",
            "datasource_id": None,
        },
    ]


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
        RenderSnapshotStep,
        "execute",
        lambda current: (
            calls.append("render_snapshot"),
            current.snapshot,
        )[1],
    )
    monkeypatch.setattr(
        RenderStep,
        "execute",
        lambda current, snapshot, render_snapshot: (
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

    assert calls == [
        "permission",
        "snapshot",
        "render_snapshot",
        "render",
    ]


def test_orchestrator_does_not_succeed_before_delivery_is_implemented(
    execution,
    monkeypatch,
):
    set_dashboard_view_permission(monkeypatch, True)
    monkeypatch.setattr(
        RenderStep,
        "execute",
        lambda current, snapshot, render_snapshot: ExecutionStepResult.COMPLETED,
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
        lambda current, snapshot, render_snapshot: later_steps.append("render"),
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
        lambda current, snapshot, render_snapshot: later_steps.append("render"),
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


def test_render_snapshot_isolated_from_later_dashboard_changes(
    execution,
    monkeypatch,
):
    execution.dashboard.filters = [{"field": "environment"}]
    execution.dashboard.other = {"title": "原始标题"}
    execution.dashboard.save(
        update_fields=["filters", "other", "updated_at"]
    )
    set_dashboard_view_permission(monkeypatch, True)
    ExecutionOrchestrator.execute(execution.id)
    render_snapshot = execution.render_snapshot
    original_dashboard_updated_at = render_snapshot.dashboard_updated_at

    execution.dashboard.name = "修改后的仪表盘"
    execution.dashboard.filters = [{"field": "region"}]
    execution.dashboard.other = {"title": "修改后的标题"}
    execution.dashboard.save(
        update_fields=["name", "filters", "other", "updated_at"]
    )
    render_snapshot.refresh_from_db()

    assert render_snapshot.dashboard_name == "编排测试仪表盘"
    assert render_snapshot.dashboard_updated_at == original_dashboard_updated_at
    assert render_snapshot.filters == [{"field": "environment"}]
    assert render_snapshot.other == {"title": "原始标题"}


def test_render_snapshot_isolated_from_later_widget_changes(
    execution,
    monkeypatch,
):
    original_view_sets = [
        {
            "id": "table-widget",
            "itemType": "widget",
            "valueConfig": {
                "chartType": "table",
                "dataSource": 23,
            },
        }
    ]
    execution.dashboard.view_sets = original_view_sets
    execution.dashboard.save(update_fields=["view_sets", "updated_at"])
    set_dashboard_view_permission(monkeypatch, True)
    ExecutionOrchestrator.execute(execution.id)
    render_snapshot = execution.render_snapshot

    execution.dashboard.view_sets = [
        {
            "id": "changed-widget",
            "itemType": "widget",
            "valueConfig": {
                "chartType": "line",
                "dataSource": 99,
            },
        }
    ]
    execution.dashboard.save(update_fields=["view_sets", "updated_at"])
    render_snapshot.refresh_from_db()

    assert render_snapshot.view_sets == original_view_sets
    assert render_snapshot.widget_manifest == [
        {
            "widget_id": "table-widget",
            "widget_type": "table",
            "datasource_id": 23,
        }
    ]


def test_render_snapshot_cannot_be_updated(execution, monkeypatch):
    set_dashboard_view_permission(monkeypatch, True)
    ExecutionOrchestrator.execute(execution.id)
    render_snapshot = execution.render_snapshot

    render_snapshot.dashboard_name = "不允许修改"
    with pytest.raises(ValidationError, match="Render Snapshot 创建后不可修改"):
        render_snapshot.save()
    with pytest.raises(ValidationError, match="Render Snapshot 创建后不可修改"):
        DashboardReportRenderSnapshot.objects.filter(
            pk=render_snapshot.pk
        ).update(dashboard_name="不允许修改")
    with pytest.raises(ValidationError, match="Render Snapshot 创建后不可修改"):
        DashboardReportRenderSnapshot.objects.bulk_update(
            [render_snapshot],
            ["dashboard_name"],
        )


def test_render_snapshot_failure_marks_execution_failed(
    execution,
    monkeypatch,
):
    set_dashboard_view_permission(monkeypatch, True)
    monkeypatch.setattr(
        "apps.operation_analysis.services.execution_orchestrator."
        "DashboardReportRenderSnapshotService.create",
        lambda current: (_ for _ in ()).throw(RuntimeError("database error")),
    )
    render_calls = []
    monkeypatch.setattr(
        RenderStep,
        "execute",
        lambda current, snapshot, render_snapshot: render_calls.append("render"),
    )

    result = ExecutionOrchestrator.execute(execution.id)

    execution.refresh_from_db()
    assert result.id == execution.id
    assert execution.status == DashboardReportExecution.Status.FAILED
    assert execution.failure_stage == "render_snapshot"
    assert execution.error_message == "Render Snapshot 创建失败"
    assert render_calls == []
