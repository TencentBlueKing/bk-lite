"""报表 CanvasReportAdapter：manifest、快照、删除终止。"""

import pytest

from apps.operation_analysis.models.models import Directory, Report
from apps.operation_analysis.services.canvas_report.registry import get_canvas_report_adapter
from apps.operation_analysis.services.canvas_report.types import RESOURCE_TYPE_REPORT
from apps.system_mgmt.models import Channel

pytestmark = pytest.mark.django_db


@pytest.fixture
def email_channel():
    return Channel.objects.create(
        name="Report Adapter 邮件通道",
        channel_type="email",
        config={},
        description="测试",
        team=[1],
    )


@pytest.fixture
def report():
    Directory.objects.create(name="Report Adapter 目录", groups=[1])
    return Report.objects.create(
        name="Report Adapter 报表",
        groups=[1],
        view_sets={
            "schema_version": 1,
            "filters": [{"id": "billing_period__dateRange", "key": "billing_period"}],
            "sections": [
                {
                    "id": "s1",
                    "valueConfig": {"chartType": "table", "dataSource": 3},
                },
                {
                    "id": "s2",
                    "valueConfig": {"chartType": "eventTable"},
                },
            ],
        },
        other={"theme": "light"},
    )


def test_report_adapter_is_registered():
    adapter = get_canvas_report_adapter(RESOURCE_TYPE_REPORT)
    assert adapter.resource_type == RESOURCE_TYPE_REPORT
    assert adapter.render_route_key() == "report"


@pytest.mark.django_db
def test_report_adapter_manifest_and_filters(report):
    adapter = get_canvas_report_adapter(RESOURCE_TYPE_REPORT)
    resource = adapter.load_resource(report.id)
    assert adapter.build_manifest(resource) == [
        {
            "widget_id": "s1",
            "widget_type": "table",
            "datasource_id": 3,
        },
        {
            "widget_id": "s2",
            "widget_type": "eventTable",
            "datasource_id": None,
        },
    ]
    assert adapter.load_filters(resource) == [{"id": "billing_period__dateRange", "key": "billing_period"}]


@pytest.mark.django_db
def test_report_adapter_render_snapshot_fields(report):
    adapter = get_canvas_report_adapter(RESOURCE_TYPE_REPORT)
    fields = adapter.build_render_snapshot_fields(adapter.load_resource(report.id))
    assert fields["dashboard_id"] is None
    assert fields["dashboard_name"] == report.name
    assert fields["resource_display_label"] == "报表"
    assert fields["view_sets"] is not report.view_sets
    assert fields["view_sets"]["schema_version"] == 1
    assert fields["filters"] == [{"id": "billing_period__dateRange", "key": "billing_period"}]


@pytest.mark.django_db
def test_report_delete_via_viewset_terminates_subscription(
    authenticated_user,
    email_channel,
    monkeypatch,
):
    from rest_framework.test import APIRequestFactory, force_authenticate

    from apps.operation_analysis.models.subscription_models import DashboardReportSubscription
    from apps.operation_analysis.views import view as view_module

    authenticated_user.is_superuser = True
    authenticated_user.permission = {
        "ops-analysis": {"view-View", "view-DeleteChart"},
    }
    authenticated_user.save()
    monkeypatch.setattr(
        view_module.ReportModelViewSet,
        "get_has_permission",
        lambda *args, **kwargs: True,
    )

    report = Report.objects.create(
        name="待删报表订阅",
        groups=[1],
        view_sets={"schema_version": 1, "filters": [], "sections": []},
    )
    sub = DashboardReportSubscription.objects.create(
        name="待终止报表",
        resource_type=RESOURCE_TYPE_REPORT,
        resource_id=report.id,
        dashboard=None,
        creator=authenticated_user.username,
        creator_domain=getattr(authenticated_user, "domain", "") or "",
        team_id=1,
        recipient_email="ops@example.com",
        email_channel=email_channel,
        status=DashboardReportSubscription.Status.ACTIVE,
    )

    factory = APIRequestFactory()
    request = factory.delete(f"/api/report/{report.id}/")
    force_authenticate(request, user=authenticated_user)
    request.COOKIES = {"current_team": "1"}
    response = view_module.ReportModelViewSet.as_view({"delete": "destroy"})(
        request,
        pk=str(report.id),
    )
    assert response.status_code in (200, 204)
    sub.refresh_from_db()
    assert sub.status == DashboardReportSubscription.Status.TERMINATED
    assert sub.termination_reason == "report_deleted"
    assert not Report.objects.filter(pk=report.id).exists()


def test_report_pdf_uses_dashboard_viewport_not_screen_fit():
    from apps.operation_analysis.services.dashboard_report_renderer import resolve_render_viewport

    assert resolve_render_viewport(resource_type="report") == {
        "width": 1440,
        "height": 900,
    }
    assert resolve_render_viewport(resource_type="dashboard") == {
        "width": 1440,
        "height": 900,
    }


@pytest.mark.django_db
def test_report_resource_state_and_execution_path(
    authenticated_user,
    email_channel,
    monkeypatch,
):
    from apps.operation_analysis.models.subscription_models import DashboardReportExecution, DashboardReportSubscription
    from apps.operation_analysis.services.execution_orchestrator import PermissionStep, SnapshotStep
    from apps.operation_analysis.services.render_snapshot_service import DashboardReportRenderSnapshotService
    from apps.operation_analysis.services.resource_state import observe_resource_state

    monkeypatch.setattr(
        "apps.operation_analysis.services.canvas_report.permissions." "can_view_canvas",
        lambda *args, **kwargs: True,
    )

    report = Report.objects.create(
        name="Report 执行路径报表",
        groups=[1],
        view_sets={
            "schema_version": 1,
            "filters": [],
            "sections": [],
        },
    )
    subscription = DashboardReportSubscription.objects.create(
        name="Report 执行订阅",
        resource_type=RESOURCE_TYPE_REPORT,
        resource_id=report.id,
        dashboard=None,
        creator=authenticated_user.username,
        creator_domain=getattr(authenticated_user, "domain", "") or "",
        team_id=1,
        recipient_email="ops@example.com",
        email_channel=email_channel,
        status=DashboardReportSubscription.Status.ACTIVE,
    )
    execution = DashboardReportExecution.objects.create(
        subscription=subscription,
        dashboard=None,
        resource_type=RESOURCE_TYPE_REPORT,
        resource_id=report.id,
        creator=subscription.creator,
        creator_domain=subscription.creator_domain,
        trigger_type=DashboardReportExecution.TriggerType.MANUAL_TEST,
        request_id="report-exec-1",
        status=DashboardReportExecution.Status.RUNNING,
    )
    from apps.operation_analysis.services.execution_service import DashboardReportExecutionService

    DashboardReportExecutionService._create_snapshot(
        execution,
        subscription,
        creator_timezone="Asia/Shanghai",
    )
    execution.refresh_from_db()
    assert execution.dashboard_id is None
    assert execution.snapshot.dashboard_id is None
    assert execution.snapshot.resource_type == RESOURCE_TYPE_REPORT
    assert execution.snapshot.resource_id == report.id

    assert observe_resource_state(execution).input_snapshot == "valid"

    perm = PermissionStep.execute(execution)
    assert perm.ok is True

    snap = SnapshotStep.execute(execution)
    assert snap.resource_id == report.id

    render_snapshot = DashboardReportRenderSnapshotService.create(execution)
    assert render_snapshot.dashboard_id is None
    assert render_snapshot.resource_type == RESOURCE_TYPE_REPORT
    assert render_snapshot.view_sets["schema_version"] == 1
    state = observe_resource_state(execution)
    assert state.input_snapshot == "valid"
    assert state.render_snapshot == "valid"


@pytest.mark.django_db
def test_report_create_subscription_http(
    api_client,
    authenticated_user,
    email_channel,
    monkeypatch,
):
    authenticated_user.permission = {"ops-analysis": {"view-View"}}
    api_client.cookies["current_team"] = "1"
    monkeypatch.setattr(
        "apps.operation_analysis.services.canvas_report.permissions." "can_view_canvas",
        lambda *args, **kwargs: True,
    )
    report = Report.objects.create(
        name="HTTP 报表订阅",
        groups=[1],
        view_sets={"schema_version": 1, "filters": [], "sections": []},
    )
    response = api_client.post(
        "/api/v1/operation_analysis/api/dashboard_subscription/",
        {
            "name": "报表订阅",
            "recipient_email": "ops@example.com",
            "email_channel": email_channel.id,
            "resource_type": "report",
            "resource_id": report.id,
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    assert response.data["resource_type"] == "report"
    assert response.data["dashboard"] is None
    assert response.data["resource_id"] == report.id


@pytest.mark.django_db
def test_report_render_input_http_returns_frozen_layout_and_scope(
    api_client,
    authenticated_user,
    email_channel,
    monkeypatch,
):
    from apps.operation_analysis.models.subscription_models import (
        DashboardReportExecution,
        DashboardReportExecutionSnapshot,
        DashboardReportRenderSnapshot,
        DashboardReportSubscription,
    )
    from apps.operation_analysis.services.render_token_service import DashboardReportRenderTokenService
    from apps.system_mgmt.models import User as SystemUser

    authenticated_user.permission = {
        "ops-analysis": {"view-View"},
    }
    api_client.cookies["current_team"] = "1"
    monkeypatch.setenv("SECRET_KEY", "report-render-input-test-secret")

    report = Report.objects.create(
        name="Render Input 报表",
        groups=[1],
        view_sets={
            "schema_version": 1,
            "filters": [{"id": "billing_period"}],
            "sections": [
                {
                    "id": "live-1",
                    "valueConfig": {"chartType": "table"},
                }
            ],
        },
    )
    subscription = DashboardReportSubscription.objects.create(
        name="Report render-input 订阅",
        resource_type=RESOURCE_TYPE_REPORT,
        resource_id=report.id,
        dashboard=None,
        creator=authenticated_user.username,
        creator_domain=getattr(authenticated_user, "domain", "") or "",
        team_id=1,
        recipient_email="ops@example.com",
        email_channel=email_channel,
        status=DashboardReportSubscription.Status.ACTIVE,
    )
    execution = DashboardReportExecution.objects.create(
        subscription=subscription,
        dashboard=None,
        resource_type=RESOURCE_TYPE_REPORT,
        resource_id=report.id,
        creator=subscription.creator,
        creator_domain=subscription.creator_domain,
        status=DashboardReportExecution.Status.RUNNING,
    )
    DashboardReportExecutionSnapshot.objects.create(
        execution=execution,
        dashboard_id=None,
        resource_type=RESOURCE_TYPE_REPORT,
        resource_id=report.id,
        resource_display_label="报表",
        creator_id=subscription.creator,
        creator_domain=subscription.creator_domain,
        subscription_id=subscription.id,
        subscription_name=subscription.name,
        recipient_email=subscription.recipient_email,
        trigger_type=execution.trigger_type,
        email_channel_id=subscription.email_channel_id,
        execution_team_id=subscription.team_id,
        subscription_revision=subscription.revision,
        filter_values={"billing_period": "2026-07"},
    )
    frozen_view_sets = {
        "schema_version": 1,
        "filters": [{"id": "billing_period"}],
        "sections": [{"id": "frozen-1", "valueConfig": {"chartType": "table"}}],
    }
    DashboardReportRenderSnapshot.objects.create(
        execution=execution,
        dashboard_id=None,
        dashboard_name="冻结报表名",
        dashboard_updated_at=report.updated_at,
        resource_type=RESOURCE_TYPE_REPORT,
        resource_id=report.id,
        resource_display_label="报表",
        view_sets=frozen_view_sets,
        filters=[{"id": "billing_period"}],
        other={},
        widget_manifest=[
            {
                "widget_id": "frozen-1",
                "widget_type": "table",
                "datasource_id": None,
            }
        ],
    )

    report.view_sets = {
        "schema_version": 1,
        "filters": [],
        "sections": [{"id": "live-changed", "valueConfig": {"chartType": "table"}}],
    }
    report.name = "已被篡改的实时名"
    report.save(update_fields=["view_sets", "name", "updated_at"])

    SystemUser.objects.get_or_create(
        username=authenticated_user.username,
        domain=authenticated_user.domain,
        defaults={
            "display_name": authenticated_user.username,
            "email": "report-render@example.com",
            "password": "unused",
            "group_list": authenticated_user.group_list,
        },
    )
    issued = DashboardReportRenderTokenService.issue(execution)
    session_user = DashboardReportRenderTokenService.consume(
        execution_id=execution.id,
        plaintext=issued.plaintext,
    )
    execution_url = "/api/v1/operation_analysis/api/dashboard_execution/"
    response = api_client.get(
        f"{execution_url}{execution.id}/render-input/",
        HTTP_AUTHORIZATION=f"Bearer {session_user['token']}",
    )
    assert response.status_code == 200, response.data
    assert response.data["execution_id"] == execution.id
    assert response.data["input_snapshot"]["resource_type"] == "report"
    assert response.data["input_snapshot"]["resource_id"] == report.id
    assert response.data["input_snapshot"]["dashboard_id"] is None
    render_snapshot = response.data["render_snapshot"]
    assert render_snapshot["resource_type"] == "report"
    assert render_snapshot["resource_id"] == report.id
    assert render_snapshot["dashboard_id"] is None
    assert render_snapshot["resource_display_label"] == "报表"
    assert render_snapshot["dashboard_name"] == "冻结报表名"
    assert render_snapshot["view_sets"] == frozen_view_sets
    assert render_snapshot["view_sets"]["sections"][0]["id"] == "frozen-1"
    assert "live-changed" not in str(render_snapshot["view_sets"])

    denied = api_client.get(f"{execution_url}{execution.id}/render-input/")
    assert denied.status_code == 403
