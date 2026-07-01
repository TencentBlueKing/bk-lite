"""Tests for image_classification / object_detection Celery task modules.

Covers the pure ``prepare_class_mappings`` class-merging logic for object
detection plus the cheap early-return branches (already-finished, missing file,
SoftTimeLimit / generic failure) of both image-heavy publish tasks.
"""
from unittest.mock import Mock

import pydantic.root_model  # noqa
import pytest
from celery.exceptions import SoftTimeLimitExceeded

from apps.mlops.constants import DatasetReleaseStatus
from apps.mlops.tasks import image_classification as ic_task
from apps.mlops.tasks import object_detection as od_task
from apps.mlops.tasks.object_detection import prepare_class_mappings

pytestmark = pytest.mark.unit


# ---------------- prepare_class_mappings (pure) ----------------


def test_prepare_class_mappings_merges_identical():
    train = {"classes": ["cat", "dog"]}
    val = {"classes": ["cat", "dog"]}
    test = {"classes": ["cat", "dog"]}
    global_classes, train_map, val_map, test_map, warnings = prepare_class_mappings(train, val, test)
    assert global_classes == ["cat", "dog"]
    assert train_map == {0: 0, 1: 1}
    assert test_map == {0: 0, 1: 1}
    assert warnings["conflicts"] == []


def test_prepare_class_mappings_extends_from_val():
    train = {"classes": ["cat"]}
    val = {"classes": ["cat", "dog"]}
    global_classes, *_ , warnings = prepare_class_mappings(train, val, None)
    assert global_classes == ["cat", "dog"]
    assert warnings["conflicts"] == []


def test_prepare_class_mappings_no_test_returns_empty_test_map():
    train = {"classes": ["cat"]}
    val = {"classes": ["cat"]}
    _, _, _, test_map, _ = prepare_class_mappings(train, val, None)
    assert test_map == {}


def test_prepare_class_mappings_conflict_raises():
    train = {"classes": ["cat", "dog"]}
    val = {"classes": ["cat", "bird"]}  # id 1 conflict: dog vs bird
    with pytest.raises(ValueError) as exc:
        prepare_class_mappings(train, val, None)
    assert "类别名称冲突" in str(exc.value)


def test_prepare_class_mappings_invalid_train_meta():
    with pytest.raises(ValueError):
        prepare_class_mappings({}, {"classes": ["a"]}, None)


def test_prepare_class_mappings_invalid_train_classes():
    with pytest.raises(ValueError):
        prepare_class_mappings({"classes": []}, {"classes": ["a"]}, None)


def test_prepare_class_mappings_invalid_val_meta():
    with pytest.raises(ValueError):
        prepare_class_mappings({"classes": ["a"]}, {}, None)


def test_prepare_class_mappings_invalid_test_meta_type():
    with pytest.raises(ValueError):
        prepare_class_mappings({"classes": ["a"]}, {"classes": ["a"]}, "not-a-dict")


# ---------------- early-return branches (DB) ----------------


def _od_release(status):
    from apps.mlops.models.object_detection import (
        ObjectDetectionDataset,
        ObjectDetectionDatasetRelease,
    )

    ds = ObjectDetectionDataset.objects.create(name="ds", description="", team=[1])
    return ObjectDetectionDatasetRelease.objects.create(
        name="r", description="", dataset=ds, version="v1",
        dataset_file="x.zip", status=status, metadata={}, file_size=1,
    )


def _ic_release(status):
    from apps.mlops.models.image_classification import (
        ImageClassificationDataset,
        ImageClassificationDatasetRelease,
    )

    ds = ImageClassificationDataset.objects.create(name="ds", description="", team=[1])
    return ImageClassificationDatasetRelease.objects.create(
        name="r", description="", dataset=ds, version="v1",
        dataset_file="x.zip", status=status, metadata={}, file_size=1,
    )


@pytest.mark.django_db
def test_object_detection_skips_already_published():
    rel = _od_release(DatasetReleaseStatus.PUBLISHED)
    result = od_task.publish_dataset_release_async.run(rel.id, 1, 2, 3)
    assert result["result"] is False
    assert "published" in result["reason"]


@pytest.mark.django_db
def test_object_detection_missing_file_marks_failed():
    rel = _od_release(DatasetReleaseStatus.PENDING)
    # train data ids don't exist -> DoesNotExist -> generic handler marks failed
    result = od_task.publish_dataset_release_async.run(rel.id, 9991, 9992, 9993)
    assert result["result"] is False
    assert "error" in result
    rel.refresh_from_db()
    assert rel.status == "failed"


@pytest.mark.django_db
def test_object_detection_soft_timeout_marks_failed(monkeypatch):
    rel = _od_release(DatasetReleaseStatus.PENDING)

    # force the inner train-data fetch to raise SoftTimeLimitExceeded
    from apps.mlops.models.object_detection import ObjectDetectionTrainData

    def boom(*a, **k):
        raise SoftTimeLimitExceeded()

    monkeypatch.setattr(ObjectDetectionTrainData.objects, "get", boom)
    result = od_task.publish_dataset_release_async.run(rel.id, 1, 2, 3)
    assert result["reason"] == "Task timeout"
    rel.refresh_from_db()
    assert rel.status == "failed"


@pytest.mark.django_db
def test_image_classification_skips_already_failed():
    rel = _ic_release(DatasetReleaseStatus.FAILED)
    result = ic_task.publish_dataset_release_async.run(rel.id, 1, 2, 3)
    assert result["result"] is False
    assert "failed" in result["reason"]


@pytest.mark.django_db
def test_image_classification_missing_file_marks_failed():
    rel = _ic_release(DatasetReleaseStatus.PENDING)
    result = ic_task.publish_dataset_release_async.run(rel.id, 9991, 9992, 9993)
    assert result["result"] is False
    assert "error" in result
    rel.refresh_from_db()
    assert rel.status == "failed"


@pytest.mark.django_db
def test_image_classification_soft_timeout_marks_failed(monkeypatch):
    rel = _ic_release(DatasetReleaseStatus.PENDING)
    from apps.mlops.models.image_classification import ImageClassificationTrainData

    def boom(*a, **k):
        raise SoftTimeLimitExceeded()

    monkeypatch.setattr(ImageClassificationTrainData.objects, "get", boom)
    result = ic_task.publish_dataset_release_async.run(rel.id, 1, 2, 3)
    assert result["reason"] == "Task timeout"
    rel.refresh_from_db()
    assert rel.status == "failed"
