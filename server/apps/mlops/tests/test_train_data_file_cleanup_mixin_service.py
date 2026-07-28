import threading
from unittest.mock import Mock

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import (
    DatabaseError,
    IntegrityError,
    close_old_connections,
    models,
    transaction,
)

from apps.mlops.models.anomaly_detection import (
    AnomalyDetectionDataset,
    AnomalyDetectionTrainData,
)
from apps.mlops.models.classification import (
    ClassificationDataset,
    ClassificationTrainData,
)
from apps.mlops.models.image_classification import (
    ImageClassificationDataset,
    ImageClassificationTrainData,
)
from apps.mlops.models.log_clustering import (
    LogClusteringDataset,
    LogClusteringTrainData,
)
from apps.mlops.models.object_detection import (
    ObjectDetectionDataset,
    ObjectDetectionTrainData,
)
from apps.mlops.models.timeseries_predict import (
    TimeSeriesPredictDataset,
    TimeSeriesPredictTrainData,
)
from apps.mlops.models.train_data_file import (
    TrainDataFileReferenceGuard,
    TrainDataFileReferenceStatus,
)
from apps.mlops.services import train_data_file_cleanup as cleanup_service
from apps.mlops.services.train_data_file_cleanup import (
    TrainDataFileReferenceUnavailable,
)
from apps.mlops.tasks.file_cleanup import cleanup_train_data_file

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

TRAIN_DATA_MODELS = [
    (AnomalyDetectionDataset, AnomalyDetectionTrainData),
    (ClassificationDataset, ClassificationTrainData),
    (ImageClassificationDataset, ImageClassificationTrainData),
    (LogClusteringDataset, LogClusteringTrainData),
    (ObjectDetectionDataset, ObjectDetectionTrainData),
    (TimeSeriesPredictDataset, TimeSeriesPredictTrainData),
]


def _create_train_data(dataset_model, train_data_model):
    dataset = dataset_model.objects.create(name="dataset", description="", team=[1])
    return train_data_model.objects.create(
        name="train-data",
        dataset=dataset,
        train_data="old/train-data.bin",
        is_train_data=True,
    )


def _mock_storage_delete(monkeypatch, train_data_model, *, side_effect=None):
    delete = Mock(side_effect=side_effect)
    storage = train_data_model._meta.get_field("train_data").storage
    monkeypatch.setattr(storage, "delete", delete)
    return delete


def _persisted_train_data_path(train_data_model, instance):
    return train_data_model.objects.values_list("train_data", flat=True).get(
        pk=instance.pk
    )


@pytest.mark.parametrize(("dataset_model", "train_data_model"), TRAIN_DATA_MODELS)
def test_database_save_failure_preserves_old_file(
    monkeypatch,
    dataset_model,
    train_data_model,
):
    instance = _create_train_data(dataset_model, train_data_model)
    delete = _mock_storage_delete(monkeypatch, train_data_model)
    instance.train_data = "new/train-data.bin"
    monkeypatch.setattr(
        models.Model,
        "save",
        Mock(side_effect=IntegrityError("database save failed")),
    )

    with pytest.raises(IntegrityError, match="database save failed"):
        instance.save()

    delete.assert_not_called()
    assert _persisted_train_data_path(train_data_model, instance) == "old/train-data.bin"


def test_outer_transaction_rollback_preserves_old_file(
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    instance = _create_train_data(
        AnomalyDetectionDataset,
        AnomalyDetectionTrainData,
    )
    delete = _mock_storage_delete(monkeypatch, AnomalyDetectionTrainData)

    with django_capture_on_commit_callbacks(execute=True):
        with pytest.raises(RuntimeError, match="rollback caller transaction"):
            with transaction.atomic():
                instance.train_data = "new/train-data.bin"
                instance.save()
                raise RuntimeError("rollback caller transaction")

    delete.assert_not_called()
    assert (
        _persisted_train_data_path(AnomalyDetectionTrainData, instance)
        == "old/train-data.bin"
    )


def test_committed_replacement_deletes_old_file(
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    instance = _create_train_data(
        AnomalyDetectionDataset,
        AnomalyDetectionTrainData,
    )
    delete = _mock_storage_delete(monkeypatch, AnomalyDetectionTrainData)

    with django_capture_on_commit_callbacks(execute=True):
        instance.train_data = "new/train-data.bin"
        instance.save()

    delete.assert_called_once_with("old/train-data.bin")
    assert (
        _persisted_train_data_path(AnomalyDetectionTrainData, instance)
        == "new/train-data.bin"
    )


def test_shared_file_reference_in_same_model_preserves_old_file(
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    dataset = AnomalyDetectionDataset.objects.create(
        name="shared-file-dataset",
        description="",
        team=[1],
    )
    first = AnomalyDetectionTrainData.objects.create(
        name="first",
        dataset=dataset,
        train_data="shared/train-data.bin",
        is_train_data=True,
    )
    second = AnomalyDetectionTrainData.objects.create(
        name="second",
        dataset=dataset,
        train_data="shared/train-data.bin",
        is_train_data=True,
    )
    delete = _mock_storage_delete(monkeypatch, AnomalyDetectionTrainData)

    with django_capture_on_commit_callbacks(execute=True):
        first.train_data = "replacement/train-data.bin"
        first.save()

    second.refresh_from_db()
    assert second.train_data.name == "shared/train-data.bin"
    delete.assert_not_called()


def test_shared_file_reference_in_another_train_data_model_preserves_old_file(
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    anomaly_dataset = AnomalyDetectionDataset.objects.create(
        name="anomaly-shared-file-dataset",
        description="",
        team=[1],
    )
    classification_dataset = ClassificationDataset.objects.create(
        name="classification-shared-file-dataset",
        description="",
        team=[1],
    )
    source = AnomalyDetectionTrainData.objects.create(
        name="source",
        dataset=anomaly_dataset,
        train_data="shared/cross-model.bin",
        is_train_data=True,
    )
    reference = ClassificationTrainData.objects.create(
        name="reference",
        dataset=classification_dataset,
        train_data="shared/cross-model.bin",
        is_train_data=True,
    )
    delete = _mock_storage_delete(monkeypatch, AnomalyDetectionTrainData)

    with django_capture_on_commit_callbacks(execute=True):
        source.train_data = "replacement/cross-model.bin"
        source.save()

    reference.refresh_from_db()
    assert reference.train_data.name == "shared/cross-model.bin"
    delete.assert_not_called()


@pytest.mark.django_db(transaction=True)
def test_concurrent_reference_cannot_commit_during_unreferenced_file_deletion(
    monkeypatch,
):
    old_path = "shared/concurrent-reference.bin"
    source_dataset = AnomalyDetectionDataset.objects.create(
        name="concurrent-source-dataset",
        description="",
        team=[1],
    )
    reference_dataset = ClassificationDataset.objects.create(
        name="concurrent-reference-dataset",
        description="",
        team=[1],
    )
    source = AnomalyDetectionTrainData.objects.create(
        name="source",
        dataset=source_dataset,
        train_data=old_path,
        is_train_data=True,
    )
    AnomalyDetectionTrainData.objects.filter(pk=source.pk).update(
        train_data="replacement/concurrent-reference.bin"
    )

    object_exists = {"value": True}

    def delete_object(path):
        assert path == old_path
        object_exists["value"] = False

    source_storage = AnomalyDetectionTrainData._meta.get_field("train_data").storage
    reference_storage = ClassificationTrainData._meta.get_field("train_data").storage
    delete = Mock(side_effect=delete_object)
    monkeypatch.setattr(source_storage, "delete", delete)
    monkeypatch.setattr(
        reference_storage,
        "exists",
        lambda path: object_exists["value"],
    )

    scan_completed = threading.Event()
    continue_cleanup = threading.Event()
    cleanup_result = []
    cleanup_errors = []
    writer_errors = []
    writer_finished = threading.Event()
    real_find_reference = cleanup_service._find_train_data_file_reference

    def pause_after_reference_scan(**kwargs):
        reference = real_find_reference(**kwargs)
        scan_completed.set()
        assert continue_cleanup.wait(timeout=5)
        return reference

    monkeypatch.setattr(
        cleanup_service,
        "_find_train_data_file_reference",
        pause_after_reference_scan,
    )

    def run_cleanup():
        close_old_connections()
        try:
            cleanup_result.append(
                cleanup_service.delete_unreferenced_train_data_file(
                    model_label=source._meta.label,
                    instance_pk=source.pk,
                    file_field_name="train_data",
                    old_path=old_path,
                )
            )
        except Exception as error:
            cleanup_errors.append(error)
        finally:
            close_old_connections()

    def create_reference():
        close_old_connections()
        try:
            ClassificationTrainData.objects.create(
                name="concurrent-reference",
                dataset_id=reference_dataset.pk,
                train_data=old_path,
                is_train_data=True,
            )
        except Exception as error:
            writer_errors.append(error)
        finally:
            writer_finished.set()
            close_old_connections()

    cleanup_thread = threading.Thread(target=run_cleanup)
    cleanup_thread.start()
    assert scan_completed.wait(timeout=5)

    writer_thread = threading.Thread(target=create_reference)
    writer_thread.start()
    writer_finished_while_cleanup_paused = writer_finished.wait(timeout=0.5)
    continue_cleanup.set()
    cleanup_thread.join(timeout=5)
    writer_thread.join(timeout=5)

    assert not cleanup_thread.is_alive()
    assert not writer_thread.is_alive()
    assert not cleanup_errors
    assert cleanup_result == ["deleted"]
    assert not writer_finished_while_cleanup_paused
    assert len(writer_errors) == 1
    assert isinstance(writer_errors[0], TrainDataFileReferenceUnavailable)
    assert not ClassificationTrainData.objects.filter(train_data=old_path).exists()
    delete.assert_called_once_with(old_path)


def test_uploaded_file_can_reactivate_a_deleted_path(monkeypatch):
    source_dataset = AnomalyDetectionDataset.objects.create(
        name="reactivation-source-dataset",
        description="",
        team=[1],
    )
    reference_dataset = ClassificationDataset.objects.create(
        name="reactivation-reference-dataset",
        description="",
        team=[1],
    )
    reference_field = ClassificationTrainData._meta.get_field("train_data")
    pending_reference = ClassificationTrainData(
        name="reactivated",
        dataset=reference_dataset,
        is_train_data=True,
    )
    old_path = reference_field.generate_filename(
        pending_reference,
        "reactivated.bin",
    )
    source = AnomalyDetectionTrainData.objects.create(
        name="source",
        dataset=source_dataset,
        train_data=old_path,
        is_train_data=True,
    )
    AnomalyDetectionTrainData.objects.filter(pk=source.pk).update(
        train_data="replacement/reactivated.bin"
    )

    source_storage = AnomalyDetectionTrainData._meta.get_field("train_data").storage
    monkeypatch.setattr(source_storage, "delete", Mock())
    assert (
        cleanup_service.delete_unreferenced_train_data_file(
            model_label=source._meta.label,
            instance_pk=source.pk,
            file_field_name="train_data",
            old_path=old_path,
        )
        == "deleted"
    )

    save = Mock(return_value=old_path)
    monkeypatch.setattr(reference_field.storage, "save", save)
    pending_reference.train_data = SimpleUploadedFile(
        "reactivated.bin",
        b"new training data",
    )
    pending_reference.save()

    pending_reference.refresh_from_db()
    assert pending_reference.train_data.name == old_path
    save.assert_called_once()


def test_duplicate_cleanup_does_not_delete_the_same_object_twice(monkeypatch):
    instance = _create_train_data(
        AnomalyDetectionDataset,
        AnomalyDetectionTrainData,
    )
    AnomalyDetectionTrainData.objects.filter(pk=instance.pk).update(
        train_data="replacement/idempotent-cleanup.bin"
    )
    delete = _mock_storage_delete(monkeypatch, AnomalyDetectionTrainData)
    cleanup_kwargs = {
        "model_label": instance._meta.label,
        "instance_pk": instance.pk,
        "file_field_name": "train_data",
        "old_path": "old/train-data.bin",
    }

    assert cleanup_service.delete_unreferenced_train_data_file(**cleanup_kwargs) == "deleted"
    assert cleanup_service.delete_unreferenced_train_data_file(**cleanup_kwargs) == "deleted"
    delete.assert_called_once_with("old/train-data.bin")


def test_guard_write_failure_after_storage_delete_blocks_string_reference(
    monkeypatch,
):
    old_path = "shared/guard-write-failure.bin"
    source_dataset = AnomalyDetectionDataset.objects.create(
        name="guard-failure-source-dataset",
        description="",
        team=[1],
    )
    reference_dataset = ClassificationDataset.objects.create(
        name="guard-failure-reference-dataset",
        description="",
        team=[1],
    )
    source = AnomalyDetectionTrainData.objects.create(
        name="source",
        dataset=source_dataset,
        train_data=old_path,
        is_train_data=True,
    )
    AnomalyDetectionTrainData.objects.filter(pk=source.pk).update(
        train_data="replacement/guard-write-failure.bin"
    )

    object_exists = {"value": True}

    def delete_object(path):
        assert path == old_path
        object_exists["value"] = False

    source_storage = AnomalyDetectionTrainData._meta.get_field("train_data").storage
    reference_storage = ClassificationTrainData._meta.get_field("train_data").storage
    delete = Mock(side_effect=delete_object)
    monkeypatch.setattr(source_storage, "delete", delete)
    monkeypatch.setattr(
        reference_storage,
        "exists",
        lambda path: object_exists["value"],
    )

    real_guard_save = TrainDataFileReferenceGuard.save

    def fail_deleted_guard_save(guard, *args, **kwargs):
        if guard.status == TrainDataFileReferenceStatus.DELETED:
            raise DatabaseError("guard tombstone write failed")
        return real_guard_save(guard, *args, **kwargs)

    monkeypatch.setattr(
        TrainDataFileReferenceGuard,
        "save",
        fail_deleted_guard_save,
    )
    cleanup_kwargs = {
        "model_label": source._meta.label,
        "instance_pk": source.pk,
        "file_field_name": "train_data",
        "old_path": old_path,
    }

    with pytest.raises(DatabaseError, match="guard tombstone write failed"):
        cleanup_service.delete_unreferenced_train_data_file(**cleanup_kwargs)

    monkeypatch.setattr(
        TrainDataFileReferenceGuard,
        "save",
        real_guard_save,
    )
    with pytest.raises(TrainDataFileReferenceUnavailable):
        ClassificationTrainData.objects.create(
            name="stale-reference",
            dataset=reference_dataset,
            train_data=old_path,
            is_train_data=True,
        )

    assert not ClassificationTrainData.objects.filter(train_data=old_path).exists()
    assert cleanup_service.delete_unreferenced_train_data_file(**cleanup_kwargs) == "deleted"
    assert delete.call_count == 2


def test_committed_clear_deletes_old_file(
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    instance = _create_train_data(
        AnomalyDetectionDataset,
        AnomalyDetectionTrainData,
    )
    delete = _mock_storage_delete(monkeypatch, AnomalyDetectionTrainData)

    with django_capture_on_commit_callbacks(execute=True):
        instance.train_data = None
        instance.save()

    delete.assert_called_once_with("old/train-data.bin")
    assert _persisted_train_data_path(AnomalyDetectionTrainData, instance) == ""


def test_unchanged_file_is_not_deleted(monkeypatch):
    instance = _create_train_data(
        AnomalyDetectionDataset,
        AnomalyDetectionTrainData,
    )
    delete = _mock_storage_delete(monkeypatch, AnomalyDetectionTrainData)

    instance.name = "renamed"
    instance.save()

    delete.assert_not_called()


def test_update_fields_without_file_keeps_persisted_file(monkeypatch):
    instance = _create_train_data(
        ImageClassificationDataset,
        ImageClassificationTrainData,
    )
    delete = _mock_storage_delete(monkeypatch, ImageClassificationTrainData)

    instance.train_data = "not-persisted/train-data.bin"
    instance.metadata = {"classes": ["cat"]}
    instance.save(update_fields=["metadata"])

    delete.assert_not_called()
    assert (
        _persisted_train_data_path(ImageClassificationTrainData, instance)
        == "old/train-data.bin"
    )


def test_cleanup_failure_schedules_retry_without_rolling_back_database_update(
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    instance = _create_train_data(
        AnomalyDetectionDataset,
        AnomalyDetectionTrainData,
    )
    delete = _mock_storage_delete(
        monkeypatch,
        AnomalyDetectionTrainData,
        side_effect=OSError("object storage unavailable"),
    )
    apply_async = Mock()
    monkeypatch.setattr(cleanup_train_data_file, "apply_async", apply_async)

    with django_capture_on_commit_callbacks(execute=True):
        instance.train_data = "new/train-data.bin"
        instance.save()

    delete.assert_called_once_with("old/train-data.bin")
    apply_async.assert_called_once_with(
        kwargs={
            "model_label": "mlops.AnomalyDetectionTrainData",
            "instance_pk": instance.pk,
            "file_field_name": "train_data",
            "old_path": "old/train-data.bin",
            "using": "default",
        },
        delivery_mode=2,
        retry=True,
        retry_policy={
            "max_retries": 3,
            "interval_start": 0,
            "interval_step": 1,
            "interval_max": 3,
        },
    )
    assert (
        _persisted_train_data_path(AnomalyDetectionTrainData, instance)
        == "new/train-data.bin"
    )


def test_stale_instance_non_file_save_preserves_committed_replacement(
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    instance = _create_train_data(
        AnomalyDetectionDataset,
        AnomalyDetectionTrainData,
    )
    stale_instance = AnomalyDetectionTrainData.objects.get(pk=instance.pk)
    delete = _mock_storage_delete(monkeypatch, AnomalyDetectionTrainData)

    with django_capture_on_commit_callbacks(execute=True):
        instance.train_data = "new/train-data.bin"
        instance.save()

    stale_instance.name = "renamed by concurrent request"
    stale_instance.save()

    assert (
        _persisted_train_data_path(AnomalyDetectionTrainData, stale_instance)
        == "new/train-data.bin"
    )
    delete.assert_called_once_with("old/train-data.bin")


def test_multiple_replacements_in_outer_transaction_keep_final_file(
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    instance = _create_train_data(
        AnomalyDetectionDataset,
        AnomalyDetectionTrainData,
    )
    delete = _mock_storage_delete(monkeypatch, AnomalyDetectionTrainData)

    with django_capture_on_commit_callbacks(execute=True):
        with transaction.atomic():
            instance.train_data = "intermediate/train-data.bin"
            instance.save()
            instance.train_data = "old/train-data.bin"
            instance.save()

    assert (
        _persisted_train_data_path(AnomalyDetectionTrainData, instance)
        == "old/train-data.bin"
    )
    delete.assert_called_once_with("intermediate/train-data.bin")


def test_retry_task_rechecks_current_database_reference(monkeypatch):
    instance = _create_train_data(
        AnomalyDetectionDataset,
        AnomalyDetectionTrainData,
    )
    delete = _mock_storage_delete(monkeypatch, AnomalyDetectionTrainData)
    cleanup_kwargs = {
        "model_label": "mlops.AnomalyDetectionTrainData",
        "instance_pk": instance.pk,
        "file_field_name": "train_data",
        "old_path": "old/train-data.bin",
        "using": "default",
    }

    assert cleanup_train_data_file.run(**cleanup_kwargs) == "referenced"
    delete.assert_not_called()

    AnomalyDetectionTrainData.objects.filter(pk=instance.pk).update(
        train_data="new/train-data.bin"
    )
    assert cleanup_train_data_file.run(**cleanup_kwargs) == "deleted"
    delete.assert_called_once_with("old/train-data.bin")
    assert cleanup_train_data_file.max_retries == 5
    assert cleanup_train_data_file.acks_late is True
    assert cleanup_train_data_file.reject_on_worker_lost is True
