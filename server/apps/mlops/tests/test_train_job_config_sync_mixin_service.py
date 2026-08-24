import pytest
from django.db import transaction
from django.db.models.query import QuerySet

from apps.mlops.models.mixins import ConfigSyncError
from apps.mlops.models.object_detection import ObjectDetectionTrainJob

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _create_job_with_config_path(path="configs/old.json"):
    job = ObjectDetectionTrainJob.objects.create(
        name="config-sync-job",
        team=[1],
        algorithm="yolo11",
        max_evals=12,
        hyperopt_config={},
    )
    ObjectDetectionTrainJob.objects.filter(pk=job.pk).update(config_url=path)
    job.refresh_from_db()
    return job


def _mock_config_storage(monkeypatch, job):
    field = job.config_url
    deleted = []

    def save(field_file, filename, _content, save=False):
        assert save is False
        field_file.name = f"uploaded/{filename}"

    monkeypatch.setattr(type(field), "save", save)
    monkeypatch.setattr(field.storage, "delete", deleted.append)
    return deleted


def test_replacing_config_keeps_old_object_until_outer_transaction_commits(
    monkeypatch,
):
    job = _create_job_with_config_path()
    deleted = _mock_config_storage(monkeypatch, job)

    with pytest.raises(RuntimeError, match="outer rollback"):
        with transaction.atomic():
            job.hyperopt_config = {"hyperparams": {"epochs": 3}}
            job.save()
            assert deleted == []
            raise RuntimeError("outer rollback")

    job.refresh_from_db()
    assert job.config_url.name == "configs/old.json"
    assert deleted == []


def test_clearing_config_keeps_old_object_until_outer_transaction_commits(
    monkeypatch,
):
    job = _create_job_with_config_path()
    deleted = _mock_config_storage(monkeypatch, job)

    with pytest.raises(RuntimeError, match="outer rollback"):
        with transaction.atomic():
            job.hyperopt_config = {}
            job.save()
            assert deleted == []
            raise RuntimeError("outer rollback")

    job.refresh_from_db()
    assert job.config_url.name == "configs/old.json"
    assert deleted == []


def test_replacing_config_deletes_old_object_after_commit(
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    job = _create_job_with_config_path()
    deleted = _mock_config_storage(monkeypatch, job)

    with django_capture_on_commit_callbacks(execute=True):
        job.hyperopt_config = {"hyperparams": {"epochs": 3}}
        job.save()
        assert deleted == []

    job.refresh_from_db()
    assert job.config_url.name.startswith("uploaded/config_")
    assert deleted == ["configs/old.json"]


def test_clearing_config_deletes_old_object_after_commit(
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    job = _create_job_with_config_path()
    deleted = _mock_config_storage(monkeypatch, job)

    with django_capture_on_commit_callbacks(execute=True):
        job.hyperopt_config = {}
        job.save()
        assert deleted == []

    job.refresh_from_db()
    assert not job.config_url
    assert deleted == ["configs/old.json"]


def test_database_pointer_failure_cleans_new_upload_without_deleting_old(
    monkeypatch,
):
    job = _create_job_with_config_path()
    deleted = _mock_config_storage(monkeypatch, job)
    real_update = QuerySet.update

    def fail_config_pointer_update(queryset, **kwargs):
        if set(kwargs) == {"config_url"}:
            raise RuntimeError("pointer update failed")
        return real_update(queryset, **kwargs)

    monkeypatch.setattr(QuerySet, "update", fail_config_pointer_update)

    job.hyperopt_config = {"hyperparams": {"epochs": 3}}
    with pytest.raises(RuntimeError, match="pointer update failed"):
        job.save()

    job.refresh_from_db()
    assert job.config_url.name == "configs/old.json"
    assert len(deleted) == 1
    assert deleted[0].startswith("uploaded/config_")


def test_initial_create_pointer_failure_rolls_back_row_and_cleans_upload(
    monkeypatch,
):
    job = ObjectDetectionTrainJob(
        name="new-config-sync-job",
        team=[1],
        algorithm="yolo11",
        max_evals=12,
        hyperopt_config={"hyperparams": {"epochs": 3}},
    )
    deleted = _mock_config_storage(monkeypatch, job)
    real_update = QuerySet.update

    def fail_config_pointer_update(queryset, **kwargs):
        if set(kwargs) == {"config_url"}:
            raise RuntimeError("pointer update failed")
        return real_update(queryset, **kwargs)

    monkeypatch.setattr(QuerySet, "update", fail_config_pointer_update)

    with pytest.raises(RuntimeError, match="pointer update failed"):
        job.save()

    assert not ObjectDetectionTrainJob.objects.filter(pk=job.pk).exists()
    assert not job.config_url
    assert len(deleted) == 1
    assert deleted[0].startswith("uploaded/config_")


def test_clearing_pointer_failure_preserves_old_object_and_pointer(
    monkeypatch,
):
    job = _create_job_with_config_path()
    deleted = _mock_config_storage(monkeypatch, job)
    real_update = QuerySet.update

    def fail_config_pointer_update(queryset, **kwargs):
        if set(kwargs) == {"config_url"}:
            raise RuntimeError("pointer update failed")
        return real_update(queryset, **kwargs)

    monkeypatch.setattr(QuerySet, "update", fail_config_pointer_update)

    job.hyperopt_config = {}
    with pytest.raises(RuntimeError, match="pointer update failed"):
        job.save()

    job.refresh_from_db()
    assert job.config_url.name == "configs/old.json"
    assert deleted == []


def test_missing_database_row_cleans_new_upload_without_deleting_old(
    monkeypatch,
):
    job = _create_job_with_config_path()
    deleted = _mock_config_storage(monkeypatch, job)
    real_update = QuerySet.update

    def miss_config_pointer_update(queryset, **kwargs):
        if set(kwargs) == {"config_url"}:
            return 0
        return real_update(queryset, **kwargs)

    monkeypatch.setattr(QuerySet, "update", miss_config_pointer_update)

    job.hyperopt_config = {"hyperparams": {"epochs": 3}}
    with pytest.raises(ConfigSyncError, match="数据库指针更新失败"):
        job.save()

    job.refresh_from_db()
    assert job.config_url.name == "configs/old.json"
    assert len(deleted) == 1
    assert deleted[0].startswith("uploaded/config_")


def test_old_object_cleanup_failure_does_not_roll_back_committed_pointer(
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    job = _create_job_with_config_path()
    field = job.config_url

    def save(field_file, filename, _content, save=False):
        assert save is False
        field_file.name = f"uploaded/{filename}"

    monkeypatch.setattr(type(field), "save", save)
    monkeypatch.setattr(
        field.storage,
        "delete",
        lambda _path: (_ for _ in ()).throw(OSError("cleanup failed")),
    )

    with django_capture_on_commit_callbacks(execute=True):
        job.hyperopt_config = {"hyperparams": {"epochs": 3}}
        job.save()

    job.refresh_from_db()
    assert job.config_url.name.startswith("uploaded/config_")
