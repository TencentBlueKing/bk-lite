import logging

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.base.tests.factories import UserFactory
from apps.mlops import nats_api
from apps.mlops.models.timeseries_predict import TimeSeriesPredictServing, TimeSeriesPredictTrainJob
from apps.mlops.serializers.timeseries_predict import TimeSeriesPredictServingSerializer, TimeSeriesPredictTrainJobSerializer
from apps.mlops.services.builtin_timeseries import PRESET_BASE_URL_ENV, builtin_predict_url, ensure_builtin_timeseries_records
from apps.mlops.views.timeseries_predict import TimeSeriesPredictServingViewSet, TimeSeriesPredictTrainJobViewSet, execute_timeseries_predict
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


def _log_record(caplog, message):
    matched = [record for record in caplog.records if record.name == "mlops" and record.msg == message]
    assert len(matched) == 1
    return matched[0]


def test_init_skips_when_preset_address_is_absent(monkeypatch, caplog):
    monkeypatch.delenv(PRESET_BASE_URL_ENV, raising=False)
    with caplog.at_level(logging.INFO, logger="mlops"):
        result = ensure_builtin_timeseries_records()
    assert result["skipped"] is True
    assert TimeSeriesPredictTrainJob.objects.filter(is_builtin=True).count() == 0
    record = _log_record(caplog, "event=builtin_timeseries_init_skipped reason=preset_base_url_absent")
    assert record.args == ()
    assert record.getMessage() == "event=builtin_timeseries_init_skipped reason=preset_base_url_absent"
    assert PRESET_URL not in caplog.text


def test_init_writes_default_org_pair_once_without_minio(monkeypatch, caplog):
    monkeypatch.setenv(PRESET_BASE_URL_ENV, f"{PRESET_URL}/")
    group = Group.objects.get(name="Default", parent_id=0)
    if not group.is_builtin:
        group.is_builtin = True
        group.save(update_fields=["is_builtin"])

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
    finished = [
        record
        for record in caplog.records
        if record.name == "mlops" and record.msg == "event=builtin_timeseries_init_finished created_train_jobs=%s created_servings=%s"
    ]
    assert [(record.args, record.getMessage()) for record in finished] == [
        ((1, 1), "event=builtin_timeseries_init_finished created_train_jobs=1 created_servings=1"),
        ((0, 0), "event=builtin_timeseries_init_finished created_train_jobs=0 created_servings=0"),
    ]
    assert PRESET_URL not in caplog.text


def test_init_command_writes_pair_after_default_group_returns(monkeypatch):
    Group.objects.filter(name="Default", parent_id=0).delete()
    monkeypatch.setenv(PRESET_BASE_URL_ENV, PRESET_URL)
    with pytest.raises(CommandError):
        call_command("init_builtin_timeseries")
    assert TimeSeriesPredictTrainJob.objects.filter(is_builtin=True).count() == 0

    Group.objects.create(name="Default", parent_id=0, is_builtin=True)
    call_command("init_builtin_timeseries")

    train_job = TimeSeriesPredictTrainJob.objects.get(is_builtin=True, algorithm="GradientBoosting")
    serving = TimeSeriesPredictServing.objects.get(is_builtin=True, train_job=train_job)
    assert train_job.name == "GradientBoosting"
    assert serving.name == "GradientBoosting"
    assert serving.container_info == {}


def test_init_fills_missing_builtin_serving_without_new_train_job(monkeypatch):
    monkeypatch.setenv(PRESET_BASE_URL_ENV, PRESET_URL)
    group = Group.objects.get(name="Default", parent_id=0)
    if not group.is_builtin:
        group.is_builtin = True
        group.save(update_fields=["is_builtin"])
    train_job = TimeSeriesPredictTrainJob.objects.create(
        name="GradientBoosting",
        description="",
        team=[group.id],
        algorithm="GradientBoosting",
        is_builtin=True,
        hyperopt_config={},
    )

    result = ensure_builtin_timeseries_records()

    assert result == {"created_train_jobs": 0, "created_servings": 1, "skipped": False}
    assert TimeSeriesPredictTrainJob.objects.filter(is_builtin=True, algorithm="GradientBoosting").count() == 1
    serving = TimeSeriesPredictServing.objects.get(is_builtin=True, train_job=train_job)
    assert serving.name == "GradientBoosting"
    assert serving.container_info == {}


def test_init_keeps_drifted_builtin_train_job_fields(monkeypatch):
    monkeypatch.setenv(PRESET_BASE_URL_ENV, PRESET_URL)
    group = Group.objects.get(name="Default", parent_id=0)
    if not group.is_builtin:
        group.is_builtin = True
        group.save(update_fields=["is_builtin"])
    other = Group.objects.create(name="Other", parent_id=0)
    train_job = TimeSeriesPredictTrainJob.objects.create(
        name="renamed",
        description="keep",
        team=[other.id],
        algorithm="GradientBoosting",
        is_builtin=True,
        hyperopt_config={},
    )

    result = ensure_builtin_timeseries_records()

    train_job.refresh_from_db()
    assert result["created_train_jobs"] == 0
    assert result["created_servings"] == 1
    assert train_job.name == "renamed"
    assert train_job.description == "keep"
    assert train_job.team == [other.id]
    assert train_job.hyperopt_config == {}
    assert TimeSeriesPredictTrainJob.objects.filter(is_builtin=True, algorithm="GradientBoosting").count() == 1
    serving = train_job.servings.get()
    assert serving.is_builtin is True
    assert serving.name == "GradientBoosting"
    assert serving.team == [group.id]


def test_init_creates_builtin_pair_beside_ordinary_same_algorithm(monkeypatch):
    monkeypatch.setenv(PRESET_BASE_URL_ENV, PRESET_URL)
    ordinary = TimeSeriesPredictTrainJob.objects.create(
        name="user-gb",
        description="",
        team=[1],
        algorithm="GradientBoosting",
        is_builtin=False,
        hyperopt_config={},
    )

    result = ensure_builtin_timeseries_records()

    ordinary.refresh_from_db()
    assert ordinary.name == "user-gb"
    assert ordinary.is_builtin is False
    assert result["created_train_jobs"] == 1
    assert result["created_servings"] == 1
    assert TimeSeriesPredictTrainJob.objects.filter(algorithm="GradientBoosting").count() == 2
    assert TimeSeriesPredictTrainJob.objects.filter(is_builtin=True, algorithm="GradientBoosting").count() == 1


def test_init_fails_when_default_group_is_missing(monkeypatch, caplog):
    Group.objects.filter(name="Default", parent_id=0).delete()
    monkeypatch.setenv(PRESET_BASE_URL_ENV, PRESET_URL)
    with caplog.at_level(logging.DEBUG, logger="mlops"):
        with pytest.raises(CommandError, match="默认组织 Default 不存在，无法写入预置时序发布记录"):
            ensure_builtin_timeseries_records()
    assert not any(record.name == "mlops" and record.levelno >= logging.WARNING for record in caplog.records)
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
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.WebhookClient.remove",
        staticmethod(lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("remove"))),
    )
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.mlflow_service.get_experiment_by_name",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("mlflow")),
    )
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.mlflow_service.get_model_versions",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("mlflow")),
    )
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.mlflow_service.get_run_metrics",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("mlflow")),
    )
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.mlflow_service.get_run_info",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("mlflow")),
    )
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.mlflow_service.delete_run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("mlflow")),
    )

    cases = [
        (TimeSeriesPredictServingViewSet, "post", "start", f"/servings/{serving.id}/start/", serving.id),
        (TimeSeriesPredictServingViewSet, "post", "stop", f"/servings/{serving.id}/stop/", serving.id),
        (TimeSeriesPredictServingViewSet, "post", "remove", f"/servings/{serving.id}/remove/", serving.id),
        (TimeSeriesPredictServingViewSet, "patch", "partial_update", f"/servings/{serving.id}/", serving.id),
        (TimeSeriesPredictServingViewSet, "delete", "destroy", f"/servings/{serving.id}/", serving.id),
        (TimeSeriesPredictTrainJobViewSet, "post", "train", f"/jobs/{train_job.id}/train/", train_job.id),
        (TimeSeriesPredictTrainJobViewSet, "post", "stop", f"/jobs/{train_job.id}/stop/", train_job.id),
        (TimeSeriesPredictTrainJobViewSet, "patch", "partial_update", f"/jobs/{train_job.id}/", train_job.id),
        (TimeSeriesPredictTrainJobViewSet, "delete", "destroy", f"/jobs/{train_job.id}/", train_job.id),
        (TimeSeriesPredictTrainJobViewSet, "get", "get_run_data_list", f"/jobs/{train_job.id}/runs_data_list/", train_job.id),
        (TimeSeriesPredictTrainJobViewSet, "get", "get_model_versions", f"/jobs/{train_job.id}/model_versions/", train_job.id),
    ]
    for viewset, method, action, path, pk in cases:
        if method == "get":
            request = factory.get(path)
        else:
            request = getattr(factory, method)(path, {"name": "changed"}, format="json")
        response = _call(viewset.as_view({method: action}), request, user, pk=pk)
        assert response.status_code == status.HTTP_400_BAD_REQUEST, action
        assert response.data["error"] == "This operation is not available for a built-in record"
    run_cases = [
        ("get", "get_runs_metrics_list", f"/jobs/{train_job.id}/runs/run-1/metrics_list/", {}),
        ("get", "get_metric_data", f"/jobs/{train_job.id}/runs/run-1/metrics_history/loss/", {"metric_name": "loss"}),
        ("get", "get_run_params", f"/jobs/{train_job.id}/runs/run-1/run_params/", {}),
        ("get", "download_model", f"/jobs/{train_job.id}/runs/run-1/download_model/", {}),
        ("delete", "delete_run", f"/jobs/{train_job.id}/runs/run-1/", {}),
    ]
    for method, action, path, extra in run_cases:
        request = getattr(factory, method)(path)
        response = _call(
            TimeSeriesPredictTrainJobViewSet.as_view({method: action}),
            request,
            user,
            pk=train_job.id,
            run_id="run-1",
            **extra,
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST, action
        assert response.data["error"] == "This operation is not available for a built-in record"
    train_job.refresh_from_db()
    serving.refresh_from_db()
    assert train_job.name == "GradientBoosting"
    assert serving.name == "GradientBoosting"


def test_builtin_serving_edit_accepts_only_team(monkeypatch):
    user = _superuser()
    train_job, serving = _builtin_pair(team_id=1)
    other = Group.objects.create(name="OtherOrg", parent_id=0)
    monkeypatch.setenv(PRESET_BASE_URL_ENV, PRESET_URL)
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.mlflow_service.get_experiment_by_name",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("mlflow")),
    )
    monkeypatch.setattr(
        "apps.mlops.views.timeseries_predict.WebhookClient.serve",
        staticmethod(lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("serve"))),
    )

    request = factory.patch(f"/servings/{serving.id}/", {"team": [other.id]}, format="json")
    response = _call(
        TimeSeriesPredictServingViewSet.as_view({"patch": "partial_update"}),
        request,
        user,
        pk=serving.id,
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.data["team"] == [other.id]
    train_job.refresh_from_db()
    serving.refresh_from_db()
    assert serving.team == [other.id]
    assert serving.name == "GradientBoosting"
    assert train_job.team == [1]

    rejected = factory.patch(
        f"/servings/{serving.id}/",
        {"team": [1], "name": "changed"},
        format="json",
    )
    rejected_response = _call(
        TimeSeriesPredictServingViewSet.as_view({"patch": "partial_update"}),
        rejected,
        user,
        pk=serving.id,
    )
    assert rejected_response.status_code == status.HTTP_400_BAD_REQUEST
    assert rejected_response.data["error"] == "This operation is not available for a built-in record"
    serving.refresh_from_db()
    assert serving.name == "GradientBoosting"
    assert serving.team == [other.id]

    train_request = factory.patch(f"/jobs/{train_job.id}/", {"team": [other.id]}, format="json")
    train_response = _call(
        TimeSeriesPredictTrainJobViewSet.as_view({"patch": "partial_update"}),
        train_request,
        user,
        pk=train_job.id,
    )
    assert train_response.status_code == status.HTTP_400_BAD_REQUEST
    train_job.refresh_from_db()
    assert train_job.team == [1]


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


@pytest.mark.parametrize(
    "algorithm",
    ["", "GradientBoosting/admin", "GradientBoosting\\admin", "..", "GradientBoosting?x=1", "GradientBoosting#frag"],
)
def test_builtin_predict_url_rejects_algorithm_that_changes_the_request_target(monkeypatch, algorithm):
    monkeypatch.setenv(PRESET_BASE_URL_ENV, PRESET_URL)
    with pytest.raises(ValueError, match="error.preset_algorithm_invalid"):
        builtin_predict_url(algorithm)


def test_builtin_predict_url_accepts_algorithm_segment(monkeypatch):
    monkeypatch.setenv(PRESET_BASE_URL_ENV, f"{PRESET_URL}/")
    assert builtin_predict_url("My-Model_1") == "http://mlops-preset:3000/My-Model_1/predict"


def test_builtin_predict_does_not_call_upstream_when_algorithm_changes_the_path(monkeypatch):
    train_job, serving = _builtin_pair()
    TimeSeriesPredictTrainJob.objects.filter(pk=train_job.pk).update(algorithm="GradientBoosting/admin")
    train_job.refresh_from_db()
    monkeypatch.setenv(PRESET_BASE_URL_ENV, PRESET_URL)
    called = {"post": False}

    def fake_post(*args, **kwargs):
        called["post"] = True
        raise AssertionError("upstream")

    monkeypatch.setattr("apps.mlops.views.timeseries_predict.requests.post", fake_post)
    body, http_status = execute_timeseries_predict(
        serving,
        [{"timestamp": 1, "value": 2}],
        4,
        lambda key, **values: key,
    )
    assert http_status == 400
    assert body == {"error": "error.preset_algorithm_invalid"}
    assert called["post"] is False
