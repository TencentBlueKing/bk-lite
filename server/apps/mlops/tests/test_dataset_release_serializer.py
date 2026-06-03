import types
from unittest.mock import Mock

import pytest
from rest_framework import serializers as drf_serializers

from apps.mlops.models.anomaly_detection import (
    AnomalyDetectionDataset,
    AnomalyDetectionDatasetRelease,
    AnomalyDetectionTrainData,
)
from apps.mlops.models.classification import (
    ClassificationDataset,
    ClassificationDatasetRelease,
    ClassificationTrainData,
)
from apps.mlops.models.image_classification import (
    ImageClassificationDataset,
    ImageClassificationDatasetRelease,
    ImageClassificationTrainData,
)
from apps.mlops.models.log_clustering import (
    LogClusteringDataset,
    LogClusteringDatasetRelease,
    LogClusteringTrainData,
)
from apps.mlops.models.object_detection import (
    ObjectDetectionDataset,
    ObjectDetectionDatasetRelease,
    ObjectDetectionTrainData,
)
from apps.mlops.models.timeseries_predict import (
    TimeSeriesPredictDataset,
    TimeSeriesPredictDatasetRelease,
    TimeSeriesPredictTrainData,
)
from apps.mlops.serializers.anomaly_detection import AnomalyDetectionDatasetReleaseSerializer
from apps.mlops.serializers.classification import ClassificationDatasetReleaseSerializer
from apps.mlops.serializers.image_classification import ImageClassificationDatasetReleaseSerializer
from apps.mlops.serializers.log_clustering import LogClusteringDatasetReleaseSerializer
from apps.mlops.serializers.object_detection import ObjectDetectionDatasetReleaseSerializer
from apps.mlops.serializers.timeseries_predict import TimeSeriesPredictDatasetReleaseSerializer
from apps.mlops.tasks.object_detection import publish_dataset_release_async
from .conftest import create_dataset_release_fixture, make_serializer_context


pytestmark = [pytest.mark.django_db, pytest.mark.integration]


DATASET_RELEASE_CASES = [
    (
        ClassificationDatasetReleaseSerializer,
        ClassificationDataset,
        ClassificationTrainData,
        ClassificationDatasetRelease,
        "apps.mlops.tasks.classification.publish_dataset_release_async.delay",
    ),
    (
        AnomalyDetectionDatasetReleaseSerializer,
        AnomalyDetectionDataset,
        AnomalyDetectionTrainData,
        AnomalyDetectionDatasetRelease,
        "apps.mlops.tasks.anomaly_detection.publish_dataset_release_async.delay",
    ),
    (
        TimeSeriesPredictDatasetReleaseSerializer,
        TimeSeriesPredictDataset,
        TimeSeriesPredictTrainData,
        TimeSeriesPredictDatasetRelease,
        "apps.mlops.tasks.timeseries.publish_dataset_release_async.delay",
    ),
    (
        LogClusteringDatasetReleaseSerializer,
        LogClusteringDataset,
        LogClusteringTrainData,
        LogClusteringDatasetRelease,
        "apps.mlops.tasks.log_clustering.publish_dataset_release_async.delay",
    ),
    (
        ImageClassificationDatasetReleaseSerializer,
        ImageClassificationDataset,
        ImageClassificationTrainData,
        ImageClassificationDatasetRelease,
        "apps.mlops.tasks.image_classification.publish_dataset_release_async.delay",
    ),
    (
        ObjectDetectionDatasetReleaseSerializer,
        ObjectDetectionDataset,
        ObjectDetectionTrainData,
        ObjectDetectionDatasetRelease,
        "apps.mlops.tasks.object_detection.publish_dataset_release_async.delay",
    ),
]


IMAGE_DATASET_VALIDATE_CASES = [
    (
        ImageClassificationDatasetReleaseSerializer,
        ImageClassificationDataset,
        ImageClassificationDatasetRelease,
    ),
    (
        ObjectDetectionDatasetReleaseSerializer,
        ObjectDetectionDataset,
        ObjectDetectionDatasetRelease,
    ),
]


@pytest.mark.parametrize("existing_status", ["pending", "processing", "published", "archived"])
@pytest.mark.parametrize(
    "serializer_class,dataset_model,train_data_model,release_model,delay_path",
    DATASET_RELEASE_CASES,
)
def test_dataset_release_serializer_rejects_same_version_non_failed_release(
    monkeypatch,
    mlops_user,
    existing_status,
    serializer_class,
    dataset_model,
    train_data_model,
    release_model,
    delay_path,
):
    context = make_serializer_context(monkeypatch, mlops_user)
    dataset, train, val, test = create_dataset_release_fixture(dataset_model, train_data_model)
    release_model.objects.create(
        name="existing",
        description="",
        dataset=dataset,
        version="v1.0.0",
        dataset_file="existing.zip",
        status=existing_status,
        metadata={},
        file_size=1,
    )
    delay_mock = Mock()
    monkeypatch.setattr(delay_path, delay_mock)

    serializer = serializer_class(context=context)

    with pytest.raises(drf_serializers.ValidationError) as exc_info:
        serializer._create_from_files(
            {"dataset": dataset, "version": "v1.0.0"},
            train.id,
            val.id,
            test.id,
        )

    assert "v1.0.0" in str(exc_info.value)
    delay_mock.assert_not_called()
    assert release_model.objects.filter(dataset=dataset, version="v1.0.0").count() == 1


@pytest.mark.parametrize(
    "serializer_class,dataset_model,train_data_model,release_model,delay_path",
    DATASET_RELEASE_CASES,
)
def test_dataset_release_serializer_retries_same_version_failed_release(
    monkeypatch,
    mlops_user,
    serializer_class,
    dataset_model,
    train_data_model,
    release_model,
    delay_path,
):
    context = make_serializer_context(monkeypatch, mlops_user)
    dataset, train, val, test = create_dataset_release_fixture(dataset_model, train_data_model)
    failed_release = release_model.objects.create(
        name="failed",
        description="old description",
        dataset=dataset,
        version="v1.0.0",
        dataset_file="failed.zip",
        status="failed",
        metadata={"error": "boom"},
        file_size=99,
    )
    delay_mock = Mock(return_value=types.SimpleNamespace(id="task-1"))
    monkeypatch.setattr(delay_path, delay_mock)

    serializer = serializer_class(context=context)
    release = serializer._create_from_files(
        {"dataset": dataset, "version": "v1.0.0"},
        train.id,
        val.id,
        test.id,
    )

    failed_release.refresh_from_db()

    assert release.id == failed_release.id
    assert failed_release.status == "pending"
    assert failed_release.file_size == 0
    assert failed_release.metadata == {}
    delay_mock.assert_called_once_with(failed_release.id, train.id, val.id, test.id)
    assert release_model.objects.filter(dataset=dataset, version="v1.0.0").count() == 1


@pytest.mark.parametrize(
    "serializer_class,dataset_model,train_data_model,release_model,delay_path",
    DATASET_RELEASE_CASES,
)
def test_dataset_release_serializer_marks_release_failed_when_dispatch_raises(
    monkeypatch,
    mlops_user,
    serializer_class,
    dataset_model,
    train_data_model,
    release_model,
    delay_path,
):
    context = make_serializer_context(monkeypatch, mlops_user)
    dataset, train, val, test = create_dataset_release_fixture(dataset_model, train_data_model)
    monkeypatch.setattr(delay_path, Mock(side_effect=RuntimeError("broker down")))

    serializer = serializer_class(context=context)

    with pytest.raises(drf_serializers.ValidationError) as exc_info:
        serializer._create_from_files(
            {"dataset": dataset, "version": "v2.0.0"},
            train.id,
            val.id,
            test.id,
        )

    release = release_model.objects.get(dataset=dataset, version="v2.0.0")
    assert release.status == "failed"
    assert "投递异步任务失败" in str(exc_info.value)
    assert "broker down" not in str(exc_info.value)


@pytest.mark.parametrize(
    "serializer_class,dataset_model,train_data_model,release_model,delay_path",
    DATASET_RELEASE_CASES,
)
def test_dataset_release_serializer_hides_raw_generic_failure_message(
    monkeypatch,
    mlops_user,
    serializer_class,
    dataset_model,
    train_data_model,
    release_model,
    delay_path,
):
    context = make_serializer_context(monkeypatch, mlops_user)
    dataset, train, val, test = create_dataset_release_fixture(dataset_model, train_data_model)
    monkeypatch.setattr(delay_path, Mock())
    monkeypatch.setattr(release_model.objects, "create", Mock(side_effect=RuntimeError("db exploded")))

    serializer = serializer_class(context=context)

    with pytest.raises(drf_serializers.ValidationError) as exc_info:
        serializer._create_from_files(
            {"dataset": dataset, "version": "v2.1.0"},
            train.id,
            val.id,
            test.id,
        )

    assert "创建发布任务失败" in str(exc_info.value)
    assert "db exploded" not in str(exc_info.value)


@pytest.mark.parametrize(
    "serializer_class,dataset_model,release_model",
    IMAGE_DATASET_VALIDATE_CASES,
)
def test_image_like_dataset_release_validate_allows_failed_same_version_retry(
    monkeypatch,
    mlops_user,
    serializer_class,
    dataset_model,
    release_model,
):
    context = make_serializer_context(monkeypatch, mlops_user)
    dataset = dataset_model.objects.create(name="dataset-1", description="", team=[1])
    release_model.objects.create(
        name="failed",
        description="",
        dataset=dataset,
        version="v3.0.0",
        dataset_file="failed.zip",
        status="failed",
        metadata={},
        file_size=1,
    )

    serializer = serializer_class(context=context)

    attrs = serializer.validate(
        {
            "dataset": dataset,
            "version": "v3.0.0",
            "train_file_id": 1,
            "val_file_id": 2,
            "test_file_id": 3,
        }
    )

    assert attrs["version"] == "v3.0.0"


@pytest.mark.parametrize(
    "serializer_class,dataset_model,release_model",
    IMAGE_DATASET_VALIDATE_CASES,
)
def test_image_like_dataset_release_validate_allows_failed_same_version_retry_with_dataset_file(
    monkeypatch,
    mlops_user,
    serializer_class,
    dataset_model,
    release_model,
):
    context = make_serializer_context(monkeypatch, mlops_user)
    dataset = dataset_model.objects.create(name="dataset-file", description="", team=[1])
    release_model.objects.create(
        name="failed-file",
        description="",
        dataset=dataset,
        version="v3.1.0",
        dataset_file="failed.zip",
        status="failed",
        metadata={"error": "boom"},
        file_size=1,
    )

    serializer = serializer_class(context=context)

    attrs = serializer.validate(
        {
            "dataset": dataset,
            "version": "v3.1.0",
            "dataset_file": "replacement.zip",
        }
    )

    assert attrs["version"] == "v3.1.0"


@pytest.mark.parametrize(
    "serializer_class,dataset_model,release_model",
    IMAGE_DATASET_VALIDATE_CASES,
)
def test_image_like_dataset_release_create_reuses_failed_same_version_with_dataset_file(
    monkeypatch,
    mlops_user,
    serializer_class,
    dataset_model,
    release_model,
):
    context = make_serializer_context(monkeypatch, mlops_user)
    dataset = dataset_model.objects.create(name="dataset-file-create", description="", team=[1])
    failed_release = release_model.objects.create(
        name="failed-file-create",
        description="old description",
        dataset=dataset,
        version="v3.2.0",
        dataset_file="failed.zip",
        status="failed",
        metadata={"error": "boom"},
        file_size=12,
    )

    serializer = serializer_class(context=context)
    release = serializer.create(
        {
            "dataset": dataset,
            "version": "v3.2.0",
            "dataset_file": "replacement.zip",
        }
    )

    failed_release.refresh_from_db()

    assert release.id == failed_release.id
    assert failed_release.status == "pending"
    assert failed_release.file_size == 0
    assert failed_release.metadata == {}


def test_object_detection_publish_dataset_release_marks_failed_on_class_conflicts(
    monkeypatch,
):
    class FakeStorage:
        def __init__(self, bucket_name):
            self.bucket_name = bucket_name

        def save(self, path, file_obj):
            return path

        def url(self, saved_path):
            return f"https://example.com/{saved_path}"

    monkeypatch.setattr("apps.mlops.tasks.object_detection.MinioBackend", FakeStorage)

    dataset, train, val, test = create_dataset_release_fixture(
        ObjectDetectionDataset,
        ObjectDetectionTrainData,
    )
    train.metadata = {"classes": ["person"]}
    val.metadata = {"classes": ["vehicle"]}
    test.metadata = {"classes": ["person"]}
    train.save(update_fields=["metadata"])
    val.save(update_fields=["metadata"])
    test.save(update_fields=["metadata"])

    release = ObjectDetectionDatasetRelease.objects.create(
        name="release-conflict",
        description="",
        dataset=dataset,
        version="v4.0.0",
        dataset_file="pending.zip",
        status="pending",
        metadata={},
        file_size=0,
    )

    result = publish_dataset_release_async(release.id, train.id, val.id, test.id)
    release.refresh_from_db()

    assert result["result"] is False
    assert release.status == "failed"
    assert "类别名称冲突" in release.metadata["error"]
