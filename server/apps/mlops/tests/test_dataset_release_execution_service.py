"""Dataset release execution ownership, lease, and fencing contracts."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Event
from unittest.mock import MagicMock

import pydantic.root_model  # noqa
import pytest
from django.core.management import call_command
from django.db import close_old_connections, connection, connections
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.mlops.models.anomaly_detection import AnomalyDetectionDataset, AnomalyDetectionDatasetRelease
from apps.mlops.tasks import base as base_mod

pytestmark = pytest.mark.unit


def _make_release(status="pending"):
    dataset = AnomalyDetectionDataset.objects.create(name="execution-dataset", description="", team=[1])
    return AnomalyDetectionDatasetRelease.objects.create(
        name="execution-release",
        description="",
        dataset=dataset,
        version="v1",
        dataset_file="",
        status=status,
        metadata={},
        file_size=0,
    )


def _execution_model():
    from apps.mlops.models.dataset_release_execution import DatasetReleaseExecution

    return DatasetReleaseExecution


def _cleanup_model():
    from apps.mlops.models.dataset_release_execution import DatasetReleaseObjectCleanup

    return DatasetReleaseObjectCleanup


@pytest.mark.django_db
def test_shadow_mode_preserves_processing_redelivery_without_execution_state(
    monkeypatch,
):
    monkeypatch.setenv("MLOPS_DATASET_RELEASE_EXECUTION_MODE", "shadow")
    release = _make_release(status="processing")

    assert hasattr(base_mod, "claim_dataset_release")
    claim = base_mod.claim_dataset_release(AnomalyDetectionDatasetRelease, release.id, "owner-shadow")

    assert claim.acquired is True
    assert claim.owner_token is None
    assert claim.release.status == "processing"
    assert not _execution_model().objects.exists()


@pytest.mark.django_db
def test_enforce_mode_retries_active_owner_and_reclaims_expired_lease(monkeypatch):
    monkeypatch.setenv("MLOPS_DATASET_RELEASE_EXECUTION_MODE", "enforce")
    release = _make_release()

    assert hasattr(base_mod, "claim_dataset_release")
    assert hasattr(base_mod, "DatasetReleaseBusy")
    first = base_mod.claim_dataset_release(AnomalyDetectionDatasetRelease, release.id, "owner-one")
    execution = _execution_model().objects.get()

    assert first.acquired is True
    assert first.owner_token == "owner-one"
    assert execution.owner_token == "owner-one"
    assert execution.attempt == 1
    assert execution.lease_expires_at >= timezone.now() + timedelta(seconds=7260)

    with pytest.raises(base_mod.DatasetReleaseBusy) as busy:
        base_mod.claim_dataset_release(AnomalyDetectionDatasetRelease, release.id, "owner-two")
    assert 1 <= busy.value.retry_after <= 300

    execution.lease_expires_at = timezone.now() - timedelta(seconds=1)
    execution.save(update_fields=["lease_expires_at"])
    second = base_mod.claim_dataset_release(AnomalyDetectionDatasetRelease, release.id, "owner-two")
    execution.refresh_from_db()

    assert second.acquired is True
    assert execution.owner_token == "owner-two"
    assert execution.attempt == 2


@pytest.mark.django_db
def test_enforce_mode_gives_legacy_processing_a_grace_lease(monkeypatch):
    monkeypatch.setenv("MLOPS_DATASET_RELEASE_EXECUTION_MODE", "enforce")
    release = _make_release(status="processing")

    assert hasattr(base_mod, "claim_dataset_release")
    assert hasattr(base_mod, "DatasetReleaseBusy")
    with pytest.raises(base_mod.DatasetReleaseBusy):
        base_mod.claim_dataset_release(AnomalyDetectionDatasetRelease, release.id, "owner-new")

    execution = _execution_model().objects.get()
    assert execution.owner_token == ""
    assert execution.attempt == 0
    assert execution.lease_expires_at >= timezone.now() + timedelta(seconds=7260)


@pytest.mark.django_db
def test_stale_owner_cannot_write_success_or_failure_after_takeover(monkeypatch):
    monkeypatch.setenv("MLOPS_DATASET_RELEASE_EXECUTION_MODE", "enforce")
    release = _make_release()

    assert hasattr(base_mod, "claim_dataset_release")
    assert hasattr(base_mod, "finalize_dataset_release")
    base_mod.claim_dataset_release(AnomalyDetectionDatasetRelease, release.id, "owner-old")
    execution = _execution_model().objects.get()
    execution.lease_expires_at = timezone.now() - timedelta(seconds=1)
    execution.save(update_fields=["lease_expires_at"])
    base_mod.claim_dataset_release(AnomalyDetectionDatasetRelease, release.id, "owner-current")

    assert (
        base_mod.finalize_dataset_release(
            AnomalyDetectionDatasetRelease,
            release.id,
            "owner-old",
            file_size=10,
            metadata={"owner": "old"},
            saved_path="old.zip",
        )
        is False
    )
    assert (
        base_mod.mark_release_as_failed(
            AnomalyDetectionDatasetRelease,
            release.id,
            "stale failure",
            owner_token="owner-old",
        )
        is False
    )
    release.refresh_from_db()
    assert release.status == "processing"
    assert release.metadata == {}

    assert (
        base_mod.finalize_dataset_release(
            AnomalyDetectionDatasetRelease,
            release.id,
            "owner-current",
            file_size=20,
            metadata={"owner": "current"},
            saved_path="current.zip",
        )
        is True
    )
    release.refresh_from_db()
    assert release.status == "published"
    assert release.metadata == {"owner": "current"}
    assert release.dataset_file.name == "current.zip"
    assert not _execution_model().objects.exists()


@pytest.mark.django_db
def test_rollback_to_shadow_does_not_unfence_stale_failure(monkeypatch):
    monkeypatch.setenv("MLOPS_DATASET_RELEASE_EXECUTION_MODE", "enforce")
    release = _make_release()
    base_mod.claim_dataset_release(AnomalyDetectionDatasetRelease, release.id, "owner-old")
    execution = _execution_model().objects.get()
    execution.lease_expires_at = timezone.now() - timedelta(seconds=1)
    execution.save(update_fields=["lease_expires_at"])
    base_mod.claim_dataset_release(AnomalyDetectionDatasetRelease, release.id, "owner-current")
    assert base_mod.finalize_dataset_release(
        AnomalyDetectionDatasetRelease,
        release.id,
        "owner-current",
        file_size=20,
        metadata={"owner": "current"},
        saved_path="current.zip",
    )

    monkeypatch.setenv("MLOPS_DATASET_RELEASE_EXECUTION_MODE", "shadow")
    assert (
        base_mod.mark_release_as_failed(
            AnomalyDetectionDatasetRelease,
            release.id,
            "stale failure after rollback",
            owner_token="owner-old",
        )
        is False
    )
    release.refresh_from_db()
    assert release.status == "published"
    assert release.metadata == {"owner": "current"}


@pytest.mark.django_db
def test_failure_cleanup_removes_orphan_execution_when_release_was_deleted(
    monkeypatch,
):
    monkeypatch.setenv("MLOPS_DATASET_RELEASE_EXECUTION_MODE", "enforce")
    release = _make_release()
    release_id = release.id
    base_mod.claim_dataset_release(AnomalyDetectionDatasetRelease, release_id, "owner-current")
    release.delete()

    assert (
        base_mod.mark_release_as_failed(
            AnomalyDetectionDatasetRelease,
            release_id,
            "release deleted",
            owner_token="owner-redelivery",
        )
        is False
    )
    assert not _execution_model().objects.filter(release_id=release_id).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("terminal_action", ["success", "failure"])
def test_shadow_terminal_write_revokes_enforce_owner(monkeypatch, terminal_action):
    monkeypatch.setenv("MLOPS_DATASET_RELEASE_EXECUTION_MODE", "enforce")
    release = _make_release()
    base_mod.claim_dataset_release(AnomalyDetectionDatasetRelease, release.id, "owner-enforce")
    monkeypatch.setenv("MLOPS_DATASET_RELEASE_EXECUTION_MODE", "shadow")

    if terminal_action == "success":
        assert base_mod.finalize_dataset_release(
            AnomalyDetectionDatasetRelease,
            release.id,
            None,
            file_size=20,
            metadata={"mode": "shadow"},
            saved_path="shadow.zip",
        )
    else:
        assert base_mod.mark_release_as_failed(
            AnomalyDetectionDatasetRelease,
            release.id,
            "shadow failure",
            owner_token=None,
        )

    assert not _execution_model().objects.filter(release_id=release.id).exists()


@pytest.mark.django_db
def test_post_upload_finalize_error_cleans_attempt_object(monkeypatch):
    assert hasattr(base_mod, "finalize_uploaded_dataset_release")
    storage = MagicMock()
    _cleanup_model().objects.create(
        release_type=AnomalyDetectionDatasetRelease._meta.label_lower,
        release_id=1,
        owner_token="owner-current",
        object_path="attempt.zip",
    )

    def boom(*args, **kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(base_mod, "finalize_dataset_release", boom)
    with pytest.raises(RuntimeError, match="database unavailable"):
        base_mod.finalize_uploaded_dataset_release(
            storage,
            "attempt.zip",
            AnomalyDetectionDatasetRelease,
            1,
            "owner-current",
            file_size=20,
            metadata={},
        )

    storage.delete.assert_called_once_with("attempt.zip")


def test_shadow_finalize_error_does_not_delete_shared_object(monkeypatch):
    storage = MagicMock()

    def boom(*args, **kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(base_mod, "finalize_dataset_release", boom)
    with pytest.raises(RuntimeError, match="database unavailable"):
        base_mod.finalize_uploaded_dataset_release(
            storage,
            "shared.zip",
            AnomalyDetectionDatasetRelease,
            1,
            None,
            file_size=20,
            metadata={},
        )

    storage.delete.assert_not_called()


@pytest.mark.django_db
def test_takeover_surfaces_persisted_object_cleanup_intent(monkeypatch):
    monkeypatch.setenv("MLOPS_DATASET_RELEASE_EXECUTION_MODE", "enforce")
    release = _make_release()
    base_mod.claim_dataset_release(AnomalyDetectionDatasetRelease, release.id, "owner-old")
    assert hasattr(base_mod, "record_dataset_release_object_path")
    assert base_mod.record_dataset_release_object_path(
        AnomalyDetectionDatasetRelease,
        release.id,
        "owner-old",
        "datasets/old-attempt.zip",
    )

    execution = _execution_model().objects.get()
    execution.lease_expires_at = timezone.now() - timedelta(seconds=1)
    execution.save(update_fields=["lease_expires_at"])
    claim = base_mod.claim_dataset_release(AnomalyDetectionDatasetRelease, release.id, "owner-new")

    assert claim.stale_object_path == "datasets/old-attempt.zip"
    assert _cleanup_model().objects.filter(object_path="datasets/old-attempt.zip").exists()
    storage = MagicMock()
    base_mod.cleanup_claim_stale_object(storage, claim)
    storage.delete.assert_called_once_with("datasets/old-attempt.zip")
    assert not _cleanup_model().objects.filter(object_path="datasets/old-attempt.zip").exists()


@pytest.mark.django_db
def test_owner_cleanup_intent_replaces_path_instead_of_indexing_long_path(monkeypatch):
    monkeypatch.setenv("MLOPS_DATASET_RELEASE_EXECUTION_MODE", "enforce")
    release = _make_release()
    base_mod.claim_dataset_release(AnomalyDetectionDatasetRelease, release.id, "owner-current")

    assert base_mod.record_dataset_release_object_path(
        AnomalyDetectionDatasetRelease,
        release.id,
        "owner-current",
        "datasets/first-attempt-path.zip",
    )
    assert base_mod.record_dataset_release_object_path(
        AnomalyDetectionDatasetRelease,
        release.id,
        "owner-current",
        "datasets/replaced-attempt-path.zip",
    )

    intents = _cleanup_model().objects.filter(release_id=release.id)
    assert intents.count() == 1
    assert intents.get().object_path == "datasets/replaced-attempt-path.zip"


@pytest.mark.django_db
def test_cleanup_failure_preserves_persistent_intent(monkeypatch):
    monkeypatch.setenv("MLOPS_DATASET_RELEASE_EXECUTION_MODE", "enforce")
    release = _make_release()
    base_mod.claim_dataset_release(AnomalyDetectionDatasetRelease, release.id, "owner-old")
    base_mod.record_dataset_release_object_path(
        AnomalyDetectionDatasetRelease,
        release.id,
        "owner-old",
        "datasets/retry-cleanup.zip",
    )
    execution = _execution_model().objects.get()
    execution.lease_expires_at = timezone.now() - timedelta(seconds=1)
    execution.save(update_fields=["lease_expires_at"])
    claim = base_mod.claim_dataset_release(AnomalyDetectionDatasetRelease, release.id, "owner-new")
    storage = MagicMock()
    storage.delete.side_effect = RuntimeError("minio unavailable")

    base_mod.cleanup_claim_stale_object(storage, claim)

    assert _cleanup_model().objects.filter(object_path="datasets/retry-cleanup.zip").exists()


@pytest.mark.django_db
def test_successful_finalize_retries_old_cleanup_intents(monkeypatch):
    monkeypatch.setenv("MLOPS_DATASET_RELEASE_EXECUTION_MODE", "enforce")
    release = _make_release()
    base_mod.claim_dataset_release(AnomalyDetectionDatasetRelease, release.id, "owner-current")
    _cleanup_model().objects.create(
        release_type=AnomalyDetectionDatasetRelease._meta.label_lower,
        release_id=release.id,
        owner_token="owner-old",
        object_path="datasets/old-orphan.zip",
    )
    base_mod.record_dataset_release_object_path(
        AnomalyDetectionDatasetRelease,
        release.id,
        "owner-current",
        "datasets/current.zip",
    )
    storage = MagicMock()

    assert base_mod.finalize_uploaded_dataset_release(
        storage,
        "datasets/current.zip",
        AnomalyDetectionDatasetRelease,
        release.id,
        "owner-current",
        file_size=20,
        metadata={},
    )

    storage.delete.assert_called_once_with("datasets/old-orphan.zip")
    assert not _cleanup_model().objects.filter(release_id=release.id).exists()


@pytest.mark.django_db
def test_cleanup_command_retries_orphans_and_retains_delete_failures(monkeypatch):
    release = _make_release(status="published")
    release_type = AnomalyDetectionDatasetRelease._meta.label_lower
    _cleanup_model().objects.create(
        release_type=release_type,
        release_id=release.id,
        owner_token="owner-cleaned",
        object_path="datasets/cleaned.zip",
    )
    _cleanup_model().objects.create(
        release_type=release_type,
        release_id=release.id + 1,
        owner_token="owner-retained",
        object_path="datasets/retained.zip",
    )
    _cleanup_model().objects.create(
        release_type=release_type,
        release_id=release.id + 2,
        owner_token="owner-active",
        object_path="datasets/active.zip",
    )
    _cleanup_model().objects.create(
        release_type=release_type,
        release_id=release.id + 3,
        owner_token="owner-expired",
        object_path="datasets/expired.zip",
    )
    _execution_model().objects.create(
        release_type=release_type,
        release_id=release.id + 2,
        owner_token="owner-active",
        lease_expires_at=timezone.now() + timedelta(minutes=5),
    )
    _execution_model().objects.create(
        release_type=release_type,
        release_id=release.id + 3,
        owner_token="owner-expired",
        lease_expires_at=timezone.now() - timedelta(seconds=1),
    )
    storage = MagicMock()
    storage.delete.side_effect = [
        None,
        RuntimeError("minio unavailable"),
        None,
    ]
    monkeypatch.setattr(base_mod, "MinioBackend", lambda **kwargs: storage)

    call_command("cleanup_dataset_release_objects")

    assert not _cleanup_model().objects.filter(object_path="datasets/cleaned.zip").exists()
    assert _cleanup_model().objects.filter(object_path="datasets/retained.zip").exists()
    assert _cleanup_model().objects.filter(object_path="datasets/active.zip").exists()
    assert not _cleanup_model().objects.filter(object_path="datasets/expired.zip").exists()


@pytest.mark.django_db(
    transaction=True,
    available_apps=["apps.base", "apps.core", "apps.mlops"],
)
def test_cleanup_sweep_cannot_delete_object_published_after_candidate_scan(monkeypatch):
    monkeypatch.setenv("MLOPS_DATASET_RELEASE_EXECUTION_MODE", "enforce")
    release = _make_release()
    base_mod.claim_dataset_release(
        AnomalyDetectionDatasetRelease,
        release.id,
        "owner-current",
    )
    base_mod.record_dataset_release_object_path(
        AnomalyDetectionDatasetRelease,
        release.id,
        "owner-current",
        "datasets/current.zip",
    )
    execution = _execution_model().objects.get(release_id=release.id)
    execution.lease_expires_at = timezone.now() - timedelta(seconds=1)
    execution.save(update_fields=["lease_expires_at"])

    candidate_scanned = Event()
    allow_cleanup = Event()
    storage = MagicMock()

    def storage_after_scan(**kwargs):
        candidate_scanned.set()
        assert allow_cleanup.wait(timeout=5)
        return storage

    monkeypatch.setattr(base_mod, "MinioBackend", storage_after_scan)

    def run_cleanup():
        close_old_connections()
        try:
            call_command("cleanup_dataset_release_objects")
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=1) as pool:
        cleanup_future = pool.submit(run_cleanup)
        assert candidate_scanned.wait(timeout=5)
        try:
            assert base_mod.finalize_dataset_release(
                AnomalyDetectionDatasetRelease,
                release.id,
                "owner-current",
                file_size=20,
                metadata={},
                saved_path="datasets/current.zip",
            )
        finally:
            allow_cleanup.set()
        cleanup_future.result(timeout=5)

    storage.delete.assert_not_called()
    release.refresh_from_db()
    assert release.status == "published"
    assert release.dataset_file.name == "datasets/current.zip"


@pytest.mark.django_db
def test_failed_owner_cleans_persisted_object_intent(monkeypatch):
    monkeypatch.setenv("MLOPS_DATASET_RELEASE_EXECUTION_MODE", "enforce")
    release = _make_release()
    base_mod.claim_dataset_release(AnomalyDetectionDatasetRelease, release.id, "owner-current")
    base_mod.record_dataset_release_object_path(
        AnomalyDetectionDatasetRelease,
        release.id,
        "owner-current",
        "datasets/failed-attempt.zip",
    )
    storage = MagicMock()
    monkeypatch.setattr(base_mod, "MinioBackend", lambda **kwargs: storage)

    assert base_mod.mark_release_as_failed(
        AnomalyDetectionDatasetRelease,
        release.id,
        "upload failed",
        owner_token="owner-current",
    )

    storage.delete.assert_called_once_with("datasets/failed-attempt.zip")
    assert not _cleanup_model().objects.filter(release_id=release.id).exists()


@pytest.mark.django_db
def test_terminal_cleanup_backend_error_does_not_change_terminal_status(monkeypatch):
    release = _make_release(status="published")
    _cleanup_model().objects.create(
        release_type=AnomalyDetectionDatasetRelease._meta.label_lower,
        release_id=release.id,
        owner_token="owner-old",
        object_path="datasets/terminal-orphan.zip",
    )
    claim = base_mod.claim_dataset_release(AnomalyDetectionDatasetRelease, release.id, "owner-redelivery")

    def unavailable(**kwargs):
        raise RuntimeError("minio unavailable")

    monkeypatch.setattr(base_mod, "MinioBackend", unavailable)
    assert base_mod.prepare_claim_storage(claim) is None
    release.refresh_from_db()
    assert release.status == "published"
    assert _cleanup_model().objects.filter(release_id=release.id).exists()


def test_storage_url_error_does_not_abort_completed_upload():
    assert hasattr(base_mod, "get_storage_display_url")
    storage = MagicMock()
    storage.url.side_effect = RuntimeError("url unavailable")

    assert base_mod.get_storage_display_url(storage, "attempt.zip") == "attempt.zip"


def test_invalid_mode_falls_back_to_shadow(monkeypatch):
    monkeypatch.setenv("MLOPS_DATASET_RELEASE_EXECUTION_MODE", "unexpected")

    assert hasattr(base_mod, "get_dataset_release_execution_mode")
    assert base_mod.get_dataset_release_execution_mode() == "shadow"


def test_enforce_object_name_is_attempt_unique_and_shadow_name_is_unchanged():
    assert hasattr(base_mod, "build_publish_object_name")

    assert base_mod.build_publish_object_name("release.zip", None) == "release.zip"
    assert base_mod.build_publish_object_name("release.zip", "abc123") == "release_abc123.zip"


@pytest.mark.django_db(
    transaction=True,
    available_apps=["apps.base", "apps.core", "apps.mlops"],
)
def test_two_database_connections_only_allow_one_pending_claim(monkeypatch):
    monkeypatch.setenv("MLOPS_DATASET_RELEASE_EXECUTION_MODE", "enforce")
    release = _make_release()
    barrier = Barrier(2)

    def compete(owner_token):
        close_old_connections()
        barrier.wait()
        try:
            claim = base_mod.claim_dataset_release(
                AnomalyDetectionDatasetRelease,
                release.id,
                owner_token,
            )
            return ("acquired", claim.owner_token)
        except base_mod.DatasetReleaseBusy:
            return ("busy", owner_token)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(compete, ["owner-a", "owner-b"]))

    assert sorted(result[0] for result in results) == ["acquired", "busy"]
    execution = _execution_model().objects.get(release_id=release.id)
    assert execution.owner_token in {"owner-a", "owner-b"}
    assert execution.attempt == 1


@pytest.mark.django_db
@pytest.mark.parametrize("terminal_action", ["success", "failure"])
def test_terminal_write_locks_release_before_execution(monkeypatch, terminal_action):
    """所有写路径保持同一锁顺序，避免接管与终态提交形成死锁。"""

    monkeypatch.setenv("MLOPS_DATASET_RELEASE_EXECUTION_MODE", "enforce")
    release = _make_release()
    base_mod.claim_dataset_release(AnomalyDetectionDatasetRelease, release.id, "owner-current")

    with CaptureQueriesContext(connection) as queries:
        if terminal_action == "success":
            base_mod.finalize_dataset_release(
                AnomalyDetectionDatasetRelease,
                release.id,
                "owner-current",
                file_size=20,
                metadata={"owner": "current"},
                saved_path="current.zip",
            )
        else:
            base_mod.mark_release_as_failed(
                AnomalyDetectionDatasetRelease,
                release.id,
                "current failure",
                owner_token="owner-current",
            )

    release_table = AnomalyDetectionDatasetRelease._meta.db_table
    execution_table = _execution_model()._meta.db_table
    locked_tables = []
    for query in queries:
        sql = query["sql"]
        if "FOR UPDATE" not in sql:
            continue
        if release_table in sql:
            locked_tables.append(release_table)
        elif execution_table in sql:
            locked_tables.append(execution_table)

    assert locked_tables[:2] == [release_table, execution_table]
