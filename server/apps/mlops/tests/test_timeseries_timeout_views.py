import pytest
import requests
from rest_framework import status

from apps.mlops.models.timeseries_predict import TimeSeriesPredictServing, TimeSeriesPredictTrainJob

from .conftest import create_train_job


pytestmark = [pytest.mark.django_db, pytest.mark.integration]

CONTAINER_INFO = {"port": 3000, "state": "running", "status": "success"}


def _create_serving(port=None):
    train_job = create_train_job(TimeSeriesPredictTrainJob, team=1)
    return TimeSeriesPredictServing.objects.create(
        name="timeseries-timeout-test",
        description="",
        team=[1],
        train_job=train_job,
        model_version="latest",
        status="inactive",
        container_info=CONTAINER_INFO,
        port=port,
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
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.TimeSeriesPredictServingViewSet.get_has_permission",
        lambda *args, **kwargs: True,
    )
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


def test_update_restores_old_service_when_new_container_fails(
    mlops_api_client,
    mlops_user,
    monkeypatch,
):
    from apps.mlops.utils.webhook_client import WebhookError

    mlops_user.permission["mlops"].add("timeseries_predict-Edit")
    serving = _create_serving(port=3000)
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.TimeSeriesPredictServingViewSet.get_has_permission",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setenv("TIMESERIES_PREDICT_TIMEOUT_SECONDS", "75")
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.get_mlflow_tracking_uri",
        lambda: "http://mlflow:15000",
    )
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.get_image_by_prefix",
        lambda prefix, algorithm: "classify-timeseries:latest",
    )
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.TimeSeriesPredictServingViewSet._resolve_model_uri",
        lambda self, instance: f"models:/timeseries/{instance.model_version}",
    )
    runtime_events = []
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.WebhookClient.remove",
        lambda serving_id: runtime_events.append(("remove", serving_id)),
    )
    serve_calls = []

    def fake_serve(*args, **kwargs):
        serve_calls.append({"args": args, "kwargs": kwargs})
        runtime_events.append(("serve", args[0]))
        if len(serve_calls) == 1:
            raise WebhookError("new container failed")
        return {"status": "success", "state": "running", "port": "3000"}

    monkeypatch.setattr("apps.mlops.views.timeseries_predict.WebhookClient.serve", fake_serve)

    response = mlops_api_client.patch(
        f"/api/v1/mlops/timeseries_predict_servings/{serving.id}/",
        {"model_version": "v2"},
        format="json",
    )

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.data["message"] == "新服务启动失败，已恢复旧配置与旧服务"
    assert runtime_events == [
        ("remove", f"TimeseriesPredict_Serving_{serving.id}"),
        ("serve", f"TimeseriesPredict_Serving_{serving.id}"),
        ("remove", f"TimeseriesPredict_Serving_{serving.id}"),
        ("serve", f"TimeseriesPredict_Serving_{serving.id}"),
    ]
    assert len(serve_calls) == 2
    assert serve_calls[0]["args"][2] == "models:/timeseries/v2"
    assert serve_calls[1]["args"][2] == "models:/timeseries/latest"
    assert serve_calls[1]["kwargs"]["port"] == 3000
    serving.refresh_from_db()
    assert serving.model_version == "latest"
    assert serving.port == 3000
    assert serving.container_info["state"] == "running"


def test_update_does_not_restore_old_service_until_failed_runtime_is_removed(
    mlops_api_client,
    mlops_user,
    monkeypatch,
):
    from apps.mlops.utils.webhook_client import WebhookError

    mlops_user.permission["mlops"].add("timeseries_predict-Edit")
    serving = _create_serving(port=3000)
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.TimeSeriesPredictServingViewSet.get_has_permission",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setenv("TIMESERIES_PREDICT_TIMEOUT_SECONDS", "75")
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.get_mlflow_tracking_uri",
        lambda: "http://mlflow:15000",
    )
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.get_image_by_prefix",
        lambda prefix, algorithm: "classify-timeseries:latest",
    )
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.TimeSeriesPredictServingViewSet._resolve_model_uri",
        lambda self, instance: f"models:/timeseries/{instance.model_version}",
    )
    remove_calls = []

    def fake_remove(serving_id):
        remove_calls.append(serving_id)
        if len(remove_calls) == 2:
            raise WebhookError("runtime cleanup unavailable")

    serve_calls = []

    def fake_serve(*args, **kwargs):
        serve_calls.append({"args": args, "kwargs": kwargs})
        raise WebhookError("new container failed")

    monkeypatch.setattr("apps.mlops.views.timeseries_predict.WebhookClient.remove", fake_remove)
    monkeypatch.setattr("apps.mlops.views.timeseries_predict.WebhookClient.serve", fake_serve)

    response = mlops_api_client.patch(
        f"/api/v1/mlops/timeseries_predict_servings/{serving.id}/",
        {"model_version": "v2"},
        format="json",
    )

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.data["message"] == "新服务启动失败，旧配置已恢复但运行时残留未清理"
    assert len(remove_calls) == 2
    assert len(serve_calls) == 1
    serving.refresh_from_db()
    assert serving.model_version == "latest"
    assert serving.port == 3000
    assert serving.container_info["status"] == "error"


def test_update_permission_denial_does_not_restart_runtime(
    mlops_api_client,
    mlops_user,
    monkeypatch,
):
    mlops_user.permission["mlops"].add("timeseries_predict-Edit")
    serving = _create_serving(port=3000)
    monkeypatch.setenv("TIMESERIES_PREDICT_TIMEOUT_SECONDS", "75")
    unexpected_calls = []
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.get_mlflow_tracking_uri",
        lambda: unexpected_calls.append("mlflow_tracking_uri"),
    )
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.get_image_by_prefix",
        lambda prefix, algorithm: unexpected_calls.append("train_image"),
    )
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.get_timeseries_predict_budget_seconds",
        lambda: unexpected_calls.append("predict_budget"),
    )
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.TimeSeriesPredictServingViewSet._resolve_model_uri",
        lambda self, instance: unexpected_calls.append("model_uri"),
    )
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.TimeSeriesPredictServingViewSet.get_has_permission",
        lambda *args, **kwargs: False,
    )
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.WebhookClient.remove",
        lambda serving_id: unexpected_calls.append("remove"),
    )
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.WebhookClient.serve",
        lambda *args, **kwargs: unexpected_calls.append("serve"),
    )

    response = mlops_api_client.patch(
        f"/api/v1/mlops/timeseries_predict_servings/{serving.id}/",
        {"model_version": "v2"},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["result"] is False
    assert unexpected_calls == []
    serving.refresh_from_db()
    assert serving.model_version == "latest"
    assert serving.container_info["state"] == "running"
