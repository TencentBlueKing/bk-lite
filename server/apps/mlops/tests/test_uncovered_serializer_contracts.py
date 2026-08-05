"""补齐六类算法序列化器原先遗漏的数据读取与校验契约。"""

import copy
import importlib
from io import BytesIO
from types import SimpleNamespace

import pytest
from rest_framework import serializers

from apps.mlops.constants import DatasetReleaseStatus
from apps.mlops.serializers.object_detection import (
    ObjectDetectionDatasetReleaseSerializer,
    ObjectDetectionServingSerializer,
    ObjectDetectionTrainDataSerializer,
    ObjectDetectionTrainJobSerializer,
)
from apps.mlops.serializers.image_classification import (
    ImageClassificationDatasetReleaseSerializer,
    ImageClassificationServingSerializer,
    ImageClassificationTrainJobSerializer,
)


pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def serializer_context(mlops_user):
    return {
        "request": SimpleNamespace(
            user=mlops_user,
            COOKIES={"current_team": "1"},
            query_params={},
            build_absolute_uri=lambda url: (
                url if url.startswith(("http://", "https://")) else f"http://testserver{url}"
            ),
        )
    }


def _valid_yolo_metadata():
    return {
        "format": "YOLO",
        "classes": ["person"],
        "num_classes": 1,
        "num_images": 1,
        "labels": {
            "image.jpg": [
                {
                    "class_id": 0,
                    "class_name": "person",
                    "x_center": 0.5,
                    "y_center": 0.5,
                    "width": 0.4,
                    "height": 0.6,
                }
            ]
        },
        "statistics": {
            "total_annotations": 1,
            "class_distribution": {"person": 1},
        },
    }


def _set_path(value, path, replacement):
    target = value
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement
    return value


@pytest.mark.parametrize(
    ("path", "replacement", "message"),
    [
        (("format",), "COCO", "format"),
        (("classes",), "person", "classes 必须是数组"),
        (("classes",), [], "classes 不能为空"),
        (("classes",), [1], "所有元素必须是字符串"),
        (("num_classes",), 0, "num_classes 必须是正整数"),
        (("num_classes",), 2, "数组长度"),
        (("num_images",), 0, "num_images 必须是正整数"),
        (("labels",), [], "labels 必须是对象"),
        (("labels",), {1: []}, "键必须是字符串"),
        (("labels", "image.jpg"), {}, "标注必须是数组"),
        (("labels", "image.jpg"), ["bad"], "标注必须是对象"),
        (
            ("labels", "image.jpg", 0),
            {"class_id": 0},
            "标注缺少字段",
        ),
        (("labels", "image.jpg", 0, "class_id"), "0", "class_id 必须是整数"),
        (("labels", "image.jpg", 0, "class_id"), 2, "超出范围"),
        (("labels", "image.jpg", 0, "class_name"), 1, "class_name 必须是字符串"),
        (("labels", "image.jpg", 0, "class_name"), "car", "不匹配"),
        (("labels", "image.jpg", 0, "width"), "wide", "width 必须是数字"),
        (("labels", "image.jpg", 0, "height"), 1.1, "必须在"),
        (("statistics",), [], "statistics 必须是对象"),
        (
            ("statistics", "total_annotations"),
            -1,
            "total_annotations 必须是非负整数",
        ),
        (
            ("statistics", "class_distribution"),
            [],
            "class_distribution 必须是对象",
        ),
    ],
)
def test_object_detection_metadata_rejects_each_invalid_contract(
    path, replacement, message
):
    metadata = _set_path(copy.deepcopy(_valid_yolo_metadata()), path, replacement)
    with pytest.raises(serializers.ValidationError, match=message):
        ObjectDetectionTrainDataSerializer.validate_metadata(None, metadata)


def test_object_detection_metadata_accepts_empty_and_complete_yolo_contract():
    assert ObjectDetectionTrainDataSerializer.validate_metadata(None, None) is None
    metadata = _valid_yolo_metadata()
    assert (
        ObjectDetectionTrainDataSerializer.validate_metadata(None, metadata)
        is metadata
    )


def test_object_detection_metadata_reports_all_missing_top_level_fields():
    with pytest.raises(serializers.ValidationError) as exc:
        ObjectDetectionTrainDataSerializer.validate_metadata(
            None, {"format": "YOLO"}
        )
    assert "classes" in str(exc.value)
    assert "labels" in str(exc.value)


@pytest.mark.parametrize(
    ("value", "valid"),
    [("latest", True), ("3", True), ("v3", False)],
)
def test_object_detection_serving_model_version_contract(value, valid):
    if valid:
        assert (
            ObjectDetectionServingSerializer.validate_model_version(None, value)
            == value
        )
    else:
        with pytest.raises(serializers.ValidationError):
            ObjectDetectionServingSerializer.validate_model_version(None, value)


@pytest.mark.parametrize(
    ("value", "valid"),
    [
        ({"hyperparams": {"epochs": 10}}, True),
        ([], False),
        ({}, False),
        ({"hyperparams": []}, False),
    ],
)
def test_object_detection_hyperopt_config_contract(value, valid):
    if valid:
        assert (
            ObjectDetectionTrainJobSerializer.validate_hyperopt_config(None, value)
            is value
        )
    else:
        with pytest.raises(serializers.ValidationError):
            ObjectDetectionTrainJobSerializer.validate_hyperopt_config(None, value)


def test_object_detection_serving_exposes_runtime_port_and_status():
    obj = SimpleNamespace(
        container_info={"port": 19090, "status": "running"}, port=8080
    )
    assert ObjectDetectionServingSerializer.get_actual_port(None, obj) == 19090
    assert (
        ObjectDetectionServingSerializer.get_container_status(None, obj)
        == "running"
    )
    obj.container_info = {}
    assert ObjectDetectionServingSerializer.get_actual_port(None, obj) == 8080
    assert (
        ObjectDetectionServingSerializer.get_container_status(None, obj)
        == "unknown"
    )


@pytest.mark.parametrize(
    "serializer_class",
    [
        ImageClassificationDatasetReleaseSerializer,
        ObjectDetectionDatasetReleaseSerializer,
    ],
)
@pytest.mark.parametrize(("value", "valid"), [("v1.2.3", True), ("1.2.3", False)])
def test_image_dataset_release_version_contract(serializer_class, value, valid):
    if valid:
        assert serializer_class.validate_version(None, value) == value
    else:
        with pytest.raises(serializers.ValidationError):
            serializer_class.validate_version(None, value)


@pytest.mark.parametrize(
    "serializer_class",
    [
        ImageClassificationTrainJobSerializer,
        ObjectDetectionTrainJobSerializer,
    ],
)
@pytest.mark.parametrize(
    ("value", "valid"),
    [
        ({"hyperparams": {"epochs": 10}}, True),
        ("invalid", False),
        ({}, False),
        ({"hyperparams": []}, False),
    ],
)
def test_image_training_hyperopt_contract(serializer_class, value, valid):
    if valid:
        assert serializer_class.validate_hyperopt_config(None, value) is value
    else:
        with pytest.raises(serializers.ValidationError):
            serializer_class.validate_hyperopt_config(None, value)


@pytest.mark.parametrize(
    "serializer_class",
    [
        ImageClassificationTrainJobSerializer,
        ObjectDetectionTrainJobSerializer,
    ],
)
def test_image_training_config_url_is_made_absolute(serializer_class):
    serializer = SimpleNamespace(
        context={
            "request": SimpleNamespace(
                build_absolute_uri=lambda url: f"https://api.example{url}"
            )
        }
    )
    obj = SimpleNamespace(config_url=SimpleNamespace(url="/media/config.json"))
    assert serializer_class.get_config_url_display(serializer, obj) == (
        "https://api.example/media/config.json"
    )
    assert (
        serializer_class.get_config_url_display(
            serializer, SimpleNamespace(config_url=None)
        )
        is None
    )


def test_image_classification_serving_runtime_fallbacks_and_model_version():
    obj = SimpleNamespace(container_info={"port": 19090, "status": "ready"}, port=8080)
    assert ImageClassificationServingSerializer.get_actual_port(None, obj) == 19090
    assert (
        ImageClassificationServingSerializer.get_container_status(None, obj)
        == "ready"
    )
    obj.container_info = {}
    assert ImageClassificationServingSerializer.get_actual_port(None, obj) == 8080
    assert (
        ImageClassificationServingSerializer.get_container_status(None, obj)
        == "unknown"
    )
    with pytest.raises(serializers.ValidationError):
        ImageClassificationServingSerializer.validate_model_version(None, "v2")


ALGORITHMS = [
    ("anomaly_detection", "AnomalyDetection"),
    ("classification", "Classification"),
    ("log_clustering", "LogClustering"),
    ("timeseries_predict", "TimeSeriesPredict"),
    ("image_classification", "ImageClassification"),
    ("object_detection", "ObjectDetection"),
]


def _module(kind, suffix):
    return importlib.import_module(f"apps.mlops.{kind}.{suffix}")


def _model_classes(suffix, basename):
    model_module = _module("models", suffix)
    return (
        getattr(model_module, f"{basename}Dataset"),
        getattr(model_module, f"{basename}TrainData"),
    )


@pytest.mark.parametrize(("suffix", "basename"), ALGORITHMS[:4])
def test_legacy_dataset_release_metadata_without_algorithm_is_readable(
    serializer_context, suffix, basename
):
    model_module = _module("models", suffix)
    dataset = getattr(model_module, f"{basename}Dataset")(id=1, name="dataset", team=[1])
    release = getattr(model_module, f"{basename}DatasetRelease")(
        id=2,
        name="legacy",
        dataset=dataset,
        version="v1",
        dataset_file="",
        metadata={"train_samples": 1, "total_samples": 1},
    )

    data = getattr(_module("serializers", suffix), f"{basename}DatasetReleaseSerializer")(
        release, context=serializer_context
    ).data

    assert data["metadata"] == {"train_samples": 1, "total_samples": 1}
    assert "sample_count_algorithm" not in data["metadata"]


@pytest.mark.parametrize(
    ("suffix", "basename"),
    [
        ("log_clustering", "LogClustering"),
        ("timeseries_predict", "TimeSeriesPredict"),
        ("image_classification", "ImageClassification"),
    ],
)
def test_dataset_release_uniqueness_allows_update_and_failed_retry(
    suffix, basename
):
    model_module = _module("models", suffix)
    serializer_class = getattr(
        _module("serializers", suffix),
        f"{basename}DatasetReleaseSerializer",
    )
    Dataset = getattr(model_module, f"{basename}Dataset")
    Release = getattr(model_module, f"{basename}DatasetRelease")
    dataset = Dataset.objects.create(name=f"{suffix}-dataset", team=[1])
    release = Release.objects.create(
        name="release",
        dataset=dataset,
        version="v1.0.0",
        dataset_file="fixtures/release.zip",
        status=DatasetReleaseStatus.PUBLISHED,
        metadata={},
        file_size=1,
    )
    attrs = {
        "dataset": dataset,
        "version": "v1.0.0",
        "dataset_file": "fixtures/replacement.zip",
    }

    with pytest.raises(serializers.ValidationError):
        serializer_class.validate(SimpleNamespace(instance=None), attrs)

    assert (
        serializer_class.validate(SimpleNamespace(instance=release), attrs)
        is attrs
    )

    release.status = DatasetReleaseStatus.FAILED
    release.save(update_fields=["status"])
    retry = {
        **attrs,
        "train_file_id": 1,
        "val_file_id": 2,
        "test_file_id": 3,
    }
    assert (
        serializer_class.validate(SimpleNamespace(instance=None), retry)
        is retry
    )


@pytest.mark.parametrize("suffix,basename", ALGORITHMS)
def test_train_data_serializer_defaults_to_omitting_large_fields(
    serializer_context, suffix, basename
):
    serializer_class = getattr(
        _module("serializers", suffix), f"{basename}TrainDataSerializer"
    )
    Dataset, TrainData = _model_classes(suffix, basename)
    instance = TrainData(
        id=9,
        name="train",
        dataset=Dataset(id=1, name="dataset", team=[1]),
        train_data="fixtures/train.data",
        metadata={"source": "fixture"},
    )

    data = serializer_class(instance, context=serializer_context).data

    assert "train_data" not in data
    assert "metadata" not in data


@pytest.mark.parametrize(
    ("suffix", "basename", "content", "expected_key", "expected_value"),
    [
        (
            "log_clustering",
            "LogClustering",
            b"first log\n\nsecond log\n",
            "log",
            "first log",
        ),
        (
            "classification",
            "Classification",
            b"text,label\nhealthy,ok\n",
            "text",
            "healthy",
        ),
        (
            "anomaly_detection",
            "AnomalyDetection",
            b"timestamp,value\n2026-01-01T00:00:00Z,10\n",
            "value",
            10,
        ),
        (
            "timeseries_predict",
            "TimeSeriesPredict",
            b"timestamp,value\n2026-01-01T00:00:00Z,10\n",
            "value",
            10,
        ),
    ],
)
def test_text_and_csv_train_data_are_read_into_structured_rows(
    monkeypatch,
    serializer_context,
    suffix,
    basename,
    content,
    expected_key,
    expected_value,
):
    serializer_class = getattr(
        _module("serializers", suffix), f"{basename}TrainDataSerializer"
    )
    Dataset, TrainData = _model_classes(suffix, basename)
    instance = TrainData(
        id=9,
        name="train",
        dataset=Dataset(id=1, name="dataset", team=[1]),
        train_data="fixtures/train.data",
        metadata={"source": "fixture"},
    )
    field = instance.train_data
    if suffix == "log_clustering":
        monkeypatch.setattr(type(field), "read", lambda _self: content)
    else:
        monkeypatch.setattr(type(field), "open", lambda _self, _mode: BytesIO(content))
    request = serializer_context["request"]
    request.query_params = {
        "include_train_data": "true",
        "include_metadata": "true",
    }

    data = serializer_class(instance, context={"request": request}).data

    assert data["train_data"][0][expected_key] == expected_value
    if suffix != "log_clustering":
        assert data["train_data"][0]["index"] == 0
    assert data["metadata"] == {"source": "fixture"}


@pytest.mark.parametrize(
    ("suffix", "basename"),
    [
        ("log_clustering", "LogClustering"),
        ("classification", "Classification"),
        ("anomaly_detection", "AnomalyDetection"),
        ("timeseries_predict", "TimeSeriesPredict"),
    ],
)
def test_train_data_read_failure_is_a_structured_serializer_error(
    monkeypatch, serializer_context, suffix, basename
):
    serializer_class = getattr(
        _module("serializers", suffix), f"{basename}TrainDataSerializer"
    )
    Dataset, TrainData = _model_classes(suffix, basename)
    instance = TrainData(
        id=9,
        name="train",
        dataset=Dataset(id=1, name="dataset", team=[1]),
        train_data="fixtures/train.data",
        metadata={},
    )
    field = instance.train_data

    def reject(*_args):
        raise OSError("object unavailable")

    monkeypatch.setattr(type(field), "read", reject)
    monkeypatch.setattr(type(field), "open", reject)
    request = serializer_context["request"]
    request.query_params = {"include_train_data": "true"}

    data = serializer_class(instance, context={"request": request}).data

    assert data["train_data"] == []
    assert data["error"] == "读取训练数据失败: object unavailable"


@pytest.mark.parametrize(
    ("suffix", "basename"),
    [
        ("image_classification", "ImageClassification"),
        ("object_detection", "ObjectDetection"),
    ],
)
def test_image_train_data_query_flags_keep_requested_large_fields(
    serializer_context, suffix, basename
):
    serializer_class = getattr(
        _module("serializers", suffix), f"{basename}TrainDataSerializer"
    )
    Dataset, TrainData = _model_classes(suffix, basename)
    instance = TrainData(
        id=9,
        name="train",
        dataset=Dataset(id=1, name="dataset", team=[1]),
        train_data="fixtures/train.zip",
        metadata={"format": "zip"},
    )
    request = serializer_context["request"]
    request.query_params = {
        "include_train_data": "true",
        "include_metadata": "true",
    }

    data = serializer_class(instance, context={"request": request}).data

    assert data["train_data"].endswith("/fixtures/train.zip")
    assert data["metadata"] == {"format": "zip"}
