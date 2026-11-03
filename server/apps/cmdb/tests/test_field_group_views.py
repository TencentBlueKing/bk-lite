"""CMDB 字段分组视图覆盖测试（patch FieldGroupService/ModelManage + 真实 FieldGroup DB）。

对照 specs/capabilities/legacy-prd-cmdb-模型管理.md：字段分组的增删改查、移动排序、批量调整归组、模型完整信息。
写操作必须同时具备目标模型的组织交集和 OPERATE；默认组织的公开 VIEW 不能当成写权限。
"""

import json

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.models.field_group import FieldGroup
from apps.cmdb.views.field_group import FieldGroupViewSet

VIEWS = "apps.cmdb.views.field_group"
MIXINS = "apps.cmdb.views.mixins"
MODEL_DENY = "抱歉！您没有此模型的权限"
VIEW_DENY = "抱歉！您没有此模型的查询权限"
MODEL_MISSING = "模型不存在"
FUNCTION_PERMS = {
    "model_management-View",
    "model_management-Edit Model",
    "model_management-Delete Model",
}


@pytest.fixture
def superuser(authenticated_user):
    u = authenticated_user
    u.is_superuser = True
    u.group_list = [{"id": 1}]
    u.group_tree = []
    u.locale = "zh-Hans"
    u.permission = set(FUNCTION_PERMS)
    return u


@pytest.fixture
def group(db):
    return FieldGroup.objects.create(model_id="host", group_name="基本信息", order=1, created_by="admin")


def _editor(user, org_ids=(1,), *, superuser=False):
    user.is_superuser = superuser
    user.group_list = [{"id": org_id} for org_id in org_ids]
    user.group_tree = []
    user.locale = "zh-Hans"
    user.permission = set(FUNCTION_PERMS)
    return user


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


def _model(model_id="host", groups=(1,)):
    return {"model_id": model_id, "group": list(groups)}


def _stub_models(monkeypatch, *models):
    by_id = {item["model_id"]: item for item in models}

    def _search(model_id):
        return by_id.get(model_id) or {}

    monkeypatch.setattr(f"{VIEWS}.ModelManage.search_model_info", _search)


def _stub_permission_map(monkeypatch, mapping):
    monkeypatch.setattr(
        f"{MIXINS}.CmdbRulesFormatUtil.format_user_groups_permissions",
        lambda *args, **kwargs: mapping,
    )


def _stub_default_group(monkeypatch, group_id):
    monkeypatch.setattr(f"{VIEWS}.get_default_group_id", lambda: [group_id])


def _grant_operate(monkeypatch, model_id="host", org_id=1):
    """组织交集成立，且该组织对模型是全量权限（含 OPERATE）。"""
    _stub_models(monkeypatch, _model(model_id, (org_id,)))
    _stub_permission_map(monkeypatch, {org_id: {"permission_instances_map": {}}})
    _stub_default_group(monkeypatch, 99)


def _view_only(monkeypatch, model_id="host", org_id=1):
    """组织交集成立，但对象权限只有 VIEW，没有 OPERATE。"""
    _stub_models(monkeypatch, _model(model_id, (org_id,)))
    _stub_permission_map(
        monkeypatch,
        {org_id: {"permission_instances_map": {model_id: ["View"]}}},
    )
    _stub_default_group(monkeypatch, 99)


def _service_spy(monkeypatch, method_name, result=None):
    calls = []

    def _fake(**kwargs):
        calls.append(kwargs)
        return result

    monkeypatch.setattr(f"{VIEWS}.FieldGroupService.{method_name}", _fake)
    return calls


def _snapshot(instance):
    instance.refresh_from_db()
    return {
        "model_id": instance.model_id,
        "group_name": instance.group_name,
        "order": instance.order,
        "description": instance.description,
        "is_collapsed": instance.is_collapsed,
        "attr_orders": instance.attr_orders,
        "created_by": instance.created_by,
    }


def _assert_denied(response, message):
    assert response.status_code == status.HTTP_403_FORBIDDEN
    body = _body(response)
    assert body["result"] is False
    assert message in body["message"]


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
    _grant_operate(monkeypatch)
    monkeypatch.setattr(f"{VIEWS}.FieldGroupService.create_group", lambda **k: group)
    response = FieldGroupViewSet.as_view({"post": "create"})(
        _req("post", superuser, data={"model_id": "host", "group_name": "基本信息"})
    )
    assert response.status_code == status.HTTP_200_OK
    assert _body(response)["data"]["group_name"] == "基本信息"


@pytest.mark.django_db
def test_create_denied_when_model_org_disjoint(authenticated_user, monkeypatch):
    editor = _editor(authenticated_user, (1,))
    _stub_models(monkeypatch, _model("host", (2,)))
    _stub_default_group(monkeypatch, 99)
    calls = _service_spy(monkeypatch, "create_group", result=None)
    before = FieldGroup.objects.count()

    response = FieldGroupViewSet.as_view({"post": "create"})(
        _req("post", editor, data={"model_id": "host", "group_name": "未授权分组"})
    )

    _assert_denied(response, MODEL_DENY)
    assert calls == []
    assert FieldGroup.objects.count() == before
    assert not FieldGroup.objects.filter(group_name="未授权分组").exists()


@pytest.mark.django_db
def test_create_denied_for_superuser_without_model_operate(superuser, monkeypatch):
    superuser.group_list = [{"id": 1}]
    _stub_models(monkeypatch, _model("host", (2,)))
    _stub_default_group(monkeypatch, 99)
    calls = _service_spy(monkeypatch, "create_group")

    response = FieldGroupViewSet.as_view({"post": "create"})(
        _req("post", superuser, data={"model_id": "host", "group_name": "未授权分组"})
    )

    _assert_denied(response, MODEL_DENY)
    assert calls == []


@pytest.mark.django_db
def test_create_denied_when_same_org_lacks_operate(authenticated_user, monkeypatch):
    editor = _editor(authenticated_user, (1,))
    _view_only(monkeypatch)
    calls = _service_spy(monkeypatch, "create_group")
    before = FieldGroup.objects.count()

    response = FieldGroupViewSet.as_view({"post": "create"})(
        _req("post", editor, data={"model_id": "host", "group_name": "未授权分组"})
    )

    _assert_denied(response, MODEL_DENY)
    assert calls == []
    assert FieldGroup.objects.count() == before


@pytest.mark.django_db
def test_create_model_not_found_does_not_call_service(authenticated_user, monkeypatch):
    editor = _editor(authenticated_user, (1,))
    _stub_models(monkeypatch)
    calls = _service_spy(monkeypatch, "create_group")

    response = FieldGroupViewSet.as_view({"post": "create"})(
        _req("post", editor, data={"model_id": "missing", "group_name": "未授权分组"})
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert _body(response)["message"] == MODEL_MISSING
    assert calls == []
    assert not FieldGroup.objects.filter(group_name="未授权分组").exists()


@pytest.mark.django_db
def test_create_calls_service_when_org_and_operate(authenticated_user, monkeypatch, group):
    editor = _editor(authenticated_user, (1,))
    _grant_operate(monkeypatch)
    calls = _service_spy(monkeypatch, "create_group", result=group)

    response = FieldGroupViewSet.as_view({"post": "create"})(
        _req("post", editor, data={"model_id": "host", "group_name": "基本信息", "description": "说明"})
    )

    assert response.status_code == status.HTTP_200_OK
    assert len(calls) == 1
    assert calls[0]["model_id"] == "host"
    assert calls[0]["group_name"] == "基本信息"
    assert _body(response)["data"]["group_name"] == "基本信息"


# --------------------------------------------------------------------------
# retrieve / update / destroy / move（真实 DB get_object）
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_retrieve(superuser, monkeypatch, group):
    _grant_operate(monkeypatch)
    response = FieldGroupViewSet.as_view({"get": "retrieve"})(_req("get", superuser), pk=group.id)
    assert _body(response)["data"]["group_name"] == "基本信息"


@pytest.mark.django_db
def test_retrieve_denied_without_model_view(authenticated_user, monkeypatch, group):
    editor = _editor(authenticated_user, (1,))
    _stub_models(monkeypatch, _model("host", (2,)))
    _stub_default_group(monkeypatch, 99)

    response = FieldGroupViewSet.as_view({"get": "retrieve"})(_req("get", editor), pk=group.id)

    _assert_denied(response, VIEW_DENY)


@pytest.mark.django_db
def test_update_ok(superuser, monkeypatch, group):
    _grant_operate(monkeypatch)
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
    _grant_operate(monkeypatch)
    monkeypatch.setattr(f"{VIEWS}.FieldGroupService.delete_group", lambda **k: {"success": True})
    response = FieldGroupViewSet.as_view({"delete": "destroy"})(_req("delete", superuser), pk=group.id)
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_move_ok(superuser, monkeypatch, group):
    _grant_operate(monkeypatch)
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


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("method", "action", "payload", "service_method"),
    [
        ("put", "update", {"group_name": "被拒绝的新名"}, "update_group"),
        ("patch", "partial_update", {"group_name": "被拒绝的新名"}, "update_group"),
        ("delete", "destroy", None, "delete_group"),
        ("post", "move", {"direction": "up"}, "move_group"),
    ],
)
def test_existing_group_writes_denied_for_other_org(
    authenticated_user, monkeypatch, group, method, action, payload, service_method
):
    editor = _editor(authenticated_user, (1,))
    _stub_models(monkeypatch, _model("host", (2,)))
    _stub_default_group(monkeypatch, 99)
    calls = _service_spy(monkeypatch, service_method, result={"success": True})
    before = _snapshot(group)
    before_count = FieldGroup.objects.count()

    response = FieldGroupViewSet.as_view({method: action})(
        _req(method, editor, data=payload), pk=group.id
    )

    _assert_denied(response, MODEL_DENY)
    assert calls == []
    assert FieldGroup.objects.count() == before_count
    assert _snapshot(group) == before


@pytest.mark.django_db
def test_update_missing_model_does_not_call_service(authenticated_user, monkeypatch, group):
    editor = _editor(authenticated_user, (1,))
    _stub_models(monkeypatch)
    calls = _service_spy(monkeypatch, "update_group")
    before = _snapshot(group)

    response = FieldGroupViewSet.as_view({"put": "update"})(
        _req("put", editor, data={"group_name": "新名"}), pk=group.id
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert _body(response)["message"] == MODEL_MISSING
    assert calls == []
    assert _snapshot(group) == before


# --------------------------------------------------------------------------
# full_info / list
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
    _grant_operate(monkeypatch)
    monkeypatch.setattr(
        f"{VIEWS}.FieldGroupService.get_model_with_groups", lambda **k: {"model_id": "host", "groups": []}
    )
    response = FieldGroupViewSet.as_view({"get": "full_info"})(_req("get", superuser, query="model_id=host"))
    assert response.status_code == status.HTTP_200_OK
    assert _body(response)["data"]["model_id"] == "host"


@pytest.mark.django_db
def test_default_group_view_does_not_grant_operate(authenticated_user, monkeypatch, group):
    editor = _editor(authenticated_user, (1,))
    _stub_models(monkeypatch, _model("host", (99,)))
    _stub_default_group(monkeypatch, 99)
    _stub_permission_map(monkeypatch, {1: {"permission_instances_map": {"host": ["View"]}}})
    monkeypatch.setattr(
        f"{VIEWS}.FieldGroupService.get_model_with_groups", lambda **k: {"model_id": "host", "groups": []}
    )
    create_calls = _service_spy(monkeypatch, "create_group")

    listed = FieldGroupViewSet.as_view({"get": "list"})(_req("get", editor, query="model_id=host"))
    info = FieldGroupViewSet.as_view({"get": "full_info"})(_req("get", editor, query="model_id=host"))
    created = FieldGroupViewSet.as_view({"post": "create"})(
        _req("post", editor, data={"model_id": "host", "group_name": "未授权分组"})
    )

    assert listed.status_code == status.HTTP_200_OK
    listed_body = _body(listed)
    assert listed_body["result"] is True
    listed_names = [item["group_name"] for item in listed_body["data"]]
    assert listed_names == ["基本信息"]
    assert info.status_code == status.HTTP_200_OK
    assert _body(info)["data"]["model_id"] == "host"
    _assert_denied(created, MODEL_DENY)
    assert create_calls == []
    assert not FieldGroup.objects.filter(group_name="未授权分组").exists()


@pytest.mark.django_db
def test_list_without_model_id_hides_other_org_groups(authenticated_user, monkeypatch, db):
    editor = _editor(authenticated_user, (1,))
    FieldGroup.objects.create(model_id="foreign", group_name="其他组织", order=1, created_by="admin")
    FieldGroup.objects.create(model_id="shared", group_name="默认组织", order=1, created_by="admin")
    _stub_models(monkeypatch, _model("foreign", (2,)), _model("shared", (99,)))
    _stub_default_group(monkeypatch, 99)
    _stub_permission_map(monkeypatch, {1: {"permission_instances_map": {}}})

    response = FieldGroupViewSet.as_view({"get": "list"})(_req("get", editor))

    assert response.status_code == status.HTTP_200_OK
    body = _body(response)
    assert body["result"] is True
    names = sorted(item["group_name"] for item in body["data"])
    assert names == ["默认组织"]


# --------------------------------------------------------------------------
# batch_update_attrs / update_attr_group / reorder_group_attrs
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_batch_update_attrs_ok(superuser, monkeypatch):
    _grant_operate(monkeypatch)
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
    _grant_operate(monkeypatch)
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
    _grant_operate(monkeypatch)
    monkeypatch.setattr(f"{VIEWS}.FieldGroupService.reorder_group_attrs", lambda **k: {"success": True})
    response = FieldGroupViewSet.as_view({"post": "reorder_group_attrs"})(
        _req("post", superuser, data={"model_id": "host", "group_name": "g", "attr_orders": ["a", "b"]})
    )
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("method", "action", "payload", "service_method"),
    [
        (
            "put",
            "batch_update_attrs",
            {"model_id": "host", "updates": [{"attr_id": "ip", "group_name": "网络"}]},
            "batch_update_attrs_group",
        ),
        (
            "post",
            "update_attr_group",
            {"model_id": "host", "attr_id": "a", "group_name": "g"},
            "update_attr_group",
        ),
        (
            "post",
            "reorder_group_attrs",
            {"model_id": "host", "group_name": "g", "attr_orders": ["a", "b"]},
            "reorder_group_attrs",
        ),
    ],
)
def test_attr_group_writes_denied_without_operate(
    authenticated_user, monkeypatch, method, action, payload, service_method
):
    editor = _editor(authenticated_user, (1,))
    _view_only(monkeypatch)
    calls = _service_spy(monkeypatch, service_method, result={"success": True})

    response = FieldGroupViewSet.as_view({method: action})(_req(method, editor, data=payload))

    _assert_denied(response, MODEL_DENY)
    assert calls == []


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("method", "action", "payload", "service_method"),
    [
        (
            "put",
            "batch_update_attrs",
            {"model_id": "missing", "updates": [{"attr_id": "ip", "group_name": "网络"}]},
            "batch_update_attrs_group",
        ),
        (
            "post",
            "update_attr_group",
            {"model_id": "missing", "attr_id": "a", "group_name": "g"},
            "update_attr_group",
        ),
        (
            "post",
            "reorder_group_attrs",
            {"model_id": "missing", "group_name": "g", "attr_orders": ["a", "b"]},
            "reorder_group_attrs",
        ),
    ],
)
def test_attr_group_writes_missing_model(
    authenticated_user, monkeypatch, method, action, payload, service_method
):
    editor = _editor(authenticated_user, (1,))
    _stub_models(monkeypatch)
    calls = _service_spy(monkeypatch, service_method)

    response = FieldGroupViewSet.as_view({method: action})(_req(method, editor, data=payload))

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert _body(response)["message"] == MODEL_MISSING
    assert calls == []
