import pytest
import requests
from rest_framework import status

from apps.mlops.models.timeseries_predict import TimeSeriesPredictServing, TimeSeriesPredictTrainJob

from .conftest import create_train_job


pytestmark = [pytest.mark.django_db, pytest.mark.integration]

CONTAINER_INFO = {"port": 3000, "state": "running", "status": "success"}


def _create_serving():
    train_job = create_train_job(TimeSeriesPredictTrainJob, team=1)
    return TimeSeriesPredictServing.objects.create(
        name="timeseries-timeout-test",
        description="",
        team=[1],
        train_job=train_job,
        model_version="latest",
        status="inactive",
        container_info=CONTAINER_INFO,
    )


def _fake_build_predict_url(serving_id, container_info):
    return "http://fake-predict/predict"


def test_predict_uses_configured_timeout_for_max_steps(mlops_api_client, mlops_user, monkeypatch):
    mlops_user.permission["mlops"].add("timeseries_predict-Predict")
    serving = _create_serving()
    monkeypatch.setattr("apps.mlops.views.timeseries_predict.build_predict_url", _fake_build_predict_url)
    monkeypatch.setenv("TIMESERIES_PREDICT_TIMEOUT_SECONDS", "75")
    captured = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"success": True, "prediction": []}

    def fake_post(*args, **kwargs):
        captured.update(kwargs)
        assert kwargs["json"]["config"]["steps"] == 1000
        return FakeResponse()

    monkeypatch.setattr("apps.mlops.views.timeseries_predict.requests.post", fake_post)

    response = mlops_api_client.post(
        f"/api/v1/mlops/timeseries_predict_servings/{serving.id}/predict/",
        {
            "data": [{"timestamp": "2024-01-01", "value": 1}],
            "config": {"steps": 1000},
        },
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert captured["timeout"] == 80


def test_predict_timeout_reports_configured_budget(mlops_api_client, mlops_user, monkeypatch):
    mlops_user.permission["mlops"].add("timeseries_predict-Predict")
    serving = _create_serving()
    monkeypatch.setattr("apps.mlops.views.timeseries_predict.build_predict_url", _fake_build_predict_url)
    monkeypatch.setenv("TIMESERIES_PREDICT_TIMEOUT_SECONDS", "75")
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.requests.post",
        lambda *args, **kwargs: (_ for _ in ()).throw(requests.exceptions.Timeout),
    )

    response = mlops_api_client.post(
        f"/api/v1/mlops/timeseries_predict_servings/{serving.id}/predict/",
        {"data": [{"timestamp": "2024-01-01", "value": 1}], "config": {"steps": 1000}},
        format="json",
    )

    assert response.status_code == status.HTTP_504_GATEWAY_TIMEOUT
    assert response.data["error"] == "预测请求超时（超过 80 秒）"


def test_update_rejects_invalid_budget_before_removing_running_container(
    mlops_api_client,
    mlops_user,
    monkeypatch,
):
    mlops_user.permission["mlops"].add("timeseries_predict-Edit")
    serving = _create_serving()
    monkeypatch.setenv("TIMESERIES_PREDICT_TIMEOUT_SECONDS", "invalid")
    remove_calls = []
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.WebhookClient.remove",
        lambda serving_id: remove_calls.append(serving_id),
    )

    response = mlops_api_client.patch(
        f"/api/v1/mlops/timeseries_predict_servings/{serving.id}/",
        {"port": 31001},
        format="json",
    )

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "TIMESERIES_PREDICT_TIMEOUT_SECONDS" in response.data["error"]
    assert remove_calls == []
    serving.refresh_from_db()
    assert serving.port is None
