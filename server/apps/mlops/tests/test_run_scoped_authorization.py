import pytest
from rest_framework import status

from apps.mlops.models.anomaly_detection import AnomalyDetectionTrainJob
from apps.mlops.models.classification import ClassificationTrainJob
from apps.mlops.models.image_classification import ImageClassificationTrainJob
from apps.mlops.models.log_clustering import LogClusteringTrainJob
from apps.mlops.models.object_detection import ObjectDetectionTrainJob
from apps.mlops.models.timeseries_predict import TimeSeriesPredictTrainJob
from .conftest import (
    allow_owned_run,
    attach_mlflow_mocks,
    create_train_job,
    set_delete_run_eligibility,
)


pytestmark = [pytest.mark.django_db, pytest.mark.integration]


ALGORITHM_CASES = [
    ("classification_train_jobs", ClassificationTrainJob, "classification-View"),
    ("anomaly_detection_train_jobs", AnomalyDetectionTrainJob, "anomaly_detection-View"),
    ("timeseries_predict_train_jobs", TimeSeriesPredictTrainJob, "timeseries_predict-View"),
    ("log_clustering_train_jobs", LogClusteringTrainJob, "log_clustering-View"),
    ("image_classification_train_jobs", ImageClassificationTrainJob, "image_classification-View"),
    ("object_detection_train_jobs", ObjectDetectionTrainJob, "object_detection-View"),
]


RUN_SCOPED_CASES = [
    ("classification_train_jobs", ClassificationTrainJob, "apps.mlops.views.classification"),
    ("anomaly_detection_train_jobs", AnomalyDetectionTrainJob, "apps.mlops.views.anomaly_detection"),
    ("timeseries_predict_train_jobs", TimeSeriesPredictTrainJob, "apps.mlops.views.timeseries_predict"),
    ("log_clustering_train_jobs", LogClusteringTrainJob, "apps.mlops.views.log_clustering"),
    ("image_classification_train_jobs", ImageClassificationTrainJob, "apps.mlops.views.image_classification"),
    ("object_detection_train_jobs", ObjectDetectionTrainJob, "apps.mlops.views.object_detection"),
]


DOWNLOAD_MODEL_CASES = [
    ("classification_train_jobs", ClassificationTrainJob, "apps.mlops.views.classification", 1),
    ("anomaly_detection_train_jobs", AnomalyDetectionTrainJob, "apps.mlops.views.anomaly_detection", 1),
    ("timeseries_predict_train_jobs", TimeSeriesPredictTrainJob, "apps.mlops.views.timeseries_predict", 1),
    ("log_clustering_train_jobs", LogClusteringTrainJob, "apps.mlops.views.log_clustering", 1),
    ("image_classification_train_jobs", ImageClassificationTrainJob, "apps.mlops.views.image_classification", 0),
    ("object_detection_train_jobs", ObjectDetectionTrainJob, "apps.mlops.views.object_detection", 0),
]


@pytest.mark.parametrize(
    "route_prefix,train_job_model,permission",
    ALGORITHM_CASES,
)
def test_old_raw_metrics_route_should_be_removed(
    mlops_api_client,
    route_prefix,
    train_job_model,
    permission,
):
    create_train_job(train_job_model, team=1)

    response = mlops_api_client.get(f"/api/v1/mlops/{route_prefix}/runs_metrics_list/foreign-run/")

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.parametrize(
    "route_prefix,train_job_model,module_path",
    RUN_SCOPED_CASES,
)
def test_scoped_run_endpoints_require_run_membership(
    mlops_api_client,
    monkeypatch,
    route_prefix,
    train_job_model,
    module_path,
):
    train_job = create_train_job(train_job_model, team=1)
    calls = attach_mlflow_mocks(monkeypatch, module_path)

    response = mlops_api_client.get(
        f"/api/v1/mlops/{route_prefix}/{train_job.id}/runs/foreign-run/metrics_list/"
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert calls["metrics"] == 0


@pytest.mark.parametrize(
    "route_prefix,train_job_model,module_path",
    RUN_SCOPED_CASES,
)
def test_scoped_run_metrics_allow_owned_run(
    mlops_api_client,
    monkeypatch,
    route_prefix,
    train_job_model,
    module_path,
):
    train_job = create_train_job(train_job_model, team=1)
    calls = attach_mlflow_mocks(monkeypatch, module_path)

    allow_owned_run(monkeypatch, module_path, train_job)

    response = mlops_api_client.get(
        f"/api/v1/mlops/{route_prefix}/{train_job.id}/runs/owned-run/metrics_list/"
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["run_id"] == "owned-run"
    assert response.data["metrics"] == ["accuracy"]
    assert calls["metrics"] == 1


@pytest.mark.parametrize(
    "route_prefix,train_job_model,module_path",
    RUN_SCOPED_CASES,
)
def test_scoped_run_metric_history_requires_run_membership(
    mlops_api_client,
    monkeypatch,
    route_prefix,
    train_job_model,
    module_path,
):
    train_job = create_train_job(train_job_model, team=1)
    calls = attach_mlflow_mocks(monkeypatch, module_path)

    response = mlops_api_client.get(
        f"/api/v1/mlops/{route_prefix}/{train_job.id}/runs/foreign-run/metrics_history/accuracy/"
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.data["code"] == "run_not_found"
    assert response.data["run_id"] == "foreign-run"
    assert calls["history"] == 0


@pytest.mark.parametrize(
    "route_prefix,train_job_model,module_path",
    RUN_SCOPED_CASES,
)
def test_scoped_run_metric_history_allows_owned_run(
    mlops_api_client,
    monkeypatch,
    route_prefix,
    train_job_model,
    module_path,
):
    train_job = create_train_job(train_job_model, team=1)
    calls = attach_mlflow_mocks(monkeypatch, module_path)

    allow_owned_run(monkeypatch, module_path, train_job)

    response = mlops_api_client.get(
        f"/api/v1/mlops/{route_prefix}/{train_job.id}/runs/owned-run/metrics_history/accuracy/"
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["run_id"] == "owned-run"
    assert response.data["metric_name"] == "accuracy"
    assert response.data["total_points"] == 1
    assert response.data["metric_history"] == [{"step": 1, "value": 0.99, "timestamp": 123}]
    assert calls["history"] == 1


@pytest.mark.parametrize(
    "route_prefix,train_job_model,module_path",
    RUN_SCOPED_CASES,
)
def test_scoped_run_params_require_run_membership(
    mlops_api_client,
    monkeypatch,
    route_prefix,
    train_job_model,
    module_path,
):
    train_job = create_train_job(train_job_model, team=1)
    calls = attach_mlflow_mocks(monkeypatch, module_path)

    response = mlops_api_client.get(
        f"/api/v1/mlops/{route_prefix}/{train_job.id}/runs/foreign-run/run_params/"
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.data["code"] == "run_not_found"
    assert response.data["run_id"] == "foreign-run"
    assert calls["run_info"] == 0
    assert calls["run_params"] == 0


@pytest.mark.parametrize(
    "route_prefix,train_job_model,module_path",
    RUN_SCOPED_CASES,
)
def test_scoped_run_params_allow_owned_run(
    mlops_api_client,
    monkeypatch,
    route_prefix,
    train_job_model,
    module_path,
):
    train_job = create_train_job(train_job_model, team=1)
    calls = attach_mlflow_mocks(monkeypatch, module_path)

    allow_owned_run(monkeypatch, module_path, train_job)

    response = mlops_api_client.get(
        f"/api/v1/mlops/{route_prefix}/{train_job.id}/runs/owned-run/run_params/"
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["run_id"] == "owned-run"
    assert response.data["run_name"] == "demo-run"
    assert response.data["status"] == "FINISHED"
    assert response.data["params"] == {"epochs": "5"}
    assert response.data["start_time"] is not None
    assert response.data["end_time"] is not None
    assert calls["run_info"] == 1
    assert calls["run_params"] == 1


@pytest.mark.parametrize(
    "route_prefix,train_job_model,module_path,expected_run_info_calls",
    DOWNLOAD_MODEL_CASES,
)
def test_scoped_download_model_requires_run_membership(
    mlops_api_client,
    monkeypatch,
    route_prefix,
    train_job_model,
    module_path,
    expected_run_info_calls,
):
    train_job = create_train_job(train_job_model, team=1)
    calls = attach_mlflow_mocks(monkeypatch, module_path)

    response = mlops_api_client.get(
        f"/api/v1/mlops/{route_prefix}/{train_job.id}/runs/foreign-run/download_model/"
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.data["code"] == "run_not_found"
    assert response.data["run_id"] == "foreign-run"
    assert calls["run_info"] == 0
    assert calls["download"] == 0


@pytest.mark.parametrize(
    "route_prefix,train_job_model,module_path,expected_run_info_calls",
    DOWNLOAD_MODEL_CASES,
)
def test_scoped_download_model_allows_owned_run(
    mlops_api_client,
    monkeypatch,
    route_prefix,
    train_job_model,
    module_path,
    expected_run_info_calls,
):
    train_job = create_train_job(train_job_model, team=1)
    calls = attach_mlflow_mocks(monkeypatch, module_path)

    allow_owned_run(monkeypatch, module_path, train_job)

    response = mlops_api_client.get(
        f"/api/v1/mlops/{route_prefix}/{train_job.id}/runs/owned-run/download_model/"
    )

    assert response.status_code == status.HTTP_200_OK
    assert ".zip" in response["Content-Disposition"]
    assert calls["run_info"] == expected_run_info_calls
    assert calls["download"] == 1


@pytest.mark.parametrize(
    "route_prefix,train_job_model,module_path",
    RUN_SCOPED_CASES,
)
def test_scoped_delete_run_requires_run_membership(
    mlops_delete_api_client,
    monkeypatch,
    route_prefix,
    train_job_model,
    module_path,
):
    train_job = create_train_job(train_job_model, team=1)
    calls = attach_mlflow_mocks(monkeypatch, module_path)

    set_delete_run_eligibility(monkeypatch, module_path, train_job, False, "run_not_found")

    response = mlops_delete_api_client.delete(
        f"/api/v1/mlops/{route_prefix}/{train_job.id}/runs/foreign-run/"
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.data["code"] == "run_not_found"
    assert response.data["run_id"] == "foreign-run"
    assert calls["delete_run"] == 0


@pytest.mark.parametrize(
    "route_prefix,train_job_model,module_path",
    RUN_SCOPED_CASES,
)
def test_scoped_delete_run_rejects_ineligible_owned_run(
    mlops_delete_api_client,
    monkeypatch,
    route_prefix,
    train_job_model,
    module_path,
):
    train_job = create_train_job(train_job_model, team=1)
    calls = attach_mlflow_mocks(monkeypatch, module_path)

    set_delete_run_eligibility(monkeypatch, module_path, train_job, False, "active_latest_run")

    response = mlops_delete_api_client.delete(
        f"/api/v1/mlops/{route_prefix}/{train_job.id}/runs/owned-run/"
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["code"] == "active_latest_run"
    assert response.data["run_id"] == "owned-run"
    assert calls["delete_run"] == 0


@pytest.mark.parametrize(
    "route_prefix,train_job_model,module_path",
    RUN_SCOPED_CASES,
)
def test_scoped_delete_run_allows_eligible_owned_run(
    mlops_delete_api_client,
    monkeypatch,
    route_prefix,
    train_job_model,
    module_path,
):
    train_job = create_train_job(train_job_model, team=1)
    calls = attach_mlflow_mocks(monkeypatch, module_path)

    set_delete_run_eligibility(monkeypatch, module_path, train_job, True, None)

    response = mlops_delete_api_client.delete(
        f"/api/v1/mlops/{route_prefix}/{train_job.id}/runs/owned-run/"
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["result"] is True
    assert response.data["run_id"] == "owned-run"
    assert response.data["train_job_id"] == train_job.id
    assert response.data["deleted"] is True
    assert response.data["deletion_type"] == "mlflow_soft_delete"
    assert calls["delete_run"] == 1
