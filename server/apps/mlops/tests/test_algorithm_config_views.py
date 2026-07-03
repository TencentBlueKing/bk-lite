import pydantic.root_model  # noqa

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.base.tests.factories import UserFactory
from apps.mlops.models import AlgorithmConfig
from apps.mlops.models.anomaly_detection import AnomalyDetectionTrainJob
from apps.mlops.views.algorithm_config import AlgorithmConfigViewSet

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

factory = APIRequestFactory()


@pytest.fixture
def superuser():
    return UserFactory(username="algo-admin", domain="domain.com", roles=[], is_superuser=True)


def _mk(algorithm_type="anomaly_detection", name="ECOD", image="repo/ecod:1", is_active=True, form_config=None):
    return AlgorithmConfig.objects.create(
        algorithm_type=algorithm_type,
        name=name,
        display_name=name,
        image=image,
        is_active=is_active,
        form_config=form_config or {},
    )


def _call(view, request, superuser, **kwargs):
    force_authenticate(request, user=superuser)
    return view(request, **kwargs)


# ---------- list / serializer selection ----------

def test_list_uses_list_serializer_omits_form_config(superuser):
    _mk(form_config={"hyperopt_config": [{"key": "n"}]})
    request = factory.get("/algorithm_configs/")
    view = AlgorithmConfigViewSet.as_view({"get": "list"})
    resp = _call(view, request, superuser)
    assert resp.status_code == status.HTTP_200_OK
    items = resp.data["items"] if isinstance(resp.data, dict) and "items" in resp.data else resp.data
    assert items
    assert "form_config" not in items[0]


def test_list_include_form_config_uses_full_serializer(superuser):
    _mk(form_config={"hyperopt_config": [{"key": "n"}]})
    request = factory.get("/algorithm_configs/?include_form_config=true")
    view = AlgorithmConfigViewSet.as_view({"get": "list"})
    resp = _call(view, request, superuser)
    items = resp.data["items"] if isinstance(resp.data, dict) and "items" in resp.data else resp.data
    assert "form_config" in items[0]


# ---------- retrieve ----------

def test_retrieve_returns_full_config(superuser):
    cfg = _mk(form_config={"a": 1})
    request = factory.get("/algorithm_configs/x/")
    view = AlgorithmConfigViewSet.as_view({"get": "retrieve"})
    resp = _call(view, request, superuser, pk=cfg.id)
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["form_config"] == {"a": 1}


# ---------- create ----------

def test_create_persists(superuser):
    payload = {
        "algorithm_type": "classification",
        "name": "XGB",
        "display_name": "XGBoost",
        "image": "repo/xgb:1",
        "form_config": {},
    }
    request = factory.post("/algorithm_configs/", payload, format="json")
    view = AlgorithmConfigViewSet.as_view({"post": "create"})
    resp = _call(view, request, superuser)
    assert resp.status_code == status.HTTP_201_CREATED
    assert AlgorithmConfig.objects.filter(name="XGB").exists()


def test_create_invalid_form_config_rejected(superuser):
    payload = {
        "algorithm_type": "classification",
        "name": "Bad",
        "display_name": "Bad",
        "image": "repo/bad:1",
        "form_config": {"hyperopt_config": [{"missing_key": 1}]},
    }
    request = factory.post("/algorithm_configs/", payload, format="json")
    view = AlgorithmConfigViewSet.as_view({"post": "create"})
    resp = _call(view, request, superuser)
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


# ---------- partial_update disable guard ----------

def test_partial_update_disable_blocked_when_tasks_exist(superuser):
    cfg = _mk(name="InUse", is_active=True)
    AnomalyDetectionTrainJob.objects.create(name="job1", algorithm="InUse", team=[1])
    request = factory.patch("/algorithm_configs/x/", {"is_active": False}, format="json")
    view = AlgorithmConfigViewSet.as_view({"patch": "partial_update"})
    resp = _call(view, request, superuser, pk=cfg.id)
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.data["task_count"] == 1
    cfg.refresh_from_db()
    assert cfg.is_active is True


def test_partial_update_disable_allowed_when_no_tasks(superuser):
    cfg = _mk(name="Free", is_active=True)
    request = factory.patch("/algorithm_configs/x/", {"is_active": False}, format="json")
    view = AlgorithmConfigViewSet.as_view({"patch": "partial_update"})
    resp = _call(view, request, superuser, pk=cfg.id)
    assert resp.status_code == status.HTTP_200_OK
    cfg.refresh_from_db()
    assert cfg.is_active is False


def test_partial_update_other_field_not_guarded(superuser):
    cfg = _mk(name="Rename", is_active=True)
    AnomalyDetectionTrainJob.objects.create(name="j", algorithm="Rename", team=[1])
    request = factory.patch("/algorithm_configs/x/", {"display_name": "NewName"}, format="json")
    view = AlgorithmConfigViewSet.as_view({"patch": "partial_update"})
    resp = _call(view, request, superuser, pk=cfg.id)
    assert resp.status_code == status.HTTP_200_OK
    cfg.refresh_from_db()
    assert cfg.display_name == "NewName"


# ---------- destroy guard ----------

def test_destroy_blocked_when_tasks_exist(superuser):
    cfg = _mk(name="Locked")
    AnomalyDetectionTrainJob.objects.create(name="j", algorithm="Locked", team=[1])
    request = factory.delete("/algorithm_configs/x/")
    view = AlgorithmConfigViewSet.as_view({"delete": "destroy"})
    resp = _call(view, request, superuser, pk=cfg.id)
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.data["task_count"] == 1
    assert AlgorithmConfig.objects.filter(id=cfg.id).exists()


def test_destroy_allowed_when_no_tasks(superuser):
    cfg = _mk(name="Deletable")
    request = factory.delete("/algorithm_configs/x/")
    view = AlgorithmConfigViewSet.as_view({"delete": "destroy"})
    resp = _call(view, request, superuser, pk=cfg.id)
    assert resp.status_code in (status.HTTP_200_OK, status.HTTP_204_NO_CONTENT)
    assert not AlgorithmConfig.objects.filter(id=cfg.id).exists()


# ---------- _count_tasks_using_algorithm direct ----------

def test_count_tasks_unknown_type_returns_zero():
    vs = AlgorithmConfigViewSet()
    assert vs._count_tasks_using_algorithm("nope", "X") == 0


def test_count_tasks_known_type_counts():
    AnomalyDetectionTrainJob.objects.create(name="a", algorithm="Z", team=[1])
    AnomalyDetectionTrainJob.objects.create(name="b", algorithm="Z", team=[1])
    AnomalyDetectionTrainJob.objects.create(name="c", algorithm="Other", team=[1])
    vs = AlgorithmConfigViewSet()
    assert vs._count_tasks_using_algorithm("anomaly_detection", "Z") == 2


# ---------- by_type action ----------

def test_by_type_returns_only_active(superuser):
    _mk(algorithm_type="log_clustering", name="Act", is_active=True)
    _mk(algorithm_type="log_clustering", name="Inact", is_active=False)
    request = factory.get("/algorithm_configs/by_type/log_clustering/")
    view = AlgorithmConfigViewSet.as_view({"get": "by_type"})
    resp = _call(view, request, superuser, algorithm_type="log_clustering")
    assert resp.status_code == status.HTTP_200_OK
    names = {r["name"] for r in resp.data}
    assert names == {"Act"}
    assert "form_config" in resp.data[0]


# ---------- get_image action ----------

def test_get_image_success(superuser):
    _mk(algorithm_type="timeseries_predict", name="Prophet", image="repo/prophet:5")
    request = factory.get("/algorithm_configs/get_image/?algorithm_type=timeseries_predict&name=Prophet")
    view = AlgorithmConfigViewSet.as_view({"get": "get_image"})
    resp = _call(view, request, superuser)
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["image"] == "repo/prophet:5"


def test_get_image_missing_params(superuser):
    request = factory.get("/algorithm_configs/get_image/?algorithm_type=x")
    view = AlgorithmConfigViewSet.as_view({"get": "get_image"})
    resp = _call(view, request, superuser)
    assert resp.status_code == 400
    assert "error" in resp.data


def test_get_image_not_found(superuser):
    request = factory.get("/algorithm_configs/get_image/?algorithm_type=anomaly_detection&name=Ghost")
    view = AlgorithmConfigViewSet.as_view({"get": "get_image"})
    resp = _call(view, request, superuser)
    assert resp.status_code == 404
    assert "error" in resp.data
