"""六套算法视图剩余错误分支：run 指标/删除 500、serving remove 超时/连接失败。"""
import types
from unittest.mock import Mock

import pydantic.root_model  # noqa
import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory

from apps.base.tests.factories import UserFactory
from apps.mlops.constants import TrainJobStatus
from apps.mlops.tests.test_views_actions_param import (
    ALGO_IDS,
    ALGOS,
    _call,
    _make_serving,
    _make_train_job,
    _model,
    _patch_mlflow,
    _runs_frame,
    _view_module,
)
from apps.mlops.utils.webhook_client import WebhookConnectionError, WebhookError, WebhookTimeoutError

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

factory = APIRequestFactory()


@pytest.fixture
def superuser():
    return UserFactory(username="mlops-err-su", domain="domain.com", roles=[], is_superuser=True)


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_metrics_list_generic_exception_returns_500(monkeypatch, superuser, suffix, prefix, model_module, basename):
    tj = _make_train_job(model_module, basename)
    mod = _view_module(suffix)
    _patch_mlflow(
        monkeypatch,
        suffix,
        get_experiment_by_name=lambda name: types.SimpleNamespace(experiment_id="1"),
        get_experiment_runs=lambda eid, **kw: _runs_frame([{"run_id": "run-1"}]),
        get_run_metrics=Mock(side_effect=RuntimeError("mlflow down")),
    )
    vs = getattr(mod, f"{basename}TrainJobViewSet")
    view = vs.as_view({"get": "get_runs_metrics_list"})
    request = factory.get(f"/{suffix}_train_jobs/x/runs/run-1/metrics_list/")
    resp = _call(view, request, superuser, pk=tj.id, run_id="run-1")
    assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert resp.data["error"] == "Failed to get metric list: mlflow down"


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_delete_run_generic_exception_returns_500(monkeypatch, superuser, suffix, prefix, model_module, basename):
    tj = _make_train_job(model_module, basename, status_value=TrainJobStatus.COMPLETED)
    mod = _view_module(suffix)
    _patch_mlflow(
        monkeypatch,
        suffix,
        get_experiment_by_name=lambda name: types.SimpleNamespace(experiment_id="1"),
        get_experiment_runs=lambda eid, **kw: _runs_frame([{"run_id": "run-1", "status": "FINISHED"}]),
        delete_run=Mock(side_effect=RuntimeError("cannot delete")),
    )
    vs = getattr(mod, f"{basename}TrainJobViewSet")
    view = vs.as_view({"delete": "delete_run"})
    request = factory.delete(f"/{suffix}_train_jobs/x/runs/run-1/")
    resp = _call(view, request, superuser, pk=tj.id, run_id="run-1")
    assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert resp.data["message"] == "Failed to delete training run: cannot delete"


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_serving_remove_timeout_and_connection_errors(monkeypatch, superuser, suffix, prefix, model_module, basename):
    serving = _make_serving(model_module, basename, container_info={"state": "running"})
    mod = _view_module(suffix)
    vs = getattr(mod, f"{basename}ServingViewSet")
    if not hasattr(vs, "remove"):
        pytest.skip(f"{suffix} serving has no remove action")
    view = vs.as_view({"post": "remove"})

    monkeypatch.setattr(mod.WebhookClient, "remove", staticmethod(Mock(side_effect=WebhookTimeoutError("timed out"))))
    resp = _call(view, factory.post(f"/{suffix}_servings/x/remove/"), superuser, pk=serving.id)
    assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert resp.data["error"] == "Request to the webhookd service timed out. Please check whether the service is running"

    monkeypatch.setattr(
        mod.WebhookClient,
        "remove",
        staticmethod(Mock(side_effect=WebhookConnectionError("conn refused"))),
    )
    resp = _call(view, factory.post(f"/{suffix}_servings/x/remove/"), superuser, pk=serving.id)
    assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert resp.data["error"] == "Unable to connect to the webhookd service"

    monkeypatch.setattr(mod.WebhookClient, "remove", staticmethod(Mock(side_effect=WebhookError("other", code="X"))))
    resp = _call(view, factory.post(f"/{suffix}_servings/x/remove/"), superuser, pk=serving.id)
    assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert resp.data["error"] == "Request to the webhookd service failed"


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_runs_data_list_generic_exception_returns_500(monkeypatch, superuser, suffix, prefix, model_module, basename):
    tj = _make_train_job(model_module, basename)
    mod = _view_module(suffix)
    _patch_mlflow(
        monkeypatch,
        suffix,
        get_experiment_by_name=Mock(side_effect=RuntimeError("mlflow down")),
    )
    view = getattr(mod, f"{basename}TrainJobViewSet").as_view({"get": "get_run_data_list"})
    resp = _call(view, factory.get(f"/{suffix}_train_jobs/x/runs_data_list/"), superuser, pk=tj.id)
    assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert resp.data["error"] == "Failed to get training records: mlflow down"


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_run_params_generic_exception_returns_500(monkeypatch, superuser, suffix, prefix, model_module, basename):
    tj = _make_train_job(model_module, basename)
    mod = _view_module(suffix)
    _patch_mlflow(
        monkeypatch,
        suffix,
        get_experiment_by_name=lambda name: types.SimpleNamespace(experiment_id="1"),
        get_experiment_runs=lambda eid, **kw: _runs_frame([{"run_id": "run-1"}]),
        get_run_info=Mock(side_effect=RuntimeError("params down")),
    )
    view = getattr(mod, f"{basename}TrainJobViewSet").as_view({"get": "get_run_params"})
    resp = _call(view, factory.get(f"/{suffix}_train_jobs/x/runs/run-1/run_params/"), superuser, pk=tj.id, run_id="run-1")
    assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert resp.data["error"] == "Failed to get run parameters: params down"


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_model_versions_generic_exception_returns_500(monkeypatch, superuser, suffix, prefix, model_module, basename):
    tj = _make_train_job(model_module, basename)
    mod = _view_module(suffix)
    _patch_mlflow(monkeypatch, suffix, get_model_versions=Mock(side_effect=RuntimeError("registry down")))
    view = getattr(mod, f"{basename}TrainJobViewSet").as_view({"get": "get_model_versions"})
    resp = _call(view, factory.get(f"/{suffix}_train_jobs/x/model_versions/"), superuser, pk=tj.id)
    assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert resp.data["error"] == "Failed to get model versions: registry down"


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_download_model_generic_exception_returns_500(monkeypatch, superuser, suffix, prefix, model_module, basename):
    tj = _make_train_job(model_module, basename)
    mod = _view_module(suffix)
    _patch_mlflow(
        monkeypatch,
        suffix,
        get_experiment_by_name=lambda name: types.SimpleNamespace(experiment_id="1"),
        get_experiment_runs=lambda eid, **kw: _runs_frame([{"run_id": "run-1"}]),
        get_run_info=Mock(side_effect=RuntimeError("artifact down")),
        download_model_artifact=Mock(side_effect=RuntimeError("artifact down")),
    )
    view = getattr(mod, f"{basename}TrainJobViewSet").as_view({"get": "download_model"})
    resp = _call(view, factory.get(f"/{suffix}_train_jobs/x/runs/run-1/download_model/"), superuser, pk=tj.id, run_id="run-1")
    assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert resp.data["error"] == "Failed to download model: artifact down"


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_serving_retrieve_missing_status_and_webhook_error(monkeypatch, superuser, suffix, prefix, model_module, basename):
    if suffix in {"object_detection", "image_classification"}:
        pytest.skip(f"{suffix} serving retrieve does not sync container status")
    serving = _make_serving(model_module, basename, container_info={"state": "cached"})
    mod = _view_module(suffix)
    vs = getattr(mod, f"{basename}ServingViewSet")
    view = vs.as_view({"get": "retrieve"})

    monkeypatch.setattr(mod.WebhookClient, "get_status", staticmethod(lambda ids: []))
    missing = _call(view, factory.get(f"/{suffix}_servings/x/"), superuser, pk=serving.id)
    assert missing.status_code == status.HTTP_200_OK
    assert missing.data["container_info"]["state"] == "unknown"
    assert missing.data["container_info"]["message"] == "webhookd did not return container status"

    monkeypatch.setattr(
        mod.WebhookClient,
        "get_status",
        staticmethod(Mock(side_effect=WebhookError("status down"))),
    )
    degraded = _call(view, factory.get(f"/{suffix}_servings/x/"), superuser, pk=serving.id)
    assert degraded.status_code == status.HTTP_200_OK
    assert degraded.data["container_info"]["status"] == "error"
    assert degraded.data["container_info"]["_query_failed"] is True
    assert degraded.data["container_info"]["_error"] == "Request to the webhookd service failed"


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_serving_list_missing_container_marks_unknown(monkeypatch, superuser, suffix, prefix, model_module, basename):
    from apps.mlops.tests.test_views_actions_param import _allow_team_one

    _allow_team_one(monkeypatch)
    serving = _make_serving(model_module, basename, container_info={"state": "cached"})
    mod = _view_module(suffix)
    monkeypatch.setattr(mod.WebhookClient, "get_status", staticmethod(lambda ids: []))
    view = getattr(mod, f"{basename}ServingViewSet").as_view({"get": "list"})
    resp = _call(view, factory.get(f"/{suffix}_servings/"), superuser)
    assert resp.status_code == status.HTTP_200_OK
    items = resp.data["items"] if isinstance(resp.data, dict) and "items" in resp.data else resp.data
    target = next(s for s in items if s["id"] == serving.id)
    assert target["container_info"]["state"] == "unknown"
    assert target["container_info"]["message"] == "webhookd did not return status for this container"


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_train_data_and_release_crud(superuser, suffix, prefix, model_module, basename):
    from apps.mlops.constants import DatasetReleaseStatus

    Dataset = _model(model_module, basename, "Dataset")
    Release = _model(model_module, basename, "DatasetRelease")
    ds = Dataset.objects.create(name=f"ds-{suffix}", description="", team=[1])
    rel = Release.objects.create(
        name="r",
        description="",
        dataset=ds,
        version="v1",
        dataset_file="",
        status=DatasetReleaseStatus.PUBLISHED,
        metadata={},
        file_size=0,
    )
    mod = _view_module(suffix)
    rel_vs = getattr(mod, f"{basename}DatasetReleaseViewSet")

    rel_list = _call(rel_vs.as_view({"get": "list"}), factory.get("/"), superuser)
    assert rel_list.status_code == status.HTTP_200_OK
    rel_get = _call(rel_vs.as_view({"get": "retrieve"}), factory.get("/x/"), superuser, pk=rel.id)
    assert rel_get.status_code == status.HTTP_200_OK
    assert rel_get.data["version"] == "v1"

    missing = _call(rel_vs.as_view({"get": "download"}), factory.get("/x/download/"), superuser, pk=rel.id)
    assert missing.status_code == status.HTTP_404_NOT_FOUND
    assert missing.data == {"error": "Dataset file was not found"}
