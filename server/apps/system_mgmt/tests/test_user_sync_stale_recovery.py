from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.system_mgmt.models import (
    IntegrationInstance,
    UserSyncRun,
    UserSyncRunStatusChoices,
    UserSyncSource,
)
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult
from apps.system_mgmt.services.user_sync_service import execute_user_sync


@pytest.fixture
def ready_user_sync_source(db):
    instance = IntegrationInstance.objects.create(
        name="stale-recovery-provider",
        provider_key="feishu",
        enabled=True,
        status="ready",
        capability_status={"user_sync": "ready"},
        config={"app_id": "cli_xxx", "app_secret": "plain-secret"},
    )
    return UserSyncSource.objects.create(
        name="stale-recovery-source",
        integration_instance=instance,
        enabled=True,
        root_group_name="Stale Recovery Root",
        business_config={"root_department_id": "0"},
        field_mapping={},
        schedule_config={},
    )


@pytest.mark.django_db
def test_execute_user_sync_releases_stale_running_run(monkeypatch, ready_user_sync_source):
    monkeypatch.setenv("USER_SYNC_STALE_TIMEOUT_SECONDS", "1800")
    stale_run = UserSyncRun.objects.create(
        source=ready_user_sync_source,
        status=UserSyncRunStatusChoices.RUNNING,
        started_at=timezone.now() - timedelta(hours=1),
    )
    provider_failure = CapabilityExecutionResult.failed_result(
        "provider unavailable",
        code="provider.request_failed",
        retryable=True,
    )

    with patch(
        "apps.system_mgmt.services.user_sync_service.RuntimeApplicationService.execute",
        return_value=provider_failure,
    ):
        result = execute_user_sync(ready_user_sync_source.id)

    stale_run.refresh_from_db()
    replacement_run = UserSyncRun.objects.exclude(id=stale_run.id).get(source=ready_user_sync_source)
    assert result["message"] == "provider unavailable"
    assert stale_run.status == UserSyncRunStatusChoices.FAILED
    assert stale_run.finished_at is not None
    assert "timed out" in stale_run.summary.lower()
    assert replacement_run.status == UserSyncRunStatusChoices.FAILED
    assert replacement_run.summary == "provider unavailable"


@pytest.mark.django_db
def test_execute_user_sync_keeps_fresh_running_run(monkeypatch, ready_user_sync_source):
    monkeypatch.setenv("USER_SYNC_STALE_TIMEOUT_SECONDS", "1800")
    fresh_run = UserSyncRun.objects.create(
        source=ready_user_sync_source,
        status=UserSyncRunStatusChoices.RUNNING,
        started_at=timezone.now() - timedelta(minutes=10),
    )

    with patch("apps.system_mgmt.services.user_sync_service.RuntimeApplicationService.execute") as mock_execute:
        result = execute_user_sync(ready_user_sync_source.id)

    fresh_run.refresh_from_db()
    assert result == {"result": False, "message": "User sync is already running"}
    assert fresh_run.status == UserSyncRunStatusChoices.RUNNING
    mock_execute.assert_not_called()


@pytest.mark.django_db
def test_execute_user_sync_does_not_apply_result_after_run_was_released(ready_user_sync_source):
    provider_result = CapabilityExecutionResult.success_result(
        "ok",
        payload={"group_list": [], "user_list": []},
    )

    def release_run_before_returning_result(**_kwargs):
        UserSyncRun.objects.filter(
            source=ready_user_sync_source,
            status=UserSyncRunStatusChoices.RUNNING,
        ).update(
            status=UserSyncRunStatusChoices.FAILED,
            summary="User sync timed out and was released automatically",
            finished_at=timezone.now(),
        )
        return provider_result

    with (
        patch(
            "apps.system_mgmt.services.user_sync_service.RuntimeApplicationService.execute",
            side_effect=release_run_before_returning_result,
        ),
        patch("apps.system_mgmt.services.user_sync_service._apply_user_sync_payload") as mock_apply,
    ):
        result = execute_user_sync(ready_user_sync_source.id)

    assert result == {
        "result": False,
        "message": "User sync run expired before applying provider result",
    }
    mock_apply.assert_not_called()
