import json
from types import SimpleNamespace

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.constants.constants import VIEW
from apps.cmdb.views.service_tree import ServiceTreeViewSet
from apps.core.exceptions.base_app_exception import BaseAppException, ValidationAppException
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


AA = "aaaaaaaa-aaaa-4aaa-8aaa-0000000000aa"
AB = "bbbbbbbb-bbbb-4bbb-8bbb-0000000000ab"
AD = "dddddddd-dddd-4ddd-8ddd-0000000000ad"
HC = "hhhhhhhh-hhhh-4hhh-8hhh-0000000000hc"
SC = "cccccccc-cccc-4ccc-8ccc-0000000000c1"
SB = "bbbbbbbb-bbbb-4bbb-8bbb-0000000000b1"
SD = "dddddddd-dddd-4ddd-8ddd-0000000000d1"
NAME_SC = "系统-SC"
SECRET_SB = "系统-SB-机密"
SECRET_SD = "系统-SD-机密"


def _application_system_catalog():
    instances = {
        SYS_UUID: {"inst_uuid": SYS_UUID, "model_id": "system", "inst_name": "系统-SA"},
        AA: {"inst_uuid": AA, "model_id": "application", "inst_name": "应用-AA"},
        AB: {"inst_uuid": AB, "model_id": "application", "inst_name": "应用-AB"},
        AD: {"inst_uuid": AD, "model_id": "application", "inst_name": "应用-AD"},
        HC: {"inst_uuid": HC, "model_id": "host", "inst_name": "主机-HC"},
        SC: {"inst_uuid": SC, "model_id": "system", "inst_name": NAME_SC},
        SB: {"inst_uuid": SB, "model_id": "system", "inst_name": SECRET_SB},
        SD: {"inst_uuid": SD, "model_id": "system", "inst_name": SECRET_SD},
    }
    parents = {
        AA: {"inst_uuid": SC, "inst_name": NAME_SC},
        AB: {"inst_uuid": SB, "inst_name": SECRET_SB},
        AD: {"inst_uuid": SD, "inst_name": SECRET_SD},
    }
    return instances, parents


def _bind_application_systems(monkeypatch, visible):
    instances, parents = _application_system_catalog()
    queried = []
    looked_up = []

    def _one(uuid):
        found = instances.get(uuid)
        return dict(found) if found else {}

    def _many(uuids):
        batch = list(uuids)
        queried.append(batch)
        if len(set(batch)) != len(batch):
            raise BaseAppException("inst_uuid 不允许重复")
        return [dict(instances[item]) for item in batch if item in instances]

    def _perm(self, request, instance, operator=None):
        if operator != VIEW or instance.get("inst_uuid") not in visible:
            return WebUtils.response_error("无权", status_code=status.HTTP_403_FORBIDDEN)
        return None

    def _systems(cls, app_uuids):
        looked_up.append(list(app_uuids))
        return {item: dict(parents[item]) for item in app_uuids if item in parents}

    monkeypatch.setattr(f"{VIEWS}.InstanceManage.query_entity_by_uuid", _one)
    monkeypatch.setattr(f"{VIEWS}.InstanceManage.query_entity_by_uuids", _many)
    monkeypatch.setattr(f"{VIEWS}.ServiceTreeViewSet.require_instance_permission", _perm)
    monkeypatch.setattr(f"{VIEWS}.ServiceTreeService.systems_for_applications", classmethod(_systems))
    return queried, looked_up


def _post_application_systems(user, uuids):
    return ServiceTreeViewSet.as_view({"post": "application_systems"})(
        _post(user, {"uuids": uuids}),
        system_uuid=SYS_UUID,
    )


def test_application_systems_omits_invisible_app_and_keeps_other_visible_system(superuser, monkeypatch):
    queried, looked_up = _bind_application_systems(monkeypatch, visible={SYS_UUID, AA, AD, SC})
    response = _post_application_systems(superuser, [AA, AB, AA, HC])
    body = _body(response)
    rendered = json.dumps(body, ensure_ascii=False)
    assert response.status_code == status.HTTP_200_OK
    assert body["data"] == {AA: {"inst_uuid": SC, "inst_name": NAME_SC}}
    assert SECRET_SB not in rendered
    assert SB not in rendered
    assert looked_up == [[AA]]
    assert any(SC in batch for batch in queried)


def test_application_systems_omits_invisible_system_of_visible_application(superuser, monkeypatch):
    queried, looked_up = _bind_application_systems(monkeypatch, visible={SYS_UUID, AA, AD, SC})
    response = _post_application_systems(superuser, [AD])
    body = _body(response)
    rendered = json.dumps(body, ensure_ascii=False)
    assert response.status_code == status.HTTP_200_OK
    assert body["data"] == {}
    assert SECRET_SD not in rendered
    assert SD not in rendered
    assert looked_up == [[AD]]
    assert any(SD in batch for batch in queried)


def test_application_systems_invisible_application_returns_empty_mapping(superuser, monkeypatch):
    queried, looked_up = _bind_application_systems(monkeypatch, visible={SYS_UUID, AA, AD, SC})
    response = _post_application_systems(superuser, [AB])
    body = _body(response)
    rendered = json.dumps(body, ensure_ascii=False)
    assert response.status_code == status.HTTP_200_OK
    assert body["data"] == {}
    assert SECRET_SB not in rendered
    assert SB not in rendered
    assert all(AB not in batch for batch in looked_up)
    assert any(AB in batch for batch in queried)


def test_application_systems_rejects_invisible_path_system(superuser, monkeypatch):
    queried, looked_up = _bind_application_systems(monkeypatch, visible={AA, AD, SC})
    response = _post_application_systems(superuser, [AA])
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert looked_up == []
    assert queried == []
