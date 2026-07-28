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
        {
            "model_version": "v2",
            "name": "must-roll-back",
            "description": "must-roll-back",
        },
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
    assert serving.name == "timeseries-timeout-test"
    assert serving.description == ""
    assert serving.port == 3000
    assert serving.container_info["state"] == "running"


def test_update_failure_does_not_overwrite_concurrent_database_update(
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
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.WebhookClient.remove",
        lambda serving_id: None,
    )
    serve_calls = 0

    def fake_serve(*args, **kwargs):
        nonlocal serve_calls
        serve_calls += 1
        if serve_calls == 1:
            TimeSeriesPredictServing.objects.filter(pk=serving.pk).update(
                name="concurrent-name",
                description="concurrent-description",
            )
            raise WebhookError("new container failed")
        return {"status": "success", "state": "running", "port": "3000"}

    monkeypatch.setattr("apps.mlops.views.timeseries_predict.WebhookClient.serve", fake_serve)

    response = mlops_api_client.patch(
        f"/api/v1/mlops/timeseries_predict_servings/{serving.id}/",
        {
            "model_version": "v2",
            "name": "request-name",
            "description": "request-description",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    serving.refresh_from_db()
    assert serving.model_version == "latest"
    assert serving.name == "concurrent-name"
    assert serving.description == "concurrent-description"
    assert serving.container_info["state"] == "running"


def test_update_acquires_row_lock_before_runtime_transition(
    mlops_api_client,
    mlops_user,
    monkeypatch,
):
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
    original_select_for_update = TimeSeriesPredictServing.objects.select_for_update

    def tracked_select_for_update(*args, **kwargs):
        runtime_events.append("lock")
        return original_select_for_update(*args, **kwargs)

    monkeypatch.setattr(TimeSeriesPredictServing.objects, "select_for_update", tracked_select_for_update)
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.WebhookClient.remove",
        lambda serving_id: runtime_events.append("remove"),
    )

    def fake_serve(*args, **kwargs):
        runtime_events.append("serve")
        return {"status": "success", "state": "running", "port": "3000"}

    monkeypatch.setattr("apps.mlops.views.timeseries_predict.WebhookClient.serve", fake_serve)

    response = mlops_api_client.patch(
        f"/api/v1/mlops/timeseries_predict_servings/{serving.id}/",
        {"model_version": "v2"},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert runtime_events == ["lock", "remove", "serve"]
    serving.refresh_from_db()
    assert serving.model_version == "v2"
    assert serving.container_info["state"] == "running"


def test_update_reconciles_remove_timeout_before_restoring_old_runtime(
    mlops_api_client,
    mlops_user,
    monkeypatch,
):
    from apps.mlops.utils.webhook_client import WebhookTimeoutError

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
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.WebhookClient.remove",
        lambda serving_id: (_ for _ in ()).throw(WebhookTimeoutError("response lost")),
    )
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.WebhookClient.get_status",
        lambda ids: [{"id": ids[0], "status": "success", "state": "not_found", "port": ""}],
    )
    serve_calls = []
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.WebhookClient.serve",
        lambda *args, **kwargs: serve_calls.append((args, kwargs))
        or {"status": "success", "state": "running", "port": "3000"},
    )

    response = mlops_api_client.patch(
        f"/api/v1/mlops/timeseries_predict_servings/{serving.id}/",
        {"model_version": "v2"},
        format="json",
    )

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.data["message"] == "配置已回滚，并在对账确认旧服务已删除后恢复旧服务"
    assert len(serve_calls) == 1
    assert serve_calls[0][0][2] == "models:/timeseries/latest"
    serving.refresh_from_db()
    assert serving.model_version == "latest"
    assert serving.container_info["state"] == "running"


def test_update_remove_error_cleans_stopped_runtime_before_restore(
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

    def fake_remove(serving_id):
        runtime_events.append(("remove", serving_id))
        if len(runtime_events) == 1:
            raise WebhookError("stop succeeded but rm failed")

    status_calls = 0

    def fake_get_status(ids):
        nonlocal status_calls
        status_calls += 1
        state = "completed" if status_calls == 1 else "not_found"
        runtime_events.append(("status", state))
        return [{"id": ids[0], "status": "success", "state": state, "port": ""}]

    def fake_serve(*args, **kwargs):
        runtime_events.append(("serve", args[0]))
        return {"status": "success", "state": "running", "port": "3000"}

    monkeypatch.setattr("apps.mlops.views.timeseries_predict.WebhookClient.remove", fake_remove)
    monkeypatch.setattr("apps.mlops.views.timeseries_predict.WebhookClient.get_status", fake_get_status)
    monkeypatch.setattr("apps.mlops.views.timeseries_predict.WebhookClient.serve", fake_serve)

    response = mlops_api_client.patch(
        f"/api/v1/mlops/timeseries_predict_servings/{serving.id}/",
        {"model_version": "v2"},
        format="json",
    )

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert runtime_events == [
        ("remove", f"TimeseriesPredict_Serving_{serving.id}"),
        ("status", "completed"),
        ("remove", f"TimeseriesPredict_Serving_{serving.id}"),
        ("status", "not_found"),
        ("serve", f"TimeseriesPredict_Serving_{serving.id}"),
    ]
    serving.refresh_from_db()
    assert serving.model_version == "latest"
    assert serving.container_info["state"] == "running"


def test_update_remove_timeout_with_failed_status_check_is_not_marked_running(
    mlops_api_client,
    mlops_user,
    monkeypatch,
):
    from apps.mlops.utils.webhook_client import WebhookError, WebhookTimeoutError

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
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.WebhookClient.remove",
        lambda serving_id: (_ for _ in ()).throw(WebhookTimeoutError("response lost")),
    )
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.WebhookClient.get_status",
        lambda ids: (_ for _ in ()).throw(WebhookError("status unavailable")),
    )
    unexpected_serve_calls = []
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.WebhookClient.serve",
        lambda *args, **kwargs: unexpected_serve_calls.append((args, kwargs)),
    )

    response = mlops_api_client.patch(
        f"/api/v1/mlops/timeseries_predict_servings/{serving.id}/",
        {"model_version": "v2"},
        format="json",
    )

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.data["message"] == "配置已回滚，但旧服务删除结果未知"
    assert unexpected_serve_calls == []
    serving.refresh_from_db()
    assert serving.model_version == "latest"
    assert serving.container_info["state"] == "unknown"
    assert serving.container_info["status"] == "error"


def test_stale_instance_rule_cannot_bypass_current_team_scope(monkeypatch):
    from types import SimpleNamespace

    from apps.core.utils import viewset_utils
    from apps.mlops.views.timeseries_predict import TimeSeriesPredictServingViewSet

    serving = _create_serving()
    serving.team = [2]
    serving.save(update_fields=["team"])
    request = SimpleNamespace(
        user=SimpleNamespace(
            is_superuser=False,
            group_list=[{"id": 1}],
            group_tree=[],
        ),
        COOKIES={"current_team": "1", "include_children": "0"},
    )
    monkeypatch.setattr(viewset_utils, "get_current_team", lambda request, default=None: "1")
    monkeypatch.setattr(
        viewset_utils,
        "get_permission_rules",
        lambda *args, **kwargs: {"instance": [{"id": serving.id}], "team": []},
    )
    viewset = TimeSeriesPredictServingViewSet()

    queryset = viewset.get_queryset_by_permission(request, TimeSeriesPredictServing.objects.all())

    assert not queryset.filter(pk=serving.pk).exists()


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


def test_update_wrong_current_team_does_not_run_external_preflight(
    mlops_api_client,
    mlops_user,
    monkeypatch,
):
    mlops_user.permission["mlops"].add("timeseries_predict-Edit")
    mlops_user.group_tree = [
        {
            "id": 2,
            "subGroups": [{"id": 1, "subGroups": []}],
        }
    ]
    mlops_api_client.cookies["current_team"] = "2"
    mlops_api_client.cookies["include_children"] = "1"
    serving = _create_serving(port=3000)
    unexpected_calls = []
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.TimeSeriesPredictServingViewSet.get_has_permission",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.get_timeseries_predict_budget_seconds",
        lambda: unexpected_calls.append("predict_budget"),
    )
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.get_mlflow_tracking_uri",
        lambda: unexpected_calls.append("mlflow_tracking_uri"),
    )
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.get_image_by_prefix",
        lambda *args: unexpected_calls.append("train_image"),
    )

    response = mlops_api_client.patch(
        f"/api/v1/mlops/timeseries_predict_servings/{serving.id}/",
        {"model_version": "v2"},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["result"] is False
    assert unexpected_calls == []


def test_update_rejects_unmanaged_new_team_before_external_preflight(
    mlops_api_client,
    mlops_user,
    monkeypatch,
):
    mlops_user.permission["mlops"].add("timeseries_predict-Edit")
    serving = _create_serving(port=3000)
    unexpected_calls = []
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.TimeSeriesPredictServingViewSet.get_has_permission",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.get_timeseries_predict_budget_seconds",
        lambda: unexpected_calls.append("predict_budget"),
    )
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.get_mlflow_tracking_uri",
        lambda: unexpected_calls.append("mlflow_tracking_uri"),
    )

    response = mlops_api_client.patch(
        f"/api/v1/mlops/timeseries_predict_servings/{serving.id}/",
        {"team": [1, 3], "model_version": "v2"},
        format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert unexpected_calls == []
