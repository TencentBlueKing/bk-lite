import types

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.base.tests.factories import UserFactory
from apps.mlops.constants import TrainJobStatus
from apps.mlops.models.anomaly_detection import AnomalyDetectionTrainJob
from apps.mlops.models.classification import ClassificationTrainJob
from apps.mlops.models.image_classification import ImageClassificationTrainJob
from apps.mlops.models.log_clustering import LogClusteringTrainJob
from apps.mlops.models.object_detection import ObjectDetectionTrainJob
from apps.mlops.models.timeseries_predict import TimeSeriesPredictTrainJob


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


@pytest.fixture
def mlops_user():
    user = UserFactory(
        username="mlops-viewer",
        domain="domain.com",
        group_list=[{"id": 1, "name": "Team 1"}, {"id": 2, "name": "Team 2"}],
        roles=[],
    )
    user.permission = {
        "mlops": {
            "classification-View",
            "anomaly_detection-View",
            "timeseries_predict-View",
            "log_clustering-View",
            "image_classification-View",
            "object_detection-View",
        }
    }
    return user


@pytest.fixture
def mlops_api_client(mlops_user):
    client = APIClient()
    client.force_authenticate(user=mlops_user)
    client.cookies["current_team"] = "1"
    return client


@pytest.fixture
def mlops_delete_user():
    user = UserFactory(
        username="mlops-deleter",
        domain="domain.com",
        group_list=[{"id": 1, "name": "Team 1"}, {"id": 2, "name": "Team 2"}],
        roles=[],
    )
    user.permission = {
        "mlops": {
            "classification-Delete",
            "anomaly_detection-Delete",
            "timeseries_predict-Delete",
            "log_clustering-Delete",
            "image_classification-Delete",
            "object_detection-Delete",
        }
    }
    return user


@pytest.fixture
def mlops_delete_api_client(mlops_delete_user):
    client = APIClient()
    client.force_authenticate(user=mlops_delete_user)
    client.cookies["current_team"] = "1"
    return client


def create_train_job(train_job_model, team):
    return train_job_model.objects.create(
        name=f"job-{team}",
        description="",
        team=[team],
        status=TrainJobStatus.COMPLETED,
        algorithm="demo-algorithm",
        dataset_version=None,
        hyperopt_config={},
    )


def attach_mlflow_mocks(monkeypatch, module_path):
    calls = {"metrics": 0, "history": 0, "run_info": 0, "run_params": 0, "download": 0, "delete_run": 0}

    def get_run_metrics(run_id, filter_system=True):
        calls["metrics"] += 1
        return ["accuracy"]

    def get_metric_history(run_id, metric_name):
        calls["history"] += 1
        return [{"step": 1, "value": 0.99, "timestamp": 123}]

    def get_run_info(run_id):
        calls["run_info"] += 1
        return types.SimpleNamespace(
            data=types.SimpleNamespace(tags={"mlflow.runName": "demo-run"}),
            info=types.SimpleNamespace(status="FINISHED", start_time=1000, end_time=2000),
        )

    def get_run_params(run_id):
        calls["run_params"] += 1
        return {"epochs": "5"}

    def download_model_artifact(run_id, artifact_path=None):
        from io import BytesIO

        calls["download"] += 1
        return BytesIO(b"zip-data")

    def delete_run(run_id):
        calls["delete_run"] += 1

    monkeypatch.setattr(f"{module_path}.mlflow_service.get_run_metrics", get_run_metrics)
    monkeypatch.setattr(f"{module_path}.mlflow_service.get_metric_history", get_metric_history)
    monkeypatch.setattr(f"{module_path}.mlflow_service.get_run_info", get_run_info)
    monkeypatch.setattr(f"{module_path}.mlflow_service.get_run_params", get_run_params)
    monkeypatch.setattr(f"{module_path}.mlflow_service.download_model_artifact", download_model_artifact)
    monkeypatch.setattr(f"{module_path}.mlflow_service.delete_run", delete_run)
    return calls


def allow_owned_run(monkeypatch, module_path, train_job):
    monkeypatch.setattr(
        f"{module_path}.{train_job.__class__.__name__}ViewSet.train_job_has_run",
        lambda self, current_train_job, run_id: run_id == "owned-run",
        raising=False,
    )


def set_delete_run_eligibility(monkeypatch, module_path, train_job, allowed, reason):
    monkeypatch.setattr(
        f"{module_path}.{train_job.__class__.__name__}ViewSet.check_run_delete_eligibility",
        lambda self, run_id, current_train_job: (allowed, reason),
        raising=False,
    )


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
