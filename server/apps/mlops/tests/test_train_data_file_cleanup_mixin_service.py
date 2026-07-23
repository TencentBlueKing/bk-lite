from unittest.mock import Mock

import pytest
from django.db import IntegrityError, models, transaction

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

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.integration]

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


def test_outer_transaction_rollback_preserves_old_file(monkeypatch):
    instance = _create_train_data(
        AnomalyDetectionDataset,
        AnomalyDetectionTrainData,
    )
    delete = _mock_storage_delete(monkeypatch, AnomalyDetectionTrainData)

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


def test_committed_replacement_deletes_old_file(monkeypatch):
    instance = _create_train_data(
        AnomalyDetectionDataset,
        AnomalyDetectionTrainData,
    )
    delete = _mock_storage_delete(monkeypatch, AnomalyDetectionTrainData)

    instance.train_data = "new/train-data.bin"
    instance.save()

    delete.assert_called_once_with("old/train-data.bin")
    assert (
        _persisted_train_data_path(AnomalyDetectionTrainData, instance)
        == "new/train-data.bin"
    )


def test_committed_clear_deletes_old_file(monkeypatch):
    instance = _create_train_data(
        AnomalyDetectionDataset,
        AnomalyDetectionTrainData,
    )
    delete = _mock_storage_delete(monkeypatch, AnomalyDetectionTrainData)

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


def test_cleanup_failure_does_not_rollback_committed_database_update(monkeypatch):
    instance = _create_train_data(
        AnomalyDetectionDataset,
        AnomalyDetectionTrainData,
    )
    delete = _mock_storage_delete(
        monkeypatch,
        AnomalyDetectionTrainData,
        side_effect=OSError("object storage unavailable"),
    )

    instance.train_data = "new/train-data.bin"
    instance.save()

    delete.assert_called_once_with("old/train-data.bin")
    assert (
        _persisted_train_data_path(AnomalyDetectionTrainData, instance)
        == "new/train-data.bin"
    )


def test_stale_instance_non_file_save_preserves_committed_replacement(monkeypatch):
    instance = _create_train_data(
        AnomalyDetectionDataset,
        AnomalyDetectionTrainData,
    )
    stale_instance = AnomalyDetectionTrainData.objects.get(pk=instance.pk)
    delete = _mock_storage_delete(monkeypatch, AnomalyDetectionTrainData)

    instance.train_data = "new/train-data.bin"
    instance.save()

    stale_instance.name = "renamed by concurrent request"
    stale_instance.save()

    assert (
        _persisted_train_data_path(AnomalyDetectionTrainData, stale_instance)
        == "new/train-data.bin"
    )
    delete.assert_called_once_with("old/train-data.bin")


def test_multiple_replacements_in_outer_transaction_keep_final_file(monkeypatch):
    instance = _create_train_data(
        AnomalyDetectionDataset,
        AnomalyDetectionTrainData,
    )
    delete = _mock_storage_delete(monkeypatch, AnomalyDetectionTrainData)

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
