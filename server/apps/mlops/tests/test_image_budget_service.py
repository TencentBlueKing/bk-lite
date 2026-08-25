import json
import time
from unittest.mock import Mock

import pytest
from rest_framework import status

from apps.base.tests.factories import UserFactory
from apps.mlops.utils.webhook_client import (
    WebhookClient,
    WebhookError,
    WebhookTimeoutError,
)
from apps.mlops.tests.test_timeseries_timeout_service import _run_serve_script
from apps.mlops.tests.test_views_actions_param import (
    _allow_team_one,
    _call,
    _make_serving,
    _patch_mlflow,
    _view_module,
    factory,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

IMAGE_PAYLOAD = {
    "id": "ImageClassification_Serving_1",
    "mlflow_tracking_uri": "http://mlflow:15000",
    "mlflow_model_uri": "models:/image/1",
    "train_image": "classify-image:latest",
    "device": "cpu",
    "image_budget_mode": "observe",
    "max_image_bytes": 10 * 1024 * 1024,
    "max_image_batch_base64_bytes": 96 * 1024 * 1024,
    "max_image_batch_bytes": 64 * 1024 * 1024,
    "max_image_batch_pixels": 64 * 1024 * 1024,
}

IMAGE_SERVINGS = [
    ("image_classification", "image_classification", "ImageClassification"),
    ("object_detection", "object_detection", "ObjectDetection"),
]


@pytest.fixture
def superuser():
    return UserFactory(username="image-budget-su", domain="domain.com", roles=[], is_superuser=True)


def test_webhook_client_forwards_default_observe_image_budget(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        WebhookClient,
        "_request",
        staticmethod(lambda endpoint, payload, **kwargs: captured.update(payload) or {"status": "success"}),
    )

    WebhookClient.serve("ImageClassification_Serving_1", "http://mlflow:15000", "models:/image/1")

    assert captured["image_budget_mode"] == "observe"
    assert captured["max_image_bytes"] == 10 * 1024 * 1024
    assert captured["max_image_batch_pixels"] == 64 * 1024 * 1024


def test_webhook_client_forwards_enforced_image_budget(monkeypatch):
    captured = {}
    monkeypatch.setenv("MLOPS_PREDICT_IMAGE_BUDGET_MODE", "enforce")
    monkeypatch.setenv("MLOPS_PREDICT_MAX_IMAGE_BATCH_PIXELS", "12345")
    monkeypatch.setattr(
        WebhookClient,
        "_request",
        staticmethod(lambda endpoint, payload, **kwargs: captured.update(payload) or {"status": "success"}),
    )

    WebhookClient.serve("ObjectDetection_Serving_1", "http://mlflow:15000", "models:/object/1")

    assert captured["image_budget_mode"] == "enforce"
    assert captured["max_image_batch_pixels"] == 12345


def test_webhook_client_rejects_invalid_image_budget_before_request(monkeypatch):
    request = Mock()
    monkeypatch.setenv("MLOPS_PREDICT_IMAGE_BUDGET_MODE", "disabled")
    monkeypatch.setattr(WebhookClient, "_request", request)

    with pytest.raises(ValueError, match="must be observe or enforce"):
        WebhookClient.serve("ImageClassification_Serving_1", "http://mlflow:15000", "models:/image/1")

    request.assert_not_called()


@pytest.mark.parametrize("runtime", ["docker", "kubernetes"])
def test_serve_script_injects_image_budget_with_observe_rollback(tmp_path, runtime):
    result, captured = _run_serve_script(tmp_path, runtime, IMAGE_PAYLOAD)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "MLOPS_PREDICT_IMAGE_BUDGET_MODE" in captured
    assert "observe" in captured
    assert "MLOPS_PREDICT_MAX_IMAGE_BATCH_PIXELS" in captured
    assert str(64 * 1024 * 1024) in captured


@pytest.mark.parametrize("runtime", ["docker", "kubernetes"])
def test_serve_script_rejects_invalid_image_budget_before_mutation(tmp_path, runtime):
    result, captured = _run_serve_script(tmp_path, runtime, {**IMAGE_PAYLOAD, "image_budget_mode": "disabled"})

    assert result.returncode == 1
    assert json.loads(result.stdout)["code"] == "INVALID_IMAGE_BUDGET_MODE"
    assert captured == ""


def _prepare_update(monkeypatch, suffix, model_module, basename):
    _allow_team_one(monkeypatch)
    monkeypatch.setattr(
        "apps.core.utils.serializers.get_permission_rules",
        lambda *args, **kwargs: {"team": [1], "instance": []},
    )
    serving = _make_serving(
        model_module,
        basename,
        container_info={"status": "success", "state": "running", "port": "9000"},
        port=9000,
    )
    module = _view_module(suffix)
    _patch_mlflow(monkeypatch, suffix)
    monkeypatch.setattr(module, "get_mlflow_tracking_uri", lambda: "http://mlflow.local")
    monkeypatch.setattr(module, "get_image_by_prefix", lambda prefix, algorithm: "repo/serve:1")
    view = getattr(module, f"{basename}ServingViewSet").as_view({"put": "update"})
    request = factory.put(
        f"/{suffix}_servings/{serving.id}/",
        {
            "name": serving.name,
            "team": [1],
            "train_job": serving.train_job_id,
            "model_version": "2",
        },
        format="json",
    )
    return serving, module, view, request


@pytest.mark.parametrize("suffix,model_module,basename", IMAGE_SERVINGS)
def test_running_update_preflights_budget_before_database_or_container_mutation(
    monkeypatch, superuser, suffix, model_module, basename
):
    serving, module, view, request = _prepare_update(monkeypatch, suffix, model_module, basename)
    remove = Mock()
    monkeypatch.setenv("MLOPS_PREDICT_IMAGE_BUDGET_MODE", "disabled")
    monkeypatch.setattr(module.WebhookClient, "remove", staticmethod(remove))

    response = _call(view, request, superuser, pk=serving.id)

    serving.refresh_from_db()
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert serving.model_version == "latest"
    assert serving.container_info["state"] == "running"
    remove.assert_not_called()


@pytest.mark.parametrize("suffix,model_module,basename", IMAGE_SERVINGS)
def test_running_update_restores_old_service_when_new_start_fails(
    monkeypatch, superuser, suffix, model_module, basename
):
    serving, module, view, request = _prepare_update(monkeypatch, suffix, model_module, basename)
    remove = Mock()
    serve = Mock(
        side_effect=[
            WebhookError("new service failed"),
            {"status": "success", "state": "running", "port": "9000"},
        ]
    )
    monkeypatch.setattr(module.WebhookClient, "remove", staticmethod(remove))
    monkeypatch.setattr(module.WebhookClient, "serve", staticmethod(serve))

    response = _call(view, request, superuser, pk=serving.id)

    serving.refresh_from_db()
    assert response.status_code == status.HTTP_200_OK
    assert serving.model_version == "latest"
    assert serving.container_info["state"] == "running"
    assert "_image_update_token" not in serving.container_info
    assert remove.call_count == 2
    assert serve.call_count == 2
    assert serve.call_args_list[1].args[0].startswith(("ImageClassification_", "ObjectDetection_"))


@pytest.mark.parametrize("suffix,model_module,basename", IMAGE_SERVINGS)
def test_running_update_reconciles_remove_timeout_and_restores_deleted_service(
    monkeypatch, superuser, suffix, model_module, basename
):
    serving, module, view, request = _prepare_update(monkeypatch, suffix, model_module, basename)
    remove = Mock(side_effect=[WebhookTimeoutError("remove timed out"), None])
    get_status = Mock(
        return_value=[
            {
                "id": f"{basename}_Serving_{serving.id}",
                "status": "success",
                "state": "not_found",
            }
        ]
    )
    serve = Mock(return_value={"status": "success", "state": "running", "port": "9000"})
    monkeypatch.setattr(module.WebhookClient, "remove", staticmethod(remove))
    monkeypatch.setattr(module.WebhookClient, "get_status", staticmethod(get_status))
    monkeypatch.setattr(module.WebhookClient, "serve", staticmethod(serve))

    response = _call(view, request, superuser, pk=serving.id)

    serving.refresh_from_db()
    assert response.status_code == status.HTTP_200_OK
    assert serving.model_version == "latest"
    assert serving.container_info["state"] == "running"
    assert "_image_update_token" not in serving.container_info
    get_status.assert_called_once()
    assert remove.call_count == 2
    serve.assert_called_once()


@pytest.mark.parametrize("suffix,model_module,basename", IMAGE_SERVINGS)
def test_failed_update_does_not_overwrite_a_newer_database_update(
    monkeypatch, superuser, suffix, model_module, basename
):
    serving, module, view, request = _prepare_update(monkeypatch, suffix, model_module, basename)
    remove = Mock()
    Serving = type(serving)

    def fail_after_newer_update(*args, **kwargs):
        Serving.objects.filter(pk=serving.pk).update(
            model_version="3",
            container_info={"status": "success", "state": "running", "port": "9001"},
        )
        raise WebhookError("new service failed")

    monkeypatch.setattr(module.WebhookClient, "remove", staticmethod(remove))
    monkeypatch.setattr(module.WebhookClient, "serve", staticmethod(fail_after_newer_update))

    response = _call(view, request, superuser, pk=serving.id)

    serving.refresh_from_db()
    assert response.status_code == status.HTTP_200_OK
    assert serving.model_version == "3"
    assert serving.container_info["port"] == "9001"
    remove.assert_called_once()


@pytest.mark.parametrize("suffix,model_module,basename", IMAGE_SERVINGS)
def test_transition_token_rejects_concurrent_update_before_remote_mutation(
    monkeypatch, superuser, suffix, model_module, basename
):
    serving, module, view, request = _prepare_update(monkeypatch, suffix, model_module, basename)
    remove = Mock()
    concurrent_responses = []

    def serve_after_concurrent_attempt(*args, **kwargs):
        serving.refresh_from_db()
        assert serving.container_info.get("_image_update_token")
        assert serving.container_info.get("_image_update_started_at", 0) > 0
        concurrent_request = factory.put(
            f"/{suffix}_servings/{serving.id}/",
            {
                "name": serving.name,
                "team": [1],
                "train_job": serving.train_job_id,
                "model_version": "3",
            },
            format="json",
        )
        concurrent_responses.append(
            _call(view, concurrent_request, superuser, pk=serving.id)
        )
        return {"status": "success", "state": "running", "port": "9000"}

    monkeypatch.setattr(module.WebhookClient, "remove", staticmethod(remove))
    monkeypatch.setattr(
        module.WebhookClient, "serve", staticmethod(serve_after_concurrent_attempt)
    )

    response = _call(view, request, superuser, pk=serving.id)

    serving.refresh_from_db()
    assert response.status_code == status.HTTP_200_OK
    assert concurrent_responses[0].status_code == status.HTTP_409_CONFLICT
    assert serving.model_version == "2"
    assert serving.container_info["state"] == "running"
    assert "_image_update_token" not in serving.container_info
    remove.assert_called_once()


@pytest.mark.parametrize("suffix,model_module,basename", IMAGE_SERVINGS)
def test_expired_transition_is_reconciled_and_restarted_with_a_new_owner(
    monkeypatch, superuser, suffix, model_module, basename
):
    serving, module, view, request = _prepare_update(monkeypatch, suffix, model_module, basename)
    serving.container_info.update(
        {"_image_update_token": "expired-owner", "_image_update_started_at": 0}
    )
    serving.save(update_fields=["container_info"])
    get_status = Mock(
        return_value=[
            {
                "id": f"{basename}_Serving_{serving.id}",
                "status": "success",
                "state": "running",
                "port": "9000",
            }
        ]
    )
    remove = Mock()
    serve = Mock(return_value={"status": "success", "state": "running", "port": "9000"})
    monkeypatch.setattr(module.WebhookClient, "get_status", staticmethod(get_status))
    monkeypatch.setattr(module.WebhookClient, "remove", staticmethod(remove))
    monkeypatch.setattr(module.WebhookClient, "serve", staticmethod(serve))

    response = _call(view, request, superuser, pk=serving.id)

    serving.refresh_from_db()
    assert response.status_code == status.HTTP_200_OK
    assert serving.model_version == "2"
    assert serving.container_info["state"] == "running"
    assert "_image_update_token" not in serving.container_info
    get_status.assert_called_once()
    remove.assert_called_once()
    serve.assert_called_once()


@pytest.mark.parametrize("suffix,model_module,basename", IMAGE_SERVINGS)
def test_expired_transition_recovery_does_not_clear_a_changed_owner(
    monkeypatch, superuser, suffix, model_module, basename
):
    serving, module, view, request = _prepare_update(monkeypatch, suffix, model_module, basename)
    serving.container_info.update(
        {"_image_update_token": "expired-owner", "_image_update_started_at": 0}
    )
    serving.save(update_fields=["container_info"])
    Serving = type(serving)
    remove = Mock()
    serve = Mock()

    def status_after_owner_change(ids):
        info = dict(Serving.objects.get(pk=serving.pk).container_info)
        info["_image_update_token"] = "new-owner"
        info["_image_update_started_at"] = time.time()
        Serving.objects.filter(pk=serving.pk).update(container_info=info)
        return [{"id": ids[0], "status": "success", "state": "running", "port": "9000"}]

    monkeypatch.setattr(module.WebhookClient, "get_status", staticmethod(status_after_owner_change))
    monkeypatch.setattr(module.WebhookClient, "remove", staticmethod(remove))
    monkeypatch.setattr(module.WebhookClient, "serve", staticmethod(serve))

    response = _call(view, request, superuser, pk=serving.id)

    serving.refresh_from_db()
    assert response.status_code == status.HTTP_409_CONFLICT
    assert serving.model_version == "latest"
    assert serving.container_info["_image_update_token"] == "new-owner"
    remove.assert_not_called()
    serve.assert_not_called()


@pytest.mark.parametrize("suffix,model_module,basename", IMAGE_SERVINGS)
def test_serializer_failure_after_claim_clears_transition_token(
    monkeypatch, superuser, suffix, model_module, basename
):
    serving, module, view, _request = _prepare_update(
        monkeypatch, suffix, model_module, basename
    )
    remove = Mock()
    serve = Mock()
    monkeypatch.setattr(module.WebhookClient, "remove", staticmethod(remove))
    monkeypatch.setattr(module.WebhookClient, "serve", staticmethod(serve))
    invalid_request = factory.put(
        f"/{suffix}_servings/{serving.id}/",
        {
            "name": "",
            "team": [1],
            "train_job": serving.train_job_id,
            "model_version": "2",
        },
        format="json",
    )

    response = _call(view, invalid_request, superuser, pk=serving.id)

    serving.refresh_from_db()
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert serving.model_version == "latest"
    assert "_image_update_token" not in serving.container_info
    remove.assert_not_called()
    serve.assert_not_called()
