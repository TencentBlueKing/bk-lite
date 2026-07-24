"""Parametrized API-action tests across all six MLOps algorithm view modules.

Every algorithm exposes structurally identical TrainJob / DatasetRelease /
Serving viewsets.  We drive each action through ``ViewSet.as_view`` with a
superuser (bypasses HasPermission + team scoping) and mock only the true
external boundaries: ``mlflow_service`` (MLflow tracking server),
``WebhookClient`` (webhookd / docker), ``requests`` (predict HTTP call) and the
config helpers (env vars).
"""
import asyncio
import importlib
import types
from io import BytesIO
from unittest.mock import Mock

import pandas as pd
import pydantic.root_model  # noqa
import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.base.tests.factories import UserFactory
from apps.mlops.constants import DatasetReleaseStatus, MLflowRunStatus, TrainJobStatus
from apps.mlops.utils.webhook_client import WebhookError

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

factory = APIRequestFactory()


async def _consume_streaming_response(response):
    return b"".join([chunk async for chunk in response])


# Each tuple: (module suffix, MLflow prefix, model module, class basename)
# Note: ``prefix`` is the *actual* MLFLOW_PREFIX used in the production view
# (TimeseriesPredict has a lowercase 's', and is intentionally kept verbatim).
ALGOS = [
    ("anomaly_detection", "AnomalyDetection", "anomaly_detection", "AnomalyDetection"),
    ("classification", "Classification", "classification", "Classification"),
    ("log_clustering", "LogClustering", "log_clustering", "LogClustering"),
    ("timeseries_predict", "TimeseriesPredict", "timeseries_predict", "TimeSeriesPredict"),
    ("image_classification", "ImageClassification", "image_classification", "ImageClassification"),
    ("object_detection", "ObjectDetection", "object_detection", "ObjectDetection"),
]

ALGO_IDS = [a[0] for a in ALGOS]

# Predict request param name per algorithm.
PREDICT_PARAM = {
    "anomaly_detection": "data",
    "log_clustering": "data",
    "timeseries_predict": "data",
    "classification": "texts",
    "image_classification": "images",
    "object_detection": "images",
}

# Algorithms whose DatasetReleaseViewSet exposes archive/unarchive.
HAS_ARCHIVE = {"anomaly_detection", "log_clustering", "timeseries_predict",
               "image_classification", "object_detection"}

# Algorithms whose archive/unarchive also mutate ``description`` (prepend /
# strip the "[已归档] " marker). image/object only flip ``status``.
ARCHIVE_TOUCHES_DESCRIPTION = {"anomaly_detection", "log_clustering", "timeseries_predict"}

# Algorithms whose predict does NOT interpret the business ``success`` flag and
# returns the raw 200 payload as-is.
PREDICT_RAW_PASSTHROUGH = {"object_detection", "image_classification"}

# Algorithms whose serving ``start`` treats a raised ConfigurationError via the
# generic Exception handler (returns "启动服务失败" instead of the explicit
# MLFLOW_TRACKER_URL message). These check ``if not uri`` rather than catching
# ConfigurationError.
START_GENERIC_CONFIG = {"classification", "image_classification", "object_detection"}


def _view_module(suffix):
    return importlib.import_module(f"apps.mlops.views.{suffix}")


def _model(model_module, basename, kind):
    mod = importlib.import_module(f"apps.mlops.models.{model_module}")
    return getattr(mod, f"{basename}{kind}")


@pytest.fixture
def superuser():
    return UserFactory(username="mlops-su", domain="domain.com", roles=[], is_superuser=True)


def _call(view, request, superuser, **kwargs):
    force_authenticate(request, user=superuser)
    # Supply the current-team context that team-scoped list/retrieve relies on.
    request.COOKIES["current_team"] = "1"
    return view(request, **kwargs)


def _make_train_job(model_module, basename, *, status_value=TrainJobStatus.COMPLETED, with_version=False):
    TrainJob = _model(model_module, basename, "TrainJob")
    dataset_version = None
    if with_version:
        Dataset = _model(model_module, basename, "Dataset")
        Release = _model(model_module, basename, "DatasetRelease")
        ds = Dataset.objects.create(name="ds", description="", team=[1])
        dataset_version = Release.objects.create(
            name="r", description="", dataset=ds, version="v1",
            dataset_file="path/to/file.zip", status=DatasetReleaseStatus.PUBLISHED,
            metadata={}, file_size=10,
        )
    return TrainJob.objects.create(
        name="job", description="", team=[1], status=status_value,
        algorithm="demo-algo", dataset_version=dataset_version, hyperopt_config={},
    )


def _make_serving(model_module, basename, *, container_info=None, port=None, status_value="inactive"):
    train_job = _make_train_job(model_module, basename)
    Serving = _model(model_module, basename, "Serving")
    return Serving.objects.create(
        name="srv", description="", team=[1], train_job=train_job,
        model_version="latest", port=port, status=status_value,
        container_info=container_info or {},
    )


def _make_release(model_module, basename, *, status_value=DatasetReleaseStatus.PUBLISHED, description=""):
    Dataset = _model(model_module, basename, "Dataset")
    Release = _model(model_module, basename, "DatasetRelease")
    ds = Dataset.objects.create(name="ds", description="", team=[1])
    return Release.objects.create(
        name="r", description=description, dataset=ds, version="v1",
        dataset_file="path/file.zip", status=status_value, metadata={}, file_size=10,
    )


def _patch_mlflow(monkeypatch, suffix, **overrides):
    """Patch the module-level ``mlflow_service`` reference for a view module."""
    mod = _view_module(suffix)
    ms = mod.mlflow_service
    defaults = {
        "build_experiment_name": lambda **kw: "exp-name",
        "build_model_name": lambda **kw: "model-name",
        "build_job_id": lambda **kw: "job-id",
        "get_experiment_by_name": lambda name: None,
        "get_experiment_runs": lambda eid, **kw: pd.DataFrame({"run_id": []}),
        "get_model_versions": lambda name: [],
        "resolve_model_uri": lambda name, version: "models:/model-name/1",
        "delete_run": lambda run_id: None,
        "get_run_metrics": lambda run_id, filter_system=True: ["accuracy"],
        "get_metric_history": lambda run_id, metric_name: [{"step": 1, "value": 0.9}],
        "get_run_params": lambda run_id: {"epochs": "5"},
        "get_run_info": lambda run_id: types.SimpleNamespace(
            data=types.SimpleNamespace(tags={"mlflow.runName": "run-x"}),
            info=types.SimpleNamespace(status="FINISHED", start_time=1000, end_time=2000),
        ),
        "download_model_artifact": lambda run_id, artifact_path=None: BytesIO(b"zip"),
    }
    defaults.update(overrides)
    for name, fn in defaults.items():
        monkeypatch.setattr(ms, name, fn, raising=False)
    return ms


def _runs_frame(rows):
    return pd.DataFrame(rows)


# =========================================================================
# TrainJob: train action
# =========================================================================


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_train_rejects_already_running(monkeypatch, superuser, suffix, prefix, model_module, basename):
    tj = _make_train_job(model_module, basename, status_value=TrainJobStatus.RUNNING)
    mod = _view_module(suffix)
    view = getattr(mod, f"{basename}TrainJobViewSet").as_view({"post": "train"})
    request = factory.post(f"/{suffix}_train_jobs/x/train/")
    resp = _call(view, request, superuser, pk=tj.id)
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "运行中" in resp.data["error"]


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_train_config_error_returns_500(monkeypatch, superuser, suffix, prefix, model_module, basename):
    from apps.mlops.services import ConfigurationError

    tj = _make_train_job(model_module, basename, status_value=TrainJobStatus.PENDING)
    mod = _view_module(suffix)

    def boom():
        raise ConfigurationError("missing env")

    monkeypatch.setattr(mod, "get_mlflow_train_config", boom)
    view = getattr(mod, f"{basename}TrainJobViewSet").as_view({"post": "train"})
    request = factory.post(f"/{suffix}_train_jobs/x/train/")
    resp = _call(view, request, superuser, pk=tj.id)
    assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "系统配置错误" in resp.data["error"]


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_train_missing_dataset_file(monkeypatch, superuser, suffix, prefix, model_module, basename):
    tj = _make_train_job(model_module, basename, status_value=TrainJobStatus.PENDING)
    mod = _view_module(suffix)
    monkeypatch.setattr(
        mod, "get_mlflow_train_config",
        lambda: types.SimpleNamespace(
            bucket="b", minio_endpoint="e", mlflow_tracking_uri="u",
            minio_access_key="ak", minio_secret_key="sk",
        ),
    )
    view = getattr(mod, f"{basename}TrainJobViewSet").as_view({"post": "train"})
    request = factory.post(f"/{suffix}_train_jobs/x/train/")
    resp = _call(view, request, superuser, pk=tj.id)
    # no dataset_version -> 数据集文件不存在
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "数据集文件不存在" in resp.data["error"]


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_train_missing_config_url(monkeypatch, superuser, suffix, prefix, model_module, basename):
    tj = _make_train_job(model_module, basename, status_value=TrainJobStatus.PENDING, with_version=True)
    mod = _view_module(suffix)
    monkeypatch.setattr(
        mod, "get_mlflow_train_config",
        lambda: types.SimpleNamespace(
            bucket="b", minio_endpoint="e", mlflow_tracking_uri="u",
            minio_access_key="ak", minio_secret_key="sk",
        ),
    )
    # dataset_version has a dataset_file but train_job has no config_url
    view = getattr(mod, f"{basename}TrainJobViewSet").as_view({"post": "train"})
    request = factory.post(f"/{suffix}_train_jobs/x/train/")
    resp = _call(view, request, superuser, pk=tj.id)
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "训练配置文件不存在" in resp.data["error"]


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_train_happy_path(monkeypatch, superuser, suffix, prefix, model_module, basename):
    # Build a train job with dataset_version + config_url so we reach launch.
    TrainJob = _model(model_module, basename, "TrainJob")
    Dataset = _model(model_module, basename, "Dataset")
    Release = _model(model_module, basename, "DatasetRelease")
    ds = Dataset.objects.create(name="ds", description="", team=[1])
    dv = Release.objects.create(
        name="r", description="", dataset=ds, version="v1",
        dataset_file="path/data.zip", status=DatasetReleaseStatus.PUBLISHED,
        metadata={}, file_size=10,
    )
    tj = TrainJob.objects.create(
        name="job", description="", team=[1], status=TrainJobStatus.PENDING,
        algorithm="demo-algo", dataset_version=dv, hyperopt_config={},
    )
    # Set config_url directly in DB to bypass TrainJobConfigSyncMixin.save(),
    # which would otherwise wipe config_url when hyperopt_config is empty.
    TrainJob.objects.filter(pk=tj.pk).update(config_url="path/config.json")
    tj.refresh_from_db()

    mod = _view_module(suffix)
    monkeypatch.setattr(
        mod, "get_mlflow_train_config",
        lambda: types.SimpleNamespace(
            bucket="b", minio_endpoint="e", mlflow_tracking_uri="u",
            minio_access_key="ak", minio_secret_key="sk",
        ),
    )
    monkeypatch.setattr(mod, "get_image_by_prefix", lambda p, algo: "repo/train:1")
    _patch_mlflow(monkeypatch, suffix)
    monkeypatch.setattr(mod.WebhookClient, "stop", staticmethod(Mock()))
    train_mock = Mock(return_value={"ok": True})
    monkeypatch.setattr(mod.WebhookClient, "train", staticmethod(train_mock))

    from apps.mlops.tasks.poll_train_job_status import poll_train_job_status as poll_task
    delay_mock = Mock()
    monkeypatch.setattr(poll_task, "delay", delay_mock)

    view = getattr(mod, f"{basename}TrainJobViewSet").as_view({"post": "train"})
    request = factory.post(f"/{suffix}_train_jobs/x/train/")
    resp = _call(view, request, superuser, pk=tj.id)
    assert resp.status_code == status.HTTP_200_OK
    assert "train_job_id" in resp.data
    train_mock.assert_called_once()
    delay_mock.assert_called_once()
    tj.refresh_from_db()
    assert tj.status == TrainJobStatus.RUNNING


# =========================================================================
# TrainJob: stop action
# =========================================================================


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_stop_not_running_rejected(monkeypatch, superuser, suffix, prefix, model_module, basename):
    tj = _make_train_job(model_module, basename, status_value=TrainJobStatus.COMPLETED)
    mod = _view_module(suffix)
    view = getattr(mod, f"{basename}TrainJobViewSet").as_view({"post": "stop"})
    request = factory.post(f"/{suffix}_train_jobs/x/stop/")
    resp = _call(view, request, superuser, pk=tj.id)
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "未在运行中" in resp.data["error"]


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_stop_running_success(monkeypatch, superuser, suffix, prefix, model_module, basename):
    tj = _make_train_job(model_module, basename, status_value=TrainJobStatus.RUNNING)
    mod = _view_module(suffix)
    _patch_mlflow(monkeypatch, suffix)
    stop_mock = Mock(return_value={"ok": True})
    monkeypatch.setattr(mod.WebhookClient, "stop", staticmethod(stop_mock))
    view = getattr(mod, f"{basename}TrainJobViewSet").as_view({"post": "stop"})
    request = factory.post(f"/{suffix}_train_jobs/x/stop/")
    resp = _call(view, request, superuser, pk=tj.id)
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["webhook_response"] == {"ok": True}
    tj.refresh_from_db()
    assert tj.status == TrainJobStatus.PENDING
    stop_mock.assert_called_once()


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_stop_webhook_error_returns_500(monkeypatch, superuser, suffix, prefix, model_module, basename):
    tj = _make_train_job(model_module, basename, status_value=TrainJobStatus.RUNNING)
    mod = _view_module(suffix)
    _patch_mlflow(monkeypatch, suffix)

    def raise_err(job_id):
        raise WebhookError("boom")

    monkeypatch.setattr(mod.WebhookClient, "stop", staticmethod(raise_err))
    view = getattr(mod, f"{basename}TrainJobViewSet").as_view({"post": "stop"})
    request = factory.post(f"/{suffix}_train_jobs/x/stop/")
    resp = _call(view, request, superuser, pk=tj.id)
    assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    # status not changed
    tj.refresh_from_db()
    assert tj.status == TrainJobStatus.RUNNING


# =========================================================================
# TrainJob: runs_data_list action
# =========================================================================


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_runs_data_list_no_experiment(monkeypatch, superuser, suffix, prefix, model_module, basename):
    tj = _make_train_job(model_module, basename)
    mod = _view_module(suffix)
    _patch_mlflow(monkeypatch, suffix, get_experiment_by_name=lambda name: None)
    view = getattr(mod, f"{basename}TrainJobViewSet").as_view({"get": "get_run_data_list"})
    request = factory.get(f"/{suffix}_train_jobs/x/runs_data_list/")
    resp = _call(view, request, superuser, pk=tj.id)
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["count"] == 0
    assert resp.data["items"] == []
    assert "未找到对应的MLflow实验" in resp.data["message"]


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_runs_data_list_empty_runs(monkeypatch, superuser, suffix, prefix, model_module, basename):
    tj = _make_train_job(model_module, basename)
    mod = _view_module(suffix)
    _patch_mlflow(
        monkeypatch, suffix,
        get_experiment_by_name=lambda name: types.SimpleNamespace(experiment_id="1"),
        get_experiment_runs=lambda eid, **kw: pd.DataFrame({"run_id": []}),
    )
    view = getattr(mod, f"{basename}TrainJobViewSet").as_view({"get": "get_run_data_list"})
    request = factory.get(f"/{suffix}_train_jobs/x/runs_data_list/")
    resp = _call(view, request, superuser, pk=tj.id)
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["count"] == 0
    assert "未找到训练运行记录" in resp.data["message"]


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_runs_data_list_with_runs_and_pagination(monkeypatch, superuser, suffix, prefix, model_module, basename):
    tj = _make_train_job(model_module, basename, status_value=TrainJobStatus.COMPLETED)
    mod = _view_module(suffix)
    t0 = pd.Timestamp("2020-01-01 00:00:00", tz="UTC")
    t1 = pd.Timestamp("2020-01-01 00:10:00", tz="UTC")
    runs = pd.DataFrame(
        [
            {"run_id": "r1", "status": "FINISHED", "start_time": t0, "end_time": t1,
             "tags.mlflow.runName": "first"},
            {"run_id": "r2", "status": "FINISHED", "start_time": t0, "end_time": t1,
             "tags.mlflow.runName": "second"},
            {"run_id": "r3", "status": "FINISHED", "start_time": t0, "end_time": t1,
             "tags.mlflow.runName": "third"},
        ]
    )
    _patch_mlflow(
        monkeypatch, suffix,
        get_experiment_by_name=lambda name: types.SimpleNamespace(experiment_id="1"),
        get_experiment_runs=lambda eid, **kw: runs,
    )
    view = getattr(mod, f"{basename}TrainJobViewSet").as_view({"get": "get_run_data_list"})
    request = factory.get(f"/{suffix}_train_jobs/x/runs_data_list/?page=1&page_size=2")
    resp = _call(view, request, superuser, pk=tj.id)
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["count"] == 3
    assert len(resp.data["items"]) == 2  # paginated
    item = resp.data["items"][0]
    assert item["run_id"] == "r1"
    assert item["duration_minutes"] == pytest.approx(10.0)
    # completed job -> all deletable
    assert item["can_delete_run"] is True


# =========================================================================
# TrainJob: delete_run action
# =========================================================================


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_delete_run_not_found(monkeypatch, superuser, suffix, prefix, model_module, basename):
    tj = _make_train_job(model_module, basename)
    mod = _view_module(suffix)
    _patch_mlflow(
        monkeypatch, suffix,
        get_experiment_by_name=lambda name: types.SimpleNamespace(experiment_id="1"),
        get_experiment_runs=lambda eid, **kw: _runs_frame([{"run_id": "other", "status": "FINISHED"}]),
    )
    view = getattr(mod, f"{basename}TrainJobViewSet").as_view({"delete": "delete_run"})
    request = factory.delete(f"/{suffix}_train_jobs/x/runs/missing/")
    resp = _call(view, request, superuser, pk=tj.id, run_id="missing")
    assert resp.status_code == status.HTTP_404_NOT_FOUND
    assert resp.data["code"] == "run_not_found"


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_delete_run_blocked_active_latest(monkeypatch, superuser, suffix, prefix, model_module, basename):
    tj = _make_train_job(model_module, basename, status_value=TrainJobStatus.RUNNING)
    mod = _view_module(suffix)
    _patch_mlflow(
        monkeypatch, suffix,
        get_experiment_by_name=lambda name: types.SimpleNamespace(experiment_id="1"),
        get_experiment_runs=lambda eid, **kw: _runs_frame([{"run_id": "r1", "status": MLflowRunStatus.RUNNING}]),
    )
    view = getattr(mod, f"{basename}TrainJobViewSet").as_view({"delete": "delete_run"})
    request = factory.delete(f"/{suffix}_train_jobs/x/runs/r1/")
    resp = _call(view, request, superuser, pk=tj.id, run_id="r1")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.data["code"] == "active_latest_run"


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_delete_run_success(monkeypatch, superuser, suffix, prefix, model_module, basename):
    tj = _make_train_job(model_module, basename, status_value=TrainJobStatus.COMPLETED)
    mod = _view_module(suffix)
    delete_calls = []
    _patch_mlflow(
        monkeypatch, suffix,
        get_experiment_by_name=lambda name: types.SimpleNamespace(experiment_id="1"),
        get_experiment_runs=lambda eid, **kw: _runs_frame([{"run_id": "r1", "status": "FINISHED"}]),
        delete_run=lambda run_id: delete_calls.append(run_id),
    )
    view = getattr(mod, f"{basename}TrainJobViewSet").as_view({"delete": "delete_run"})
    request = factory.delete(f"/{suffix}_train_jobs/x/runs/r1/")
    resp = _call(view, request, superuser, pk=tj.id, run_id="r1")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["deleted"] is True
    assert delete_calls == ["r1"]


# =========================================================================
# TrainJob: metrics_list / metric_data / run_params / model_versions
# =========================================================================


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_metrics_list_run_not_found(monkeypatch, superuser, suffix, prefix, model_module, basename):
    tj = _make_train_job(model_module, basename)
    mod = _view_module(suffix)
    _patch_mlflow(
        monkeypatch, suffix,
        get_experiment_by_name=lambda name: types.SimpleNamespace(experiment_id="1"),
        get_experiment_runs=lambda eid, **kw: _runs_frame([{"run_id": "other"}]),
    )
    view = getattr(mod, f"{basename}TrainJobViewSet").as_view({"get": "get_runs_metrics_list"})
    request = factory.get(f"/{suffix}_train_jobs/x/runs/r1/metrics_list/")
    resp = _call(view, request, superuser, pk=tj.id, run_id="r1")
    assert resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_metrics_list_success(monkeypatch, superuser, suffix, prefix, model_module, basename):
    tj = _make_train_job(model_module, basename)
    mod = _view_module(suffix)
    _patch_mlflow(
        monkeypatch, suffix,
        get_experiment_by_name=lambda name: types.SimpleNamespace(experiment_id="1"),
        get_experiment_runs=lambda eid, **kw: _runs_frame([{"run_id": "r1"}]),
        get_run_metrics=lambda run_id, filter_system=True: ["accuracy", "loss"],
    )
    view = getattr(mod, f"{basename}TrainJobViewSet").as_view({"get": "get_runs_metrics_list"})
    request = factory.get(f"/{suffix}_train_jobs/x/runs/r1/metrics_list/")
    resp = _call(view, request, superuser, pk=tj.id, run_id="r1")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["metrics"] == ["accuracy", "loss"]
    assert resp.data["run_id"] == "r1"


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_metric_data_empty(monkeypatch, superuser, suffix, prefix, model_module, basename):
    tj = _make_train_job(model_module, basename)
    mod = _view_module(suffix)
    _patch_mlflow(
        monkeypatch, suffix,
        get_experiment_by_name=lambda name: types.SimpleNamespace(experiment_id="1"),
        get_experiment_runs=lambda eid, **kw: _runs_frame([{"run_id": "r1"}]),
        get_metric_history=lambda run_id, metric_name: [],
    )
    view = getattr(mod, f"{basename}TrainJobViewSet").as_view({"get": "get_metric_data"})
    request = factory.get(f"/{suffix}_train_jobs/x/runs/r1/metrics_history/acc/")
    resp = _call(view, request, superuser, pk=tj.id, run_id="r1", metric_name="acc")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["total_points"] == 0


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_metric_data_with_points(monkeypatch, superuser, suffix, prefix, model_module, basename):
    tj = _make_train_job(model_module, basename)
    mod = _view_module(suffix)
    _patch_mlflow(
        monkeypatch, suffix,
        get_experiment_by_name=lambda name: types.SimpleNamespace(experiment_id="1"),
        get_experiment_runs=lambda eid, **kw: _runs_frame([{"run_id": "r1"}]),
        get_metric_history=lambda run_id, metric_name: [{"step": 1, "value": 0.5}, {"step": 2, "value": 0.7}],
    )
    view = getattr(mod, f"{basename}TrainJobViewSet").as_view({"get": "get_metric_data"})
    request = factory.get(f"/{suffix}_train_jobs/x/runs/r1/metrics_history/acc/")
    resp = _call(view, request, superuser, pk=tj.id, run_id="r1", metric_name="acc")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["total_points"] == 2


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_run_params_success(monkeypatch, superuser, suffix, prefix, model_module, basename):
    tj = _make_train_job(model_module, basename)
    mod = _view_module(suffix)
    _patch_mlflow(
        monkeypatch, suffix,
        get_experiment_by_name=lambda name: types.SimpleNamespace(experiment_id="1"),
        get_experiment_runs=lambda eid, **kw: _runs_frame([{"run_id": "r1"}]),
        get_run_params=lambda run_id: {"lr": "0.01"},
    )
    view = getattr(mod, f"{basename}TrainJobViewSet").as_view({"get": "get_run_params"})
    request = factory.get(f"/{suffix}_train_jobs/x/runs/r1/run_params/")
    resp = _call(view, request, superuser, pk=tj.id, run_id="r1")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["params"] == {"lr": "0.01"}
    assert resp.data["run_name"] == "run-x"


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_model_versions_empty(monkeypatch, superuser, suffix, prefix, model_module, basename):
    tj = _make_train_job(model_module, basename)
    mod = _view_module(suffix)
    _patch_mlflow(monkeypatch, suffix, get_model_versions=lambda name: [])
    view = getattr(mod, f"{basename}TrainJobViewSet").as_view({"get": "get_model_versions"})
    request = factory.get(f"/{suffix}_train_jobs/x/model_versions/")
    resp = _call(view, request, superuser, pk=tj.id)
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["total"] == 0
    assert resp.data["versions"] == []


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_model_versions_present(monkeypatch, superuser, suffix, prefix, model_module, basename):
    tj = _make_train_job(model_module, basename)
    mod = _view_module(suffix)
    _patch_mlflow(monkeypatch, suffix, get_model_versions=lambda name: [{"version": "1"}, {"version": "2"}])
    view = getattr(mod, f"{basename}TrainJobViewSet").as_view({"get": "get_model_versions"})
    request = factory.get(f"/{suffix}_train_jobs/x/model_versions/")
    resp = _call(view, request, superuser, pk=tj.id)
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["total"] == 2


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_download_model_run_not_found(monkeypatch, superuser, suffix, prefix, model_module, basename):
    tj = _make_train_job(model_module, basename)
    mod = _view_module(suffix)
    _patch_mlflow(
        monkeypatch, suffix,
        get_experiment_by_name=lambda name: types.SimpleNamespace(experiment_id="1"),
        get_experiment_runs=lambda eid, **kw: _runs_frame([{"run_id": "other"}]),
    )
    view = getattr(mod, f"{basename}TrainJobViewSet").as_view({"get": "download_model"})
    request = factory.get(f"/{suffix}_train_jobs/x/runs/r1/download_model/")
    resp = _call(view, request, superuser, pk=tj.id, run_id="r1")
    assert resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_download_model_success(monkeypatch, superuser, suffix, prefix, model_module, basename):
    tj = _make_train_job(model_module, basename)
    mod = _view_module(suffix)
    archive = BytesIO(b"zipdata")
    _patch_mlflow(
        monkeypatch, suffix,
        get_experiment_by_name=lambda name: types.SimpleNamespace(experiment_id="1"),
        get_experiment_runs=lambda eid, **kw: _runs_frame([{"run_id": "r1"}]),
        download_model_artifact=lambda run_id, artifact_path=None: archive,
    )
    view = getattr(mod, f"{basename}TrainJobViewSet").as_view({"get": "download_model"})
    request = factory.get(f"/{suffix}_train_jobs/x/runs/r1/download_model/")
    resp = _call(view, request, superuser, pk=tj.id, run_id="r1")
    assert resp.status_code == status.HTTP_200_OK
    assert resp["Content-Type"] == "application/zip"
    assert resp["Content-Length"] == "7"
    assert ".zip" in resp["Content-Disposition"]
    assert resp.streaming
    assert resp.is_async
    assert asyncio.run(_consume_streaming_response(resp)) == b"zipdata"
    resp.close()
    assert archive.closed


# =========================================================================
# DatasetRelease: archive / unarchive
# =========================================================================


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_release_archive_success(monkeypatch, superuser, suffix, prefix, model_module, basename):
    if suffix not in HAS_ARCHIVE:
        pytest.skip(f"{suffix} DatasetReleaseViewSet has no archive action")
    rel = _make_release(model_module, basename, status_value=DatasetReleaseStatus.PUBLISHED, description="orig")
    mod = _view_module(suffix)
    view = getattr(mod, f"{basename}DatasetReleaseViewSet").as_view({"post": "archive"})
    request = factory.post(f"/{suffix}_dataset_releases/x/archive/")
    resp = _call(view, request, superuser, pk=rel.id)
    assert resp.status_code == status.HTTP_200_OK
    rel.refresh_from_db()
    assert rel.status == DatasetReleaseStatus.ARCHIVED
    if suffix in ARCHIVE_TOUCHES_DESCRIPTION:
        assert rel.description.startswith("[已归档]")


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_release_archive_already_archived(monkeypatch, superuser, suffix, prefix, model_module, basename):
    if suffix not in HAS_ARCHIVE:
        pytest.skip(f"{suffix} DatasetReleaseViewSet has no archive action")
    rel = _make_release(model_module, basename, status_value=DatasetReleaseStatus.ARCHIVED)
    mod = _view_module(suffix)
    view = getattr(mod, f"{basename}DatasetReleaseViewSet").as_view({"post": "archive"})
    request = factory.post(f"/{suffix}_dataset_releases/x/archive/")
    resp = _call(view, request, superuser, pk=rel.id)
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_release_unarchive_success(monkeypatch, superuser, suffix, prefix, model_module, basename):
    if suffix not in HAS_ARCHIVE:
        pytest.skip(f"{suffix} DatasetReleaseViewSet has no unarchive action")
    rel = _make_release(model_module, basename, status_value=DatasetReleaseStatus.ARCHIVED, description="[已归档] orig")
    mod = _view_module(suffix)
    view = getattr(mod, f"{basename}DatasetReleaseViewSet").as_view({"post": "unarchive"})
    request = factory.post(f"/{suffix}_dataset_releases/x/unarchive/")
    resp = _call(view, request, superuser, pk=rel.id)
    assert resp.status_code == status.HTTP_200_OK
    rel.refresh_from_db()
    assert rel.status == DatasetReleaseStatus.PUBLISHED
    if suffix in ARCHIVE_TOUCHES_DESCRIPTION:
        assert rel.description == "orig"


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_release_unarchive_not_archived(monkeypatch, superuser, suffix, prefix, model_module, basename):
    if suffix not in HAS_ARCHIVE:
        pytest.skip(f"{suffix} DatasetReleaseViewSet has no unarchive action")
    rel = _make_release(model_module, basename, status_value=DatasetReleaseStatus.PUBLISHED)
    mod = _view_module(suffix)
    view = getattr(mod, f"{basename}DatasetReleaseViewSet").as_view({"post": "unarchive"})
    request = factory.post(f"/{suffix}_dataset_releases/x/unarchive/")
    resp = _call(view, request, superuser, pk=rel.id)
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


# =========================================================================
# Serving: stop / remove / predict / start
# =========================================================================


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_serving_stop_success(monkeypatch, superuser, suffix, prefix, model_module, basename):
    serving = _make_serving(model_module, basename)
    mod = _view_module(suffix)
    stop_mock = Mock(return_value={"removed": True})
    monkeypatch.setattr(mod.WebhookClient, "stop", staticmethod(stop_mock))
    view = getattr(mod, f"{basename}ServingViewSet").as_view({"post": "stop"})
    request = factory.post(f"/{suffix}_servings/x/stop/")
    resp = _call(view, request, superuser, pk=serving.id)
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["serving_id"] == f"{prefix}_Serving_{serving.id}"
    stop_mock.assert_called_once()


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_serving_stop_webhook_error(monkeypatch, superuser, suffix, prefix, model_module, basename):
    serving = _make_serving(model_module, basename)
    mod = _view_module(suffix)

    def raise_err(sid):
        raise WebhookError("down")

    monkeypatch.setattr(mod.WebhookClient, "stop", staticmethod(raise_err))
    view = getattr(mod, f"{basename}ServingViewSet").as_view({"post": "stop"})
    request = factory.post(f"/{suffix}_servings/x/stop/")
    resp = _call(view, request, superuser, pk=serving.id)
    assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_serving_predict_empty_data(monkeypatch, superuser, suffix, prefix, model_module, basename):
    # object_detection validates container_info before payload, so give it a
    # running container so we reach the empty-payload branch.
    serving = _make_serving(
        model_module, basename,
        container_info={"state": "running", "port": "9000"},
    )
    mod = _view_module(suffix)
    monkeypatch.setattr(
        mod, "build_predict_url",
        lambda serving_id, container_info: "http://predict.local/invocations",
    )
    view = getattr(mod, f"{basename}ServingViewSet").as_view({"post": "predict"})
    request = factory.post(f"/{suffix}_servings/x/predict/", {}, format="json")
    resp = _call(view, request, superuser, pk=serving.id)
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    # message mentions the missing param name (不能为空 / 缺少参数)
    err = resp.data["error"]
    assert PREDICT_PARAM[suffix] in err or "不能为空" in err or "缺少参数" in err


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_serving_predict_non_list_data(monkeypatch, superuser, suffix, prefix, model_module, basename):
    serving = _make_serving(
        model_module, basename,
        container_info={"state": "running", "port": "9000"},
    )
    mod = _view_module(suffix)
    monkeypatch.setattr(
        mod, "build_predict_url",
        lambda serving_id, container_info: "http://predict.local/invocations",
    )
    view = getattr(mod, f"{basename}ServingViewSet").as_view({"post": "predict"})
    param = PREDICT_PARAM[suffix]
    request = factory.post(f"/{suffix}_servings/x/predict/", {param: {"a": 1}}, format="json")
    resp = _call(view, request, superuser, pk=serving.id)
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "数组格式" in resp.data["error"]


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_serving_predict_success(monkeypatch, superuser, suffix, prefix, model_module, basename):
    serving = _make_serving(
        model_module, basename,
        container_info={"state": "running", "port": "9000", "ports": {"8080/tcp": "9000"}},
        port=9000,
    )
    mod = _view_module(suffix)
    monkeypatch.setattr(mod, "build_predict_url", lambda serving_id, container_info: "http://predict.local/invocations")

    resp_mock = Mock(status_code=200)
    resp_mock.raise_for_status = Mock()
    resp_mock.json.return_value = {"success": True, "data": [1, 2, 3]}
    post_mock = Mock(return_value=resp_mock)
    monkeypatch.setattr(mod.requests, "post", post_mock)

    view = getattr(mod, f"{basename}ServingViewSet").as_view({"post": "predict"})
    param = PREDICT_PARAM[suffix]
    request = factory.post(f"/{suffix}_servings/x/predict/", {param: ["a", "b"]}, format="json")
    resp = _call(view, request, superuser, pk=serving.id)
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["data"] == [1, 2, 3]
    post_mock.assert_called_once()


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_serving_predict_business_failure(monkeypatch, superuser, suffix, prefix, model_module, basename):
    # object_detection / image_classification do not branch on result["success"];
    # they return the raw 200 payload. Skip them for this business-failure contract.
    if suffix in PREDICT_RAW_PASSTHROUGH:
        pytest.skip(f"{suffix} predict does not interpret success flag")
    serving = _make_serving(
        model_module, basename,
        container_info={"state": "running", "port": "9000"},
        port=9000,
    )
    mod = _view_module(suffix)
    monkeypatch.setattr(mod, "build_predict_url", lambda serving_id, container_info: "http://predict.local/invocations")
    resp_mock = Mock(status_code=200)
    resp_mock.raise_for_status = Mock()
    resp_mock.json.return_value = {
        "success": False,
        "error": {"code": "BAD_INPUT", "message": "输入非法", "details": {}},
    }
    monkeypatch.setattr(mod.requests, "post", Mock(return_value=resp_mock))
    view = getattr(mod, f"{basename}ServingViewSet").as_view({"post": "predict"})
    param = PREDICT_PARAM[suffix]
    request = factory.post(f"/{suffix}_servings/x/predict/", {param: ["a"]}, format="json")
    resp = _call(view, request, superuser, pk=serving.id)
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.data["error_code"] == "BAD_INPUT"


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_serving_predict_http_error(monkeypatch, superuser, suffix, prefix, model_module, basename):
    serving = _make_serving(
        model_module, basename,
        container_info={"state": "running", "port": "9000"}, port=9000,
    )
    mod = _view_module(suffix)
    monkeypatch.setattr(mod, "build_predict_url", lambda serving_id, container_info: "http://predict.local/invocations")
    resp_mock = Mock(status_code=500)
    resp_mock.text = "boom"
    resp_mock.json.side_effect = ValueError("no json")
    # raise_for_status raises for object/image passthrough algos
    import requests as _rq
    resp_mock.raise_for_status = Mock(side_effect=_rq.exceptions.HTTPError("500"))
    monkeypatch.setattr(mod.requests, "post", Mock(return_value=resp_mock))
    view = getattr(mod, f"{basename}ServingViewSet").as_view({"post": "predict"})
    param = PREDICT_PARAM[suffix]
    request = factory.post(f"/{suffix}_servings/x/predict/", {param: ["a"]}, format="json")
    resp = _call(view, request, superuser, pk=serving.id)
    assert resp.status_code >= 500
    assert "error" in resp.data


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_serving_predict_connection_error(monkeypatch, superuser, suffix, prefix, model_module, basename):
    import requests as _rq

    serving = _make_serving(
        model_module, basename,
        container_info={"state": "running", "port": "9000"}, port=9000,
    )
    mod = _view_module(suffix)
    monkeypatch.setattr(mod, "build_predict_url", lambda serving_id, container_info: "http://predict.local/invocations")

    def conn_err(*a, **k):
        raise _rq.exceptions.ConnectionError("refused")

    monkeypatch.setattr(mod.requests, "post", conn_err)
    view = getattr(mod, f"{basename}ServingViewSet").as_view({"post": "predict"})
    param = PREDICT_PARAM[suffix]
    request = factory.post(f"/{suffix}_servings/x/predict/", {param: ["a"]}, format="json")
    resp = _call(view, request, superuser, pk=serving.id)
    assert resp.status_code >= 500
    assert "error" in resp.data


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_serving_predict_invalid_container_info(monkeypatch, superuser, suffix, prefix, model_module, basename):
    # build_predict_url raises ValueError when container info lacks a usable port.
    serving = _make_serving(model_module, basename, container_info={})
    mod = _view_module(suffix)

    def bad_url(serving_id, container_info):
        raise ValueError("无法解析服务地址")

    monkeypatch.setattr(mod, "build_predict_url", bad_url)
    view = getattr(mod, f"{basename}ServingViewSet").as_view({"post": "predict"})
    param = PREDICT_PARAM[suffix]
    request = factory.post(f"/{suffix}_servings/x/predict/", {param: ["a"]}, format="json")
    resp = _call(view, request, superuser, pk=serving.id)
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "error" in resp.data


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_serving_start_config_error(monkeypatch, superuser, suffix, prefix, model_module, basename):
    """When MLflow tracking URI is unavailable, start fails with HTTP 500.

    Two production patterns exist:
    - anomaly_detection catches ConfigurationError explicitly;
    - the others guard ``if not uri`` and so a falsy URI triggers the error.
    """
    from apps.mlops.services import ConfigurationError

    serving = _make_serving(model_module, basename)
    mod = _view_module(suffix)

    if suffix == "anomaly_detection":
        def boom():
            raise ConfigurationError("no uri")

        monkeypatch.setattr(mod, "get_mlflow_tracking_uri", boom)
    else:
        monkeypatch.setattr(mod, "get_mlflow_tracking_uri", lambda: "")

    view = getattr(mod, f"{basename}ServingViewSet").as_view({"post": "start"})
    request = factory.post(f"/{suffix}_servings/x/start/")
    resp = _call(view, request, superuser, pk=serving.id)
    assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    # Config-related error: either explicit env-var message or generic config error.
    assert ("MLFLOW_TRACKER_URL" in resp.data["error"]) or ("配置" in resp.data["error"])


def _allow_team_one(monkeypatch):
    """Make permission filtering admit team 1 for list/retrieve endpoints."""
    monkeypatch.setattr(
        "apps.core.utils.viewset_utils.get_permission_rules",
        lambda *a, **k: {"team": [1], "instance": []},
    )


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_serving_list_syncs_container_status(monkeypatch, superuser, suffix, prefix, model_module, basename):
    _allow_team_one(monkeypatch)
    serving = _make_serving(model_module, basename, container_info={"state": "old"})
    mod = _view_module(suffix)
    container_id = f"{prefix}_Serving_{serving.id}"
    status_payload = [{"id": container_id, "state": "running", "status": "success", "port": "9000"}]
    monkeypatch.setattr(mod.WebhookClient, "get_status", staticmethod(Mock(return_value=status_payload)))
    view = getattr(mod, f"{basename}ServingViewSet").as_view({"get": "list"})
    request = factory.get(f"/{suffix}_servings/")
    resp = _call(view, request, superuser)
    assert resp.status_code == status.HTTP_200_OK
    items = resp.data["items"] if isinstance(resp.data, dict) and "items" in resp.data else resp.data
    assert items
    # the matching serving's container_info synced from webhook payload
    target = next(s for s in items if s["id"] == serving.id)
    assert target["container_info"]["state"] == "running"
    serving.refresh_from_db()
    assert serving.container_info["state"] == "running"


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_serving_list_webhook_error_degrades(monkeypatch, superuser, suffix, prefix, model_module, basename):
    _allow_team_one(monkeypatch)
    serving = _make_serving(model_module, basename, container_info={"state": "cached"})
    mod = _view_module(suffix)

    def raise_err(ids):
        raise WebhookError("status down")

    monkeypatch.setattr(mod.WebhookClient, "get_status", staticmethod(raise_err))
    view = getattr(mod, f"{basename}ServingViewSet").as_view({"get": "list"})
    request = factory.get(f"/{suffix}_servings/")
    resp = _call(view, request, superuser)
    assert resp.status_code == status.HTTP_200_OK
    items = resp.data["items"] if isinstance(resp.data, dict) and "items" in resp.data else resp.data
    target = next(s for s in items if s["id"] == serving.id)
    # degraded: error marker added, old value preserved
    assert target["container_info"]["status"] == "error"
    assert target["container_info"].get("_query_failed") is True


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_serving_retrieve_syncs_container_status(monkeypatch, superuser, suffix, prefix, model_module, basename):
    # image_classification / object_detection retrieve are plain passthroughs
    # (no live status sync); only the CSV-based algorithms sync on retrieve.
    if suffix in ("object_detection", "image_classification"):
        pytest.skip(f"{suffix} serving retrieve does not sync container status")
    serving = _make_serving(model_module, basename, container_info={"state": "old"})
    mod = _view_module(suffix)
    container_id = f"{prefix}_Serving_{serving.id}"
    monkeypatch.setattr(
        mod.WebhookClient, "get_status",
        staticmethod(Mock(return_value=[{"id": container_id, "state": "running", "status": "success"}])),
    )
    view = getattr(mod, f"{basename}ServingViewSet").as_view({"get": "retrieve"})
    request = factory.get(f"/{suffix}_servings/x/")
    resp = _call(view, request, superuser, pk=serving.id)
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["container_info"]["state"] == "running"


def _serving_create_request(suffix, train_job):
    return factory.post(
        f"/{suffix}_servings/",
        {"name": "srv", "description": "", "team": [1],
         "train_job": train_job.id, "model_version": "latest"},
        format="json",
    )


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_serving_create_config_error_keeps_record(monkeypatch, superuser, suffix, prefix, model_module, basename):
    from apps.mlops.services import ConfigurationError

    _allow_team_one(monkeypatch)
    monkeypatch.setattr(
        "apps.core.utils.serializers.get_permission_rules",
        lambda *a, **k: {"team": [1], "instance": []},
    )
    train_job = _make_train_job(model_module, basename, status_value=TrainJobStatus.COMPLETED)
    mod = _view_module(suffix)
    _patch_mlflow(monkeypatch, suffix)

    # Either raises ConfigurationError or returns falsy, depending on the view.
    if suffix == "anomaly_detection":
        def cfg():
            raise ConfigurationError("missing")
        monkeypatch.setattr(mod, "get_mlflow_tracking_uri", cfg)
    else:
        monkeypatch.setattr(mod, "get_mlflow_tracking_uri", lambda: "")

    Serving = _model(model_module, basename, "Serving")
    view = getattr(mod, f"{basename}ServingViewSet").as_view({"post": "create"})
    resp = _call(view, _serving_create_request(suffix, train_job), superuser)
    # The serving record is created up-front (super().create runs first); only the
    # auto-start fails. Different views surface this as 200 (with error
    # container_info) or 500 (config error response). Either way a record exists.
    assert resp.status_code in (
        status.HTTP_200_OK, status.HTTP_201_CREATED, status.HTTP_500_INTERNAL_SERVER_ERROR
    )
    assert Serving.objects.count() == 1


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_serving_create_serve_error_keeps_record(monkeypatch, superuser, suffix, prefix, model_module, basename):
    _allow_team_one(monkeypatch)
    monkeypatch.setattr(
        "apps.core.utils.serializers.get_permission_rules",
        lambda *a, **k: {"team": [1], "instance": []},
    )
    train_job = _make_train_job(model_module, basename, status_value=TrainJobStatus.COMPLETED)
    mod = _view_module(suffix)
    _patch_mlflow(monkeypatch, suffix)
    monkeypatch.setattr(mod, "get_mlflow_tracking_uri", lambda: "http://mlflow.local")
    monkeypatch.setattr(mod, "get_image_by_prefix", lambda p, algo: "repo/serve:1")

    def serve_err(*a, **k):
        raise WebhookError("serve failed", code="OTHER")

    monkeypatch.setattr(mod.WebhookClient, "serve", staticmethod(serve_err))
    Serving = _model(model_module, basename, "Serving")
    view = getattr(mod, f"{basename}ServingViewSet").as_view({"post": "create"})
    resp = _call(view, _serving_create_request(suffix, train_job), superuser)
    assert resp.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED)
    # the serving record persists despite the failed container launch
    assert Serving.objects.filter(id=resp.data["id"]).exists()


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_serving_update_restarts_running_container(monkeypatch, superuser, suffix, prefix, model_module, basename):
    # anomaly/log/classification/timeseries serving.update auto-restart a running
    # container on model_version change. image/object update differ; skip them.
    if suffix in ("image_classification", "object_detection"):
        pytest.skip(f"{suffix} serving update has a different restart contract")
    _allow_team_one(monkeypatch)
    monkeypatch.setattr(
        "apps.core.utils.serializers.get_permission_rules",
        lambda *a, **k: {"team": [1], "instance": []},
    )
    serving = _make_serving(
        model_module, basename,
        container_info={"state": "running", "port": "9000"},
        port=9000,
    )
    mod = _view_module(suffix)
    _patch_mlflow(monkeypatch, suffix)
    monkeypatch.setattr(mod, "get_mlflow_tracking_uri", lambda: "http://mlflow.local")
    monkeypatch.setattr(mod, "get_image_by_prefix", lambda p, algo: "repo/serve:1")
    monkeypatch.setattr(mod.WebhookClient, "remove", staticmethod(Mock()))
    serve_mock = Mock(return_value={"status": "success", "state": "running", "port": "9000"})
    monkeypatch.setattr(mod.WebhookClient, "serve", staticmethod(serve_mock))

    view = getattr(mod, f"{basename}ServingViewSet").as_view({"put": "update"})
    request = factory.put(
        f"/{suffix}_servings/x/",
        {"name": serving.name, "team": [1], "train_job": serving.train_job_id,
         "model_version": "2"},
        format="json",
    )
    resp = _call(view, request, superuser, pk=serving.id)
    assert resp.status_code == status.HTTP_200_OK
    # model_version change on a running container triggers a re-serve
    serve_mock.assert_called_once()


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_serving_update_inactive_container_no_restart(monkeypatch, superuser, suffix, prefix, model_module, basename):
    if suffix in ("image_classification", "object_detection"):
        pytest.skip(f"{suffix} serving update has a different restart contract")
    _allow_team_one(monkeypatch)
    monkeypatch.setattr(
        "apps.core.utils.serializers.get_permission_rules",
        lambda *a, **k: {"team": [1], "instance": []},
    )
    serving = _make_serving(
        model_module, basename,
        container_info={"state": "exited"},
        port=9000,
    )
    mod = _view_module(suffix)
    serve_mock = Mock()
    monkeypatch.setattr(mod.WebhookClient, "serve", staticmethod(serve_mock))
    view = getattr(mod, f"{basename}ServingViewSet").as_view({"put": "update"})
    request = factory.put(
        f"/{suffix}_servings/x/",
        {"name": serving.name, "team": [1], "train_job": serving.train_job_id,
         "model_version": "2"},
        format="json",
    )
    resp = _call(view, request, superuser, pk=serving.id)
    assert resp.status_code == status.HTTP_200_OK
    # not running -> no restart
    serve_mock.assert_not_called()


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_serving_create_autostarts_container(monkeypatch, superuser, suffix, prefix, model_module, basename):
    _allow_team_one(monkeypatch)
    # A train job to attach the serving to.
    train_job = _make_train_job(model_module, basename, status_value=TrainJobStatus.COMPLETED)
    mod = _view_module(suffix)
    _patch_mlflow(monkeypatch, suffix)
    monkeypatch.setattr(mod, "get_mlflow_tracking_uri", lambda: "http://mlflow.local")
    monkeypatch.setattr(mod, "get_image_by_prefix", lambda p, algo: "repo/serve:1")
    serve_mock = Mock(return_value={"status": "success", "state": "running", "port": "9100"})
    monkeypatch.setattr(mod.WebhookClient, "serve", staticmethod(serve_mock))
    # permission rules used by AuthSerializer team validation
    monkeypatch.setattr(
        "apps.core.utils.serializers.get_permission_rules",
        lambda *a, **k: {"team": [1], "instance": []},
    )

    Serving = _model(model_module, basename, "Serving")
    payload = {
        "name": "srv",
        "description": "",
        "team": [1],
        "train_job": train_job.id,
        "model_version": "latest",
    }
    view = getattr(mod, f"{basename}ServingViewSet").as_view({"post": "create"})
    request = factory.post(f"/{suffix}_servings/", payload, format="json")
    resp = _call(view, request, superuser)
    assert resp.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED)
    serving = Serving.objects.get(id=resp.data["id"])
    # container auto-start invoked and info persisted
    serve_mock.assert_called_once()
    assert serving.container_info.get("state") == "running"


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_serving_start_success(monkeypatch, superuser, suffix, prefix, model_module, basename):
    serving = _make_serving(model_module, basename)
    mod = _view_module(suffix)
    _patch_mlflow(monkeypatch, suffix)
    monkeypatch.setattr(mod, "get_mlflow_tracking_uri", lambda: "http://mlflow.local")
    monkeypatch.setattr(mod, "get_image_by_prefix", lambda prefix_, algo: "repo/img:1")
    serve_mock = Mock(return_value={"status": "success", "state": "running", "port": "9001"})
    monkeypatch.setattr(mod.WebhookClient, "serve", staticmethod(serve_mock))
    view = getattr(mod, f"{basename}ServingViewSet").as_view({"post": "start"})
    request = factory.post(f"/{suffix}_servings/x/start/")
    resp = _call(view, request, superuser, pk=serving.id)
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["serving_id"] == f"{prefix}_Serving_{serving.id}"
    serving.refresh_from_db()
    assert serving.container_info["state"] == "running"


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_serving_start_container_already_exists_syncs(monkeypatch, superuser, suffix, prefix, model_module, basename):
    # image/object start do not special-case CONTAINER_ALREADY_EXISTS; they
    # re-raise to the generic handler (covered by the generic-error test).
    if suffix in ("image_classification", "object_detection"):
        pytest.skip(f"{suffix} start has no CONTAINER_ALREADY_EXISTS sync branch")
    serving = _make_serving(model_module, basename)
    mod = _view_module(suffix)
    _patch_mlflow(monkeypatch, suffix)
    monkeypatch.setattr(mod, "get_mlflow_tracking_uri", lambda: "http://mlflow.local")
    monkeypatch.setattr(mod, "get_image_by_prefix", lambda p, algo: "repo/serve:1")

    def serve_conflict(*a, **k):
        raise WebhookError("exists", code="CONTAINER_ALREADY_EXISTS")

    monkeypatch.setattr(mod.WebhookClient, "serve", staticmethod(serve_conflict))
    container_id = f"{prefix}_Serving_{serving.id}"
    monkeypatch.setattr(
        mod.WebhookClient, "get_status",
        staticmethod(Mock(return_value=[{"id": container_id, "state": "running", "status": "success"}])),
    )
    view = getattr(mod, f"{basename}ServingViewSet").as_view({"post": "start"})
    request = factory.post(f"/{suffix}_servings/x/start/")
    resp = _call(view, request, superuser, pk=serving.id)
    assert resp.status_code == status.HTTP_200_OK
    # container info synced from get_status
    serving.refresh_from_db()
    assert serving.container_info["state"] == "running"


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_serving_start_generic_webhook_error(monkeypatch, superuser, suffix, prefix, model_module, basename):
    serving = _make_serving(model_module, basename)
    mod = _view_module(suffix)
    _patch_mlflow(monkeypatch, suffix)
    monkeypatch.setattr(mod, "get_mlflow_tracking_uri", lambda: "http://mlflow.local")
    monkeypatch.setattr(mod, "get_image_by_prefix", lambda p, algo: "repo/serve:1")

    def serve_err(*a, **k):
        raise WebhookError("boom", code="OTHER")

    monkeypatch.setattr(mod.WebhookClient, "serve", staticmethod(serve_err))
    view = getattr(mod, f"{basename}ServingViewSet").as_view({"post": "start"})
    request = factory.post(f"/{suffix}_servings/x/start/")
    resp = _call(view, request, superuser, pk=serving.id)
    assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "error" in resp.data


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_serving_remove_success(monkeypatch, superuser, suffix, prefix, model_module, basename):
    serving = _make_serving(model_module, basename, container_info={"state": "running"})
    mod = _view_module(suffix)
    remove_mock = Mock(return_value={"removed": True})
    monkeypatch.setattr(mod.WebhookClient, "remove", staticmethod(remove_mock))
    # the remove/delete-container action is named "remove" in some views; resolve dynamically
    vs = getattr(mod, f"{basename}ServingViewSet")
    action_name = "remove" if hasattr(vs, "remove") else None
    if action_name is None:
        pytest.skip(f"{suffix} serving has no remove action")
    view = vs.as_view({"post": action_name})
    request = factory.post(f"/{suffix}_servings/x/remove/")
    resp = _call(view, request, superuser, pk=serving.id)
    assert resp.status_code == status.HTTP_200_OK
    remove_mock.assert_called_once()
