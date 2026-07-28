import pytest
import requests
from rest_framework import status

from apps.mlops.models.timeseries_predict import (
    TimeSeriesPredictServing,
    TimeSeriesPredictTrainJob,
    TimeSeriesRuntimeCleanupIntent,
    TimeSeriesRuntimeGuard,
)

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


def _create_serving_payload(train_job, name):
    return {
        "name": name,
        "description": "",
        "team": [1],
        "train_job": train_job.id,
        "model_version": "latest",
        "status": "inactive",
        "port": 3000,
    }


def _mock_create_runtime_dependencies(monkeypatch):
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
    assert serving.container_info["_runtime_generation"] == 2


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
    assert serving.container_info["_runtime_generation"] == 2


@pytest.mark.parametrize(
    ("action_name", "permission_name"),
    [
        ("start", "timeseries_predict-Start"),
        ("stop", "timeseries_predict-Stop"),
        ("remove", "timeseries_predict-Remove"),
    ],
)
def test_runtime_actions_acquire_shared_row_lock(
    mlops_api_client,
    mlops_user,
    monkeypatch,
    action_name,
    permission_name,
):
    mlops_user.permission["mlops"].add(permission_name)
    serving = _create_serving(port=3000)
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
        "apps.mlops.views.timeseries_predict.WebhookClient.serve",
        lambda *args, **kwargs: runtime_events.append("start")
        or {"status": "success", "state": "running", "port": "3000"},
    )
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.WebhookClient.stop",
        lambda serving_id: runtime_events.append("stop")
        or {"status": "success", "state": "terminating"},
    )
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.WebhookClient.remove",
        lambda serving_id: runtime_events.append("remove") or {"status": "success"},
    )

    response = mlops_api_client.post(
        f"/api/v1/mlops/timeseries_predict_servings/{serving.id}/{action_name}/",
        {},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert runtime_events == ["lock", action_name]
    serving.refresh_from_db()
    expected_state = {
        "start": "running",
        "stop": "terminating",
        "remove": "removed",
    }[action_name]
    assert serving.container_info["state"] == expected_state
    assert serving.container_info["_runtime_generation"] == 2


@pytest.mark.parametrize(
    ("action_name", "webhook_method", "permission_name", "actual_state"),
    [
        ("start", "serve", "timeseries_predict-Start", "running"),
        ("stop", "stop", "timeseries_predict-Stop", "not_found"),
        ("remove", "remove", "timeseries_predict-Remove", "not_found"),
    ],
)
def test_runtime_action_timeout_reconciles_and_advances_generation(
    mlops_api_client,
    mlops_user,
    monkeypatch,
    action_name,
    webhook_method,
    permission_name,
    actual_state,
):
    from apps.mlops.utils.webhook_client import WebhookTimeoutError

    mlops_user.permission["mlops"].add(permission_name)
    serving = _create_serving(port=3000)
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
        f"apps.mlops.views.timeseries_predict.WebhookClient.{webhook_method}",
        lambda *args, **kwargs: (_ for _ in ()).throw(WebhookTimeoutError("response lost")),
    )
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.WebhookClient.get_status",
        lambda ids: [{"id": ids[0], "status": "success", "state": actual_state}],
    )

    response = mlops_api_client.post(
        f"/api/v1/mlops/timeseries_predict_servings/{serving.id}/{action_name}/",
        {},
        format="json",
    )

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    serving.refresh_from_db()
    assert serving.container_info["state"] == actual_state
    assert serving.container_info["_runtime_generation"] == 2


def test_runtime_action_timeout_without_matching_status_keeps_unknown(
    mlops_api_client,
    mlops_user,
    monkeypatch,
):
    from apps.mlops.utils.webhook_client import WebhookTimeoutError

    mlops_user.permission["mlops"].add("timeseries_predict-Stop")
    serving = _create_serving(port=3000)
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.WebhookClient.stop",
        lambda serving_id: (_ for _ in ()).throw(WebhookTimeoutError("response lost")),
    )
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.WebhookClient.get_status",
        lambda ids: [{"id": "TimeseriesPredict_Serving_foreign", "status": "success", "state": "running"}],
    )

    response = mlops_api_client.post(
        f"/api/v1/mlops/timeseries_predict_servings/{serving.id}/stop/",
        {},
        format="json",
    )

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    serving.refresh_from_db()
    assert serving.container_info["state"] == "unknown"
    assert serving.container_info["_runtime_generation"] == 2


def test_retrieve_rejects_foreign_runtime_status(
    mlops_api_client,
    monkeypatch,
):
    serving = _create_serving(port=3000)
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.TimeSeriesPredictServingViewSet.get_has_permission",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.WebhookClient.get_status",
        lambda ids: [{"id": "TimeseriesPredict_Serving_foreign", "status": "success", "state": "running"}],
    )

    response = mlops_api_client.get(
        f"/api/v1/mlops/timeseries_predict_servings/{serving.id}/",
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["container_info"]["state"] == "unknown"
    assert "foreign" not in str(response.data["container_info"])


@pytest.mark.parametrize("runtime_response_kind", ["missing_state", "non_list"])
def test_list_rejects_runtime_status_without_executable_contract(
    mlops_api_client,
    monkeypatch,
    runtime_response_kind,
):
    from apps.mlops.views.timeseries_predict import TimeSeriesPredictServingViewSet

    serving = _create_serving(port=3000)
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.TimeSeriesPredictServingViewSet.get_has_permission",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        "apps.core.utils.viewset_utils.get_permission_rules",
        lambda *args, **kwargs: {"team": [1], "instance": []},
    )

    def invalid_status(ids):
        invalid_item = {
            "id": ids[0],
            "status": "error",
            "message": "Container not found",
        }
        return [invalid_item] if runtime_response_kind == "missing_state" else invalid_item

    finalize_calls = []
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.WebhookClient.get_status",
        invalid_status,
    )
    monkeypatch.setattr(
        TimeSeriesPredictServingViewSet,
        "_finalize_runtime_status_sync",
        lambda *args, **kwargs: finalize_calls.append((args, kwargs)),
    )

    response = mlops_api_client.get(
        "/api/v1/mlops/timeseries_predict_servings/",
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    items = response.data.get("items", []) if isinstance(response.data, dict) else response.data
    response_serving = next(item for item in items if item["id"] == serving.id)
    assert response_serving["container_info"]["state"] == "unknown"
    assert finalize_calls == []
    serving.refresh_from_db()
    assert serving.container_info["state"] == "running"
    assert "Container not found" not in str(serving.container_info)


def test_start_already_exists_rejects_foreign_runtime_status(
    mlops_api_client,
    mlops_user,
    monkeypatch,
):
    from apps.mlops.utils.webhook_client import WebhookError

    mlops_user.permission["mlops"].add("timeseries_predict-Start")
    serving = _create_serving(port=3000)
    _mock_create_runtime_dependencies(monkeypatch)
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.WebhookClient.serve",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            WebhookError("exists", code="CONTAINER_ALREADY_EXISTS")
        ),
    )
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.WebhookClient.get_status",
        lambda ids: [{"id": "TimeseriesPredict_Serving_foreign", "status": "success", "state": "running"}],
    )

    response = mlops_api_client.post(
        f"/api/v1/mlops/timeseries_predict_servings/{serving.id}/start/",
        {},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["container_info"]["state"] == "unknown"
    assert response.data["container_info"]["id"] == f"TimeseriesPredict_Serving_{serving.id}"


def test_create_already_exists_rejects_foreign_runtime_status(
    mlops_api_client,
    mlops_user,
    monkeypatch,
):
    from apps.mlops.utils.webhook_client import WebhookError

    mlops_user.permission["mlops"].add("timeseries_predict-Add")
    train_job = create_train_job(TimeSeriesPredictTrainJob, team=1)
    _mock_create_runtime_dependencies(monkeypatch)
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.WebhookClient.serve",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            WebhookError("exists", code="CONTAINER_ALREADY_EXISTS")
        ),
    )
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.WebhookClient.get_status",
        lambda ids: [{"id": "TimeseriesPredict_Serving_foreign", "status": "success", "state": "running"}],
    )

    response = mlops_api_client.post(
        "/api/v1/mlops/timeseries_predict_servings/",
        _create_serving_payload(train_job, "foreign-create-status"),
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["container_info"]["state"] == "unknown"
    assert response.data["container_info"]["id"] == f"TimeseriesPredict_Serving_{response.data['id']}"


def test_create_initializes_runtime_inside_atomic_row_lock(
    mlops_api_client,
    mlops_user,
    monkeypatch,
):
    from django.db import connection
    from django.db.models import QuerySet

    mlops_user.permission["mlops"].add("timeseries_predict-Add")
    train_job = create_train_job(TimeSeriesPredictTrainJob, team=1)
    _mock_create_runtime_dependencies(monkeypatch)
    locked_in_atomic = []
    runtime_guard_locked = []
    original_select_for_update = QuerySet.select_for_update

    def track_select_for_update(queryset, *args, **kwargs):
        if queryset.model is TimeSeriesPredictServing:
            locked_in_atomic.append(connection.in_atomic_block)
        if queryset.model is TimeSeriesRuntimeGuard:
            runtime_guard_locked.append(connection.in_atomic_block)
        return original_select_for_update(queryset, *args, **kwargs)

    def fake_serve(container_id, *args, **kwargs):
        assert connection.in_atomic_block
        assert locked_in_atomic == [True]
        assert runtime_guard_locked == [True]
        return {"id": container_id, "status": "success", "state": "running", "port": "3000"}

    monkeypatch.setattr(QuerySet, "select_for_update", track_select_for_update)
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.WebhookClient.serve",
        fake_serve,
    )

    response = mlops_api_client.post(
        "/api/v1/mlops/timeseries_predict_servings/",
        _create_serving_payload(train_job, "atomic-create"),
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["container_info"]["state"] == "running"
    assert response.data["container_info"]["_runtime_generation"] == 2
    assert locked_in_atomic == [True]
    assert runtime_guard_locked == [True]
    assert TimeSeriesRuntimeGuard.objects.filter(serving_id=response.data["id"]).exists()


def test_create_save_failure_rolls_back_record_and_cleans_runtime(
    mlops_api_client,
    mlops_user,
    monkeypatch,
):
    from django.db import DatabaseError

    mlops_user.permission["mlops"].add("timeseries_predict-Add")
    train_job = create_train_job(TimeSeriesPredictTrainJob, team=1)
    _mock_create_runtime_dependencies(monkeypatch)
    runtime_ids = []
    removed_ids = []
    original_save = TimeSeriesPredictServing.save

    def fake_serve(container_id, *args, **kwargs):
        runtime_ids.append(container_id)
        return {"id": container_id, "status": "success", "state": "running", "port": "3000"}

    def fail_final_save(instance, *args, **kwargs):
        if kwargs.get("update_fields") == ["container_info", "port"]:
            raise DatabaseError("commit state unavailable")
        return original_save(instance, *args, **kwargs)

    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.WebhookClient.serve",
        fake_serve,
    )
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.WebhookClient.remove",
        lambda container_id: removed_ids.append(container_id),
    )
    monkeypatch.setattr(
        "apps.mlops.services.timeseries_runtime_cleanup.WebhookClient.get_status",
        lambda ids: [{"id": ids[0], "status": "success", "state": "not_found"}],
    )
    monkeypatch.setattr(TimeSeriesPredictServing, "save", fail_final_save)

    response = mlops_api_client.post(
        "/api/v1/mlops/timeseries_predict_servings/",
        _create_serving_payload(train_job, "failed-create"),
        format="json",
    )

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert runtime_ids
    assert removed_ids == runtime_ids
    assert not TimeSeriesPredictServing.objects.filter(name="failed-create").exists()
    cleanup_intent = TimeSeriesRuntimeCleanupIntent.objects.get(
        container_id=runtime_ids[0],
    )
    assert cleanup_intent.status == TimeSeriesRuntimeCleanupIntent.Status.COMPLETED


def test_create_cleanup_failure_dispatches_retry_task(monkeypatch):
    from apps.mlops.views.timeseries_predict import TimeSeriesPredictServingViewSet

    dispatch_calls = []
    monkeypatch.setattr(
        "apps.mlops.services.timeseries_runtime_cleanup.process_runtime_cleanup_intent",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("cleanup unavailable")),
    )
    monkeypatch.setattr(
        "apps.mlops.tasks.runtime_cleanup.cleanup_orphan_timeseries_runtime.apply_async",
        lambda *args, **kwargs: dispatch_calls.append((args, kwargs)),
    )

    TimeSeriesPredictServingViewSet._cleanup_uncommitted_create_runtime(
        "TimeseriesPredict_Serving_9001",
        9001,
        "31bee19f-34bf-47c8-b1d8-3ba0826ff26b",
    )

    intent = TimeSeriesRuntimeCleanupIntent.objects.get(serving_id=9001)
    assert dispatch_calls == [
        (
            (),
            {
                "args": (intent.pk,),
                "retry": True,
                "retry_policy": {
                    "max_retries": 5,
                    "interval_start": 0,
                    "interval_step": 1,
                    "interval_max": 5,
                },
            },
        )
    ]


def test_cleanup_intent_persist_failure_dispatches_bootstrap_task(monkeypatch):
    from apps.mlops.views.timeseries_predict import TimeSeriesPredictServingViewSet

    dispatch_calls = []
    monkeypatch.setattr(
        "apps.mlops.services.timeseries_runtime_cleanup.create_runtime_cleanup_intent",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("database unavailable")),
    )
    monkeypatch.setattr(
        "apps.mlops.tasks.runtime_cleanup.bootstrap_timeseries_runtime_cleanup.apply_async",
        lambda *args, **kwargs: dispatch_calls.append((args, kwargs)),
    )

    TimeSeriesPredictServingViewSet._cleanup_uncommitted_create_runtime(
        "TimeseriesPredict_Serving_9008",
        9008,
        "973a0b28-1ef9-4767-b72f-bb4c281c6a2c",
    )

    assert dispatch_calls == [
        (
            (),
            {
                "args": (
                    "TimeseriesPredict_Serving_9008",
                    9008,
                    "973a0b28-1ef9-4767-b72f-bb4c281c6a2c",
                ),
                "retry": True,
                "retry_policy": {
                    "max_retries": 5,
                    "interval_start": 0,
                    "interval_step": 1,
                    "interval_max": 5,
                },
            },
        )
    ]


def test_orphan_cleanup_confirms_not_found_after_lost_remove_response(monkeypatch):
    from apps.mlops.services.timeseries_runtime_cleanup import (
        reconcile_orphan_timeseries_runtime,
    )
    from apps.mlops.utils.webhook_client import WebhookTimeoutError

    monkeypatch.setattr(
        "apps.mlops.services.timeseries_runtime_cleanup.WebhookClient.remove",
        lambda container_id: (_ for _ in ()).throw(WebhookTimeoutError("response lost")),
    )
    monkeypatch.setattr(
        "apps.mlops.services.timeseries_runtime_cleanup.WebhookClient.get_status",
        lambda ids: [{"id": ids[0], "status": "success", "state": "not_found"}],
    )

    result = reconcile_orphan_timeseries_runtime(
        "TimeseriesPredict_Serving_9002",
        9002,
    )

    assert result["result"] is True
    assert result["state"] == "not_found"
    assert TimeSeriesRuntimeGuard.objects.filter(serving_id=9002).exists()


def test_orphan_cleanup_stops_when_database_id_is_owned(monkeypatch):
    from apps.mlops.services.timeseries_runtime_cleanup import (
        reconcile_orphan_timeseries_runtime,
    )

    serving = _create_serving(port=3000)
    unexpected_remove_calls = []
    monkeypatch.setattr(
        "apps.mlops.services.timeseries_runtime_cleanup.WebhookClient.remove",
        lambda container_id: unexpected_remove_calls.append(container_id),
    )

    result = reconcile_orphan_timeseries_runtime(
        f"TimeseriesPredict_Serving_{serving.id}",
        serving.id,
    )

    assert result["result"] is False
    assert result["reason"] == "serving id is owned by a database record"
    assert unexpected_remove_calls == []


def test_orphan_cleanup_task_retries_until_not_found(monkeypatch):
    from celery.exceptions import Retry

    from apps.mlops.services.timeseries_runtime_cleanup import (
        create_runtime_cleanup_intent,
    )
    from apps.mlops.tasks.runtime_cleanup import cleanup_orphan_timeseries_runtime

    retry_calls = []
    intent = create_runtime_cleanup_intent(
        "TimeseriesPredict_Serving_9003",
        9003,
        "8dcfd813-d1ec-45c8-8a47-2c9b8acbc6ac",
    )
    monkeypatch.setattr(
        "apps.mlops.tasks.runtime_cleanup.process_runtime_cleanup_intent",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("still running")),
    )

    def fake_retry(*args, **kwargs):
        retry_calls.append((args, kwargs))
        raise Retry()

    monkeypatch.setattr(cleanup_orphan_timeseries_runtime, "retry", fake_retry)

    with pytest.raises(Retry):
        cleanup_orphan_timeseries_runtime.run(intent.pk)

    assert cleanup_orphan_timeseries_runtime.max_retries is None
    assert cleanup_orphan_timeseries_runtime.acks_late is True
    assert cleanup_orphan_timeseries_runtime.reject_on_worker_lost is True
    assert retry_calls[0][1]["countdown"] == 30


def test_cleanup_bootstrap_task_retries_until_intent_can_be_persisted(monkeypatch):
    from celery.exceptions import Retry

    from apps.mlops.tasks.runtime_cleanup import (
        bootstrap_timeseries_runtime_cleanup,
    )

    retry_calls = []
    monkeypatch.setattr(
        "apps.mlops.tasks.runtime_cleanup.create_runtime_cleanup_intent",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("database unavailable")),
    )

    def fake_retry(*args, **kwargs):
        retry_calls.append((args, kwargs))
        raise Retry()

    monkeypatch.setattr(bootstrap_timeseries_runtime_cleanup, "retry", fake_retry)

    with pytest.raises(Retry):
        bootstrap_timeseries_runtime_cleanup.run(
            "TimeseriesPredict_Serving_9009",
            9009,
            "d9be670a-d486-4e49-a5b7-351c3120085f",
        )

    assert bootstrap_timeseries_runtime_cleanup.max_retries is None
    assert bootstrap_timeseries_runtime_cleanup.acks_late is True
    assert bootstrap_timeseries_runtime_cleanup.reject_on_worker_lost is True
    assert retry_calls[0][1]["countdown"] == 30


def test_cleanup_intent_survives_initial_broker_publish_failure(monkeypatch):
    from datetime import timedelta

    from django.utils import timezone

    from apps.mlops.tasks.runtime_cleanup import (
        dispatch_pending_timeseries_runtime_cleanup,
    )
    from apps.mlops.views.timeseries_predict import TimeSeriesPredictServingViewSet

    monkeypatch.setattr(
        "apps.mlops.services.timeseries_runtime_cleanup.process_runtime_cleanup_intent",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("cleanup unavailable")),
    )
    monkeypatch.setattr(
        "apps.mlops.tasks.runtime_cleanup.cleanup_orphan_timeseries_runtime.apply_async",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("broker unavailable")),
    )

    TimeSeriesPredictServingViewSet._cleanup_uncommitted_create_runtime(
        "TimeseriesPredict_Serving_9004",
        9004,
        "e5d772ac-2516-4e46-a4cf-afc8bbd35d4d",
    )

    intent = TimeSeriesRuntimeCleanupIntent.objects.get(serving_id=9004)
    assert intent.status == TimeSeriesRuntimeCleanupIntent.Status.PENDING

    scheduled = []
    TimeSeriesRuntimeCleanupIntent.objects.filter(pk=intent.pk).update(
        next_retry_at=timezone.now() - timedelta(seconds=1),
    )
    monkeypatch.setattr(
        "apps.mlops.tasks.runtime_cleanup.cleanup_orphan_timeseries_runtime.delay",
        lambda intent_id: scheduled.append(intent_id),
    )

    result = dispatch_pending_timeseries_runtime_cleanup()

    assert result == {"claimed": 1, "scheduled": 1}
    assert scheduled == [intent.pk]


def test_cleanup_intent_records_retry_then_completes(monkeypatch):
    from apps.mlops.services.timeseries_runtime_cleanup import (
        create_runtime_cleanup_intent,
        process_runtime_cleanup_intent,
    )

    intent = create_runtime_cleanup_intent(
        "TimeseriesPredict_Serving_9005",
        9005,
        "ec948061-cbdb-45c0-85a3-1c0ac45ed42f",
    )
    monkeypatch.setattr(
        "apps.mlops.services.timeseries_runtime_cleanup.WebhookClient.remove",
        lambda container_id: {"status": "success"},
    )
    monkeypatch.setattr(
        "apps.mlops.services.timeseries_runtime_cleanup.WebhookClient.get_status",
        lambda ids: [{"id": ids[0], "status": "success", "state": "running"}],
    )

    with pytest.raises(RuntimeError, match="state=running"):
        process_runtime_cleanup_intent(intent.pk)

    intent.refresh_from_db()
    assert intent.status == TimeSeriesRuntimeCleanupIntent.Status.PENDING
    assert intent.attempts == 1
    assert intent.next_retry_at is not None
    assert "state=running" in intent.last_error

    monkeypatch.setattr(
        "apps.mlops.services.timeseries_runtime_cleanup.WebhookClient.get_status",
        lambda ids: [{"id": ids[0], "status": "success", "state": "not_found"}],
    )
    result = process_runtime_cleanup_intent(intent.pk)

    intent.refresh_from_db()
    assert result["result"] is True
    assert intent.status == TimeSeriesRuntimeCleanupIntent.Status.COMPLETED
    assert intent.completed_at is not None
    assert intent.next_retry_at is None
    assert intent.last_error == ""


def test_cleanup_rejects_noncanonical_container_id():
    from apps.mlops.services.timeseries_runtime_cleanup import (
        reconcile_orphan_timeseries_runtime,
    )

    with pytest.raises(ValueError, match="does not belong"):
        reconcile_orphan_timeseries_runtime(
            "TimeseriesPredict_Serving_9006",
            9005,
        )


@pytest.mark.django_db(transaction=True)
def test_cleanup_waits_for_uncommitted_create_owner(monkeypatch):
    import threading

    from django.db import close_old_connections, connection, transaction

    from apps.mlops.services.timeseries_runtime_cleanup import (
        lock_timeseries_runtime_id,
        reconcile_orphan_timeseries_runtime,
    )

    if connection.vendor == "sqlite":
        pytest.skip("SQLite does not provide the production row-lock semantics")

    train_job = create_train_job(TimeSeriesPredictTrainJob, team=1)
    owner_locked = threading.Event()
    allow_owner_commit = threading.Event()
    cleanup_finished = threading.Event()
    thread_errors = []
    cleanup_results = []
    removed_ids = []

    monkeypatch.setattr(
        "apps.mlops.services.timeseries_runtime_cleanup.WebhookClient.remove",
        lambda container_id: removed_ids.append(container_id),
    )

    def create_owner():
        close_old_connections()
        try:
            with transaction.atomic():
                TimeSeriesPredictServing.objects.create(
                    id=9007,
                    name="concurrent-owner",
                    description="",
                    team=[1],
                    train_job_id=train_job.id,
                    model_version="latest",
                    status="inactive",
                    container_info={},
                )
                lock_timeseries_runtime_id(9007)
                owner_locked.set()
                if not allow_owner_commit.wait(timeout=5):
                    raise TimeoutError("test did not release create transaction")
        except Exception as error:
            thread_errors.append(error)
        finally:
            close_old_connections()

    def cleanup_orphan():
        close_old_connections()
        try:
            cleanup_results.append(
                reconcile_orphan_timeseries_runtime(
                    "TimeseriesPredict_Serving_9007",
                    9007,
                )
            )
        except Exception as error:
            thread_errors.append(error)
        finally:
            cleanup_finished.set()
            close_old_connections()

    owner_thread = threading.Thread(target=create_owner)
    cleanup_thread = threading.Thread(target=cleanup_orphan)
    owner_thread.start()
    assert owner_locked.wait(timeout=5)
    cleanup_thread.start()

    # cleanup 必须阻塞在同一 guard，不能越过未提交 owner 执行 remove。
    assert not cleanup_finished.wait(timeout=0.2)
    allow_owner_commit.set()
    owner_thread.join(timeout=5)
    cleanup_thread.join(timeout=5)

    assert thread_errors == []
    assert cleanup_results[0]["reason"] == "serving id is owned by a database record"
    assert removed_ids == []


def test_destroy_acquires_shared_row_lock_before_runtime_cleanup(
    mlops_api_client,
    mlops_user,
    monkeypatch,
):
    mlops_user.permission["mlops"].add("timeseries_predict-Delete")
    serving = _create_serving(port=3000)
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.TimeSeriesPredictServingViewSet.get_has_permission",
        lambda *args, **kwargs: True,
    )
    runtime_events = []
    original_select_for_update = TimeSeriesPredictServing.objects.select_for_update

    def tracked_select_for_update(*args, **kwargs):
        runtime_events.append("lock")
        return original_select_for_update(*args, **kwargs)

    monkeypatch.setattr(TimeSeriesPredictServing.objects, "select_for_update", tracked_select_for_update)
    monkeypatch.setattr(
        "apps.mlops.views.base.WebhookClient.remove",
        lambda serving_id: runtime_events.append("cleanup") or {"status": "success"},
    )

    response = mlops_api_client.delete(
        f"/api/v1/mlops/timeseries_predict_servings/{serving.id}/",
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert runtime_events == ["lock", "cleanup"]
    assert not TimeSeriesPredictServing.objects.filter(pk=serving.pk).exists()


def test_destroy_permission_denial_has_no_runtime_side_effect(
    mlops_api_client,
    mlops_user,
    monkeypatch,
):
    mlops_user.permission["mlops"].add("timeseries_predict-Delete")
    serving = _create_serving(port=3000)
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.TimeSeriesPredictServingViewSet.get_has_permission",
        lambda *args, **kwargs: False,
    )
    remove_calls = []
    monkeypatch.setattr(
        "apps.mlops.views.base.WebhookClient.remove",
        lambda serving_id: remove_calls.append(serving_id),
    )

    response = mlops_api_client.delete(
        f"/api/v1/mlops/timeseries_predict_servings/{serving.id}/",
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["result"] is False
    assert remove_calls == []
    assert TimeSeriesPredictServing.objects.filter(pk=serving.pk).exists()


def test_destroy_timeout_reconciles_and_advances_generation(
    mlops_api_client,
    mlops_user,
    monkeypatch,
):
    from apps.mlops.utils.webhook_client import WebhookTimeoutError

    mlops_user.permission["mlops"].add("timeseries_predict-Delete")
    serving = _create_serving(port=3000)
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.TimeSeriesPredictServingViewSet.get_has_permission",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        "apps.mlops.views.base.WebhookClient.remove",
        lambda serving_id: (_ for _ in ()).throw(WebhookTimeoutError("response lost")),
    )
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.WebhookClient.get_status",
        lambda ids: [{"id": ids[0], "status": "success", "state": "not_found"}],
    )

    response = mlops_api_client.delete(
        f"/api/v1/mlops/timeseries_predict_servings/{serving.id}/",
        format="json",
    )

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    serving.refresh_from_db()
    assert serving.container_info["state"] == "not_found"
    assert serving.container_info["_runtime_generation"] == 2


@pytest.mark.parametrize("endpoint", ["list", "retrieve"])
def test_runtime_status_sync_does_not_overwrite_concurrent_transition(
    mlops_api_client,
    mlops_user,
    monkeypatch,
    endpoint,
):
    mlops_user.permission["mlops"].add("timeseries_predict-View")
    serving = _create_serving(port=3000)
    transitioned_info = {"status": "success", "state": "running", "port": 31001}
    stale_runtime_info = {
        "id": f"TimeseriesPredict_Serving_{serving.id}",
        "status": "success",
        "state": "not_found",
    }
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.TimeSeriesPredictServingViewSet.get_has_permission",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        "apps.core.utils.viewset_utils.get_permission_rules",
        lambda *args, **kwargs: {"team": [1], "instance": []},
    )

    def query_stale_status(_serving_ids):
        TimeSeriesPredictServing.objects.filter(pk=serving.pk).update(container_info=transitioned_info)
        return [stale_runtime_info]

    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.WebhookClient.get_status",
        query_stale_status,
    )
    url = (
        "/api/v1/mlops/timeseries_predict_servings/"
        if endpoint == "list"
        else f"/api/v1/mlops/timeseries_predict_servings/{serving.id}/"
    )

    response = mlops_api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    if endpoint == "list":
        response_items = response.data.get("items", []) if isinstance(response.data, dict) else response.data
    else:
        response_items = [response.data]
    response_serving = next(item for item in response_items if item["id"] == serving.id)
    assert response_serving["container_info"] == transitioned_info
    serving.refresh_from_db()
    assert serving.container_info == transitioned_info


@pytest.mark.parametrize("endpoint", ["list", "retrieve"])
def test_runtime_status_sync_generation_blocks_aba_transition(
    mlops_api_client,
    mlops_user,
    monkeypatch,
    endpoint,
):
    mlops_user.permission["mlops"].add("timeseries_predict-View")
    serving = _create_serving(port=3000)
    initial_info = {**CONTAINER_INFO, "_runtime_generation": 4}
    transitioned_info = {**CONTAINER_INFO, "_runtime_generation": 5}
    TimeSeriesPredictServing.objects.filter(pk=serving.pk).update(container_info=initial_info)
    stale_runtime_info = {
        "id": f"TimeseriesPredict_Serving_{serving.id}",
        "status": "success",
        "state": "not_found",
    }
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.TimeSeriesPredictServingViewSet.get_has_permission",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        "apps.core.utils.viewset_utils.get_permission_rules",
        lambda *args, **kwargs: {"team": [1], "instance": []},
    )

    def query_stale_status(_serving_ids):
        # 新 runtime 的公开状态与旧 runtime 相同，只有单调 generation 能识别 ABA。
        TimeSeriesPredictServing.objects.filter(pk=serving.pk).update(container_info=transitioned_info)
        return [stale_runtime_info]

    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.WebhookClient.get_status",
        query_stale_status,
    )
    url = (
        "/api/v1/mlops/timeseries_predict_servings/"
        if endpoint == "list"
        else f"/api/v1/mlops/timeseries_predict_servings/{serving.id}/"
    )

    response = mlops_api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    if endpoint == "list":
        response_items = response.data.get("items", []) if isinstance(response.data, dict) else response.data
    else:
        response_items = [response.data]
    response_serving = next(item for item in response_items if item["id"] == serving.id)
    assert response_serving["container_info"] == transitioned_info
    serving.refresh_from_db()
    assert serving.container_info == transitioned_info


@pytest.mark.parametrize("endpoint", ["list", "retrieve"])
def test_runtime_status_sync_tolerates_concurrent_delete(
    mlops_api_client,
    mlops_user,
    monkeypatch,
    endpoint,
):
    mlops_user.permission["mlops"].add("timeseries_predict-View")
    serving = _create_serving(port=3000)
    runtime_info = {
        "id": f"TimeseriesPredict_Serving_{serving.id}",
        "status": "success",
        "state": "not_found",
    }
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.TimeSeriesPredictServingViewSet.get_has_permission",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        "apps.core.utils.viewset_utils.get_permission_rules",
        lambda *args, **kwargs: {"team": [1], "instance": []},
    )

    def query_after_delete(_serving_ids):
        TimeSeriesPredictServing.objects.filter(pk=serving.pk).delete()
        return [runtime_info]

    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.WebhookClient.get_status",
        query_after_delete,
    )
    url = (
        "/api/v1/mlops/timeseries_predict_servings/"
        if endpoint == "list"
        else f"/api/v1/mlops/timeseries_predict_servings/{serving.id}/"
    )

    response = mlops_api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert not TimeSeriesPredictServing.objects.filter(pk=serving.pk).exists()


def test_runtime_status_batch_sync_uses_three_queries(django_assert_num_queries):
    from apps.mlops.views.timeseries_predict import TimeSeriesPredictServingViewSet

    first = _create_serving(port=3000)
    second = _create_serving(port=3001)
    observed_statuses = [
        (first.id, first.container_info),
        (second.id, second.container_info),
    ]
    runtime_info_by_id = {
        first.id: {"id": f"TimeseriesPredict_Serving_{first.id}", "status": "success", "state": "running"},
        second.id: {"id": f"TimeseriesPredict_Serving_{second.id}", "status": "success", "state": "running"},
    }

    with django_assert_num_queries(3):
        claims_by_id = TimeSeriesPredictServingViewSet._reserve_runtime_status_sync(observed_statuses)
        current_info = TimeSeriesPredictServingViewSet._finalize_runtime_status_sync(
            claims_by_id,
            runtime_info_by_id,
        )

    assert set(current_info) == {first.id, second.id}
    assert current_info[first.id]["_runtime_generation"] == 1
    assert current_info[second.id]["_runtime_generation"] == 1


def test_later_runtime_status_claim_prevents_older_result_overwrite():
    from apps.mlops.views.timeseries_predict import TimeSeriesPredictServingViewSet

    serving = _create_serving(port=3000)
    first_claim = TimeSeriesPredictServingViewSet._reserve_runtime_status_sync(
        [(serving.id, serving.container_info)]
    )
    second_claim = TimeSeriesPredictServingViewSet._reserve_runtime_status_sync(
        [(serving.id, first_claim[serving.id])]
    )

    TimeSeriesPredictServingViewSet._finalize_runtime_status_sync(
        first_claim,
        {serving.id: {"status": "success", "state": "pending"}},
    )
    current_info = TimeSeriesPredictServingViewSet._finalize_runtime_status_sync(
        second_claim,
        {serving.id: {"status": "success", "state": "running"}},
    )

    assert current_info[serving.id]["state"] == "running"
    assert current_info[serving.id]["_runtime_generation"] == 2


def test_uncertain_runtime_transition_invalidates_inflight_status_claim():
    from apps.mlops.views.timeseries_predict import TimeSeriesPredictServingViewSet

    serving = _create_serving(port=3000)
    stale_claim = TimeSeriesPredictServingViewSet._reserve_runtime_status_sync(
        [(serving.id, serving.container_info)]
    )
    serving.refresh_from_db()
    TimeSeriesPredictServingViewSet._claim_runtime_transition(serving, "stop")
    TimeSeriesPredictServingViewSet._assign_runtime_container_info(
        serving,
        {"status": "success", "state": "not_found"},
    )
    serving.save(update_fields=["container_info"])

    current_info = TimeSeriesPredictServingViewSet._finalize_runtime_status_sync(
        stale_claim,
        {serving.id: {"status": "success", "state": "running"}},
    )

    assert current_info[serving.id]["state"] == "not_found"
    assert current_info[serving.id]["_runtime_generation"] == 3


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


def test_update_remove_timeout_rejects_foreign_not_found_status(
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
    _mock_create_runtime_dependencies(monkeypatch)
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.WebhookClient.remove",
        lambda serving_id: (_ for _ in ()).throw(WebhookTimeoutError("response lost")),
    )
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.WebhookClient.get_status",
        lambda ids: [
            {
                "id": "TimeseriesPredict_Serving_foreign",
                "status": "success",
                "state": "not_found",
            }
        ],
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


def test_update_cannot_override_runtime_generation(
    mlops_api_client,
    mlops_user,
    monkeypatch,
):
    mlops_user.permission["mlops"].add("timeseries_predict-Edit")
    serving = _create_serving(port=3000)
    owned_runtime_info = {**CONTAINER_INFO, "_runtime_generation": 7}
    TimeSeriesPredictServing.objects.filter(pk=serving.pk).update(container_info=owned_runtime_info)
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.TimeSeriesPredictServingViewSet.get_has_permission",
        lambda *args, **kwargs: True,
    )

    response = mlops_api_client.patch(
        f"/api/v1/mlops/timeseries_predict_servings/{serving.id}/",
        {
            "description": "allowed update",
            "container_info": {"state": "not_found", "_runtime_generation": 1},
        },
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    serving.refresh_from_db()
    assert serving.description == "allowed update"
    assert serving.container_info == owned_runtime_info


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
