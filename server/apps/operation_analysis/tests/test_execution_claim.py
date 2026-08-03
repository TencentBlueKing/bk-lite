from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.db import close_old_connections

from apps.operation_analysis.models.models import Dashboard, Directory
from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
    DashboardReportSubscription,
)
from apps.operation_analysis.services.execution_service import (
    DashboardReportExecutionService,
)


pytestmark = pytest.mark.django_db


@pytest.fixture
def pending_execution(authenticated_user):
    directory = Directory.objects.create(name="领取测试目录", groups=[1])
    dashboard = Dashboard.objects.create(
        name="领取测试仪表盘",
        directory=directory,
        groups=[1],
        created_by=authenticated_user.username,
    )
    subscription = DashboardReportSubscription.objects.create(
        dashboard=dashboard,
        creator=authenticated_user.username,
        name="领取测试订阅",
        recipient_email="ops@example.com",
    )
    return DashboardReportExecution.objects.create(
        subscription=subscription,
        dashboard=dashboard,
        creator=authenticated_user.username,
    )


def test_pending_execution_can_be_claimed(pending_execution):
    claimed = DashboardReportExecutionService.claim_execution(
        pending_execution.id
    )

    pending_execution.refresh_from_db()
    assert claimed is True
    assert pending_execution.status == DashboardReportExecution.Status.RUNNING
    assert pending_execution.started_at is not None


def test_execution_cannot_be_claimed_twice(pending_execution):
    first_claim = DashboardReportExecutionService.claim_execution(
        pending_execution.id
    )
    second_claim = DashboardReportExecutionService.claim_execution(
        pending_execution.id
    )

    assert first_claim is True
    assert second_claim is False


def test_missing_execution_cannot_be_claimed():
    assert DashboardReportExecutionService.claim_execution(-1) is False


@pytest.mark.parametrize(
    "status",
    [
        DashboardReportExecution.Status.RUNNING,
        DashboardReportExecution.Status.SUCCEEDED,
        DashboardReportExecution.Status.FAILED,
        DashboardReportExecution.Status.UNKNOWN,
    ],
)
def test_non_pending_execution_cannot_be_claimed(pending_execution, status):
    DashboardReportExecution.objects.filter(pk=pending_execution.id).update(
        status=status
    )

    claimed = DashboardReportExecutionService.claim_execution(
        pending_execution.id
    )

    assert claimed is False


@pytest.mark.django_db(transaction=True)
def test_concurrent_claim_allows_only_one_worker(pending_execution):
    ready = Barrier(2, timeout=5)

    def claim():
        close_old_connections()
        ready.wait()
        try:
            return DashboardReportExecutionService.claim_execution(
                pending_execution.id
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: claim(), range(2)))

    pending_execution.refresh_from_db()
    assert sorted(results) == [False, True]
    assert pending_execution.status == DashboardReportExecution.Status.RUNNING
