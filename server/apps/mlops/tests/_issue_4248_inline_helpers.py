"""Issue #4248：TrainData 列表内联读取资源边界回归。"""

import importlib
from io import BytesIO
from types import SimpleNamespace

SERIALIZER_CASES = (
    ("log_clustering", "LogClustering", b"first log\nsecond log\n"),
    ("classification", "Classification", b"text,label\nhealthy,ok\n"),
    (
        "anomaly_detection",
        "AnomalyDetection",
        b"timestamp,value\n2026-01-01T00:00:00Z,10\n",
    ),
    (
        "timeseries_predict",
        "TimeSeriesPredict",
        b"timestamp,value\n2026-01-01T00:00:00Z,10\n",
    ),
)

RECORD_LIMIT_CASES = (
    ("log_clustering", "LogClustering", b"first log\nsecond log\n"),
    (
        "classification",
        "Classification",
        b"text,label\nhealthy,ok\nunhealthy,bad\n",
    ),
    (
        "anomaly_detection",
        "AnomalyDetection",
        b"timestamp,value\n2026-01-01T00:00:00Z,10\n2026-01-02T00:00:00Z,20\n",
    ),
    (
        "timeseries_predict",
        "TimeSeriesPredict",
        b"timestamp,value\n2026-01-01T00:00:00Z,10\n2026-01-02T00:00:00Z,20\n",
    ),
)

CSV_SERIALIZER_CASES = (
    ("classification", "Classification"),
    ("anomaly_detection", "AnomalyDetection"),
    ("timeseries_predict", "TimeSeriesPredict"),
)

HTTP_TRAIN_DATA_CASES = (
    ("anomaly_detection", "AnomalyDetection", "anomaly_detection_train_data"),
    ("classification", "Classification", "classification_train_data"),
    ("log_clustering", "LogClustering", "log_clustering_train_data"),
    ("timeseries_predict", "TimeSeriesPredict", "timeseries_predict_train_data"),
)


def _request(mlops_user, *, include_train_data=True):
    return SimpleNamespace(
        user=mlops_user,
        COOKIES={"current_team": "1"},
        query_params={"include_train_data": "true" if include_train_data else "false"},
        build_absolute_uri=lambda url: (url if url.startswith(("http://", "https://")) else f"http://testserver{url}"),
    )


def _fixed_base_content(seed):
    return seed * max(1, 32 * 1024 // len(seed))


def _classes(suffix, basename):
    serializer_module = importlib.import_module(f"apps.mlops.serializers.{suffix}")
    model_module = importlib.import_module(f"apps.mlops.models.{suffix}")
    return (
        getattr(serializer_module, f"{basename}TrainDataSerializer"),
        getattr(model_module, f"{basename}Dataset"),
        getattr(model_module, f"{basename}TrainData"),
    )


def _instances(suffix, basename, count):
    serializer_class, Dataset, TrainData = _classes(suffix, basename)
    dataset = Dataset(id=1, name="dataset", team=[1])
    instances = [
        TrainData(
            id=index + 1,
            name=f"train-{index}",
            dataset=dataset,
            train_data=f"fixtures/{index}.data",
            metadata={},
        )
        for index in range(count)
    ]
    return serializer_class, instances


def _install_file_reader(monkeypatch, instances, content, stream_factory=BytesIO):
    reads = []

    def open_file(name, *_args, **_kwargs):
        reads.append(name)
        return stream_factory(content)

    monkeypatch.setattr(instances[0].train_data.storage, "open", open_file)
    return reads
