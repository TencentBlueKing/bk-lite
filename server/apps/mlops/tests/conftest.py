import types
from unittest.mock import Mock

import pytest
from rest_framework.test import APIClient

from apps.base.tests.factories import UserFactory
from apps.mlops.constants import TrainJobStatus
from apps.mlops.models.object_detection import ObjectDetectionServing


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
def mlops_add_user():
    user = UserFactory(
        username="mlops-adder",
        domain="domain.com",
        group_list=[{"id": 1, "name": "Team 1"}, {"id": 2, "name": "Team 2"}],
        roles=[],
        is_superuser=True,
    )
    user.permission = {
        "mlops": {
            "classification-Add",
        }
    }
    return user


@pytest.fixture
def mlops_add_api_client(mlops_add_user):
    client = APIClient()
    client.force_authenticate(user=mlops_add_user)
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


def create_object_detection_serving(train_job, team, *, status_value="inactive", container_info=None):
    return ObjectDetectionServing.objects.create(
        name=f"serving-{team}",
        description="",
        team=[team],
        train_job=train_job,
        model_version="latest",
        status=status_value,
        container_info=container_info or {},
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


def make_serializer_context(monkeypatch, mlops_user):
    monkeypatch.setattr(
        "apps.core.utils.serializers.get_permission_rules",
        lambda *args, **kwargs: {"team": [1], "instance": []},
    )
    return {"request": types.SimpleNamespace(user=mlops_user, COOKIES={"current_team": "1"})}


def create_dataset_release_fixture(dataset_model, train_data_model):
    dataset = dataset_model.objects.create(name="dataset-1", description="", team=[1])
    train = train_data_model.objects.create(name="train.csv", dataset=dataset, is_train_data=True)
    val = train_data_model.objects.create(name="val.csv", dataset=dataset, is_val_data=True)
    test = train_data_model.objects.create(name="test.csv", dataset=dataset, is_test_data=True)
    return dataset, train, val, test


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
