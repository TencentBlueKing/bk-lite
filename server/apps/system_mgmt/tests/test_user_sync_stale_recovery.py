from datetime import timedelta
from threading import Event, Thread
from time import monotonic, sleep
from unittest.mock import patch

import pytest
from django.db import close_old_connections, connection, transaction
from django.db.utils import OperationalError
from django.utils import timezone

from apps.system_mgmt.models import (
    IntegrationInstance,
    UserSyncRun,
    UserSyncRunStatusChoices,
    UserSyncSource,
)
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult
from apps.system_mgmt.services.user_sync_service import (
    _lock_user_sync_source,
    _release_stale_user_sync_runs,
    _touch_running_user_sync_run,
    execute_user_sync,
)


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
    stale_timestamp = timezone.now() - timedelta(hours=1)
    UserSyncRun.objects.filter(pk=stale_run.pk).update(
        started_at=stale_timestamp,
        updated_at=stale_timestamp,
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
    assert result["message"] == "provider_fetch_failed"
    assert stale_run.status == UserSyncRunStatusChoices.FAILED
    assert stale_run.finished_at is not None
    assert "timed out" in stale_run.summary.lower()
    assert replacement_run.status == UserSyncRunStatusChoices.FAILED
    assert replacement_run.summary == "provider_fetch_failed"


@pytest.mark.django_db
def test_execute_user_sync_keeps_fresh_running_run(monkeypatch, ready_user_sync_source):
    monkeypatch.setenv("USER_SYNC_STALE_TIMEOUT_SECONDS", "1800")
    fresh_run = UserSyncRun.objects.create(
        source=ready_user_sync_source,
        status=UserSyncRunStatusChoices.RUNNING,
        started_at=timezone.now() - timedelta(hours=1),
    )
    UserSyncRun.objects.filter(pk=fresh_run.pk).update(
        started_at=timezone.now() - timedelta(hours=1),
        updated_at=timezone.now() - timedelta(minutes=10),
    )

    with patch("apps.system_mgmt.services.user_sync_service.RuntimeApplicationService.execute") as mock_execute:
        result = execute_user_sync(ready_user_sync_source.id)

    fresh_run.refresh_from_db()
    assert result == {"result": False, "message": "User sync is already running"}
    assert fresh_run.status == UserSyncRunStatusChoices.RUNNING
    mock_execute.assert_not_called()


@pytest.mark.django_db(transaction=True)
def test_execute_user_sync_heartbeats_during_blocking_provider_call(monkeypatch, ready_user_sync_source):
    monkeypatch.setenv("USER_SYNC_STALE_TIMEOUT_SECONDS", "60")
    provider_entered = Event()
    allow_provider_return = Event()
    thread_errors = []
    first_result = {}
    provider_failure = CapabilityExecutionResult.failed_result(
        "provider unavailable",
        code="provider.request_failed",
        retryable=True,
    )

    def blocking_provider(**_kwargs):
        provider_entered.set()
        if not allow_provider_return.wait(5):
            raise TimeoutError("test did not release provider")
        return provider_failure

    def run_first_sync():
        close_old_connections()
        try:
            first_result.update(execute_user_sync(ready_user_sync_source.id))
        except Exception as error:
            thread_errors.append(error)
        finally:
            close_old_connections()

    with (
        patch(
            "apps.system_mgmt.services.user_sync_service._get_user_sync_heartbeat_interval_seconds",
            return_value=0.02,
        ),
        patch(
            "apps.system_mgmt.services.user_sync_service.RuntimeApplicationService.execute",
            side_effect=blocking_provider,
        ) as mock_execute,
    ):
        sync_thread = Thread(target=run_first_sync)
        sync_thread.start()
        try:
            assert provider_entered.wait(5)
            running_run = UserSyncRun.objects.get(
                source=ready_user_sync_source,
                status=UserSyncRunStatusChoices.RUNNING,
            )
            stale_timestamp = timezone.now() - timedelta(minutes=2)
            UserSyncRun.objects.filter(pk=running_run.pk).update(updated_at=stale_timestamp)

            deadline = monotonic() + 5
            while monotonic() < deadline:
                running_run.refresh_from_db(fields=["updated_at"])
                if running_run.updated_at > timezone.now() - timedelta(seconds=60):
                    break
                sleep(0.02)
            else:
                pytest.fail("provider heartbeat did not refresh updated_at")

            second_result = execute_user_sync(ready_user_sync_source.id)
            assert second_result == {"result": False, "message": "User sync is already running"}
            assert mock_execute.call_count == 1
        finally:
            allow_provider_return.set()
            sync_thread.join(timeout=5)

    assert not sync_thread.is_alive()
    assert thread_errors == []
    assert first_result["message"] == "provider_fetch_failed"


@pytest.mark.django_db(transaction=True)
def test_stale_release_skips_actively_locked_run(monkeypatch, ready_user_sync_source):
    if not connection.features.has_select_for_update_skip_locked:
        pytest.skip("database does not support SELECT FOR UPDATE SKIP LOCKED")
    monkeypatch.setenv("USER_SYNC_STALE_TIMEOUT_SECONDS", "60")
    stale_timestamp = timezone.now() - timedelta(minutes=2)
    run = UserSyncRun.objects.create(
        source=ready_user_sync_source,
        status=UserSyncRunStatusChoices.RUNNING,
    )
    UserSyncRun.objects.filter(pk=run.pk).update(updated_at=stale_timestamp)
    run_locked = Event()
    allow_commit = Event()
    thread_errors = []

    def hold_active_stage_lock():
        close_old_connections()
        try:
            with transaction.atomic():
                _lock_user_sync_source(ready_user_sync_source.id)
                _touch_running_user_sync_run(run.id)
                run_locked.set()
                if not allow_commit.wait(5):
                    raise TimeoutError("test did not release active stage")
                _touch_running_user_sync_run(run.id)
        except Exception as error:
            thread_errors.append(error)
        finally:
            close_old_connections()

    stage_thread = Thread(target=hold_active_stage_lock)
    stage_thread.start()
    try:
        assert run_locked.wait(5)
        started_at = monotonic()
        assert _release_stale_user_sync_runs(ready_user_sync_source) == 0
        assert monotonic() - started_at < 2
    finally:
        allow_commit.set()
        stage_thread.join(timeout=5)

    assert not stage_thread.is_alive()
    assert thread_errors == []
    run.refresh_from_db()
    assert run.status == UserSyncRunStatusChoices.RUNNING
    assert run.updated_at > stale_timestamp


@pytest.mark.django_db(transaction=True)
def test_stale_release_without_skip_locked_waits_for_latest_heartbeat(monkeypatch, ready_user_sync_source):
    monkeypatch.setenv("USER_SYNC_STALE_TIMEOUT_SECONDS", "60")
    stale_timestamp = timezone.now() - timedelta(minutes=2)
    run = UserSyncRun.objects.create(
        source=ready_user_sync_source,
        status=UserSyncRunStatusChoices.RUNNING,
    )
    UserSyncRun.objects.filter(pk=run.pk).update(updated_at=stale_timestamp)
    stage_locked = Event()
    allow_commit = Event()
    release_result = {}
    thread_errors = []

    def hold_active_stage():
        close_old_connections()
        try:
            with transaction.atomic():
                _lock_user_sync_source(ready_user_sync_source.id)
                _touch_running_user_sync_run(run.id)
                stage_locked.set()
                if not allow_commit.wait(5):
                    raise TimeoutError("test did not release active stage")
                _touch_running_user_sync_run(run.id)
        except Exception as error:
            thread_errors.append(error)
        finally:
            close_old_connections()

    def release_stale_run():
        close_old_connections()
        try:
            release_result["count"] = _release_stale_user_sync_runs(ready_user_sync_source)
        except Exception as error:
            thread_errors.append(error)
        finally:
            close_old_connections()

    with patch(
        "apps.system_mgmt.services.user_sync_service._supports_user_sync_skip_locked",
        return_value=False,
    ):
        stage_thread = Thread(target=hold_active_stage)
        stage_thread.start()
        assert stage_locked.wait(5)
        release_thread = Thread(target=release_stale_run)
        release_thread.start()
        try:
            sleep(0.1)
            assert release_thread.is_alive()
        finally:
            allow_commit.set()
            stage_thread.join(timeout=5)
            release_thread.join(timeout=5)

    assert not stage_thread.is_alive()
    assert not release_thread.is_alive()
    assert thread_errors == []
    assert release_result == {"count": 0}
    run.refresh_from_db()
    assert run.status == UserSyncRunStatusChoices.RUNNING
    assert run.updated_at > stale_timestamp


@pytest.mark.django_db(transaction=True)
def test_stale_release_without_row_locks_rechecks_after_active_write(monkeypatch, ready_user_sync_source):
    monkeypatch.setenv("USER_SYNC_STALE_TIMEOUT_SECONDS", "60")
    stale_timestamp = timezone.now() - timedelta(minutes=2)
    run = UserSyncRun.objects.create(
        source=ready_user_sync_source,
        status=UserSyncRunStatusChoices.RUNNING,
    )
    UserSyncRun.objects.filter(pk=run.pk).update(updated_at=stale_timestamp)
    active_write_started = Event()
    allow_commit = Event()
    release_result = {}
    thread_errors = []

    def hold_active_write():
        close_old_connections()
        try:
            with transaction.atomic():
                _touch_running_user_sync_run(run.id)
                active_write_started.set()
                if not allow_commit.wait(5):
                    raise TimeoutError("test did not release active write")
                _touch_running_user_sync_run(run.id)
        except Exception as error:
            thread_errors.append(error)
        finally:
            close_old_connections()

    def release_stale_run():
        close_old_connections()
        try:
            release_result["count"] = _release_stale_user_sync_runs(ready_user_sync_source)
        except Exception as error:
            thread_errors.append(error)
        finally:
            close_old_connections()

    with patch(
        "apps.system_mgmt.services.user_sync_service._supports_user_sync_row_locks",
        return_value=False,
    ):
        stage_thread = Thread(target=hold_active_write)
        stage_thread.start()
        assert active_write_started.wait(5)
        release_thread = Thread(target=release_stale_run)
        release_thread.start()
        try:
            sleep(0.1)
            assert release_thread.is_alive()
        finally:
            allow_commit.set()
            stage_thread.join(timeout=5)
            release_thread.join(timeout=5)

    assert not stage_thread.is_alive()
    assert not release_thread.is_alive()
    assert thread_errors == []
    assert release_result == {"count": 0}
    run.refresh_from_db()
    assert run.status == UserSyncRunStatusChoices.RUNNING
    assert run.updated_at > stale_timestamp


@pytest.mark.django_db
def test_stale_release_without_row_locks_fails_closed_when_database_is_busy(ready_user_sync_source):
    with (
        patch(
            "apps.system_mgmt.services.user_sync_service._supports_user_sync_row_locks",
            return_value=False,
        ),
        patch.object(
            UserSyncRun.objects,
            "filter",
            side_effect=OperationalError("database is locked"),
        ),
    ):
        assert _release_stale_user_sync_runs(ready_user_sync_source) == 0


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


@pytest.mark.django_db
def test_execute_user_sync_stops_before_group_write_when_run_expires_after_provider_result(
    ready_user_sync_source,
):
    provider_result = CapabilityExecutionResult.success_result(
        "ok",
        payload={"group_list": [], "user_list": []},
    )

    def expire_after_fetch_progress(run_id, phase, **_kwargs):
        if phase == "fetch_directory":
            UserSyncRun.objects.filter(pk=run_id).update(
                status=UserSyncRunStatusChoices.FAILED,
                summary="User sync timed out and was released automatically",
                finished_at=timezone.now(),
            )

    with (
        patch(
            "apps.system_mgmt.services.user_sync_service.RuntimeApplicationService.execute",
            return_value=provider_result,
        ),
        patch(
            "apps.system_mgmt.services.user_sync_service._write_phase_progress",
            side_effect=expire_after_fetch_progress,
        ),
        patch("apps.system_mgmt.services.user_sync_service._get_or_create_root_group") as mock_create_root,
    ):
        result = execute_user_sync(ready_user_sync_source.id)

    assert result == {
        "result": False,
        "message": "User sync run expired before applying provider result",
    }
    mock_create_root.assert_not_called()
