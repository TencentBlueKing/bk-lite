"""Phase 3：Screen Adapter 与 PDF 策略常量。"""

import pytest

from apps.operation_analysis.models.models import Directory, Screen
from apps.operation_analysis.services.canvas_report.registry import (
    get_canvas_report_adapter,
)
from apps.operation_analysis.services.canvas_report.types import (
    RESOURCE_TYPE_SCREEN,
    SCREEN_PDF_FORMAT,
    SCREEN_PDF_LANDSCAPE,
    SCREEN_PDF_SINGLE_PAGE,
)
from apps.operation_analysis.services.dashboard_report_renderer import (
    resolve_render_viewport,
    resolve_screen_pdf_scale,
)
from apps.system_mgmt.models import Channel


pytestmark = pytest.mark.django_db


@pytest.fixture
def email_channel():
    return Channel.objects.create(
        name="Screen Adapter 邮件通道",
        channel_type="email",
        config={},
        description="测试",
        team=[1],
    )


@pytest.fixture
def screen():
    Directory.objects.create(name="Screen Adapter 目录", groups=[1])
    return Screen.objects.create(
        name="Screen Adapter 大屏",
        groups=[1],
        view_sets={
            "viewport": {"width": 1920, "height": 1080},
            "items": [
                {
                    "id": "s1",
                    "chartType": "gauge",
                    "valueConfig": {"chartType": "gauge", "dataSource": 3},
                },
                {
                    "id": "s2",
                    "title": "无 DS",
                    "chartType": "single",
                    "valueConfig": {"chartType": "single"},
                },
            ],
            "filters": [{"id": "env"}],
            "decorations": {"showTitle": True},
        },
        other={"theme": "dark"},
    )


def test_screen_adapter_is_registered():
    adapter = get_canvas_report_adapter(RESOURCE_TYPE_SCREEN)
    assert adapter.resource_type == RESOURCE_TYPE_SCREEN
    assert adapter.render_route_key() == "screen"


def test_screen_adapter_manifest_and_filters(screen):
    adapter = get_canvas_report_adapter(RESOURCE_TYPE_SCREEN)
    resource = adapter.load_resource(screen.id)
    assert adapter.build_manifest(resource) == [
        {
            "widget_id": "s1",
            "widget_type": "gauge",
            "datasource_id": 3,
        },
        {
            "widget_id": "s2",
            "widget_type": "single",
            "datasource_id": None,
        },
    ]
    assert adapter.load_filters(resource) == [{"id": "env"}]


def test_screen_adapter_render_snapshot_fields(screen):
    adapter = get_canvas_report_adapter(RESOURCE_TYPE_SCREEN)
    fields = adapter.build_render_snapshot_fields(adapter.load_resource(screen.id))
    assert fields["dashboard_id"] is None
    assert fields["dashboard_name"] == screen.name
    assert fields["resource_display_label"] == "大屏"
    assert fields["view_sets"]["viewport"]["width"] == 1920
    assert fields["view_sets"] is not screen.view_sets
    assert fields["filters"] == [{"id": "env"}]


def test_screen_pdf_strategy_constants():
    assert SCREEN_PDF_FORMAT == "A4"
    assert SCREEN_PDF_LANDSCAPE is True
    assert SCREEN_PDF_SINGLE_PAGE is True


def test_resolve_screen_viewport_and_scale():
    viewport = resolve_render_viewport(
        resource_type="screen",
        viewport_width=1920,
        viewport_height=1080,
    )
    assert viewport == {"width": 1920, "height": 1080}
    scale = resolve_screen_pdf_scale(1920, 1080)
    assert 0.1 <= scale <= 1.0
    dashboard_viewport = resolve_render_viewport(resource_type="dashboard")
    assert dashboard_viewport == {"width": 1440, "height": 900}


def test_screen_resource_state_and_execution_path(
    authenticated_user,
    email_channel,
    monkeypatch,
):
    """Screen 执行允许 dashboard=None，且 resource_state 视为 valid。"""
    from apps.operation_analysis.models.subscription_models import (
        DashboardReportExecution,
        DashboardReportSubscription,
    )
    from apps.operation_analysis.services.execution_orchestrator import (
        PermissionStep,
        SnapshotStep,
    )
    from apps.operation_analysis.services.render_snapshot_service import (
        DashboardReportRenderSnapshotService,
    )
    from apps.operation_analysis.services.resource_state import (
        observe_resource_state,
    )

    monkeypatch.setattr(
        "apps.operation_analysis.services.canvas_report.permissions."
        "can_view_canvas",
        lambda *args, **kwargs: True,
    )

    screen = Screen.objects.create(
        name="Screen 执行路径大屏",
        groups=[1],
        view_sets={
            "viewport": {"width": 1920, "height": 1080},
            "items": [],
            "filters": [],
        },
    )
    subscription = DashboardReportSubscription.objects.create(
        name="Screen 执行订阅",
        resource_type=RESOURCE_TYPE_SCREEN,
        resource_id=screen.id,
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
        resource_type=RESOURCE_TYPE_SCREEN,
        resource_id=screen.id,
        creator=subscription.creator,
        creator_domain=subscription.creator_domain,
        trigger_type=DashboardReportExecution.TriggerType.MANUAL_TEST,
        request_id="screen-exec-1",
        status=DashboardReportExecution.Status.RUNNING,
    )
    from apps.operation_analysis.services.execution_service import (
        DashboardReportExecutionService,
    )

    DashboardReportExecutionService._create_snapshot(
        execution,
        subscription,
        creator_timezone="Asia/Shanghai",
    )
    execution.refresh_from_db()
    assert execution.dashboard_id is None
    assert execution.snapshot.dashboard_id is None
    assert execution.snapshot.resource_type == RESOURCE_TYPE_SCREEN
    assert execution.snapshot.resource_id == screen.id

    assert observe_resource_state(execution).input_snapshot == "valid"

    perm = PermissionStep.execute(execution)
    assert perm.ok is True

    snap = SnapshotStep.execute(execution)
    assert snap.resource_id == screen.id

    render_snapshot = DashboardReportRenderSnapshotService.create(execution)
    assert render_snapshot.dashboard_id is None
    assert render_snapshot.resource_type == RESOURCE_TYPE_SCREEN
    assert render_snapshot.view_sets["viewport"] == {
        "width": 1920,
        "height": 1080,
    }
    state = observe_resource_state(execution)
    assert state.input_snapshot == "valid"
    assert state.render_snapshot == "valid"


def test_screen_delete_via_viewset_terminates_subscription(
    authenticated_user,
    email_channel,
    monkeypatch,
):
    from rest_framework.test import APIRequestFactory, force_authenticate

    from apps.operation_analysis.models.subscription_models import (
        DashboardReportSubscription,
    )
    from apps.operation_analysis.views import view as view_module

    authenticated_user.is_superuser = True
    authenticated_user.permission = {
        "ops-analysis": {"view-View", "view-DeleteChart"},
    }
    authenticated_user.save()
    monkeypatch.setattr(
        view_module.ScreenModelViewSet,
        "get_has_permission",
        lambda *args, **kwargs: True,
    )

    screen = Screen.objects.create(
        name="待删大屏订阅",
        groups=[1],
        view_sets={"viewport": {"width": 800, "height": 600}, "items": []},
    )
    sub = DashboardReportSubscription.objects.create(
        name="待终止",
        resource_type=RESOURCE_TYPE_SCREEN,
        resource_id=screen.id,
        dashboard=None,
        creator=authenticated_user.username,
        creator_domain=getattr(authenticated_user, "domain", "") or "",
        team_id=1,
        recipient_email="ops@example.com",
        email_channel=email_channel,
        status=DashboardReportSubscription.Status.ACTIVE,
    )

    factory = APIRequestFactory()
    request = factory.delete(f"/api/screen/{screen.id}/")
    force_authenticate(request, user=authenticated_user)
    # current_team cookie 供 Groups 过滤
    request.COOKIES = {"current_team": "1"}
    response = view_module.ScreenModelViewSet.as_view(
        {"delete": "destroy"}
    )(request, pk=str(screen.id))
    # CustomRenderer 可能把 204 改写为 200
    assert response.status_code in (200, 204)
    sub.refresh_from_db()
    assert sub.status == DashboardReportSubscription.Status.TERMINATED
    assert sub.termination_reason == "screen_deleted"
    assert not Screen.objects.filter(pk=screen.id).exists()


def test_screen_render_input_http_returns_frozen_viewport_and_scope(
    api_client,
    authenticated_user,
    email_channel,
    monkeypatch,
):
    """Phase 3：Screen render-input HTTP 合同（冻结 viewport + scope）。"""
    from apps.operation_analysis.models.subscription_models import (
        DashboardReportExecution,
        DashboardReportExecutionSnapshot,
        DashboardReportRenderSnapshot,
        DashboardReportSubscription,
    )
    from apps.operation_analysis.services.render_token_service import (
        DashboardReportRenderTokenService,
    )
    from apps.system_mgmt.models import User as SystemUser

    authenticated_user.permission = {
        "ops-analysis": {"view-View"},
    }
    api_client.cookies["current_team"] = "1"
    monkeypatch.setenv("SECRET_KEY", "screen-render-input-test-secret")

    screen = Screen.objects.create(
        name="Render Input 大屏",
        groups=[1],
        view_sets={
            "viewport": {"width": 1920, "height": 1080},
            "items": [
                {
                    "id": "live-1",
                    "chartType": "line",
                    "valueConfig": {"chartType": "line"},
                }
            ],
            "filters": [{"id": "env"}],
        },
    )
    subscription = DashboardReportSubscription.objects.create(
        name="Screen render-input 订阅",
        resource_type=RESOURCE_TYPE_SCREEN,
        resource_id=screen.id,
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
        resource_type=RESOURCE_TYPE_SCREEN,
        resource_id=screen.id,
        creator=subscription.creator,
        creator_domain=subscription.creator_domain,
        status=DashboardReportExecution.Status.RUNNING,
    )
    DashboardReportExecutionSnapshot.objects.create(
        execution=execution,
        dashboard_id=None,
        resource_type=RESOURCE_TYPE_SCREEN,
        resource_id=screen.id,
        resource_display_label="大屏",
        creator_id=subscription.creator,
        creator_domain=subscription.creator_domain,
        subscription_id=subscription.id,
        subscription_name=subscription.name,
        recipient_email=subscription.recipient_email,
        trigger_type=execution.trigger_type,
        email_channel_id=subscription.email_channel_id,
        execution_team_id=subscription.team_id,
        subscription_revision=subscription.revision,
        filter_values={"env": "prod"},
    )
    frozen_view_sets = {
        "viewport": {"width": 1600, "height": 900},
        "items": [{"id": "frozen-1", "chartType": "gauge"}],
        "filters": [{"id": "env"}],
        "decorations": {"showTitle": True},
    }
    DashboardReportRenderSnapshot.objects.create(
        execution=execution,
        dashboard_id=None,
        dashboard_name="冻结大屏名",
        dashboard_updated_at=screen.updated_at,
        resource_type=RESOURCE_TYPE_SCREEN,
        resource_id=screen.id,
        resource_display_label="大屏",
        view_sets=frozen_view_sets,
        filters=[{"id": "env"}],
        other={"theme": "dark"},
        widget_manifest=[
            {
                "widget_id": "frozen-1",
                "widget_type": "gauge",
                "datasource_id": None,
            }
        ],
    )

    # 篡改实时 Screen：render-input 不得读回 live layout
    screen.view_sets = {
        "viewport": {"width": 3840, "height": 2160},
        "items": [{"id": "live-changed"}],
        "filters": [],
    }
    screen.name = "已被篡改的实时名"
    screen.save(update_fields=["view_sets", "name", "updated_at"])

    SystemUser.objects.get_or_create(
        username=authenticated_user.username,
        domain=authenticated_user.domain,
        defaults={
            "display_name": authenticated_user.username,
            "email": "screen-render@example.com",
            "password": "unused",
            "group_list": authenticated_user.group_list,
        },
    )
    issued = DashboardReportRenderTokenService.issue(execution)
    session_user = DashboardReportRenderTokenService.consume(
        execution_id=execution.id,
        plaintext=issued.plaintext,
    )
    execution_url = (
        "/api/v1/operation_analysis/api/dashboard_execution/"
    )
    response = api_client.get(
        f"{execution_url}{execution.id}/render-input/",
        HTTP_AUTHORIZATION=f"Bearer {session_user['token']}",
    )
    assert response.status_code == 200, response.data
    assert response.data["execution_id"] == execution.id
    assert response.data["input_snapshot"]["resource_type"] == "screen"
    assert response.data["input_snapshot"]["resource_id"] == screen.id
    assert response.data["input_snapshot"]["dashboard_id"] is None
    render_snapshot = response.data["render_snapshot"]
    assert render_snapshot["resource_type"] == "screen"
    assert render_snapshot["resource_id"] == screen.id
    assert render_snapshot["dashboard_id"] is None
    assert render_snapshot["resource_display_label"] == "大屏"
    assert render_snapshot["dashboard_name"] == "冻结大屏名"
    assert render_snapshot["view_sets"] == frozen_view_sets
    assert render_snapshot["view_sets"]["viewport"] == {
        "width": 1600,
        "height": 900,
    }
    assert render_snapshot["view_sets"]["items"][0]["id"] == "frozen-1"
    assert "live-changed" not in str(render_snapshot["view_sets"])

    # 无 Render Session：scope 拒绝
    denied = api_client.get(f"{execution_url}{execution.id}/render-input/")
    assert denied.status_code == 403

    # 跨 Execution token 不可读本 execution
    other = DashboardReportExecution.objects.create(
        subscription=subscription,
        dashboard=None,
        resource_type=RESOURCE_TYPE_SCREEN,
        resource_id=screen.id,
        creator=subscription.creator,
        creator_domain=subscription.creator_domain,
        status=DashboardReportExecution.Status.RUNNING,
        request_id="screen-other-exec",
    )
    DashboardReportExecutionSnapshot.objects.create(
        execution=other,
        dashboard_id=None,
        resource_type=RESOURCE_TYPE_SCREEN,
        resource_id=screen.id,
        creator_id=subscription.creator,
        creator_domain=subscription.creator_domain,
        subscription_id=subscription.id,
        subscription_name=subscription.name,
        recipient_email=subscription.recipient_email,
        trigger_type=other.trigger_type,
        email_channel_id=subscription.email_channel_id,
        execution_team_id=subscription.team_id,
        subscription_revision=subscription.revision,
        filter_values={},
    )
    DashboardReportRenderSnapshot.objects.create(
        execution=other,
        dashboard_id=None,
        dashboard_name="other",
        dashboard_updated_at=screen.updated_at,
        resource_type=RESOURCE_TYPE_SCREEN,
        resource_id=screen.id,
        view_sets=frozen_view_sets,
        filters=[],
        other={},
        widget_manifest=[],
    )
    other_issued = DashboardReportRenderTokenService.issue(other)
    other_session = DashboardReportRenderTokenService.consume(
        execution_id=other.id,
        plaintext=other_issued.plaintext,
    )
    cross = api_client.get(
        f"{execution_url}{execution.id}/render-input/",
        HTTP_AUTHORIZATION=f"Bearer {other_session['token']}",
    )
    assert cross.status_code == 403


def _allow_screen_instance_permission(monkeypatch, *, allowed=True):
    monkeypatch.setattr(
        "apps.core.utils.viewset_utils.get_permission_rules",
        lambda *args, **kwargs: {
            "team": [1] if allowed else [],
            "instance": [],
            "all": False,
        },
    )


def test_screen_create_uses_real_instance_permission_chain(
    api_client,
    authenticated_user,
    email_channel,
    monkeypatch,
):
    """不 mock can_view_canvas：经 ScreenModelViewSet 实例权限创建。"""
    authenticated_user.permission = {"ops-analysis": {"view-View"}}
    authenticated_user.is_superuser = False
    api_client.cookies["current_team"] = "1"
    _allow_screen_instance_permission(monkeypatch, allowed=True)

    screen = Screen.objects.create(
        name="真实权限大屏-允许",
        groups=[1],
        view_sets={"viewport": {"width": 800, "height": 600}, "items": []},
    )
    response = api_client.post(
        "/api/v1/operation_analysis/api/dashboard_subscription/",
        {
            "name": "真实权限订阅",
            "recipient_email": "ops@example.com",
            "email_channel": email_channel.id,
            "resource_type": "screen",
            "resource_id": screen.id,
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    assert response.data["resource_type"] == "screen"
    assert response.data["dashboard"] is None


def test_screen_create_denied_by_real_instance_permission_chain(
    api_client,
    authenticated_user,
    email_channel,
    monkeypatch,
):
    authenticated_user.permission = {"ops-analysis": {"view-View"}}
    authenticated_user.is_superuser = False
    api_client.cookies["current_team"] = "1"
    _allow_screen_instance_permission(monkeypatch, allowed=False)

    screen = Screen.objects.create(
        name="真实权限大屏-拒绝",
        groups=[1],
        view_sets={"viewport": {"width": 800, "height": 600}, "items": []},
    )
    response = api_client.post(
        "/api/v1/operation_analysis/api/dashboard_subscription/",
        {
            "name": "拒绝订阅",
            "recipient_email": "ops@example.com",
            "email_channel": email_channel.id,
            "resource_type": "screen",
            "resource_id": screen.id,
        },
        format="json",
    )
    assert response.status_code == 403


def test_permission_step_uses_real_screen_instance_permission(
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
    from apps.operation_analysis.services.execution_orchestrator import (
        PermissionStep,
    )

    authenticated_user.is_superuser = False
    _allow_screen_instance_permission(monkeypatch, allowed=True)

    screen = Screen.objects.create(
        name="PermissionStep 大屏",
        groups=[1],
        view_sets={"viewport": {"width": 800, "height": 600}, "items": []},
    )
    sub = DashboardReportSubscription.objects.create(
        name="PermissionStep 订阅",
        resource_type=RESOURCE_TYPE_SCREEN,
        resource_id=screen.id,
        dashboard=None,
        creator=authenticated_user.username,
        creator_domain=getattr(authenticated_user, "domain", "") or "",
        team_id=1,
        recipient_email="ops@example.com",
        email_channel=email_channel,
        status=DashboardReportSubscription.Status.ACTIVE,
    )
    execution = DashboardReportExecution.objects.create(
        subscription=sub,
        dashboard=None,
        resource_type=RESOURCE_TYPE_SCREEN,
        resource_id=screen.id,
        creator=sub.creator,
        creator_domain=sub.creator_domain,
        status=DashboardReportExecution.Status.RUNNING,
    )
    DashboardReportExecutionSnapshot.objects.create(
        execution=execution,
        dashboard_id=None,
        resource_type=RESOURCE_TYPE_SCREEN,
        resource_id=screen.id,
        resource_display_label="大屏",
        creator_id=sub.creator,
        creator_domain=sub.creator_domain,
        subscription_id=sub.id,
        subscription_name=sub.name,
        recipient_email=sub.recipient_email,
        trigger_type=execution.trigger_type,
        email_channel_id=sub.email_channel_id,
        execution_team_id=sub.team_id,
        subscription_revision=sub.revision,
        filter_values={},
    )

    result = PermissionStep.execute(execution)
    assert result.ok is True

    _allow_screen_instance_permission(monkeypatch, allowed=False)
    denied = PermissionStep.execute(execution)
    assert denied.ok is False
    assert denied.error_code == "dashboard_view_denied"


def test_screen_delivery_contract_reuses_channel_boundary(
    authenticated_user,
    email_channel,
    tmp_path,
):
    from datetime import timedelta
    from unittest.mock import patch

    from django.utils import timezone

    from apps.operation_analysis.models.subscription_models import (
        DashboardReportExecution,
        DashboardReportExecutionSnapshot,
        DashboardReportPdfArtifact,
        DashboardReportRenderSnapshot,
        DashboardReportSubscription,
    )
    from apps.operation_analysis.services.delivery_service import (
        DashboardReportDeliveryError,
        DashboardReportDeliveryService,
    )
    from apps.operation_analysis.services.execution_service import (
        DashboardReportExecutionService,
    )
    from apps.system_mgmt.models import User as SystemUser

    SystemUser.objects.get_or_create(
        username=authenticated_user.username,
        domain=authenticated_user.domain,
        defaults={
            "display_name": authenticated_user.username,
            "email": "screen-delivery@example.com",
            "password": "unused",
            "group_list": [1],
        },
    )
    screen = Screen.objects.create(
        name="投递合同大屏",
        groups=[1],
        view_sets={"viewport": {"width": 800, "height": 600}, "items": []},
    )
    sub = DashboardReportSubscription.objects.create(
        name="Screen 投递订阅",
        resource_type=RESOURCE_TYPE_SCREEN,
        resource_id=screen.id,
        dashboard=None,
        creator=authenticated_user.username,
        creator_domain=authenticated_user.domain,
        team_id=1,
        recipient_email="recipient@example.com",
        email_channel=email_channel,
    )
    execution = DashboardReportExecution.objects.create(
        subscription=sub,
        dashboard=None,
        resource_type=RESOURCE_TYPE_SCREEN,
        resource_id=screen.id,
        creator=sub.creator,
        creator_domain=sub.creator_domain,
    )
    snapshot = DashboardReportExecutionSnapshot.objects.create(
        execution=execution,
        dashboard_id=None,
        resource_type=RESOURCE_TYPE_SCREEN,
        resource_id=screen.id,
        resource_display_label="大屏",
        creator_id=sub.creator,
        creator_domain=sub.creator_domain,
        execution_team_id=sub.team_id,
        creator_timezone="Asia/Shanghai",
        subscription_id=sub.id,
        subscription_name=sub.name,
        recipient_email=sub.recipient_email,
        trigger_type=execution.trigger_type,
        email_channel_id=email_channel.id,
        filter_values={},
    )
    assert DashboardReportExecutionService.claim_execution(execution.id)
    execution.refresh_from_db()
    DashboardReportRenderSnapshot.objects.create(
        execution=execution,
        dashboard_id=None,
        dashboard_name="投递合同大屏",
        dashboard_updated_at=screen.updated_at,
        resource_type=RESOURCE_TYPE_SCREEN,
        resource_id=screen.id,
        resource_display_label="大屏",
        view_sets={"viewport": {"width": 800, "height": 600}, "items": []},
        filters=[],
        other={},
        widget_manifest=[],
    )
    DashboardReportPdfArtifact.objects.create(
        execution=execution,
        storage_reference=f"execution-{execution.id}/report.pdf",
        filename="screen_report.pdf",
        size_bytes=21,
        sha256="b" * 64,
        expires_at=timezone.now() + timedelta(hours=24),
    )

    html = DashboardReportDeliveryService._build_html(snapshot, execution)
    assert "大屏：投递合同大屏" in html
    assert "仪表盘：" not in html

    pdf_file = tmp_path / "screen_report.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 screen")
    email_channel.team = [999]
    email_channel.save(update_fields=["team"])
    with patch(
        "apps.operation_analysis.services.delivery_service."
        "DashboardReportRenderService.resolve_artifact_path",
        return_value=pdf_file,
    ):
        with pytest.raises(DashboardReportDeliveryError) as exc_info:
            DashboardReportDeliveryService.deliver(execution, snapshot)
    assert exc_info.value.error_code == "channel_team_denied"

