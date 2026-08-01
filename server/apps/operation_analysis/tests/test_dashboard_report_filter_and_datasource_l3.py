from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import MagicMock

import pytest
from django.db import OperationalError
from django.utils import timezone

from apps.operation_analysis.models.datasource_models import DataSourceAPIModel
from apps.operation_analysis.models.models import Dashboard, Directory
from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
    DashboardReportSubscription,
)
from apps.operation_analysis.services.execution_orchestrator import (
    PermissionStep,
)
from apps.operation_analysis.services.execution_service import (
    DashboardReportExecutionService,
)
from apps.operation_analysis.services.filter_snapshot import (
    VALUE_KIND_DYNAMIC_DATE_RANGE,
    VALUE_KIND_DYNAMIC_TIME_RANGE,
    VALUE_KIND_STATIC,
    normalize_applied_filter_values,
)
from apps.operation_analysis.services.filter_snapshot_resolver import (
    resolve_date_range,
    resolve_filter_snapshot,
)
from apps.system_mgmt.models import Channel


pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def grant_feature_permission(authenticated_user):
    authenticated_user.permission = {
        "ops-analysis": {"view-View", "data_source-View"},
    }
    return authenticated_user


@pytest.fixture(autouse=True)
def bind_current_team(api_client):
    api_client.cookies["current_team"] = "1"
    return api_client


@pytest.fixture
def email_channel(db):
    return Channel.objects.create(
        name="筛选邮件通道",
        channel_type="email",
        config={},
        description="测试",
        team=[1],
    )


@pytest.fixture
def dashboard(authenticated_user):
    directory = Directory.objects.create(name="筛选目录", groups=[1])
    return Dashboard.objects.create(
        name="筛选仪表盘",
        directory=directory,
        groups=[1],
        created_by=authenticated_user.username,
        filters=[
            {
                "id": "env",
                "key": "env",
                "name": "环境",
                "type": "string",
                "order": 1,
                "enabled": True,
            },
            {
                "id": "period",
                "key": "period",
                "name": "日期",
                "type": "dateRange",
                "order": 2,
                "enabled": True,
            },
            {
                "id": "window",
                "key": "window",
                "name": "时间窗",
                "type": "timeRange",
                "order": 3,
                "enabled": True,
            },
        ],
        view_sets=[],
    )


@pytest.fixture
def subscription_url():
    return "/api/v1/operation_analysis/api/dashboard_subscription/"


def grant_dashboard_view(monkeypatch, allowed=True):
    monkeypatch.setattr(
        "apps.operation_analysis.services.subscription_service."
        "DashboardSubscriptionService.can_view_dashboard",
        lambda request, dashboard: allowed,
    )


def grant_datasource_view(monkeypatch, allowed=True):
    outcome = "allowed" if allowed else "denied"
    monkeypatch.setattr(
        "apps.operation_analysis.services.subscription_service."
        "DashboardSubscriptionService.evaluate_datasource_for_create_scan",
        lambda request, datasource: outcome,
    )


# --- A4 normalize / resolve unit ---


def test_normalize_static_and_dynamic_kinds():
    snap = normalize_applied_filter_values(
        {
            "env": "prod",
            "period": {"rangeType": "last_7_days"},
            "window": {
                "start": "2026-01-01T00:00:00Z",
                "end": "2026-01-01T01:00:00Z",
                "selectValue": 60,
            },
            "custom_period": {
                "rangeType": "custom",
                "startDate": "2026-07-01",
                "endDate": "2026-07-07",
            },
        },
        dashboard_filters=None,
    )
    assert snap["entries"]["env"] == {
        "value_kind": VALUE_KIND_STATIC,
        "value": "prod",
    }
    assert snap["entries"]["period"] == {
        "value_kind": VALUE_KIND_DYNAMIC_DATE_RANGE,
        "date_range_type": "last_7_days",
    }
    assert snap["entries"]["window"] == {
        "value_kind": VALUE_KIND_DYNAMIC_TIME_RANGE,
        "time_range_select_minutes": 60,
    }
    assert snap["entries"]["custom_period"]["value_kind"] == VALUE_KIND_STATIC


def test_resolve_last_7_days_differs_by_scheduled_time():
    t1 = datetime(2026, 7, 10, 1, 0, tzinfo=dt_timezone.utc)
    t2 = datetime(2026, 7, 20, 1, 0, tzinfo=dt_timezone.utc)
    a = resolve_date_range(
        "last_7_days", reference_at=t1, timezone_name="Asia/Shanghai"
    )
    b = resolve_date_range(
        "last_7_days", reference_at=t2, timezone_name="Asia/Shanghai"
    )
    assert a != b
    assert a == ("2026-07-04", "2026-07-10")
    assert b == ("2026-07-14", "2026-07-20")


def test_resolve_dynamic_time_range_from_reference():
    reference = datetime(2026, 7, 10, 12, 0, tzinfo=dt_timezone.utc)
    semantics, values = resolve_filter_snapshot(
        {
            "filter_snapshot": {
                "version": 1,
                "captured_at": "2026-07-01T00:00:00Z",
                "entries": {
                    "window": {
                        "value_kind": VALUE_KIND_DYNAMIC_TIME_RANGE,
                        "time_range_select_minutes": 30,
                    }
                },
            }
        },
        reference_at=reference,
        timezone_name="Asia/Shanghai",
    )
    assert "window" in semantics
    assert values["window"]["start"] == "2026-07-10T11:30:00Z"
    assert values["window"]["end"] == "2026-07-10T12:00:00Z"
    assert "selectValue" not in values["window"]


# --- A4 API / Execution ---


def test_create_persists_static_filter_snapshot_and_execution_values(
    api_client,
    authenticated_user,
    dashboard,
    subscription_url,
    email_channel,
    monkeypatch,
):
    grant_dashboard_view(monkeypatch)
    grant_datasource_view(monkeypatch)
    monkeypatch.setattr(
        DashboardReportExecutionService,
        "_dispatch_render",
        MagicMock(),
    )

    created = api_client.post(
        subscription_url,
        {
            "dashboard": dashboard.id,
            "name": "静态筛选",
            "recipient_email": "ops@example.com",
            "email_channel": email_channel.id,
            "applied_filter_values": {"env": "production"},
        },
        format="json",
    )
    assert created.status_code == 201
    snap = created.data["config"]["filter_snapshot"]
    assert snap["entries"]["env"] == {
        "value_kind": "static",
        "value": "production",
    }

    sub = DashboardReportSubscription.objects.get(pk=created.data["id"])
    request = MagicMock()
    request.user = authenticated_user
    request.data = {"request_id": "static-1"}
    execution, _ = DashboardReportExecutionService.execute_manual(
        request,
        sub,
    )
    execution.refresh_from_db()
    assert execution.status == "pending"
    assert execution.snapshot.filter_values == {"env": "production"}
    assert execution.snapshot.filter_semantics["env"]["value_kind"] == "static"


def test_scheduled_dynamic_date_resolves_against_scheduled_time(
    authenticated_user,
    dashboard,
    email_channel,
    monkeypatch,
):
    grant_datasource_view(monkeypatch)
    monkeypatch.setattr(
        DashboardReportExecutionService,
        "_dispatch_render",
        MagicMock(),
    )
    scheduled = datetime(2026, 7, 31, 1, 0, tzinfo=dt_timezone.utc)
    sub = DashboardReportSubscription.objects.create(
        dashboard=dashboard,
        creator=authenticated_user.username,
        name="动态日期",
        recipient_email="ops@example.com",
        email_channel=email_channel,
        schedule_type=DashboardReportSubscription.ScheduleType.DAILY,
        schedule_hour=9,
        schedule_minute=0,
        timezone="Asia/Shanghai",
        next_run_at=scheduled,
        version=1,
        config={
            "filter_snapshot": {
                "version": 1,
                "captured_at": "2026-07-01T00:00:00Z",
                "entries": {
                    "period": {
                        "value_kind": VALUE_KIND_DYNAMIC_DATE_RANGE,
                        "date_range_type": "last_7_days",
                    }
                },
            }
        },
    )
    result = DashboardReportExecutionService.create_scheduled(
        sub.id,
        now=scheduled,
    )
    assert result.created is True
    # Asia/Shanghai 2026-07-31 09:00
    assert result.execution.snapshot.filter_values["period"] == {
        "rangeType": "custom",
        "startDate": "2026-07-25",
        "endDate": "2026-07-31",
    }


def test_invalid_filter_snapshot_fails_execution_with_filter_invalid(
    authenticated_user,
    dashboard,
    email_channel,
    monkeypatch,
):
    monkeypatch.setattr(
        DashboardReportExecutionService,
        "_dispatch_render",
        MagicMock(),
    )
    due = timezone.now() - timedelta(minutes=1)
    sub = DashboardReportSubscription.objects.create(
        dashboard=dashboard,
        creator=authenticated_user.username,
        name="非法筛选",
        recipient_email="ops@example.com",
        email_channel=email_channel,
        schedule_type=DashboardReportSubscription.ScheduleType.DAILY,
        schedule_hour=9,
        schedule_minute=0,
        timezone="Asia/Shanghai",
        next_run_at=due,
        version=1,
        config={
            "filter_snapshot": {
                "version": 1,
                "captured_at": "2026-07-01T00:00:00Z",
                "entries": {
                    "period": {
                        "value_kind": VALUE_KIND_DYNAMIC_DATE_RANGE,
                        "date_range_type": "not_a_real_range",
                    }
                },
            }
        },
    )
    result = DashboardReportExecutionService.create_scheduled(
        sub.id,
        now=timezone.now(),
    )
    assert result.created is True
    execution = result.execution
    execution.refresh_from_db()
    assert execution.status == DashboardReportExecution.Status.FAILED
    assert execution.failure_stage == "snapshot"
    assert execution.error_code == "filter_invalid"


def test_update_filters_does_not_change_next_run_at(
    api_client,
    dashboard,
    subscription_url,
    email_channel,
    monkeypatch,
):
    grant_dashboard_view(monkeypatch)
    grant_datasource_view(monkeypatch)
    created = api_client.post(
        subscription_url,
        {
            "dashboard": dashboard.id,
            "name": "改筛选",
            "recipient_email": "ops@example.com",
            "email_channel": email_channel.id,
            "schedule_type": "daily",
            "schedule_hour": 9,
            "schedule_minute": 0,
            "timezone": "Asia/Shanghai",
            "applied_filter_values": {"env": "a"},
        },
        format="json",
    )
    assert created.status_code == 201
    original_next = created.data["next_run_at"]

    updated = api_client.patch(
        f"{subscription_url}{created.data['id']}/",
        {
            "applied_filter_values": {"env": "b"},
            "revision": created.data["revision"],
        },
        format="json",
    )
    assert updated.status_code == 200
    assert updated.data["next_run_at"] == original_next
    assert (
        updated.data["config"]["filter_snapshot"]["entries"]["env"]["value"]
        == "b"
    )


# --- A5 create-time DS scan ---


def _dashboard_with_datasource(authenticated_user, groups=None):
    directory = Directory.objects.create(name="DS目录", groups=[1])
    ds = DataSourceAPIModel.objects.create(
        name="被引用数据源",
        groups=groups if groups is not None else [1],
        rest_api="",
        source_type=DataSourceAPIModel.SOURCE_TYPE_REST_API,
    )
    dashboard = Dashboard.objects.create(
        name="含DS仪表盘",
        directory=directory,
        groups=[1],
        created_by=authenticated_user.username,
        filters=[],
        view_sets=[
            {
                "id": "w1",
                "itemType": "chart",
                "valueConfig": {"dataSource": ds.id},
            }
        ],
    )
    return dashboard, ds


def test_create_fails_without_datasource_view(
    api_client,
    authenticated_user,
    subscription_url,
    email_channel,
    monkeypatch,
):
    grant_dashboard_view(monkeypatch)
    dashboard, _ds = _dashboard_with_datasource(authenticated_user)
    authenticated_user.permission = {"ops-analysis": {"view-View"}}

    response = api_client.post(
        subscription_url,
        {
            "dashboard": dashboard.id,
            "name": "无DS权限",
            "recipient_email": "ops@example.com",
            "email_channel": email_channel.id,
        },
        format="json",
    )
    assert response.status_code == 403


def test_create_fails_when_datasource_missing(
    api_client,
    authenticated_user,
    subscription_url,
    email_channel,
    monkeypatch,
):
    grant_dashboard_view(monkeypatch)
    grant_datasource_view(monkeypatch)
    directory = Directory.objects.create(name="缺DS目录", groups=[1])
    dashboard = Dashboard.objects.create(
        name="引用已删DS",
        directory=directory,
        groups=[1],
        created_by=authenticated_user.username,
        view_sets=[
            {
                "id": "w1",
                "itemType": "chart",
                "valueConfig": {"dataSource": 999999},
            }
        ],
    )
    response = api_client.post(
        subscription_url,
        {
            "dashboard": dashboard.id,
            "name": "缺DS",
            "recipient_email": "ops@example.com",
            "email_channel": email_channel.id,
        },
        format="json",
    )
    assert response.status_code == 400


def test_create_succeeds_when_datasource_scan_has_transient_error(
    api_client,
    authenticated_user,
    subscription_url,
    email_channel,
    monkeypatch,
):
    grant_dashboard_view(monkeypatch)
    dashboard, _ds = _dashboard_with_datasource(authenticated_user)

    def boom(*args, **kwargs):
        raise OperationalError("simulated timeout")

    monkeypatch.setattr(
        DataSourceAPIModel.objects,
        "filter",
        boom,
    )
    response = api_client.post(
        subscription_url,
        {
            "dashboard": dashboard.id,
            "name": "瞬时失败可存",
            "recipient_email": "ops@example.com",
            "email_channel": email_channel.id,
        },
        format="json",
    )
    assert response.status_code == 201


def test_create_succeeds_when_permission_rule_rpc_times_out(
    api_client,
    authenticated_user,
    subscription_url,
    email_channel,
    monkeypatch,
):
    grant_dashboard_view(monkeypatch)
    dashboard, _ds = _dashboard_with_datasource(authenticated_user)
    authenticated_user.permission = {
        "ops-analysis": {"view-View", "data_source-View"},
    }

    monkeypatch.setattr(
        "apps.core.utils.permission_cache.get_cached_permission_rules",
        lambda **kwargs: None,
    )

    class BoomClient:
        def get_user_rules_by_app(self, *args, **kwargs):
            raise TimeoutError("permission rules rpc timeout")

    monkeypatch.setattr(
        "apps.core.utils.permission_utils.set_rules_module_params",
        lambda *args, **kwargs: (
            "ops-analysis",
            "",
            BoomClient(),
            "datasource",
        ),
    )

    response = api_client.post(
        subscription_url,
        {
            "dashboard": dashboard.id,
            "name": "RPC瞬时可存",
            "recipient_email": "ops@example.com",
            "email_channel": email_channel.id,
        },
        format="json",
    )
    assert response.status_code == 201


def test_resume_active_rechecks_datasource_permission(
    api_client,
    authenticated_user,
    subscription_url,
    email_channel,
    monkeypatch,
):
    grant_dashboard_view(monkeypatch)
    dashboard, _ds = _dashboard_with_datasource(authenticated_user)
    grant_datasource_view(monkeypatch, allowed=True)

    created = api_client.post(
        subscription_url,
        {
            "dashboard": dashboard.id,
            "name": "恢复扫描",
            "recipient_email": "ops@example.com",
            "email_channel": email_channel.id,
            "status": "paused",
        },
        format="json",
    )
    assert created.status_code == 201

    grant_datasource_view(monkeypatch, allowed=False)
    resume = api_client.patch(
        f"{subscription_url}{created.data['id']}/",
        {"status": "active", "revision": created.data["revision"]},
        format="json",
    )
    assert resume.status_code == 403


def test_permission_step_still_enforced_at_execution(
    authenticated_user,
    dashboard,
    email_channel,
    monkeypatch,
):
    sub = DashboardReportSubscription.objects.create(
        dashboard=dashboard,
        creator=authenticated_user.username,
        name="执行期权限",
        recipient_email="ops@example.com",
        email_channel=email_channel,
    )
    execution = DashboardReportExecution.objects.create(
        subscription=sub,
        dashboard=dashboard,
        creator=sub.creator,
        trigger_type=DashboardReportExecution.TriggerType.MANUAL_TEST,
        request_id="perm-step",
        status=DashboardReportExecution.Status.RUNNING,
    )
    monkeypatch.setattr(
        "apps.operation_analysis.views.view."
        "DashboardModelViewSet.get_has_permission",
        lambda *args, **kwargs: False,
    )
    result = PermissionStep.execute(execution)
    assert result.ok is False
    assert result.error_code == "dashboard_view_denied"
