"""Tests for MLOps post_delete cleanup signal handlers (apps.mlops.signals.base).

The signal handlers run via ``transaction.on_commit``; we use
``django_capture_on_commit_callbacks(execute=True)`` to fire them and mock the
external boundaries (MLflow, WebhookClient, file storage).
"""
from unittest.mock import Mock

import pydantic.root_model  # noqa
import pytest

from apps.mlops import signals as signals_pkg  # noqa: ensures signals registered
from apps.mlops.constants import TrainJobStatus
from apps.mlops.models.anomaly_detection import (
    AnomalyDetectionDataset,
    AnomalyDetectionDatasetRelease,
    AnomalyDetectionServing,
    AnomalyDetectionTrainData,
    AnomalyDetectionTrainJob,
)
from apps.mlops.signals import base as signals_base

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _dataset():
    return AnomalyDetectionDataset.objects.create(name="ds", description="", team=[1])


def test_train_job_delete_triggers_mlflow_cleanup(monkeypatch, django_capture_on_commit_callbacks):
    delete_mock = Mock()
    monkeypatch.setattr(signals_base.mlflow_service, "delete_experiment_and_model", delete_mock)

    tj = AnomalyDetectionTrainJob.objects.create(
        name="job", description="", team=[1], status=TrainJobStatus.COMPLETED,
        algorithm="algo", dataset_version=None, hyperopt_config={},
    )
    with django_capture_on_commit_callbacks(execute=True):
        tj.delete()
    delete_mock.assert_called_once()


def test_train_job_delete_mlflow_failure_is_swallowed(monkeypatch, django_capture_on_commit_callbacks):
    def boom(**kwargs):
        raise RuntimeError("mlflow down")

    monkeypatch.setattr(signals_base.mlflow_service, "delete_experiment_and_model", boom)
    tj = AnomalyDetectionTrainJob.objects.create(
        name="job", description="", team=[1], status=TrainJobStatus.COMPLETED,
        algorithm="algo", dataset_version=None, hyperopt_config={},
    )
    # must not raise even though cleanup fails
    with django_capture_on_commit_callbacks(execute=True):
        tj.delete()
    assert not AnomalyDetectionTrainJob.objects.filter(id=tj.id).exists()


def test_serving_direct_delete_skips_container_cleanup(monkeypatch, django_capture_on_commit_callbacks):
    remove_mock = Mock()
    monkeypatch.setattr(signals_base.WebhookClient, "remove", staticmethod(remove_mock))

    tj = AnomalyDetectionTrainJob.objects.create(
        name="job", description="", team=[1], status=TrainJobStatus.COMPLETED,
        algorithm="algo", dataset_version=None, hyperopt_config={},
    )
    serving = AnomalyDetectionServing.objects.create(
        name="srv", description="", team=[1], train_job=tj,
        model_version="latest", status="inactive", container_info={},
    )
    # direct .delete() -> origin is the instance -> cleanup skipped
    with django_capture_on_commit_callbacks(execute=True):
        serving.delete()
    remove_mock.assert_not_called()


def test_serving_train_job_cascade_skips_container_cleanup(monkeypatch, django_capture_on_commit_callbacks):
    remove_mock = Mock()
    monkeypatch.setattr(signals_base.WebhookClient, "remove", staticmethod(remove_mock))

    tj = AnomalyDetectionTrainJob.objects.create(
        name="job", description="", team=[1], status=TrainJobStatus.COMPLETED,
        algorithm="algo", dataset_version=None, hyperopt_config={},
    )
    AnomalyDetectionServing.objects.create(
        name="srv", description="", team=[1], train_job=tj,
        model_version="latest", status="inactive", container_info={},
    )
    # deleting the train_job cascades to its servings -> cleanup skipped for cascade
    with django_capture_on_commit_callbacks(execute=True):
        tj.delete()
    remove_mock.assert_not_called()


def test_train_data_delete_runs_without_file(monkeypatch, django_capture_on_commit_callbacks):
    dataset = _dataset()
    td = AnomalyDetectionTrainData.objects.create(
        name="t.csv", dataset=dataset, is_train_data=True,
    )
    # no train_data file / no metadata -> handler takes the no-file debug branch
    with django_capture_on_commit_callbacks(execute=True):
        td.delete()
    assert not AnomalyDetectionTrainData.objects.filter(id=td.id).exists()


def test_train_job_delete_runs_without_config(monkeypatch, django_capture_on_commit_callbacks):
    # also patch mlflow cleanup so the train_job delete only exercises config branch
    monkeypatch.setattr(signals_base.mlflow_service, "delete_experiment_and_model", Mock())
    tj = AnomalyDetectionTrainJob.objects.create(
        name="job", description="", team=[1], status=TrainJobStatus.COMPLETED,
        algorithm="algo", dataset_version=None, hyperopt_config={},
    )
    # no config_url -> the train-job config cleanup takes the "no file" branch
    with django_capture_on_commit_callbacks(execute=True):
        tj.delete()
    assert not AnomalyDetectionTrainJob.objects.filter(id=tj.id).exists()


def test_dataset_release_delete_runs_without_file(monkeypatch, django_capture_on_commit_callbacks):
    dataset = _dataset()
    rel = AnomalyDetectionDatasetRelease.objects.create(
        name="r", description="", dataset=dataset, version="v1",
        dataset_file="", status="pending", metadata={}, file_size=0,
    )
    # no dataset_file -> the handler takes the "no file" branch, no error
    with django_capture_on_commit_callbacks(execute=True):
        rel.delete()
    assert not AnomalyDetectionDatasetRelease.objects.filter(id=rel.id).exists()
