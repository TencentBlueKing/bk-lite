import hashlib
import io
from datetime import timedelta

import pytest
from django.db import transaction
from django.utils.timezone import now

from apps.cmdb.models.config_file_version import ConfigFileContentStatus, ConfigFileVersion, ConfigFileVersionStatus
from apps.cmdb.services.config_file_content_lifecycle import ConfigFileContentLifecycle


class FakeStorage:
    def __init__(self):
        self.objects = {}
        self.saved_keys = []
        self.deleted_keys = []
        self.delete_error = None
        self.modified_at = {}

    def save(self, key, content):
        self.objects[key] = content.read()
        self.saved_keys.append(key)
        return key

    def open(self, key, _mode="rb"):
        return io.BytesIO(self.objects[key])

    def exists(self, key):
        return key in self.objects

    def delete(self, key):
        if self.delete_error:
            raise self.delete_error
        self.deleted_keys.append(key)
        self.objects.pop(key, None)

    def listdir(self, prefix):
        marker = prefix.rstrip("/") + "/"
        return [], [key[len(marker) :] for key in self.objects if key.startswith(marker) and "/" not in key[len(marker) :]]

    def get_modified_time(self, key):
        return self.modified_at[key]


@pytest.fixture
def fake_storage(monkeypatch):
    storage = FakeStorage()
    monkeypatch.setattr(ConfigFileContentLifecycle, "_storage", staticmethod(lambda: storage))
    return storage


def _create_version(**kw):
    defaults = {
        "instance_id": "inst-1",
        "model_id": "host",
        "version": "1700000000000",
        "file_path": "/etc/app.conf",
        "file_name": "app.conf",
        "content_hash": hashlib.sha256(b"v1").hexdigest(),
        "content": "host/inst-1/formal.txt",
        "temp_content_key": "tmp/config-file/staged.txt",
        "status": ConfigFileVersionStatus.SUCCESS,
        "content_status": ConfigFileContentStatus.PENDING,
    }
    defaults.update(kw)
    return ConfigFileVersion.objects.create(**defaults)


@pytest.mark.django_db
def test_publish_moves_staged_content_to_formal_key_idempotently(fake_storage):
    fake_storage.objects["tmp/config-file/staged.txt"] = b"v1"
    version_obj = _create_version()

    assert ConfigFileContentLifecycle.publish_version(version_obj.id) is True
    assert ConfigFileContentLifecycle.publish_version(version_obj.id) is True

    version_obj.refresh_from_db()
    assert version_obj.content_status == ConfigFileContentStatus.READY
    assert version_obj.temp_content_key == ""
    assert version_obj.content_error == ""
    assert version_obj.content_attempt_count == 1
    assert fake_storage.objects["host/inst-1/formal.txt"] == b"v1"
    assert "tmp/config-file/staged.txt" not in fake_storage.objects
    assert fake_storage.saved_keys == ["host/inst-1/formal.txt"]


@pytest.mark.django_db
def test_stage_and_discard_temp_content_are_idempotent(fake_storage):
    temp_key = ConfigFileContentLifecycle.stage_content("v1")

    assert temp_key.startswith("tmp/config-file/")
    assert fake_storage.objects[temp_key] == b"v1"

    ConfigFileContentLifecycle.discard_temp_content(temp_key)
    ConfigFileContentLifecycle.discard_temp_content("")
    ConfigFileContentLifecycle.discard_temp_content(temp_key)
    assert temp_key not in fake_storage.objects


@pytest.mark.django_db
def test_publish_handles_missing_ready_and_non_publishable_states(fake_storage):
    assert ConfigFileContentLifecycle.publish_version(999999) is False

    ready = _create_version(content_status=ConfigFileContentStatus.READY)
    deleting = _create_version(
        version="1700000000001",
        content_status=ConfigFileContentStatus.DELETE_PENDING,
    )

    assert ConfigFileContentLifecycle.publish_version(ready.id) is True
    assert ConfigFileContentLifecycle.publish_version(deleting.id) is False


@pytest.mark.django_db
def test_publish_accepts_matching_existing_formal_object(fake_storage):
    fake_storage.objects["tmp/config-file/staged.txt"] = b"v1"
    fake_storage.objects["host/inst-1/formal.txt"] = b"v1"
    version_obj = _create_version()

    assert ConfigFileContentLifecycle.publish_version(version_obj.id) is True

    version_obj.refresh_from_db()
    assert version_obj.content_status == ConfigFileContentStatus.READY
    assert fake_storage.saved_keys == []


@pytest.mark.django_db
def test_publish_rejects_conflicting_existing_formal_object(fake_storage):
    fake_storage.objects["tmp/config-file/staged.txt"] = b"v1"
    fake_storage.objects["host/inst-1/formal.txt"] = b"different"
    version_obj = _create_version()

    assert ConfigFileContentLifecycle.publish_version(version_obj.id) is False

    version_obj.refresh_from_db()
    assert version_obj.content_status == ConfigFileContentStatus.ERROR
    assert "内容冲突" in version_obj.content_error


@pytest.mark.django_db
def test_publish_failure_keeps_recoverable_error_state(fake_storage):
    version_obj = _create_version()

    assert ConfigFileContentLifecycle.publish_version(version_obj.id) is False

    version_obj.refresh_from_db()
    assert version_obj.content_status == ConfigFileContentStatus.ERROR
    assert version_obj.temp_content_key == "tmp/config-file/staged.txt"
    assert version_obj.content_attempt_count == 1
    assert version_obj.content_error


@pytest.mark.django_db
def test_request_delete_removes_object_and_row_after_commit(fake_storage, django_capture_on_commit_callbacks):
    fake_storage.objects["host/inst-1/formal.txt"] = b"v1"
    version_obj = _create_version(
        temp_content_key="",
        content_status=ConfigFileContentStatus.READY,
    )

    with django_capture_on_commit_callbacks(execute=True):
        assert ConfigFileContentLifecycle.request_delete(version_obj.id) is True

    assert not ConfigFileVersion.objects.filter(id=version_obj.id).exists()
    assert "host/inst-1/formal.txt" not in fake_storage.objects


@pytest.mark.django_db
def test_missing_delete_targets_are_idempotent():
    assert ConfigFileContentLifecycle.request_delete(999999) is False
    assert ConfigFileContentLifecycle.delete_version(999999) is True


@pytest.mark.django_db
def test_delete_failure_keeps_delete_pending_row(fake_storage):
    fake_storage.objects["host/inst-1/formal.txt"] = b"v1"
    fake_storage.delete_error = RuntimeError("storage down")
    version_obj = _create_version(
        temp_content_key="",
        content_status=ConfigFileContentStatus.DELETE_PENDING,
    )

    assert ConfigFileContentLifecycle.delete_version(version_obj.id) is False

    version_obj.refresh_from_db()
    assert version_obj.content_status == ConfigFileContentStatus.DELETE_PENDING
    assert version_obj.content_attempt_count == 1
    assert "storage down" in version_obj.content_error


@pytest.mark.django_db(transaction=True)
def test_request_delete_rollback_keeps_ready_row_and_object(fake_storage):
    fake_storage.objects["host/inst-1/formal.txt"] = b"v1"
    version_obj = _create_version(
        temp_content_key="",
        content_status=ConfigFileContentStatus.READY,
    )

    with pytest.raises(RuntimeError, match="rollback"):
        with transaction.atomic():
            ConfigFileContentLifecycle.request_delete(version_obj.id)
            raise RuntimeError("rollback")

    version_obj.refresh_from_db()
    assert version_obj.content_status == ConfigFileContentStatus.READY
    assert fake_storage.objects["host/inst-1/formal.txt"] == b"v1"


@pytest.mark.django_db
def test_recover_stale_content_processes_publish_and_delete_in_batches(fake_storage):
    pending = _create_version()
    deleting = _create_version(
        version="1700000000001",
        content="host/inst-1/delete.txt",
        temp_content_key="",
        content_status=ConfigFileContentStatus.DELETE_PENDING,
    )
    fresh = _create_version(
        version="1700000000002",
        content="host/inst-1/fresh.txt",
        temp_content_key="tmp/config-file/fresh.txt",
    )
    fake_storage.objects["tmp/config-file/staged.txt"] = b"v1"
    fake_storage.objects["host/inst-1/delete.txt"] = b"old"
    old_time = now() - timedelta(hours=1)
    ConfigFileVersion.objects.filter(id__in=[pending.id, deleting.id]).update(content_updated_at=old_time)

    stats = ConfigFileContentLifecycle.recover_stale(
        batch_size=10,
        lease_seconds=300,
        now_time=now(),
    )

    pending.refresh_from_db()
    fresh.refresh_from_db()
    assert pending.content_status == ConfigFileContentStatus.READY
    assert fresh.content_status == ConfigFileContentStatus.PENDING
    assert not ConfigFileVersion.objects.filter(id=deleting.id).exists()
    assert stats == {"scanned": 2, "recovered": 2, "failed": 0}


@pytest.mark.django_db
def test_cleanup_orphan_temp_objects_keeps_referenced_and_fresh_objects(fake_storage):
    referenced_key = "tmp/config-file/referenced.txt"
    old_orphan = "tmp/config-file/old-orphan.txt"
    fresh_orphan = "tmp/config-file/fresh-orphan.txt"
    _create_version(temp_content_key=referenced_key)
    fake_storage.objects.update(
        {
            referenced_key: b"v1",
            old_orphan: b"old",
            fresh_orphan: b"fresh",
        }
    )
    old_time = now() - timedelta(hours=2)
    fake_storage.modified_at = {
        referenced_key: old_time,
        old_orphan: old_time,
        fresh_orphan: now(),
    }

    deleted = ConfigFileContentLifecycle.cleanup_orphan_temp_objects(
        retention_seconds=3600,
        batch_size=10,
        now_time=now(),
    )

    assert deleted == 1
    assert referenced_key in fake_storage.objects
    assert fresh_orphan in fake_storage.objects
    assert old_orphan not in fake_storage.objects


def test_periodic_task_combines_recovery_and_orphan_stats(monkeypatch):
    from apps.cmdb.tasks.celery_tasks import reconcile_config_file_content_task

    monkeypatch.setattr(
        ConfigFileContentLifecycle,
        "recover_stale",
        classmethod(lambda cls: {"scanned": 3, "recovered": 2, "failed": 1}),
    )
    monkeypatch.setattr(
        ConfigFileContentLifecycle,
        "cleanup_orphan_temp_objects",
        classmethod(lambda cls: 4),
    )

    assert reconcile_config_file_content_task() == {
        "scanned": 3,
        "recovered": 2,
        "failed": 1,
        "orphans_deleted": 4,
    }


def test_periodic_schedule_is_registered():
    from apps.cmdb.config import CELERY_BEAT_SCHEDULE

    schedule = CELERY_BEAT_SCHEDULE["reconcile_config_file_content_task"]
    assert schedule["task"] == "apps.cmdb.tasks.celery_tasks.reconcile_config_file_content_task"
