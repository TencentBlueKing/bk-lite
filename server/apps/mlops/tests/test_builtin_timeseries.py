import logging

import pytest
from django.core.management.base import CommandError
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.base.tests.factories import UserFactory
from apps.mlops import nats_api
from apps.mlops.models.timeseries_predict import TimeSeriesPredictServing, TimeSeriesPredictTrainJob
from apps.mlops.serializers.timeseries_predict import (
    TimeSeriesPredictServingSerializer,
    TimeSeriesPredictTrainJobSerializer,
)
from apps.mlops.services.builtin_timeseries import (
    PRESET_BASE_URL_ENV,
    ensure_builtin_timeseries_records,
)
from apps.mlops.views.timeseries_predict import (
    TimeSeriesPredictServingViewSet,
    TimeSeriesPredictTrainJobViewSet,
    execute_timeseries_predict,
)
from apps.system_mgmt.models import Group

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

factory = APIRequestFactory()
PRESET_URL = "http://mlops-preset:3000"


def _superuser():
    user = UserFactory(username="builtin-su", domain="domain.com", roles=[], is_superuser=True)
    user.locale = "en"
    return user


def _call(view, request, user, **kwargs):
    force_authenticate(request, user=user)
    request.COOKIES["current_team"] = "1"
    return view(request, **kwargs)


def _builtin_pair(team_id=1):
    train_job = TimeSeriesPredictTrainJob.objects.create(
        name="GradientBoosting",
        description="",
        team=[team_id],
        algorithm="GradientBoosting",
        is_builtin=True,
        dataset_version=None,
        hyperopt_config={},
    )
    serving = TimeSeriesPredictServing.objects.create(
        name="GradientBoosting",
        description="",
        team=[team_id],
        train_job=train_job,
        is_builtin=True,
        model_version="latest",
        container_info={},
    )
    return train_job, serving


def _allow_team(monkeypatch):
    monkeypatch.setattr(
        "apps.core.utils.viewset_utils.get_permission_rules",
        lambda *args, **kwargs: {"team": [1], "instance": []},
    )


def _patch_team_contains(monkeypatch):
    original = TimeSeriesPredictServing.objects.filter

    def _filter(**kwargs):
        team_id = kwargs.pop("team__contains", None)
        queryset = original(**kwargs)
        if team_id is None:
            return queryset
        matched = [row.id for row in queryset if team_id in (row.team or [])]
        return original(id__in=matched)

    monkeypatch.setattr(TimeSeriesPredictServing.objects, "filter", _filter)


def test_init_skips_when_preset_address_is_absent(monkeypatch, caplog):
    monkeypatch.delenv(PRESET_BASE_URL_ENV, raising=False)
    with caplog.at_level(logging.INFO, logger="mlops"):
        result = ensure_builtin_timeseries_records()
    assert result["skipped"] is True
    assert TimeSeriesPredictTrainJob.objects.filter(is_builtin=True).count() == 0
    assert "event=builtin_timeseries_init_skipped reason=preset_base_url_absent" in caplog.text


def test_init_writes_default_org_pair_once_without_minio(monkeypatch, caplog):
    monkeypatch.setenv(PRESET_BASE_URL_ENV, f"{PRESET_URL}/")
    group = Group.objects.get(name="Default", parent_id=0)

    def fail_sync(self):
        raise AssertionError("empty hyperopt_config must not upload")

    monkeypatch.setattr(TimeSeriesPredictTrainJob, "_sync_config_to_minio", fail_sync)
    with caplog.at_level(logging.INFO, logger="mlops"):
        first = ensure_builtin_timeseries_records()
        second = ensure_builtin_timeseries_records()

    assert first == {"created_train_jobs": 1, "created_servings": 1, "skipped": False}
    assert second["created_train_jobs"] == 0
    assert second["created_servings"] == 0
    train_job = TimeSeriesPredictTrainJob.objects.get(is_builtin=True)
    serving = train_job.servings.get()
    assert train_job.name == "GradientBoosting"
    assert train_job.algorithm == "GradientBoosting"
    assert train_job.dataset_version_id is None
    assert train_job.hyperopt_config == {}
    assert train_job.team == [group.id]
    assert serving.name == "GradientBoosting"
    assert serving.is_builtin is True
    assert serving.container_info == {}
    assert serving.team == [group.id]
    assert "event=builtin_timeseries_init_finished created_train_jobs=1 created_servings=1" in caplog.text
    assert PRESET_URL not in caplog.text


def test_init_fails_when_default_group_is_missing(monkeypatch, caplog):
    Group.objects.filter(name="Default", parent_id=0).delete()
    monkeypatch.setenv(PRESET_BASE_URL_ENV, PRESET_URL)
    with caplog.at_level(logging.ERROR, logger="mlops"):
        with pytest.raises(CommandError):
            ensure_builtin_timeseries_records()
    assert "failed_stage=resolve_default_group" in caplog.text
    assert "error_type=MissingDefaultGroup" in caplog.text
    assert PRESET_URL not in caplog.text


def test_serializers_do_not_accept_builtin_flag():
    train_job, serving = _builtin_pair()
    request = factory.patch("/")
    request.user = _superuser()
    train_serializer = TimeSeriesPredictTrainJobSerializer(
        train_job,
        data={"is_builtin": False},
        partial=True,
        context={"request": request},
    )
    serving_serializer = TimeSeriesPredictServingSerializer(
        serving,
        data={"is_builtin": False},
        partial=True,
        context={"request": request},
    )
    assert train_serializer.is_valid(), train_serializer.errors
    assert serving_serializer.is_valid(), serving_serializer.errors
    train_serializer.save()
    serving_serializer.save()
    train_job.refresh_from_db()
    serving.refresh_from_db()
    assert train_job.is_builtin is True
    assert serving.is_builtin is True


def test_lists_hide_builtin_records_until_preset_address_exists(monkeypatch):
    user = _superuser()
    _allow_team(monkeypatch)
    _builtin_pair()
    TimeSeriesPredictServing.objects.create(
        name="trained",
        description="",
        team=[1],
        train_job=TimeSeriesPredictTrainJob.objects.create(
            name="trained-job",
            description="",
            team=[1],
            algorithm="Prophet",
            hyperopt_config={},
        ),
        model_version="latest",
        container_info={"port": 3000, "status": "success", "state": "running"},
    )
    monkeypatch.delenv(PRESET_BASE_URL_ENV, raising=False)
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.WebhookClient.get_status",
        staticmethod(lambda ids: []),
    )
    hidden = _call(
        TimeSeriesPredictServingViewSet.as_view({"get": "list"}),
        factory.get("/servings/", {"page_size": "50"}),
        user,
    )
    assert hidden.status_code == 200
    assert {item["name"] for item in hidden.data["items"]} == {"trained"}

    monkeypatch.setenv(PRESET_BASE_URL_ENV, PRESET_URL)
    visible = _call(
        TimeSeriesPredictServingViewSet.as_view({"get": "list"}),
        factory.get("/servings/", {"page_size": "50"}),
        user,
    )
    assert {item["name"] for item in visible.data["items"]} == {"trained", "GradientBoosting"}
    builtin = next(item for item in visible.data["items"] if item["name"] == "GradientBoosting")
    assert builtin["is_builtin"] is True


def test_status_refresh_skips_builtin_serving(monkeypatch):
    user = _superuser()
    _allow_team(monkeypatch)
    _builtin_pair()
    monkeypatch.setenv(PRESET_BASE_URL_ENV, PRESET_URL)
    called = []
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.WebhookClient.get_status",
        staticmethod(lambda ids: called.append(ids) or []),
    )
    response = _call(
        TimeSeriesPredictServingViewSet.as_view({"get": "list"}),
        factory.get("/servings/", {"page_size": "50"}),
        user,
    )
    assert response.status_code == 200
    assert called == []
    item = response.data["items"][0]
    assert item["container_info"] == {}


def test_builtin_mutations_are_rejected(monkeypatch):
    user = _superuser()
    train_job, serving = _builtin_pair()
    monkeypatch.setenv(PRESET_BASE_URL_ENV, PRESET_URL)
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.WebhookClient.serve",
        staticmethod(lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("serve"))),
    )
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.WebhookClient.stop",
        staticmethod(lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("stop"))),
    )
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.WebhookClient.train",
        staticmethod(lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("train"))),
    )

    cases = [
        (TimeSeriesPredictServingViewSet, "post", "start", f"/servings/{serving.id}/start/", serving.id),
        (TimeSeriesPredictServingViewSet, "post", "stop", f"/servings/{serving.id}/stop/", serving.id),
        (TimeSeriesPredictServingViewSet, "patch", "partial_update", f"/servings/{serving.id}/", serving.id),
        (TimeSeriesPredictServingViewSet, "delete", "destroy", f"/servings/{serving.id}/", serving.id),
        (TimeSeriesPredictTrainJobViewSet, "post", "train", f"/jobs/{train_job.id}/train/", train_job.id),
        (TimeSeriesPredictTrainJobViewSet, "post", "stop", f"/jobs/{train_job.id}/stop/", train_job.id),
        (TimeSeriesPredictTrainJobViewSet, "patch", "partial_update", f"/jobs/{train_job.id}/", train_job.id),
        (TimeSeriesPredictTrainJobViewSet, "delete", "destroy", f"/jobs/{train_job.id}/", train_job.id),
    ]
    for viewset, method, action, path, pk in cases:
        request = getattr(factory, method)(path, {"name": "changed"}, format="json")
        response = _call(viewset.as_view({method: action}), request, user, pk=pk)
        assert response.status_code == status.HTTP_400_BAD_REQUEST, action
        assert response.data["error"] == "This operation is not available for a built-in record"
    train_job.refresh_from_db()
    serving.refresh_from_db()
    assert train_job.name == "GradientBoosting"
    assert serving.name == "GradientBoosting"


def test_predictable_list_includes_builtin_without_port(monkeypatch):
    _patch_team_contains(monkeypatch)
    train_job, serving = _builtin_pair(team_id=7)
    TimeSeriesPredictServing.objects.create(
        name="no-port",
        description="",
        team=[7],
        train_job=train_job,
        model_version="latest",
        container_info={},
    )
    actor = {"is_superuser": False, "group_list": [7], "locale": "en"}
    monkeypatch.delenv(PRESET_BASE_URL_ENV, raising=False)
    hidden = nats_api.get_mlops_module_data(
        "serving",
        "timeseries_predict_serving",
        1,
        20,
        7,
        actor_context=actor,
        predictable_only=True,
    )
    assert hidden["items"] == []

    monkeypatch.setenv(PRESET_BASE_URL_ENV, PRESET_URL)
    listed = nats_api.get_mlops_module_data(
        "serving",
        "timeseries_predict_serving",
        1,
        20,
        7,
        actor_context=actor,
        predictable_only=True,
    )
    assert listed["result"] is True
    assert listed["items"] == [{"id": serving.id, "name": "GradientBoosting"}]


def test_builtin_predict_uses_algorithm_path(monkeypatch):
    _train_job, serving = _builtin_pair()
    monkeypatch.setenv(PRESET_BASE_URL_ENV, f"{PRESET_URL}/")
    captured = {}

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"success": True, "predictions": [1]}

    def fake_post(url, json, timeout, headers):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        captured["headers"] = headers
        return Response()

    monkeypatch.setattr("apps.mlops.views.timeseries_predict.requests.post", fake_post)
    body, http_status = execute_timeseries_predict(
        serving,
        [{"timestamp": 1, "value": 2}],
        4,
        lambda key, **values: key,
    )
    assert http_status == 200
    assert body["success"] is True
    assert captured["url"] == "http://mlops-preset:3000/GradientBoosting/predict"
    assert captured["json"] == {"data": [{"timestamp": 1, "value": 2}], "config": {"steps": 4}}
