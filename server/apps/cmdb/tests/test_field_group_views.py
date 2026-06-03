"""CMDB 字段分组视图覆盖测试（patch FieldGroupService/ModelManage + 真实 FieldGroup DB）。

对照 spec/prd/CMDB·模型管理：字段分组的增删改查、移动排序、批量调整归组、模型完整信息。
"""

import json

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.models.field_group import FieldGroup
from apps.cmdb.views.field_group import FieldGroupViewSet

VIEWS = "apps.cmdb.views.field_group"


@pytest.fixture
def superuser(authenticated_user):
    u = authenticated_user
    u.is_superuser = True
    u.group_list = [{"id": 1}]
    u.group_tree = []
    u.locale = "zh-Hans"
    return u


@pytest.fixture
def group(db):
    return FieldGroup.objects.create(model_id="host", group_name="基本信息", order=1, created_by="admin")


def _req(method, user, data=None, query=""):
    factory = APIRequestFactory()
    fn = getattr(factory, method)
    path = "/x/" + (f"?{query}" if query else "")
    request = fn(path) if data is None else fn(path, data=data, format="json")
    force_authenticate(request, user=user)
    return request


def _body(response):
    if hasattr(response, "render"):
        response.render()
        return json.loads(response.rendered_content)
    return json.loads(response.content)


# --------------------------------------------------------------------------
# create
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_create_missing_model_id(superuser):
    response = FieldGroupViewSet.as_view({"post": "create"})(_req("post", superuser, data={"group_name": "g"}))
    assert _body(response)["result"] is False


@pytest.mark.django_db
def test_create_invalid_serializer(superuser):
    # group_name 缺失
    response = FieldGroupViewSet.as_view({"post": "create"})(
        _req("post", superuser, data={"model_id": "host"})
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_create_ok(superuser, monkeypatch, group):
    monkeypatch.setattr(f"{VIEWS}.FieldGroupService.create_group", lambda **k: group)
    response = FieldGroupViewSet.as_view({"post": "create"})(
        _req("post", superuser, data={"model_id": "host", "group_name": "基本信息"})
    )
    assert response.status_code == status.HTTP_200_OK
    assert _body(response)["data"]["group_name"] == "基本信息"


# --------------------------------------------------------------------------
# retrieve / update / destroy / move（真实 DB get_object）
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_retrieve(superuser, group):
    response = FieldGroupViewSet.as_view({"get": "retrieve"})(_req("get", superuser), pk=group.id)
    assert _body(response)["data"]["group_name"] == "基本信息"


@pytest.mark.django_db
def test_update_ok(superuser, monkeypatch, group):
    monkeypatch.setattr(f"{VIEWS}.FieldGroupService.update_group", lambda **k: group)
    response = FieldGroupViewSet.as_view({"put": "update"})(
        _req("put", superuser, data={"group_name": "新名"}), pk=group.id
    )
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_update_invalid(superuser, group):
    response = FieldGroupViewSet.as_view({"put": "update"})(
        _req("put", superuser, data={}), pk=group.id
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_destroy(superuser, monkeypatch, group):
    monkeypatch.setattr(f"{VIEWS}.FieldGroupService.delete_group", lambda **k: {"success": True})
    response = FieldGroupViewSet.as_view({"delete": "destroy"})(_req("delete", superuser), pk=group.id)
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_move_ok(superuser, monkeypatch, group):
    monkeypatch.setattr(f"{VIEWS}.FieldGroupService.move_group", lambda **k: {"new_orders": []})
    response = FieldGroupViewSet.as_view({"post": "move"})(
        _req("post", superuser, data={"direction": "up"}), pk=group.id
    )
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_move_invalid_direction(superuser, group):
    response = FieldGroupViewSet.as_view({"post": "move"})(
        _req("post", superuser, data={"direction": "sideways"}), pk=group.id
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


# --------------------------------------------------------------------------
# full_info
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_full_info_missing_model_id(superuser):
    response = FieldGroupViewSet.as_view({"get": "full_info"})(_req("get", superuser))
    assert _body(response)["result"] is False


@pytest.mark.django_db
def test_full_info_model_not_found(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.ModelManage.search_model_info", lambda mid: {})
    response = FieldGroupViewSet.as_view({"get": "full_info"})(_req("get", superuser, query="model_id=host"))
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_full_info_ok(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.ModelManage.search_model_info", lambda mid: {"model_id": "host", "group": [1]})
    monkeypatch.setattr(f"{VIEWS}.get_default_group_id", lambda: [1])
    monkeypatch.setattr(
        f"{VIEWS}.FieldGroupViewSet.require_model_view_permission", lambda self, *a, **k: None
    )
    monkeypatch.setattr(
        f"{VIEWS}.FieldGroupService.get_model_with_groups", lambda **k: {"model_id": "host", "groups": []}
    )
    response = FieldGroupViewSet.as_view({"get": "full_info"})(_req("get", superuser, query="model_id=host"))
    assert response.status_code == status.HTTP_200_OK
    assert _body(response)["data"]["model_id"] == "host"


# --------------------------------------------------------------------------
# batch_update_attrs / update_attr_group / reorder_group_attrs
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_batch_update_attrs_ok(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.FieldGroupService.batch_update_attrs_group", lambda **k: {"updated_count": 1}
    )
    response = FieldGroupViewSet.as_view({"put": "batch_update_attrs"})(
        _req("put", superuser, data={"model_id": "host", "updates": [{"attr_id": "ip", "group_name": "网络"}]})
    )
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_batch_update_attrs_missing_model(superuser):
    response = FieldGroupViewSet.as_view({"put": "batch_update_attrs"})(
        _req("put", superuser, data={"updates": [{"attr_id": "ip", "group_name": "x"}]})
    )
    assert _body(response)["result"] is False


@pytest.mark.django_db
def test_update_attr_group_validations(superuser):
    view = FieldGroupViewSet.as_view({"post": "update_attr_group"})
    assert _body(view(_req("post", superuser, data={"attr_id": "a", "group_name": "g"})))["result"] is False
    assert _body(view(_req("post", superuser, data={"model_id": "host", "group_name": "g"})))["result"] is False
    assert _body(view(_req("post", superuser, data={"model_id": "host", "attr_id": "a"})))["result"] is False


@pytest.mark.django_db
def test_update_attr_group_ok(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.FieldGroupService.update_attr_group", lambda **k: {"success": True})
    response = FieldGroupViewSet.as_view({"post": "update_attr_group"})(
        _req("post", superuser, data={"model_id": "host", "attr_id": "a", "group_name": "g"})
    )
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_reorder_group_attrs_validations(superuser):
    view = FieldGroupViewSet.as_view({"post": "reorder_group_attrs"})
    assert _body(view(_req("post", superuser, data={"group_name": "g", "attr_orders": ["a"]})))["result"] is False
    assert _body(view(_req("post", superuser, data={"model_id": "host", "attr_orders": ["a"]})))["result"] is False
    assert _body(view(_req("post", superuser, data={"model_id": "host", "group_name": "g", "attr_orders": "x"})))["result"] is False


@pytest.mark.django_db
def test_reorder_group_attrs_ok(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.FieldGroupService.reorder_group_attrs", lambda **k: {"success": True})
    response = FieldGroupViewSet.as_view({"post": "reorder_group_attrs"})(
        _req("post", superuser, data={"model_id": "host", "group_name": "g", "attr_orders": ["a", "b"]})
    )
    assert response.status_code == status.HTTP_200_OK
