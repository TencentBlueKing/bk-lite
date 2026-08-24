from types import SimpleNamespace

import pandas as pd
import pydantic.root_model  # noqa
import pytest
from mlflow.exceptions import MlflowException
from mlflow.protos.databricks_pb2 import INVALID_PARAMETER_VALUE, RESOURCE_DOES_NOT_EXIST

from apps.mlops.utils import mlflow_service
from apps.mlops.views.anomaly_detection import AnomalyDetectionTrainJobViewSet

pytestmark = pytest.mark.unit


def test_train_job_has_run_uses_one_precise_lookup_independent_of_history_size(monkeypatch):
    view = AnomalyDetectionTrainJobViewSet()
    train_job = SimpleNamespace(id=7, algorithm="demo")
    observed = []

    monkeypatch.setattr(
        "apps.mlops.views.base.mlflow_service.get_experiment_by_name",
        lambda name: SimpleNamespace(experiment_id="experiment-7"),
    )

    for history_size in (1, 50, 200, 1000):
        calls = {"full_query": 0, "returned_runs": 0, "precise_query": 0}

        def full_query(experiment_id):
            calls["full_query"] += 1
            calls["returned_runs"] += history_size
            return pd.DataFrame({"run_id": [f"historical-{index}" for index in range(history_size - 1)] + ["owned-run"]})

        def precise_query(experiment_id, run_id):
            calls["precise_query"] += 1
            return experiment_id == "experiment-7" and run_id == "owned-run"

        monkeypatch.setattr("apps.mlops.views.base.mlflow_service.get_experiment_runs", full_query)
        monkeypatch.setattr(
            "apps.mlops.views.base.mlflow_service.run_belongs_to_experiment",
            precise_query,
        )

        assert view.train_job_has_run(train_job, "owned-run") is True
        observed.append((history_size, calls))

    assert observed == [
        (1, {"full_query": 0, "returned_runs": 0, "precise_query": 1}),
        (50, {"full_query": 0, "returned_runs": 0, "precise_query": 1}),
        (200, {"full_query": 0, "returned_runs": 0, "precise_query": 1}),
        (1000, {"full_query": 0, "returned_runs": 0, "precise_query": 1}),
    ]


def test_train_job_has_run_returns_false_when_experiment_is_missing(monkeypatch):
    view = AnomalyDetectionTrainJobViewSet()
    train_job = SimpleNamespace(id=7, algorithm="demo")
    precise_query = pytest.fail
    monkeypatch.setattr(
        "apps.mlops.views.base.mlflow_service.get_experiment_by_name",
        lambda name: None,
    )
    monkeypatch.setattr(
        "apps.mlops.views.base.mlflow_service.run_belongs_to_experiment",
        precise_query,
    )

    assert view.train_job_has_run(train_job, "run-1") is False


def test_train_job_has_run_propagates_experiment_lookup_failure(monkeypatch):
    view = AnomalyDetectionTrainJobViewSet()
    train_job = SimpleNamespace(id=7, algorithm="demo")

    def fail_lookup(name):
        raise RuntimeError("mlflow unavailable")

    monkeypatch.setattr(
        "apps.mlops.views.base.mlflow_service.get_experiment_by_name",
        fail_lookup,
    )

    with pytest.raises(RuntimeError, match="mlflow unavailable"):
        view.train_job_has_run(train_job, "run-1")


def test_run_belongs_to_experiment_accepts_active_owned_run(mocker):
    run = SimpleNamespace(info=SimpleNamespace(experiment_id="e1", lifecycle_stage="active"))
    get_run = mocker.Mock(return_value=run)
    mocker.patch(
        "apps.mlops.utils.mlflow_service.get_mlflow_client",
        return_value=SimpleNamespace(get_run=get_run),
    )

    assert mlflow_service.run_belongs_to_experiment("e1", "r1") is True
    get_run.assert_called_once_with("r1")


@pytest.mark.parametrize(
    ("experiment_id", "lifecycle_stage"),
    [("other", "active"), ("e1", "deleted"), ("e1", None)],
)
def test_run_belongs_to_experiment_rejects_cross_experiment_or_deleted_run(mocker, experiment_id, lifecycle_stage):
    run = SimpleNamespace(
        info=SimpleNamespace(
            experiment_id=experiment_id,
            lifecycle_stage=lifecycle_stage,
        )
    )
    mocker.patch(
        "apps.mlops.utils.mlflow_service.get_mlflow_client",
        return_value=SimpleNamespace(get_run=lambda run_id: run),
    )

    assert mlflow_service.run_belongs_to_experiment("e1", "r1") is False


def test_run_belongs_to_experiment_returns_false_when_run_is_missing(mocker):
    missing = MlflowException(
        "missing",
        error_code=RESOURCE_DOES_NOT_EXIST,
    )
    client = SimpleNamespace(get_run=mocker.Mock(side_effect=missing))
    mocker.patch("apps.mlops.utils.mlflow_service.get_mlflow_client", return_value=client)

    assert mlflow_service.run_belongs_to_experiment("e1", "missing") is False


def test_run_belongs_to_experiment_returns_false_when_run_id_is_invalid(mocker):
    invalid = MlflowException(
        "invalid run id",
        error_code=INVALID_PARAMETER_VALUE,
    )
    client = SimpleNamespace(get_run=mocker.Mock(side_effect=invalid))
    mocker.patch("apps.mlops.utils.mlflow_service.get_mlflow_client", return_value=client)

    assert mlflow_service.run_belongs_to_experiment("e1", "bad.id") is False


def test_run_belongs_to_experiment_reraises_unexpected_mlflow_failure(mocker):
    denied = MlflowException("denied", error_code="PERMISSION_DENIED")
    client = SimpleNamespace(get_run=mocker.Mock(side_effect=denied))
    mocker.patch("apps.mlops.utils.mlflow_service.get_mlflow_client", return_value=client)

    with pytest.raises(MlflowException, match="denied"):
        mlflow_service.run_belongs_to_experiment("e1", "r1")
