from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import MagicMock

import pytest
from django.db import close_old_connections
from rest_framework.exceptions import ValidationError as DRFValidationError

from apps.operation_analysis.models.models import Dashboard, Directory
from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
    DashboardReportSubscription,
)
from apps.operation_analysis.services.execution_service import (
    DashboardReportExecutionService,
)
from apps.system_mgmt.models import Channel


pytestmark = pytest.mark.django_db


@pytest.fixture
def subscription(authenticated_user):
    directory = Directory.objects.create(name="幂等测试目录", groups=[1])
    dashboard = Dashboard.objects.create(
        name="幂等测试仪表盘",
        directory=directory,
        groups=[1],
        created_by=authenticated_user.username,
    )
    channel = Channel.objects.create(
        name="幂等邮件通道",
        channel_type="email",
        config={},
        description="测试",
        team=[1],
    )
    return DashboardReportSubscription.objects.create(
        dashboard=dashboard,
        creator=authenticated_user.username,
        name="幂等测试订阅",
        recipient_email="ops@example.com",
        email_channel=channel,
    )


@pytest.fixture
def mock_request(authenticated_user):
    request = MagicMock()
    request.user = authenticated_user
    request.data = {}
    return request


@pytest.fixture(autouse=True)
def allow_view_and_skip_dispatch(monkeypatch):
    monkeypatch.setattr(
        "apps.operation_analysis.services.subscription_service."
        "DashboardSubscriptionService.require_canvas_view",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        DashboardReportExecutionService,
        "_dispatch_render",
        staticmethod(lambda execution_id: None),
    )


def test_same_request_id_returns_existing_execution(
    subscription, mock_request
):
    first, created_first = DashboardReportExecutionService.execute_manual(
        mock_request,
        subscription,
        request_id="same-req",
    )
    second, created_second = DashboardReportExecutionService.execute_manual(
        mock_request,
        subscription,
        request_id="same-req",
    )

    assert created_first is True
    assert created_second is False
    assert first.id == second.id
    assert (
        DashboardReportExecution.objects.filter(
            subscription=subscription
        ).count()
        == 1
    )


def test_in_flight_execution_rejects_different_request_id(
    subscription, mock_request
):
    first, created = DashboardReportExecutionService.execute_manual(
        mock_request,
        subscription,
        request_id="req-a",
    )
    assert created is True
    assert first.status == DashboardReportExecution.Status.PENDING

    with pytest.raises(DRFValidationError, match="进行中的报告执行"):
        DashboardReportExecutionService.execute_manual(
            mock_request,
            subscription,
            request_id="req-b",
        )

    assert (
        DashboardReportExecution.objects.filter(
            subscription=subscription
        ).count()
        == 1
    )


def test_finished_execution_allows_new_request_id(
    subscription, mock_request
):
    first, _ = DashboardReportExecutionService.execute_manual(
        mock_request,
        subscription,
        request_id="req-done",
    )
    DashboardReportExecutionService.claim_execution(first.id)
    first.refresh_from_db()
    DashboardReportExecutionService.transition(
        first,
        DashboardReportExecution.Status.SUCCEEDED,
    )

    second, created = DashboardReportExecutionService.execute_manual(
        mock_request,
        subscription,
        request_id="req-next",
    )

    assert created is True
    assert second.id != first.id
    assert (
        DashboardReportExecution.objects.filter(
            subscription=subscription
        ).count()
        == 2
    )


def test_missing_request_id_is_rejected(subscription, mock_request):
    with pytest.raises(DRFValidationError, match="request_id 必填"):
        DashboardReportExecutionService.execute_manual(
            mock_request,
            subscription,
            request_id="",
        )


@pytest.mark.django_db(transaction=True)
def test_concurrent_different_request_ids_allow_only_one(
    subscription, authenticated_user, monkeypatch
):
    monkeypatch.setattr(
        "apps.operation_analysis.services.subscription_service."
        "DashboardSubscriptionService.require_canvas_view",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        DashboardReportExecutionService,
        "_dispatch_render",
        staticmethod(lambda execution_id: None),
    )
    ready = Barrier(2, timeout=5)

    def run(request_id: str):
        close_old_connections()
        request = MagicMock()
        request.user = authenticated_user
        request.data = {"request_id": request_id}
        ready.wait()
        try:
            return DashboardReportExecutionService.execute_manual(
                request,
                subscription,
                request_id=request_id,
            )
        except DRFValidationError as exc:
            return exc
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(run, ["concurrent-a", "concurrent-b"])
        )

    successes = [
        item
        for item in results
        if isinstance(item, tuple) and item[1] is True
    ]
    rejections = [
        item for item in results if isinstance(item, DRFValidationError)
    ]
    assert len(successes) == 1
    assert len(rejections) == 1
    assert (
        DashboardReportExecution.objects.filter(
            subscription=subscription,
            status__in=[
                DashboardReportExecution.Status.PENDING,
                DashboardReportExecution.Status.RUNNING,
            ],
        ).count()
        == 1
    )


@pytest.mark.django_db(transaction=True)
def test_concurrent_same_request_id_creates_one_execution(
    subscription, authenticated_user, monkeypatch
):
    monkeypatch.setattr(
        "apps.operation_analysis.services.subscription_service."
        "DashboardSubscriptionService.require_canvas_view",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        DashboardReportExecutionService,
        "_dispatch_render",
        staticmethod(lambda execution_id: None),
    )
    ready = Barrier(2, timeout=5)

    def run(_):
        close_old_connections()
        request = MagicMock()
        request.user = authenticated_user
        ready.wait()
        try:
            execution, created = DashboardReportExecutionService.execute_manual(
                request,
                subscription,
                request_id="same-concurrent",
            )
            return execution.id, created
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(run, range(2)))

    execution_ids = {item[0] for item in results}
    created_flags = sorted(item[1] for item in results)
    assert len(execution_ids) == 1
    assert created_flags == [False, True]
    assert (
        DashboardReportExecution.objects.filter(
            subscription=subscription,
            request_id="same-concurrent",
        ).count()
        == 1
    )
