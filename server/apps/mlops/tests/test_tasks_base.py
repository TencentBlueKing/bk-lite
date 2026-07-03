"""Tests for ``apps.mlops.tasks.base`` shared dataset-publish helpers.

Covers the pure sample-counting / metadata helpers and the
``publish_dataset_release_base`` orchestration with MinIO storage mocked at the
module boundary.
"""
import io
from types import SimpleNamespace
from unittest.mock import MagicMock

import pydantic.root_model  # noqa
import pytest

from apps.mlops.models.anomaly_detection import (
    AnomalyDetectionDataset,
    AnomalyDetectionDatasetRelease,
    AnomalyDetectionTrainData,
)
from apps.mlops.tasks import base as base_mod
from apps.mlops.tasks.base import (
    DatasetPublishConfig,
    build_base_metadata,
    count_csv_samples,
    count_txt_samples,
    mark_release_as_failed,
    publish_dataset_release_base,
)

pytestmark = pytest.mark.unit


# ---------------- count_csv_samples ----------------


def test_count_csv_samples_subtracts_header(tmp_path):
    f = tmp_path / "a.csv"
    f.write_bytes(b"col1,col2\n1,2\n3,4\n5,6\n")
    assert count_csv_samples(f) == 3


def test_count_csv_samples_header_only_is_zero(tmp_path):
    f = tmp_path / "h.csv"
    f.write_bytes(b"col1,col2\n")
    assert count_csv_samples(f) == 0


def test_count_csv_samples_empty_file(tmp_path):
    f = tmp_path / "e.csv"
    f.write_bytes(b"")
    assert count_csv_samples(f) == 0


# ---------------- count_txt_samples ----------------


def test_count_txt_samples_trailing_newline(tmp_path):
    f = tmp_path / "a.txt"
    f.write_bytes(b"line1\nline2\nline3\n")
    assert count_txt_samples(f) == 3


def test_count_txt_samples_no_trailing_newline(tmp_path):
    f = tmp_path / "b.txt"
    f.write_bytes(b"line1\nline2\nline3")
    assert count_txt_samples(f) == 3


def test_count_txt_samples_empty(tmp_path):
    f = tmp_path / "c.txt"
    f.write_bytes(b"")
    assert count_txt_samples(f) == 0


# ---------------- build_base_metadata ----------------


def test_build_base_metadata_totals_and_source():
    train_obj = SimpleNamespace(name="train.csv")
    val_obj = SimpleNamespace(name="val.csv")
    test_obj = SimpleNamespace(name="test.csv")
    md = build_base_metadata(10, 3, 2, train_obj, val_obj, test_obj, 1, 2, 3)
    assert md["train_samples"] == 10
    assert md["val_samples"] == 3
    assert md["test_samples"] == 2
    assert md["total_samples"] == 15
    assert md["source"]["type"] == "manual_selection"
    assert md["source"]["train_file_id"] == 1
    assert md["source"]["test_file_name"] == "test.csv"


def test_build_base_metadata_merges_extra_fields():
    obj = SimpleNamespace(name="x")
    md = build_base_metadata(1, 1, 1, obj, obj, obj, 1, 2, 3, extra_fields={"classes": ["a", "b"]})
    assert md["classes"] == ["a", "b"]
    # source still present after extra merge
    assert "source" in md


# ---------------- mark_release_as_failed ----------------


def _make_release(status="pending"):
    dataset = AnomalyDetectionDataset.objects.create(name="ds", description="", team=[1])
    return AnomalyDetectionDatasetRelease.objects.create(
        name="r", description="", dataset=dataset, version="v1",
        dataset_file="x.zip", status=status, metadata={}, file_size=1,
    )


@pytest.mark.django_db
def test_mark_release_as_failed_sets_status():
    rel = _make_release()
    ok = mark_release_as_failed(AnomalyDetectionDatasetRelease, rel.id)
    assert ok is True
    rel.refresh_from_db()
    assert rel.status == "failed"


@pytest.mark.django_db
def test_mark_release_as_failed_with_error_message_writes_metadata():
    rel = _make_release()
    ok = mark_release_as_failed(AnomalyDetectionDatasetRelease, rel.id, "任务超时")
    assert ok is True
    rel.refresh_from_db()
    assert rel.status == "failed"
    assert rel.metadata["error"] == "任务超时"
    assert "failed_at" in rel.metadata


@pytest.mark.django_db
def test_mark_release_as_failed_missing_returns_false():
    assert mark_release_as_failed(AnomalyDetectionDatasetRelease, 999999) is False


# ---------------- publish_dataset_release_base ----------------


def _config():
    return DatasetPublishConfig(
        release_model=AnomalyDetectionDatasetRelease,
        train_data_model=AnomalyDetectionTrainData,
        task_type="anomaly_detection",
        file_extension="csv",
        storage_prefix="anomaly_datasets",
        count_samples=count_csv_samples,
        build_metadata=build_base_metadata,
    )


@pytest.mark.django_db
def test_publish_base_skips_when_already_published(monkeypatch):
    dataset = AnomalyDetectionDataset.objects.create(name="ds", description="", team=[1])
    rel = AnomalyDetectionDatasetRelease.objects.create(
        name="r", description="", dataset=dataset, version="v1",
        dataset_file="x.zip", status="published", metadata={}, file_size=1,
    )
    result = publish_dataset_release_base(_config(), rel.id, 1, 2, 3)
    assert result["result"] is False
    assert "published" in result["reason"]


@pytest.mark.django_db
def test_publish_base_skips_when_failed(monkeypatch):
    dataset = AnomalyDetectionDataset.objects.create(name="ds", description="", team=[1])
    rel = AnomalyDetectionDatasetRelease.objects.create(
        name="r", description="", dataset=dataset, version="v1",
        dataset_file="x.zip", status="failed", metadata={}, file_size=1,
    )
    result = publish_dataset_release_base(_config(), rel.id, 1, 2, 3)
    assert result["result"] is False
    assert "failed" in result["reason"]


@pytest.mark.django_db
def test_publish_base_full_success(monkeypatch):
    dataset = AnomalyDetectionDataset.objects.create(name="ds", description="", team=[1])
    rel = AnomalyDetectionDatasetRelease.objects.create(
        name="r", description="", dataset=dataset, version="v1",
        dataset_file="", status="pending", metadata={}, file_size=0,
    )
    train = AnomalyDetectionTrainData.objects.create(name="train.csv", dataset=dataset, is_train_data=True)
    val = AnomalyDetectionTrainData.objects.create(name="val.csv", dataset=dataset, is_val_data=True)
    test = AnomalyDetectionTrainData.objects.create(name="test.csv", dataset=dataset, is_test_data=True)

    # Provide a fake MinIO storage at the module boundary.
    fake_storage = MagicMock()
    fake_storage.save.return_value = "anomaly_datasets/1/saved.zip"
    fake_storage.url.return_value = "http://minio.local/saved.zip"
    monkeypatch.setattr(base_mod, "MinioBackend", lambda **kw: fake_storage)
    monkeypatch.setattr(base_mod, "iso_date_prefix", lambda obj, name: f"2020/{name}")

    # publish_base fetches each TrainData via objects.get(); wrap that to attach
    # an openable fake FileField returning CSV bytes (3 rows + header).
    real_get = AnomalyDetectionTrainData.objects.get

    def fake_get(*args, **kwargs):
        obj = real_get(*args, **kwargs)
        fake_field = MagicMock()
        fake_field.name = obj.name
        fake_field.open.return_value = io.BytesIO(b"col\nr1\nr2\n")
        obj.train_data = fake_field
        return obj

    monkeypatch.setattr(AnomalyDetectionTrainData.objects, "get", fake_get)

    result = publish_dataset_release_base(_config(), rel.id, train.id, val.id, test.id)
    assert result["result"] is True
    assert result["release_id"] == rel.id

    rel.refresh_from_db()
    assert rel.status == "published"
    assert rel.metadata["train_samples"] == 2  # 3 lines - header
    assert rel.metadata["total_samples"] == 6
    assert rel.dataset_file.name == "anomaly_datasets/1/saved.zip"
    fake_storage.save.assert_called_once()
