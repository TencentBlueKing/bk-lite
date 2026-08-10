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
    ExecutionStepError,
    ExecutionStepResult,
    PermissionStep,
    RenderSnapshotStep,
    RenderStep,
    SnapshotStep,
)
from apps.operation_analysis.services.execution_service import (
    DashboardReportExecutionService,
)
from apps.operation_analysis.services.dashboard_report_renderer import (
    DashboardRenderError,
)
from apps.operation_analysis.services.report_render_service import (
    DashboardReportRenderService,
)
from apps.system_mgmt.models import Channel


pytestmark = pytest.mark.django_db


def set_dashboard_view_permission(monkeypatch, allowed):
    monkeypatch.setattr(
        "apps.operation_analysis.views.view."
        "DashboardModelViewSet.get_has_permission",
        lambda self, user, dashboard, team_id, **kwargs: allowed,
    )


def stub_render_and_delivery(monkeypatch):
    monkeypatch.setattr(
        RenderStep,
        "execute",
        lambda *args, **kwargs: ExecutionStepResult.COMPLETED,
    )
    monkeypatch.setattr(
        DeliveryStep,
        "execute",
        lambda *args, **kwargs: ExecutionStepResult.COMPLETED,
    )


@pytest.fixture
def email_channel():
    return Channel.objects.create(
        name="编排邮件通道",
        channel_type="email",
        config={},
        description="测试",
        team=[1],
    )


@pytest.fixture
def execution(authenticated_user, email_channel):
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
        email_channel=email_channel,
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
        subscription_name=subscription.name,
        recipient_email=subscription.recipient_email,
        trigger_type=execution.trigger_type,
        email_channel_id=email_channel.id,
        filter_values={"environment": "production"},
    )
    assert DashboardReportExecutionService.claim_execution(execution.id)
    execution.refresh_from_db()
    return execution


def test_orchestrator_marks_unavailable_renderer_failed(
    execution,
    monkeypatch,
):
    set_dashboard_view_permission(monkeypatch, True)

    def unavailable_renderer(
        cls,
        current,
        snapshot,
        render_snapshot,
    ):
        raise DashboardRenderError("Chromium 不可用")

    monkeypatch.setattr(
        DashboardReportRenderService,
        "render",
        classmethod(unavailable_renderer),
    )

    result = ExecutionOrchestrator.execute(execution.id)

    execution.refresh_from_db()
    assert result.id == execution.id
    assert execution.status == DashboardReportExecution.Status.FAILED
    assert execution.started_at is not None
    assert execution.finished_at is not None
    assert execution.failure_stage == "render"
    assert execution.error_message == "报告 PDF 生成失败"


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

    monkeypatch.setattr(
        RenderStep,
        "execute",
        lambda *args, **kwargs: ExecutionStepResult.COMPLETED,
    )
    monkeypatch.setattr(
        DeliveryStep,
        "execute",
        lambda *args, **kwargs: ExecutionStepResult.COMPLETED,
    )

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

    def render_snapshot_step(current):
        calls.append("render_snapshot")
        return DashboardReportRenderSnapshot.objects.create(
            execution=current,
            dashboard_id=current.dashboard_id,
            dashboard_name=current.dashboard.name,
            dashboard_updated_at=current.dashboard.updated_at,
            view_sets=[],
            filters=[],
            other={},
            widget_manifest=[],
        )

    monkeypatch.setattr(
        RenderSnapshotStep,
        "execute",
        render_snapshot_step,
    )
    monkeypatch.setattr(
        RenderStep,
        "execute",
        lambda current, snapshot, render_snapshot: (
            calls.append("render"),
            ExecutionStepResult.COMPLETED,
        )[1],
    )
    monkeypatch.setattr(
        DeliveryStep,
        "execute",
        lambda current, snapshot: (
            calls.append("delivery"),
            ExecutionStepResult.COMPLETED,
        )[1],
    )

    ExecutionOrchestrator.execute(execution.id)

    assert calls == [
        "permission",
        "snapshot",
        "render_snapshot",
        "render",
        "delivery",
    ]


def test_orchestrator_succeeds_only_after_delivery_success(
    execution,
    monkeypatch,
):
    set_dashboard_view_permission(monkeypatch, True)
    monkeypatch.setattr(
        RenderStep,
        "execute",
        lambda current, snapshot, render_snapshot: ExecutionStepResult.COMPLETED,
    )
    monkeypatch.setattr(
        DeliveryStep,
        "execute",
        lambda current, snapshot: ExecutionStepResult.COMPLETED,
    )

    result = ExecutionOrchestrator.execute(execution.id)

    execution.refresh_from_db()
    assert result.id == execution.id
    assert execution.status == DashboardReportExecution.Status.SUCCEEDED
    assert execution.finished_at is not None


def test_delivery_failure_marks_execution_email_failed(
    execution,
    monkeypatch,
):
    set_dashboard_view_permission(monkeypatch, True)
    monkeypatch.setattr(
        RenderStep,
        "execute",
        lambda current, snapshot, render_snapshot: ExecutionStepResult.COMPLETED,
    )

    def fail_delivery(current, snapshot):
        raise ExecutionStepError("email", "SMTP 失败")

    monkeypatch.setattr(DeliveryStep, "execute", fail_delivery)

    result = ExecutionOrchestrator.execute(execution.id)

    execution.refresh_from_db()
    assert result.id == execution.id
    assert execution.status == DashboardReportExecution.Status.FAILED
    assert execution.failure_stage == "email"
    assert execution.error_message == "SMTP 失败"


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
    stub_render_and_delivery(monkeypatch)
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
    stub_render_and_delivery(monkeypatch)
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
    stub_render_and_delivery(monkeypatch)
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
    assert execution.error_code == ""
    assert execution.error_message == "Render Snapshot 创建失败"
    assert execution.attempt_count == 1
    assert render_calls == []


def test_render_snapshot_value_error_is_permanent_terminal(
    execution,
    monkeypatch,
):
    set_dashboard_view_permission(monkeypatch, True)
    monkeypatch.setattr(
        "apps.operation_analysis.services.execution_orchestrator."
        "DashboardReportRenderSnapshotService.create",
        lambda current: (_ for _ in ()).throw(ValueError("Dashboard 不存在")),
    )
    result = ExecutionOrchestrator.execute(execution.id)
    execution.refresh_from_db()
    assert result.status == DashboardReportExecution.Status.FAILED
    assert execution.error_code == "render_snapshot_create_permanent"
    assert execution.attempt_count == 1


def test_render_snapshot_operational_error_can_retry(
    execution,
    monkeypatch,
):
    from django.db import OperationalError

    set_dashboard_view_permission(monkeypatch, True)
    calls = {"n": 0}

    def flaky_create(current):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OperationalError("db busy")
        from apps.operation_analysis.models.subscription_models import (
            DashboardReportRenderSnapshot,
        )

        return DashboardReportRenderSnapshot.objects.create(
            execution=current,
            dashboard_id=current.dashboard_id,
            dashboard_name=current.dashboard.name,
            dashboard_updated_at=current.dashboard.updated_at,
            view_sets=[],
            filters=[],
            other={},
            widget_manifest=[],
        )

    monkeypatch.setattr(
        "apps.operation_analysis.services.execution_orchestrator."
        "DashboardReportRenderSnapshotService.create",
        flaky_create,
    )
    stub_render_and_delivery(monkeypatch)
    result = ExecutionOrchestrator.execute(execution.id)
    execution.refresh_from_db()
    assert result.status == DashboardReportExecution.Status.SUCCEEDED
    assert execution.attempt_count == 2
    assert calls["n"] == 2


def test_render_snapshot_keeps_datasource_identity_without_runtime_config(
    execution,
    monkeypatch,
):
    execution.dashboard.view_sets = [
        {
            "id": "widget-ds",
            "itemType": "widget",
            "valueConfig": {
                "chartType": "table",
                "dataSource": 42,
            },
        }
    ]
    execution.dashboard.save(update_fields=["view_sets", "updated_at"])
    set_dashboard_view_permission(monkeypatch, True)

    stub_render_and_delivery(monkeypatch)
    ExecutionOrchestrator.execute(execution.id)

    render_snapshot = DashboardReportRenderSnapshot.objects.get(
        execution=execution
    )
    assert render_snapshot.widget_manifest == [
        {
            "widget_id": "widget-ds",
            "widget_type": "table",
            "datasource_id": 42,
        }
    ]
    assert not hasattr(render_snapshot, "datasource_snapshots")


def test_widget_manifest_preserves_missing_datasource_reference(
    execution,
    monkeypatch,
):
    execution.dashboard.view_sets = [
        {
            "id": "widget-no-ds",
            "itemType": "widget",
            "valueConfig": {
                "chartType": "single",
            },
        },
        {
            "id": "widget-deleted-ds",
            "itemType": "widget",
            "valueConfig": {
                "chartType": "table",
                "dataSource": 99999,
            },
        },
    ]
    execution.dashboard.save(update_fields=["view_sets", "updated_at"])
    set_dashboard_view_permission(monkeypatch, True)

    stub_render_and_delivery(monkeypatch)
    ExecutionOrchestrator.execute(execution.id)

    render_snapshot = DashboardReportRenderSnapshot.objects.get(execution=execution)
    assert render_snapshot.widget_manifest == [
        {
            "widget_id": "widget-no-ds",
            "widget_type": "single",
            "datasource_id": None,
        },
        {
            "widget_id": "widget-deleted-ds",
            "widget_type": "table",
            "datasource_id": 99999,
        },
    ]
