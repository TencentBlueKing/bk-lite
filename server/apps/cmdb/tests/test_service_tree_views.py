import json
from types import SimpleNamespace

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.views.service_tree import ServiceTreeViewSet
from apps.core.exceptions.base_app_exception import ValidationAppException
from apps.core.utils.web_utils import WebUtils

pytestmark = pytest.mark.unit

VIEWS = "apps.cmdb.views.service_tree"
SYS_UUID = "cccccccc-dddd-4eee-8fff-000000000000"


@pytest.fixture
def superuser():
    return SimpleNamespace(
        username="admin",
        is_superuser=True,
        is_authenticated=True,
        is_active=True,
        permission={"cmdb": set()},
        group_list=[{"id": 1}],
        group_tree=[],
        roles=["admin"],
        locale="zh-Hans",
    )


@pytest.fixture(autouse=True)
def _perm(monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.ServiceTreeViewSet.require_instance_permission",
        lambda self, request, instance, operator=None: None,
    )


def _req(method, user):
    factory = APIRequestFactory()
    request = getattr(factory, method)("/x/")
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=user)
    return request


def _post(user, data):
    factory = APIRequestFactory()
    request = factory.post("/x/", data, format="json")
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=user)
    return request


def _body(response):
    if hasattr(response, "render"):
        response.render()
        return json.loads(response.rendered_content)
    return json.loads(response.content)


def test_service_tree_rejects_non_system(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_uuid",
        lambda uuid: {"inst_uuid": uuid, "model_id": "host", "inst_name": "web"},
    )
    response = ServiceTreeViewSet.as_view({"get": "tree"})(_req("get", superuser), system_uuid=SYS_UUID)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "应用系统" in _body(response)["message"]


def test_service_tree_returns_tree_payload(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_uuid",
        lambda uuid: {"inst_uuid": uuid, "model_id": "system", "inst_name": "门户"},
    )
    monkeypatch.setattr(
        f"{VIEWS}.ServiceTreeService.get_tree",
        classmethod(lambda cls, system, is_visible=None: {"inst_uuid": SYS_UUID, "kind": "system", "children": [], "host_count": 0}),
    )
    response = ServiceTreeViewSet.as_view({"get": "tree"})(_req("get", superuser), system_uuid=SYS_UUID)
    assert response.status_code == status.HTTP_200_OK
    assert _body(response)["data"]["kind"] == "system"


def test_service_tree_transfer_rejects_invisible_target(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_uuid",
        lambda uuid: (
            {"inst_uuid": SYS_UUID, "model_id": "system", "inst_name": "门户"}
            if uuid == SYS_UUID
            else {"inst_uuid": uuid, "model_id": "application", "inst_name": "其它应用"}
        ),
    )
    monkeypatch.setattr(
        f"{VIEWS}.ServiceTreeViewSet.require_instance_permission",
        lambda self, request, instance, operator=None: (
            None if instance.get("model_id") == "system" else WebUtils.response_error("无权", status_code=403)
        ),
    )
    captured = {}

    def _transfer(cls, **kwargs):
        captured.update(kwargs)
        if not kwargs.get("target_visible"):
            raise ValidationAppException("目标应用不可见")
        return {"transferred": []}

    monkeypatch.setattr(f"{VIEWS}.ServiceTreeService.transfer_hosts", classmethod(_transfer))
    response = ServiceTreeViewSet.as_view({"post": "transfer"})(
        _post(superuser, {"source_app": "a1", "target_app": "a-hidden", "host_uuids": ["h1"]}),
        system_uuid=SYS_UUID,
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "不可见" in _body(response)["message"]
    assert captured == {}


def test_service_tree_unbind_passes_selected_hosts(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_uuid",
        lambda uuid: {"inst_uuid": uuid, "model_id": "system", "inst_name": "门户"},
    )
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_uuids",
        lambda uuids: [{"inst_uuid": uuid, "model_id": "host"} for uuid in uuids],
    )
    captured = {}

    def _unbind(cls, **kwargs):
        captured.update(kwargs)
        return {"unbound": kwargs["host_uuids"]}

    monkeypatch.setattr(f"{VIEWS}.ServiceTreeService.unbind_hosts", classmethod(_unbind))
    response = ServiceTreeViewSet.as_view({"post": "unbind"})(
        _post(superuser, {"application_uuid": "a1", "host_uuids": ["h1"]}),
        system_uuid=SYS_UUID,
    )
    assert response.status_code == status.HTTP_200_OK
    assert captured["application_uuid"] == "a1"
    assert captured["host_uuids"] == ["h1"]
    assert _body(response)["data"]["unbound"] == ["h1"]
