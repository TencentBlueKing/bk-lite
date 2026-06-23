import io
import types
from unittest.mock import Mock

import pytest
from rest_framework import serializers as drf_serializers

from apps.mlops.models.anomaly_detection import (
    AnomalyDetectionDataset,
    AnomalyDetectionDatasetRelease,
    AnomalyDetectionTrainData,
)
from apps.mlops.serializers.anomaly_detection import (
    AnomalyDetectionDatasetReleaseSerializer,
    AnomalyDetectionPredictRequestSerializer,
    AnomalyDetectionTrainDataSerializer,
)
from .conftest import make_serializer_context

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


# ---------------- DatasetRelease.validate ----------------


def _make_dataset():
    return AnomalyDetectionDataset.objects.create(name="ds", description="", team=[1])


def test_release_validate_rejects_existing_non_failed_version(monkeypatch, mlops_user):
    context = make_serializer_context(monkeypatch, mlops_user)
    dataset = _make_dataset()
    AnomalyDetectionDatasetRelease.objects.create(
        name="r", description="", dataset=dataset, version="v1",
        dataset_file="x.zip", status="pending", metadata={}, file_size=1,
    )
    serializer = AnomalyDetectionDatasetReleaseSerializer(context=context)
    with pytest.raises(drf_serializers.ValidationError) as exc:
        serializer.validate({"dataset": dataset, "version": "v1"})
    assert "已存在" in str(exc.value)


def test_release_validate_allows_failed_retry_with_file_ids(monkeypatch, mlops_user):
    context = make_serializer_context(monkeypatch, mlops_user)
    dataset = _make_dataset()
    AnomalyDetectionDatasetRelease.objects.create(
        name="r", description="", dataset=dataset, version="v1",
        dataset_file="x.zip", status="failed", metadata={}, file_size=1,
    )
    serializer = AnomalyDetectionDatasetReleaseSerializer(context=context)
    attrs = serializer.validate(
        {"dataset": dataset, "version": "v1", "train_file_id": 1, "val_file_id": 2, "test_file_id": 3}
    )
    assert attrs["version"] == "v1"


def test_release_validate_no_dataset_or_version_passes(monkeypatch, mlops_user):
    context = make_serializer_context(monkeypatch, mlops_user)
    serializer = AnomalyDetectionDatasetReleaseSerializer(context=context)
    attrs = serializer.validate({"dataset": None, "version": None})
    assert attrs == {"dataset": None, "version": None}


# ---------------- DatasetRelease.create dispatch ----------------


def test_release_create_dispatches_to_from_files(monkeypatch, mlops_user):
    context = make_serializer_context(monkeypatch, mlops_user)
    serializer = AnomalyDetectionDatasetReleaseSerializer(context=context)
    sentinel = object()
    captured = {}

    def fake_from_files(validated_data, t, v, te):
        captured["args"] = (validated_data, t, v, te)
        return sentinel

    monkeypatch.setattr(serializer, "_create_from_files", fake_from_files)
    result = serializer.create(
        {"version": "v1", "train_file_id": 11, "val_file_id": 22, "test_file_id": 33}
    )
    assert result is sentinel
    # file ids popped, passed positionally
    assert captured["args"][1:] == (11, 22, 33)
    assert "train_file_id" not in captured["args"][0]


def test_release_create_standard_path_without_file_ids(monkeypatch, mlops_user):
    context = make_serializer_context(monkeypatch, mlops_user)
    serializer = AnomalyDetectionDatasetReleaseSerializer(context=context)

    # without all three file ids -> falls through to ModelSerializer.create
    not_called = Mock()
    monkeypatch.setattr(serializer, "_create_from_files", not_called)

    dataset = _make_dataset()
    release = serializer.create(
        {"dataset": dataset, "version": "v-std", "name": "n", "dataset_file": "f.zip"}
    )
    not_called.assert_not_called()
    assert isinstance(release, AnomalyDetectionDatasetRelease)
    assert release.version == "v-std"
    assert release.pk is not None


# ---------------- _create_from_files DoesNotExist branch ----------------


def test_create_from_files_missing_train_data_raises(monkeypatch, mlops_user):
    context = make_serializer_context(monkeypatch, mlops_user)
    dataset = _make_dataset()
    monkeypatch.setattr(
        "apps.mlops.tasks.anomaly_detection.publish_dataset_release_async.delay", Mock()
    )
    serializer = AnomalyDetectionDatasetReleaseSerializer(context=context)
    with pytest.raises(drf_serializers.ValidationError) as exc:
        serializer._create_from_files(
            {"dataset": dataset, "version": "v9"}, 9991, 9992, 9993
        )
    assert "训练数据文件不存在" in str(exc.value)


def test_create_from_files_success_creates_pending(monkeypatch, mlops_user):
    context = make_serializer_context(monkeypatch, mlops_user)
    dataset = _make_dataset()
    train = AnomalyDetectionTrainData.objects.create(name="t.csv", dataset=dataset, is_train_data=True)
    val = AnomalyDetectionTrainData.objects.create(name="v.csv", dataset=dataset, is_val_data=True)
    test = AnomalyDetectionTrainData.objects.create(name="te.csv", dataset=dataset, is_test_data=True)
    delay_mock = Mock(return_value=types.SimpleNamespace(id="task"))
    monkeypatch.setattr(
        "apps.mlops.tasks.anomaly_detection.publish_dataset_release_async.delay", delay_mock
    )
    serializer = AnomalyDetectionDatasetReleaseSerializer(context=context)
    release = serializer._create_from_files(
        {"dataset": dataset, "version": "v3"}, train.id, val.id, test.id
    )
    assert release.status == "pending"
    assert release.name == "ds_vv3"
    assert release.file_size == 0
    delay_mock.assert_called_once_with(release.id, train.id, val.id, test.id)


# ---------------- TrainData.validate_train_data (CSV) ----------------


def _train_request(query_params=None):
    return types.SimpleNamespace(
        query_params=query_params or {},
        COOKIES={"current_team": "1"},
        user=types.SimpleNamespace(is_superuser=False, group_list=[{"id": 1}]),
    )


def _train_data_serializer(monkeypatch, mlops_user):
    context = make_serializer_context(monkeypatch, mlops_user)
    context["request"] = _train_request()
    return AnomalyDetectionTrainDataSerializer(context=context)


def test_validate_train_data_valid_csv(monkeypatch, mlops_user):
    csv = io.BytesIO(b"timestamp,value,label\n2020-01-01 00:00:00,1.0,0\n2020-01-01 00:01:00,2.0,1\n")
    result = _train_data_serializer(monkeypatch, mlops_user).validate_train_data(csv)
    assert result is csv
    # pointer reset to start
    assert csv.tell() == 0


def test_validate_train_data_missing_columns(monkeypatch, mlops_user):
    csv = io.BytesIO(b"timestamp,value\n2020-01-01,1.0\n")
    with pytest.raises(drf_serializers.ValidationError) as exc:
        _train_data_serializer(monkeypatch, mlops_user).validate_train_data(csv)
    assert "缺少必需列" in str(exc.value)
    assert "label" in str(exc.value)


def test_validate_train_data_null_value(monkeypatch, mlops_user):
    csv = io.BytesIO(b"timestamp,value,label\n2020-01-01,,0\n2020-01-02,2.0,1\n")
    with pytest.raises(drf_serializers.ValidationError) as exc:
        _train_data_serializer(monkeypatch, mlops_user).validate_train_data(csv)
    assert "value" in str(exc.value)


def test_validate_train_data_null_label(monkeypatch, mlops_user):
    csv = io.BytesIO(b"timestamp,value,label\n2020-01-01,1.0,\n2020-01-02,2.0,1\n")
    with pytest.raises(drf_serializers.ValidationError) as exc:
        _train_data_serializer(monkeypatch, mlops_user).validate_train_data(csv)
    assert "label" in str(exc.value)


# ---------------- TrainData.__init__ include flags ----------------


def test_train_data_serializer_include_flags_from_request(monkeypatch, mlops_user):
    context = make_serializer_context(monkeypatch, mlops_user)
    context["request"] = _train_request(
        {"include_train_data": "TRUE", "include_metadata": "true"}
    )
    s = AnomalyDetectionTrainDataSerializer(context=context)
    assert s.include_train_data is True
    assert s.include_metadata is True


def test_train_data_serializer_include_flags_default_false(monkeypatch, mlops_user):
    context = make_serializer_context(monkeypatch, mlops_user)
    context["request"] = _train_request({})
    s = AnomalyDetectionTrainDataSerializer(context=context)
    assert s.include_train_data is False
    assert s.include_metadata is False


# ---------------- PredictRequest.validate_data ----------------


def test_predict_request_validate_data_empty():
    s = AnomalyDetectionPredictRequestSerializer()
    with pytest.raises(drf_serializers.ValidationError) as exc:
        s.validate_data([])
    assert "不能为空" in str(exc.value)


def test_predict_request_validate_data_too_few():
    s = AnomalyDetectionPredictRequestSerializer()
    with pytest.raises(drf_serializers.ValidationError) as exc:
        s.validate_data([{"timestamp": "t", "value": 1.0}])
    assert "至少需要2个" in str(exc.value)


def test_predict_request_validate_data_ok():
    s = AnomalyDetectionPredictRequestSerializer()
    data = [{"timestamp": "t1", "value": 1.0}, {"timestamp": "t2", "value": 2.0}]
    assert s.validate_data(data) == data
