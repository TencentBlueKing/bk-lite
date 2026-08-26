"""Tests for MLOps post_delete cleanup signal handlers (apps.mlops.signals.base).

The signal handlers run via ``transaction.on_commit``; we use
``django_capture_on_commit_callbacks(execute=True)`` to fire them and mock the
external boundaries (MLflow, WebhookClient, file storage).
"""
import importlib
import importlib.util
from unittest.mock import Mock

import pydantic.root_model  # noqa
import pytest

from apps.mlops import signals as signals_pkg  # noqa: ensures signals registered
from apps.mlops.constants import TrainJobStatus
from apps.mlops.models import ExternalResourceCleanupIntent
from apps.mlops.models.anomaly_detection import (
    AnomalyDetectionDataset,
    AnomalyDetectionDatasetRelease,
    AnomalyDetectionServing,
    AnomalyDetectionTrainData,
    AnomalyDetectionTrainJob,
)
from apps.mlops.models.classification import ClassificationTrainJob
from apps.mlops.models.image_classification import ImageClassificationTrainJob
from apps.mlops.models.log_clustering import LogClusteringTrainJob
from apps.mlops.models.object_detection import ObjectDetectionTrainJob
from apps.mlops.models.timeseries_predict import TimeSeriesPredictTrainJob
from apps.mlops.signals import base as signals_base
from apps.mlops.tasks.file_cleanup import cleanup_train_data_file

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _dataset():
    return AnomalyDetectionDataset.objects.create(name="ds", description="", team=[1])


def _cleanup_tasks():
    module_name = "apps.mlops.tasks.external_resource_cleanup"
    assert importlib.util.find_spec(module_name) is not None, "缺少持久清理任务"
    return importlib.import_module(module_name)


@pytest.mark.parametrize(
    ("train_job_model", "prefix"),
    [
        (AnomalyDetectionTrainJob, "AnomalyDetection"),
        (ClassificationTrainJob, "Classification"),
        (ImageClassificationTrainJob, "ImageClassification"),
        (LogClusteringTrainJob, "LogClustering"),
        (ObjectDetectionTrainJob, "ObjectDetection"),
        (TimeSeriesPredictTrainJob, "TimeseriesPredict"),
    ],
)
def test_six_train_job_types_persist_and_dispatch_mlflow_cleanup(
    monkeypatch,
    django_capture_on_commit_callbacks,
    train_job_model,
    prefix,
):
    cleanup_tasks = _cleanup_tasks()
    enqueue = Mock(return_value=True)
    monkeypatch.setattr(cleanup_tasks, "enqueue_external_resource_cleanup_intent", enqueue)

    tj = train_job_model.objects.create(
        name="job",
        description="",
        team=[1],
        status=TrainJobStatus.COMPLETED,
        algorithm="algo",
        dataset_version=None,
        hyperopt_config={},
    )
    train_job_id = tj.id
    with django_capture_on_commit_callbacks(execute=True):
        tj.delete()
    intent = ExternalResourceCleanupIntent.objects.get()
    assert intent.resource_type == ExternalResourceCleanupIntent.ResourceType.MLFLOW_EXPERIMENT_MODEL
    assert intent.payload == {
        "experiment_name": f"{prefix}_algo_{train_job_id}",
        "model_name": f"{prefix}_algo_{train_job_id}",
    }
    enqueue.assert_called_once_with(intent.pk, using="default")


def test_train_job_delete_rollback_removes_cleanup_intent(monkeypatch):
    cleanup_tasks = _cleanup_tasks()
    enqueue = Mock(return_value=True)
    monkeypatch.setattr(cleanup_tasks, "enqueue_external_resource_cleanup_intent", enqueue)
    tj = AnomalyDetectionTrainJob.objects.create(
        name="job",
        description="",
        team=[1],
        status=TrainJobStatus.COMPLETED,
        algorithm="algo",
        dataset_version=None,
        hyperopt_config={},
    )
    train_job_id = tj.id

    with pytest.raises(RuntimeError, match="rollback"):
        with signals_base.transaction.atomic():
            tj.delete()
            raise RuntimeError("rollback")

    assert AnomalyDetectionTrainJob.objects.filter(id=train_job_id).exists()
    assert not ExternalResourceCleanupIntent.objects.exists()
    enqueue.assert_not_called()


def test_serving_direct_delete_skips_container_cleanup(monkeypatch, django_capture_on_commit_callbacks):
    remove_mock = Mock()
    monkeypatch.setattr(signals_base.WebhookClient, "remove", staticmethod(remove_mock))

    tj = AnomalyDetectionTrainJob.objects.create(
        name="job",
        description="",
        team=[1],
        status=TrainJobStatus.COMPLETED,
        algorithm="algo",
        dataset_version=None,
        hyperopt_config={},
    )
    serving = AnomalyDetectionServing.objects.create(
        name="srv",
        description="",
        team=[1],
        train_job=tj,
        model_version="latest",
        status="inactive",
        container_info={},
    )
    # direct .delete() -> origin is the instance -> cleanup skipped
    with django_capture_on_commit_callbacks(execute=True):
        serving.delete()
    remove_mock.assert_not_called()


def test_serving_train_job_cascade_skips_container_cleanup(monkeypatch, django_capture_on_commit_callbacks):
    cleanup_tasks = _cleanup_tasks()
    remove_mock = Mock()
    monkeypatch.setattr(signals_base.WebhookClient, "remove", staticmethod(remove_mock))
    monkeypatch.setattr(
        cleanup_tasks,
        "enqueue_external_resource_cleanup_intent",
        Mock(return_value=True),
    )

    tj = AnomalyDetectionTrainJob.objects.create(
        name="job",
        description="",
        team=[1],
        status=TrainJobStatus.COMPLETED,
        algorithm="algo",
        dataset_version=None,
        hyperopt_config={},
    )
    AnomalyDetectionServing.objects.create(
        name="srv",
        description="",
        team=[1],
        train_job=tj,
        model_version="latest",
        status="inactive",
        container_info={},
    )
    # deleting the train_job cascades to its servings -> cleanup skipped for cascade
    with django_capture_on_commit_callbacks(execute=True):
        tj.delete()
    remove_mock.assert_not_called()


def test_train_data_delete_runs_without_file(monkeypatch, django_capture_on_commit_callbacks):
    dataset = _dataset()
    td = AnomalyDetectionTrainData.objects.create(
        name="t.csv",
        dataset=dataset,
        is_train_data=True,
    )
    # no train_data file / no metadata -> handler takes the no-file debug branch
    with django_capture_on_commit_callbacks(execute=True):
        td.delete()
    assert not AnomalyDetectionTrainData.objects.filter(id=td.id).exists()


def test_train_data_delete_registers_cleanup_on_the_write_database(monkeypatch):
    dataset = _dataset()
    td = AnomalyDetectionTrainData.objects.create(
        name="using.csv",
        dataset=dataset,
        is_train_data=True,
    )
    on_commit = Mock()
    monkeypatch.setattr(signals_base.transaction, "on_commit", on_commit)

    td.delete(using="default")

    on_commit.assert_called_once()
    assert on_commit.call_args.kwargs == {"using": "default"}


def test_train_data_delete_preserves_file_referenced_by_another_row(
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    dataset = _dataset()
    first = AnomalyDetectionTrainData.objects.create(
        name="first.csv",
        dataset=dataset,
        train_data="shared/deleted-row.csv",
        is_train_data=True,
    )
    AnomalyDetectionTrainData.objects.create(
        name="second.csv",
        dataset=dataset,
        train_data="shared/deleted-row.csv",
        is_train_data=True,
    )
    storage = AnomalyDetectionTrainData._meta.get_field("train_data").storage
    delete = Mock()
    monkeypatch.setattr(storage, "delete", delete)

    with django_capture_on_commit_callbacks(execute=True):
        first.delete()

    delete.assert_not_called()


def test_train_data_delete_storage_failure_schedules_retry(
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    dataset = _dataset()
    td = AnomalyDetectionTrainData.objects.create(
        name="retry.csv",
        dataset=dataset,
        train_data="shared/delete-retry.csv",
        is_train_data=True,
    )
    instance_pk = td.pk
    storage = AnomalyDetectionTrainData._meta.get_field("train_data").storage
    monkeypatch.setattr(
        storage,
        "delete",
        Mock(side_effect=OSError("object storage unavailable")),
    )
    apply_async = Mock()
    monkeypatch.setattr(cleanup_train_data_file, "apply_async", apply_async)

    with django_capture_on_commit_callbacks(execute=True):
        td.delete()

    apply_async.assert_called_once_with(
        kwargs={
            "model_label": "mlops.AnomalyDetectionTrainData",
            "instance_pk": instance_pk,
            "file_field_name": "train_data",
            "old_path": "shared/delete-retry.csv",
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


def test_train_job_delete_runs_without_config(monkeypatch, django_capture_on_commit_callbacks):
    # The train-job delete only exercises the config branch in this test.
    cleanup_tasks = _cleanup_tasks()
    monkeypatch.setattr(
        cleanup_tasks,
        "enqueue_external_resource_cleanup_intent",
        Mock(return_value=True),
    )
    tj = AnomalyDetectionTrainJob.objects.create(
        name="job",
        description="",
        team=[1],
        status=TrainJobStatus.COMPLETED,
        algorithm="algo",
        dataset_version=None,
        hyperopt_config={},
    )
    # no config_url -> the train-job config cleanup takes the "no file" branch
    with django_capture_on_commit_callbacks(execute=True):
        tj.delete()
    assert not AnomalyDetectionTrainJob.objects.filter(id=tj.id).exists()


def test_dataset_release_delete_runs_without_file(monkeypatch, django_capture_on_commit_callbacks):
    dataset = _dataset()
    rel = AnomalyDetectionDatasetRelease.objects.create(
        name="r",
        description="",
        dataset=dataset,
        version="v1",
        dataset_file="",
        status="pending",
        metadata={},
        file_size=0,
    )
    # no dataset_file -> the handler takes the "no file" branch, no error
    with django_capture_on_commit_callbacks(execute=True):
        rel.delete()
    assert not AnomalyDetectionDatasetRelease.objects.filter(id=rel.id).exists()
