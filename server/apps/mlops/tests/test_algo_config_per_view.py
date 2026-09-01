"""六套算法视图内嵌 AlgorithmConfigViewSet：列表序列化、禁用/删除护栏、by_type 与 get_image。"""
import importlib

import pydantic.root_model  # noqa
import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory

from apps.base.tests.factories import UserFactory
from apps.mlops.models import AlgorithmConfig
from apps.mlops.tests.test_views_actions_param import ALGO_IDS, ALGOS, _call, _make_train_job

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

factory = APIRequestFactory()


@pytest.fixture
def superuser():
    return UserFactory(username="algo-per-view-su", domain="domain.com", roles=[], is_superuser=True)


def _view_module(suffix):
    return importlib.import_module(f"apps.mlops.views.{suffix}")


def _mk(algorithm_type, name, *, is_active=True, image="repo/algo:1", form_config=None):
    return AlgorithmConfig.objects.create(
        algorithm_type=algorithm_type,
        name=name,
        display_name=name,
        image=image,
        is_active=is_active,
        form_config=form_config or {"k": 1},
    )


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_algo_config_list_omits_form_config_unless_requested(superuser, suffix, prefix, model_module, basename):
    _mk(suffix, f"List-{suffix}")
    mod = _view_module(suffix)
    vs = getattr(mod, f"{basename}AlgorithmConfigViewSet")
    view = vs.as_view({"get": "list"})
    resp = _call(view, factory.get(f"/{suffix}_algo_configs/"), superuser)
    assert resp.status_code == status.HTTP_200_OK
    items = resp.data["items"] if isinstance(resp.data, dict) and "items" in resp.data else resp.data
    assert items
    assert "form_config" not in items[0]

    resp_full = _call(
        view,
        factory.get(f"/{suffix}_algo_configs/?include_form_config=true"),
        superuser,
    )
    items_full = resp_full.data["items"] if isinstance(resp_full.data, dict) and "items" in resp_full.data else resp_full.data
    assert "form_config" in items_full[0]


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_algo_config_create_forces_algorithm_type(superuser, suffix, prefix, model_module, basename):
    mod = _view_module(suffix)
    vs = getattr(mod, f"{basename}AlgorithmConfigViewSet")
    view = vs.as_view({"post": "create"})
    payload = {
        "algorithm_type": "classification",
        "name": f"Forced-{suffix}",
        "display_name": "Forced",
        "image": "repo/forced:1",
        "form_config": {},
    }
    resp = _call(view, factory.post(f"/{suffix}_algo_configs/", payload, format="json"), superuser)
    assert resp.status_code == status.HTTP_201_CREATED
    cfg = AlgorithmConfig.objects.get(name=f"Forced-{suffix}")
    assert cfg.algorithm_type == suffix


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_algo_config_disable_and_destroy_blocked_when_jobs_exist(superuser, suffix, prefix, model_module, basename):
    cfg = _mk(suffix, f"InUse-{suffix}", is_active=True)
    _make_train_job(model_module, basename)
    job_model = importlib.import_module(f"apps.mlops.models.{model_module}")
    TrainJob = getattr(job_model, f"{basename}TrainJob")
    TrainJob.objects.filter(name="job").update(algorithm=cfg.name)

    mod = _view_module(suffix)
    vs = getattr(mod, f"{basename}AlgorithmConfigViewSet")
    disable = _call(
        vs.as_view({"patch": "partial_update"}),
        factory.patch(f"/{suffix}_algo_configs/x/", {"is_active": False}, format="json"),
        superuser,
        pk=cfg.id,
    )
    assert disable.status_code == status.HTTP_400_BAD_REQUEST
    assert disable.data["task_count"] == 1
    cfg.refresh_from_db()
    assert cfg.is_active is True

    destroy = _call(
        vs.as_view({"delete": "destroy"}),
        factory.delete(f"/{suffix}_algo_configs/x/"),
        superuser,
        pk=cfg.id,
    )
    assert destroy.status_code == status.HTTP_400_BAD_REQUEST
    assert AlgorithmConfig.objects.filter(id=cfg.id).exists()


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_algo_config_disable_destroy_and_get_image_when_unused(superuser, suffix, prefix, model_module, basename):
    cfg = _mk(suffix, f"Free-{suffix}", is_active=True, image="repo/free:9")
    _mk(suffix, f"Inactive-{suffix}", is_active=False, image="repo/off:1")
    mod = _view_module(suffix)
    vs = getattr(mod, f"{basename}AlgorithmConfigViewSet")

    disable = _call(
        vs.as_view({"patch": "partial_update"}),
        factory.patch(f"/{suffix}_algo_configs/x/", {"is_active": False}, format="json"),
        superuser,
        pk=cfg.id,
    )
    assert disable.status_code == status.HTTP_200_OK
    cfg.refresh_from_db()
    assert cfg.is_active is False

    cfg.is_active = True
    cfg.save(update_fields=["is_active"])

    by_type = _call(vs.as_view({"get": "by_type"}), factory.get(f"/{suffix}_algo_configs/by_type/"), superuser)
    assert by_type.status_code == status.HTTP_200_OK
    names = {item["name"] for item in by_type.data}
    assert f"Free-{suffix}" in names
    assert f"Inactive-{suffix}" not in names

    missing_name = _call(
        vs.as_view({"get": "get_image"}),
        factory.get(f"/{suffix}_algo_configs/get_image/"),
        superuser,
    )
    assert missing_name.status_code == 400
    assert missing_name.data["error"] == "name is required"

    not_found = _call(
        vs.as_view({"get": "get_image"}),
        factory.get(f"/{suffix}_algo_configs/get_image/?name=no-such"),
        superuser,
    )
    assert not_found.status_code == 404
    assert f"{suffix}/no-such" in not_found.data["error"]

    ok = _call(
        vs.as_view({"get": "get_image"}),
        factory.get(f"/{suffix}_algo_configs/get_image/?name=Free-{suffix}"),
        superuser,
    )
    assert ok.status_code == status.HTTP_200_OK
    assert ok.data["image"] == "repo/free:9"

    destroy = _call(
        vs.as_view({"delete": "destroy"}),
        factory.delete(f"/{suffix}_algo_configs/x/"),
        superuser,
        pk=cfg.id,
    )
    assert destroy.status_code in (status.HTTP_200_OK, status.HTTP_204_NO_CONTENT)
    assert not AlgorithmConfig.objects.filter(id=cfg.id).exists()
