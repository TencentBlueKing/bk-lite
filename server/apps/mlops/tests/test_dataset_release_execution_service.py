"""Dataset release execution ownership, lease, and fencing contracts."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Event
from unittest.mock import MagicMock

import pydantic.root_model  # noqa
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import close_old_connections, connections
from django.utils import timezone

from apps.mlops.constants import DatasetReleaseStatus
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


def _cleanup_cursor_model():
    from apps.mlops.models.dataset_release_execution import DatasetReleaseObjectCleanupCursor

    return DatasetReleaseObjectCleanupCursor


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
def test_expired_owner_cannot_register_object_or_write_terminal_state(monkeypatch):
    monkeypatch.setenv("MLOPS_DATASET_RELEASE_EXECUTION_MODE", "enforce")
    release = _make_release()
    base_mod.claim_dataset_release(AnomalyDetectionDatasetRelease, release.id, "owner-expired")
    _execution_model().objects.filter(release_id=release.id).update(lease_expires_at=timezone.now() - timedelta(seconds=1))

    assert not base_mod.record_dataset_release_object_path(
        AnomalyDetectionDatasetRelease,
        release.id,
        "owner-expired",
        "datasets/expired.zip",
    )
    assert not base_mod.finalize_dataset_release(
        AnomalyDetectionDatasetRelease,
        release.id,
        "owner-expired",
        file_size=20,
        metadata={"owner": "expired"},
        saved_path="datasets/expired.zip",
    )
    assert not base_mod.mark_release_as_failed(
        AnomalyDetectionDatasetRelease,
        release.id,
        "expired failure",
        owner_token="owner-expired",
    )
    release.refresh_from_db()
    assert release.status == DatasetReleaseStatus.PROCESSING
    assert release.metadata == {}


@pytest.mark.django_db
def test_object_intent_registration_renews_active_owner_lease(monkeypatch):
    monkeypatch.setenv("MLOPS_DATASET_RELEASE_EXECUTION_MODE", "enforce")
    release = _make_release()
    base_mod.claim_dataset_release(AnomalyDetectionDatasetRelease, release.id, "owner-current")
    _execution_model().objects.filter(release_id=release.id).update(lease_expires_at=timezone.now() + timedelta(seconds=1))

    assert base_mod.record_dataset_release_object_path(
        AnomalyDetectionDatasetRelease,
        release.id,
        "owner-current",
        "datasets/current.zip",
    )
    execution = _execution_model().objects.get(release_id=release.id)
    assert execution.lease_expires_at >= timezone.now() + timedelta(seconds=7260)


@pytest.mark.django_db
@pytest.mark.parametrize("terminal_action", ["success", "failure"])
def test_archived_release_fences_current_owner_terminal_write(monkeypatch, terminal_action):
    monkeypatch.setenv("MLOPS_DATASET_RELEASE_EXECUTION_MODE", "enforce")
    release = _make_release()
    base_mod.claim_dataset_release(AnomalyDetectionDatasetRelease, release.id, "owner-current")
    AnomalyDetectionDatasetRelease.objects.filter(id=release.id).update(status=DatasetReleaseStatus.ARCHIVED)

    if terminal_action == "success":
        updated = base_mod.finalize_dataset_release(
            AnomalyDetectionDatasetRelease,
            release.id,
            "owner-current",
            file_size=20,
            metadata={"owner": "current"},
            saved_path="current.zip",
        )
    else:
        updated = base_mod.mark_release_as_failed(
            AnomalyDetectionDatasetRelease,
            release.id,
            "late failure",
            owner_token="owner-current",
        )

    assert updated is False
    release.refresh_from_db()
    assert release.status == DatasetReleaseStatus.ARCHIVED
    assert release.metadata == {}


@pytest.mark.django_db
def test_archived_release_redelivery_is_not_claimed(monkeypatch):
    monkeypatch.setenv("MLOPS_DATASET_RELEASE_EXECUTION_MODE", "enforce")
    release = _make_release(status=DatasetReleaseStatus.ARCHIVED)

    claim = base_mod.claim_dataset_release(AnomalyDetectionDatasetRelease, release.id, "owner-current")

    assert claim.acquired is False
    assert claim.reason == "Task already archived"
    assert not _execution_model().objects.filter(release_id=release.id).exists()


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
def test_upload_preflight_removes_execution_when_release_was_deleted(monkeypatch):
    monkeypatch.setenv("MLOPS_DATASET_RELEASE_EXECUTION_MODE", "enforce")
    release = _make_release()
    release_id = release.id
    base_mod.claim_dataset_release(AnomalyDetectionDatasetRelease, release_id, "owner-current")
    release.delete()

    assert not base_mod.record_dataset_release_object_path(
        AnomalyDetectionDatasetRelease,
        release_id,
        "owner-current",
        "datasets/deleted-release.zip",
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
            cleanup_owner_token="owner-current",
        )

    storage.delete.assert_called_once_with("attempt.zip")


@pytest.mark.django_db
def test_shadow_finalize_error_defers_recorded_attempt_cleanup(monkeypatch):
    storage = MagicMock()
    _cleanup_model().objects.create(
        release_type=AnomalyDetectionDatasetRelease._meta.label_lower,
        release_id=1,
        owner_token="shadow-attempt",
        object_path="shared.zip",
    )

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
            cleanup_owner_token="shadow-attempt",
        )

    storage.delete.assert_not_called()
    assert _cleanup_model().objects.filter(owner_token="shadow-attempt", object_path="shared.zip").exists()


@pytest.mark.django_db
def test_shadow_upload_intent_is_persisted_with_a_cleanup_grace_lease(monkeypatch):
    monkeypatch.setenv("MLOPS_DATASET_RELEASE_EXECUTION_MODE", "shadow")
    release = _make_release(status=DatasetReleaseStatus.PROCESSING)

    assert base_mod.record_dataset_release_object_path(
        AnomalyDetectionDatasetRelease,
        release.id,
        "shadow-attempt",
        "datasets/shadow.zip",
    )

    intent = _cleanup_model().objects.get(release_id=release.id, owner_token="shadow-attempt")
    assert intent.cleanup_token == "shadow-attempt"
    assert intent.cleanup_lease_expires_at >= timezone.now() + timedelta(seconds=7260)


@pytest.mark.django_db
def test_shadow_persists_allocated_path_before_object_write(monkeypatch):
    monkeypatch.setenv("MLOPS_DATASET_RELEASE_EXECUTION_MODE", "shadow")
    release = _make_release(status=DatasetReleaseStatus.PROCESSING)
    storage = MagicMock()
    storage.get_available_name.return_value = "datasets/release_renamed.zip"

    def worker_lost_after_intent(saved_path, content):
        assert saved_path == "datasets/release_renamed.zip"
        assert (
            _cleanup_model()
            .objects.filter(
                release_id=release.id,
                owner_token="shadow-attempt",
                object_path=saved_path,
            )
            .exists()
        )
        raise SystemExit("worker lost")

    storage._save.side_effect = worker_lost_after_intent

    with pytest.raises(SystemExit, match="worker lost"):
        base_mod.save_dataset_release_object(
            storage,
            MagicMock(),
            "datasets/release.zip",
            AnomalyDetectionDatasetRelease,
            release.id,
            None,
            "shadow-attempt",
        )

    storage.get_available_name.assert_called_once_with("datasets/release.zip")


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
        cleanup_owner_token="owner-current",
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


@pytest.mark.django_db
def test_cleanup_command_rotates_skipped_intents_without_starving_later_rows(monkeypatch):
    release_type = AnomalyDetectionDatasetRelease._meta.label_lower
    active = _cleanup_model().objects.create(
        release_type=release_type,
        release_id=1001,
        owner_token="owner-active",
        object_path="datasets/active.zip",
    )
    orphan = _cleanup_model().objects.create(
        release_type=release_type,
        release_id=1002,
        owner_token="owner-orphan",
        object_path="datasets/orphan.zip",
    )
    _cleanup_model().objects.filter(id=active.id).update(updated_at=timezone.now() - timedelta(minutes=2))
    _cleanup_model().objects.filter(id=orphan.id).update(updated_at=timezone.now() - timedelta(minutes=1))
    _execution_model().objects.create(
        release_type=release_type,
        release_id=1001,
        owner_token="owner-active",
        lease_expires_at=timezone.now() + timedelta(minutes=5),
    )
    storage = MagicMock()
    monkeypatch.setattr(base_mod, "MinioBackend", lambda **kwargs: storage)

    call_command("cleanup_dataset_release_objects", limit=1)
    storage.delete.assert_not_called()
    assert _cleanup_cursor_model().objects.get(scope="global").last_intent_id == active.id
    call_command("cleanup_dataset_release_objects", limit=1)

    storage.delete.assert_called_once_with("datasets/orphan.zip")
    assert _cleanup_cursor_model().objects.get(scope="global").last_intent_id == orphan.id
    assert _cleanup_model().objects.filter(id=active.id).exists()
    assert not _cleanup_model().objects.filter(id=orphan.id).exists()

    call_command("cleanup_dataset_release_objects", limit=1)
    assert _cleanup_cursor_model().objects.get(scope="global").last_intent_id == active.id


@pytest.mark.django_db
def test_cleanup_command_dry_run_has_no_side_effect_and_limit_is_bounded(monkeypatch):
    intent = _cleanup_model().objects.create(
        release_type=AnomalyDetectionDatasetRelease._meta.label_lower,
        release_id=1003,
        owner_token="owner-dry-run",
        object_path="datasets/dry-run.zip",
    )
    storage_factory = MagicMock()
    monkeypatch.setattr(base_mod, "MinioBackend", storage_factory)

    call_command("cleanup_dataset_release_objects", dry_run=True)

    storage_factory.assert_not_called()
    assert _cleanup_model().objects.filter(id=intent.id).exists()
    assert not _cleanup_cursor_model().objects.exists()
    with pytest.raises(CommandError, match="--limit 必须在 1 到 1000 之间"):
        call_command("cleanup_dataset_release_objects", limit=1001)


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


@pytest.mark.django_db
def test_cleanup_never_deletes_an_object_still_referenced_by_release(monkeypatch):
    release = _make_release(status=DatasetReleaseStatus.FAILED)
    release.dataset_file.name = "datasets/referenced.zip"
    release.save(update_fields=["dataset_file"])
    _cleanup_model().objects.create(
        release_type=AnomalyDetectionDatasetRelease._meta.label_lower,
        release_id=release.id,
        owner_token="shadow-loser",
        object_path="datasets/referenced.zip",
        cleanup_token="shadow-loser",
        cleanup_lease_expires_at=timezone.now() - timedelta(seconds=1),
    )
    storage = MagicMock()
    monkeypatch.setattr(base_mod, "MinioBackend", lambda **kwargs: storage)

    call_command("cleanup_dataset_release_objects")

    storage.delete.assert_not_called()
    assert not _cleanup_model().objects.filter(release_id=release.id).exists()


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
