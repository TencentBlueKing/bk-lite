"""ModelViewSet.save_layout：超管鉴权、入参校验、模型写失败回滚分类布局。"""
import json

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.views.model import ModelViewSet

VIEWS = "apps.cmdb.views.model"


@pytest.fixture
def superuser(authenticated_user):
    u = authenticated_user
    u.is_superuser = True
    u.group_list = [{"id": 1}]
    return u


def _req(user, data=None):
    factory = APIRequestFactory()
    request = factory.post("/x/", data=data or {}, format="json")
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=user)
    return request


def _body(response):
    if hasattr(response, "render"):
        response.render()
        return json.loads(response.rendered_content)
    return json.loads(response.content)


@pytest.mark.django_db
def test_save_layout_ok(superuser, monkeypatch):
    calls = []
    monkeypatch.setattr(
        f"{VIEWS}.ClassificationManage.snapshot_classification_layout",
        lambda ids: calls.append(("snapshot", ids)) or [{"classification_id": "biz"}],
    )
    monkeypatch.setattr(
        f"{VIEWS}.ClassificationManage.update_classification_layout",
        lambda items: calls.append(("update_cls", items)),
    )
    monkeypatch.setattr(
        f"{VIEWS}.ModelManage.update_model_orders",
        lambda items: calls.append(("update_models", items)),
    )
    payload = {"classifications": [{"classification_id": "biz"}], "models": [{"model_id": "host"}]}
    response = ModelViewSet.as_view({"post": "save_layout"})(_req(superuser, payload))
    assert response.status_code == status.HTTP_200_OK
    assert ("snapshot", ["biz"]) in calls
    assert ("update_models", payload["models"]) in calls


@pytest.mark.django_db
def test_save_layout_reverts_classification_when_model_write_fails(superuser, monkeypatch):
    reverted = []
    monkeypatch.setattr(
        f"{VIEWS}.ClassificationManage.snapshot_classification_layout",
        lambda ids: [{"classification_id": "biz", "order": 1}],
    )
    monkeypatch.setattr(
        f"{VIEWS}.ClassificationManage.update_classification_layout",
        lambda items: reverted.append(items),
    )

    def boom(items):
        raise RuntimeError("graph write failed")

    monkeypatch.setattr(f"{VIEWS}.ModelManage.update_model_orders", boom)
    with pytest.raises(RuntimeError, match="graph write failed"):
        ModelViewSet.as_view({"post": "save_layout"})(
            _req(superuser, {"classifications": [{"classification_id": "biz"}], "models": [{"model_id": "host"}]})
        )
    assert reverted == [[{"classification_id": "biz"}], [{"classification_id": "biz", "order": 1}]]
