"""Parametrized tests for the per-algorithm Celery task wrappers.

The four CSV/TXT algorithms (anomaly_detection, classification, log_clustering,
timeseries) share a thin ``publish_dataset_release_async`` wrapper that
delegates to ``publish_dataset_release_base`` and maps SoftTimeLimit / generic
failures onto ``mark_release_as_failed`` + re-raise.
"""
import importlib
from types import SimpleNamespace
from unittest.mock import Mock

import pydantic.root_model  # noqa
import pytest
from celery.exceptions import SoftTimeLimitExceeded

pytestmark = pytest.mark.unit


# (task_module, model_module, basename)
WRAPPERS = [
    ("anomaly_detection", "anomaly_detection", "AnomalyDetection"),
    ("classification", "classification", "Classification"),
    ("log_clustering", "log_clustering", "LogClustering"),
    ("timeseries", "timeseries_predict", "TimeSeriesPredict"),
]
WRAPPER_IDS = [w[0] for w in WRAPPERS]


def _task_mod(task_module):
    return importlib.import_module(f"apps.mlops.tasks.{task_module}")


@pytest.mark.parametrize("task_module,model_module,basename", WRAPPERS, ids=WRAPPER_IDS)
def test_wrapper_delegates_to_base(monkeypatch, task_module, model_module, basename):
    tm = _task_mod(task_module)
    captured = {}

    def fake_base(config, release_id, t, v, te):
        captured["args"] = (config, release_id, t, v, te)
        return {"result": True, "release_id": release_id}

    monkeypatch.setattr(tm, "publish_dataset_release_base", fake_base)
    result = tm.publish_dataset_release_async.run(101, 1, 2, 3)
    assert result == {"result": True, "release_id": 101}
    assert captured["args"][1:] == (101, 1, 2, 3)
    # config carries the algorithm-specific publish config
    cfg = captured["args"][0]
    assert cfg.release_model is not None
    assert cfg.train_data_model is not None


@pytest.mark.parametrize("task_module,model_module,basename", WRAPPERS, ids=WRAPPER_IDS)
def test_wrapper_soft_timeout_marks_failed_and_reraises(monkeypatch, task_module, model_module, basename):
    tm = _task_mod(task_module)

    def boom(*a, **k):
        raise SoftTimeLimitExceeded()

    monkeypatch.setattr(tm, "publish_dataset_release_base", boom)
    mark_mock = Mock()
    monkeypatch.setattr(tm, "mark_release_as_failed", mark_mock)
    with pytest.raises(SoftTimeLimitExceeded):
        tm.publish_dataset_release_async.run(55, 1, 2, 3)
    mark_mock.assert_called_once()
    # release_id passed positionally
    assert mark_mock.call_args[0][1] == 55


@pytest.mark.parametrize("task_module,model_module,basename", WRAPPERS, ids=WRAPPER_IDS)
def test_wrapper_generic_failure_marks_failed_and_reraises(monkeypatch, task_module, model_module, basename):
    tm = _task_mod(task_module)

    def boom(*a, **k):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(tm, "publish_dataset_release_base", boom)
    mark_mock = Mock()
    monkeypatch.setattr(tm, "mark_release_as_failed", mark_mock)
    with pytest.raises(RuntimeError):
        tm.publish_dataset_release_async.run(77, 1, 2, 3)
    mark_mock.assert_called_once()
    assert mark_mock.call_args[0][1] == 77


@pytest.mark.parametrize("task_module,model_module,basename", WRAPPERS, ids=WRAPPER_IDS)
def test_get_config_shape(task_module, model_module, basename):
    tm = _task_mod(task_module)
    cfg = tm._get_config()
    assert cfg.task_type
    assert cfg.file_extension in ("csv", "txt")
    assert callable(cfg.count_samples)
    assert callable(cfg.build_metadata)


def _fake_data_obj(name, metadata=None):
    return SimpleNamespace(name=name, metadata=metadata)


def test_anomaly_metadata_counts_anomaly_points(monkeypatch):
    tm = _task_mod("anomaly_detection")
    train = _fake_data_obj("t", {"anomaly_point": [1, 2, 3]})
    val = _fake_data_obj("v", {"anomaly_point": [4]})
    test = _fake_data_obj("te", {})
    md = tm._build_anomaly_detection_metadata(80, 10, 10, train, val, test, 1, 2, 3)
    assert md["total_anomaly_count"] == 4
    assert md["train_anomaly_count"] == 3
    assert md["anomaly_rate"] == round(4 / 100, 4)
    assert md["features"] == ["timestamp", "value"]


def test_anomaly_get_anomaly_count_handles_missing_metadata():
    tm = _task_mod("anomaly_detection")
    assert tm._get_anomaly_count(_fake_data_obj("x", None)) == 0
    assert tm._get_anomaly_count(_fake_data_obj("x", {"anomaly_point": "notalist"})) == 0
    assert tm._get_anomaly_count(_fake_data_obj("x", {"anomaly_point": [1, 2]})) == 2


def test_classification_metadata_delegates_to_base():
    tm = _task_mod("classification")
    obj = _fake_data_obj("f")
    md = tm._build_classification_metadata(5, 2, 3, obj, obj, obj, 1, 2, 3)
    assert md["total_samples"] == 10
    assert "source" in md
