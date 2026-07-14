"""CollectModelViewSet / OidModelViewSet 视图动作单元测试。

对照 apps/cmdb/views/collect.py：
  - 静态辅助 _parse_positive_int / apply_visibility_filter
  - collect_task_names / model_instances / task_status / task_overview 聚合
  - nodes / list_regions（NodeMgmt 边界打桩）
  - model_doc 路径校验与读取
  - info 详情
  - OidModelViewSet create 的 oid 空白与重复校验

视图测试经 DRF as_view 完整 dispatch（force_authenticate + superuser 绕过 HasPermission）；
service / NodeMgmt / 权限规则在真实边界打桩，断言真实 JSON 响应与 DB 副作用。
"""
import pydantic.root_model  # noqa: F401

import json

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.constants.constants import CollectPluginTypes, CollectRunStatusType
from apps.cmdb.models.collect_model import CollectModels, OidMapping
from apps.cmdb.views.collect import CollectModelViewSet, OidModelViewSet


@pytest.fixture
def superuser(authenticated_user):
    u = authenticated_user
    u.is_superuser = True
    u.group_list = [{"id": 1}]
    u.roles = ["admin"]
    u.domain = "domain.com"
    return u


def _req(method, user, data=None, query=None, **cookies):
    factory = APIRequestFactory()
    fn = getattr(factory, method)
    path = "/x/"
    if query:
        path = "/x/?" + "&".join(f"{k}={v}" for k, v in query.items())
    request = fn(path) if data is None else fn(path, data=data, format="json")
    for k, v in cookies.items():
        request.COOKIES[k] = v
    force_authenticate(request, user=user)
    return request


def _body(response):
    if hasattr(response, "render"):
        response.render()
        return json.loads(response.rendered_content)
    return json.loads(response.content)


def _bypass_permission(monkeypatch):
    # 让 get_queryset_by_permission 与 AuthSerializer 退化为不裁剪（base_queryset）
    monkeypatch.setattr("apps.cmdb.views.collect.get_permission_rules", lambda *a, **k: {})
    monkeypatch.setattr("apps.core.utils.serializers.get_permission_rules", lambda *a, **k: {})
    monkeypatch.setattr("apps.core.utils.permission_utils.get_permission_rules", lambda *a, **k: {})


# --------------------------------------------------------------------------
# _parse_positive_int（纯静态）
# --------------------------------------------------------------------------
def test_parse_positive_int_default_on_empty():
    assert CollectModelViewSet._parse_positive_int("", "page", 1) == 1
    assert CollectModelViewSet._parse_positive_int(None, "page", 5) == 5


def test_parse_positive_int_valid():
    assert CollectModelViewSet._parse_positive_int("3", "page", 1) == 3


def test_parse_positive_int_non_integer_raises():
    with pytest.raises(ValueError, match="必须是整数"):
        CollectModelViewSet._parse_positive_int("abc", "page", 1)


def test_parse_positive_int_below_one_raises():
    with pytest.raises(ValueError, match="必须大于等于 1"):
        CollectModelViewSet._parse_positive_int("0", "page", 1)


# --------------------------------------------------------------------------
# apply_visibility_filter
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_apply_visibility_filter_excludes_hidden():
    CollectModels.objects.create(name="vis", task_type=CollectPluginTypes.HOST, model_id="host", cycle_value_type="cycle", is_visible=True, team=[1])
    CollectModels.objects.create(name="hid", task_type=CollectPluginTypes.HOST, model_id="host", driver_type="snmp", cycle_value_type="cycle", is_visible=False, team=[1])
    qs = CollectModelViewSet.apply_visibility_filter(CollectModels.objects.all())
    names = sorted(qs.values_list("name", flat=True))
    assert names == ["vis"]


# --------------------------------------------------------------------------
# model_doc
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_model_doc_empty_id(superuser):
    request = _req("get", superuser, query={"id": ""})
    resp = CollectModelViewSet.as_view({"get": "model_doc"})(request)
    body = _body(resp)
    assert body["result"] is False
    assert "不能为空" in body["message"]


@pytest.mark.django_db
def test_model_doc_illegal_id(superuser):
    request = _req("get", superuser, query={"id": "abc.def"})
    resp = CollectModelViewSet.as_view({"get": "model_doc"})(request)
    body = _body(resp)
    assert body["result"] is False
    assert "非法" in body["message"]


@pytest.mark.django_db
def test_model_doc_not_found_returns_placeholder(superuser):
    request = _req("get", superuser, query={"id": "definitely_missing_doc_xyz"})
    resp = CollectModelViewSet.as_view({"get": "model_doc"})(request)
    body = _body(resp)
    assert body["result"] is True
    assert body["data"] == "未找到对应的文档！"


# --------------------------------------------------------------------------
# nodes（NodeMgmt 打桩）
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_nodes_invalid_page(superuser):
    request = _req("get", superuser, query={"page": "abc"})
    resp = CollectModelViewSet.as_view({"get": "nodes"})(request)
    body = _body(resp)
    assert body["result"] is False


@pytest.mark.django_db
def test_nodes_success(superuser, monkeypatch):
    request = _req("get", superuser, query={"page": "1", "page_size": "10"}, current_team="1")
    captured_query = {}

    def fake_node_list(self, query_data):
        captured_query.update(query_data)
        return {"count": 1, "nodes": [{"id": "n1"}]}

    monkeypatch.setattr("apps.cmdb.views.collect.NodeMgmt.node_list", fake_node_list)
    resp = CollectModelViewSet.as_view({"get": "nodes"})(request)
    body = _body(resp)
    assert body["result"] is True
    assert body["data"]["count"] == 1
    assert captured_query["is_container"] is True
    assert "node_type" not in captured_query


# --------------------------------------------------------------------------
# list_regions
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_list_regions_unknown_cloud_id(superuser, monkeypatch):
    monkeypatch.setattr("apps.cmdb.views.collect.NodeMgmt.cloud_region_list", lambda self: [{"id": "aws", "name": "AWS"}])
    request = _req("post", superuser, data={"cloud_id": "unknown", "model_id": "aws_account"})
    resp = CollectModelViewSet.as_view({"post": "list_regions"})(request)
    body = _body(resp)
    assert body["result"] is False
    assert "cloud_id 不存在" in body["message"]


@pytest.mark.django_db
def test_list_regions_success(superuser, monkeypatch):
    monkeypatch.setattr("apps.cmdb.views.collect.NodeMgmt.cloud_region_list", lambda self: [{"id": "aws", "name": "AWS"}])
    monkeypatch.setattr(
        CollectModelViewSet, "_build_region_query_credential", lambda self, req, params, task_id=None: {"k": "v"}
    )
    monkeypatch.setattr(
        "apps.cmdb.views.collect.CollectModelService.list_regions",
        lambda credential, cloud_name: {"success": True, "result": [{"region": "cn-north"}]},
    )
    request = _req("post", superuser, data={"cloud_id": "aws", "model_id": "aws_account"})
    resp = CollectModelViewSet.as_view({"post": "list_regions"})(request)
    body = _body(resp)
    assert body["result"] is True
    assert body["data"][0]["region"] == "cn-north"


@pytest.mark.django_db
def test_list_regions_service_failure(superuser, monkeypatch):
    monkeypatch.setattr("apps.cmdb.views.collect.NodeMgmt.cloud_region_list", lambda self: [{"id": "aws", "name": "AWS"}])
    monkeypatch.setattr(
        CollectModelViewSet, "_build_region_query_credential", lambda self, req, params, task_id=None: {}
    )
    monkeypatch.setattr(
        "apps.cmdb.views.collect.CollectModelService.list_regions",
        lambda credential, cloud_name: {"success": False, "message": "鉴权失败"},
    )
    request = _req("post", superuser, data={"cloud_id": "aws", "model_id": "aws_account"})
    resp = CollectModelViewSet.as_view({"post": "list_regions"})(request)
    body = _body(resp)
    assert body["result"] is False
    assert body["message"] == "鉴权失败"


# --------------------------------------------------------------------------
# task_status / task_overview / model_instances / collect_task_names
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_task_status_aggregates_by_status(superuser, monkeypatch):
    _bypass_permission(monkeypatch)
    CollectModels.objects.create(name="t1", task_type=CollectPluginTypes.HOST, model_id="host", cycle_value_type="cycle", exec_status=CollectRunStatusType.SUCCESS, team=[1])
    CollectModels.objects.create(name="t2", task_type=CollectPluginTypes.HOST, model_id="host", driver_type="snmp", cycle_value_type="cycle", exec_status=CollectRunStatusType.ERROR, team=[1])
    request = _req("get", superuser, current_team="1")
    resp = CollectModelViewSet.as_view({"get": "task_status"})(request)
    body = _body(resp)
    assert body["result"] is True
    # driver_type 默认为 "protocol"（非空），故 key 形如 "<model_id>__<driver_type>"
    assert body["data"]["host__protocol"]["success"] == 1
    assert body["data"]["host__snmp"]["failed"] == 1


@pytest.mark.django_db
def test_task_overview_counts(superuser, monkeypatch):
    _bypass_permission(monkeypatch)
    CollectModels.objects.create(name="o1", task_type=CollectPluginTypes.HOST, model_id="host", cycle_value_type="cycle", exec_status=CollectRunStatusType.SUCCESS, team=[1])
    CollectModels.objects.create(name="o2", task_type=CollectPluginTypes.HOST, model_id="switch", driver_type="snmp", cycle_value_type="cycle", exec_status=CollectRunStatusType.ERROR, team=[1])
    request = _req("get", superuser, current_team="1")
    resp = CollectModelViewSet.as_view({"get": "task_overview"})(request)
    body = _body(resp)["data"]
    assert body["total"] == 2
    assert body["normal"] == 1
    assert body["error"] == 1
    assert body["covered_models"] == 2


@pytest.mark.django_db
def test_model_instances_filters_empty_instances(superuser, monkeypatch):
    _bypass_permission(monkeypatch)
    CollectModels.objects.create(
        name="mi1", task_type=CollectPluginTypes.HOST, model_id="host", cycle_value_type="cycle", team=[1],
        instances=[{"_id": "h1", "inst_name": "10.0.0.1"}],
    )
    CollectModels.objects.create(
        name="mi-empty", task_type=CollectPluginTypes.HOST, model_id="host", driver_type="x", cycle_value_type="cycle", team=[1],
        instances=[],
    )
    request = _req("get", superuser, query={"task_type": CollectPluginTypes.HOST}, current_team="1")
    resp = CollectModelViewSet.as_view({"get": "model_instances"})(request)
    body = _body(resp)["data"]
    assert body == [{"id": "h1", "inst_name": "10.0.0.1"}]


@pytest.mark.django_db
def test_collect_task_names_includes_plugin_meta(superuser, monkeypatch):
    _bypass_permission(monkeypatch)
    CollectModels.objects.create(name="ctn", task_type=CollectPluginTypes.HOST, model_id="host", cycle_value_type="cycle", team=[1], is_visible=True)
    monkeypatch.setattr(
        "apps.cmdb.views.collect.get_collect_obj_tree",
        lambda: [{"id": "compute", "name": "计算", "children": [{"id": "host", "name": "主机"}]}],
    )
    request = _req("get", superuser, current_team="1")
    resp = CollectModelViewSet.as_view({"get": "collect_task_names"})(request)
    body = _body(resp)["data"]
    assert len(body) == 1
    assert body[0]["plugin"] == "host"
    assert body[0]["category"] == "compute"
    assert body[0]["plugin_name"] == "主机"


@pytest.mark.django_db
def test_tree_returns_obj_tree(superuser, monkeypatch):
    monkeypatch.setattr("apps.cmdb.views.collect.get_collect_obj_tree", lambda: [{"id": "a"}])
    request = _req("get", superuser)
    resp = CollectModelViewSet.as_view({"get": "tree"})(request)
    assert _body(resp)["data"] == [{"id": "a"}]


@pytest.mark.django_db
def test_info_returns_instance_info(superuser, monkeypatch):
    _bypass_permission(monkeypatch)
    task = CollectModels.objects.create(
        name="info1", task_type=CollectPluginTypes.HOST, model_id="host", cycle_value_type="cycle", team=[1],
        format_data={"add": [{"x": 1}], "update": [], "delete": [], "association": [], "__raw_data__": []},
    )
    request = _req("get", superuser, current_team="1")
    resp = CollectModelViewSet.as_view({"get": "info"})(request, pk=task.id)
    body = _body(resp)["data"]
    assert body["add"]["count"] == 1


# --------------------------------------------------------------------------
# OidModelViewSet 校验
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_oid_create_empty_oid(superuser):
    request = _req("post", superuser, data={"oid": "   "})
    resp = OidModelViewSet.as_view({"post": "create"})(request)
    body = _body(resp)
    assert body["result"] is False
    assert "不能为空" in body["message"]


@pytest.mark.django_db
def test_oid_create_with_whitespace_rejected(superuser):
    request = _req("post", superuser, data={"oid": " 1.3.6 "})
    resp = OidModelViewSet.as_view({"post": "create"})(request)
    body = _body(resp)
    assert body["result"] is False
    assert "首尾空格" in body["message"]


@pytest.mark.django_db
def test_oid_create_duplicate(superuser):
    OidMapping.objects.create(oid="1.3.6.1", device_type="switch")
    request = _req("post", superuser, data={"oid": "1.3.6.1"})
    resp = OidModelViewSet.as_view({"post": "create"})(request)
    body = _body(resp)
    assert body["result"] is False
    assert "OID已存在" in body["message"]
