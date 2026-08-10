"""目录/仪表盘/拓扑/架构 视图、序列化器、目录服务与树构建的覆盖测试。

对照 specs/capabilities/legacy-prd-运营分析-运营分析.md：视图按组织隔离、内置对象只读、目录树聚合各类画布节点。
"""

import json

import pytest
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.operation_analysis.models.models import Architecture, Dashboard, Directory, Topology
from apps.operation_analysis.services.directory_service import DictDirectoryService
from apps.operation_analysis.services.node_tree import TreeNodeBuilder
from apps.operation_analysis.views import view as view_module
from apps.system_mgmt.models import OperationLog


def _request(method, path, user, data=None, team="1", include_children="0"):
    factory = APIRequestFactory()
    fn = getattr(factory, method)
    if data is None:
        request = fn(path)
    else:
        request = fn(path, data=data, format="json")
    if team is not None:
        request.COOKIES["current_team"] = team
    request.COOKIES["include_children"] = include_children
    force_authenticate(request, user=user)
    return request


def _superuser(authenticated_user):
    authenticated_user.is_superuser = True
    return authenticated_user


def _render(response):
    response.render()
    return json.loads(response.rendered_content)


# --------------------------------------------------------------------------
# Directory CRUD
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_directory_create_as_superuser_returns_201(authenticated_user):
    user = _superuser(authenticated_user)
    request = _request("post", "/directory/", user, data={"name": "目录A", "groups": [1], "parent": None})
    response = view_module.DirectoryModelViewSet.as_view({"post": "create"})(request)
    payload = _render(response)

    assert response.status_code == status.HTTP_201_CREATED
    assert payload["data"]["name"] == "目录A"
    assert Directory.objects.filter(name="目录A").exists()


@pytest.mark.django_db
def test_directory_create_writes_operation_log(authenticated_user):
    user = _superuser(authenticated_user)
    request = _request("post", "/directory/", user, data={"name": "目录审计", "groups": [1], "parent": None})

    response = view_module.DirectoryModelViewSet.as_view({"post": "create"})(request)
    _render(response)

    log = OperationLog.objects.get(app="ops-analysis", action_type="create")
    assert log.username == "testuser"
    assert log.summary == "新增目录: 目录审计"


@pytest.mark.django_db
def test_directory_list_returns_objects_in_team(authenticated_user, monkeypatch):
    user = _superuser(authenticated_user)
    Directory.objects.create(name="目录A", groups=[1], created_by="testuser")
    # 让权限规则放行 team 1，使普通对象出现在列表中
    monkeypatch.setattr(
        "apps.core.utils.viewset_utils.get_permission_rules",
        lambda *a, **k: {"instance": [], "team": ["1"]},
    )
    request = _request("get", "/directory/", user)
    response = view_module.DirectoryModelViewSet.as_view({"get": "list"})(request)
    payload = _render(response)

    assert response.status_code == status.HTTP_200_OK
    data = payload["data"]
    items = data["items"] if isinstance(data, dict) else data
    names = [item["name"] for item in items]
    assert "目录A" in names


@pytest.mark.django_db
def test_directory_update_builtin_is_forbidden(authenticated_user):
    user = _superuser(authenticated_user)
    builtin = Directory.objects.create(name="内置目录", groups=[1], is_build_in=True, build_in_key="k1")
    request = _request("put", f"/directory/{builtin.id}/", user, data={"name": "改名", "groups": [1]})
    response = view_module.DirectoryModelViewSet.as_view({"put": "update"})(request, pk=str(builtin.id))
    payload = _render(response)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert payload["result"] is False
    assert "内置对象不允许编辑" in payload["message"]


@pytest.mark.django_db
def test_directory_destroy_builtin_is_forbidden(authenticated_user):
    user = _superuser(authenticated_user)
    builtin = Directory.objects.create(name="内置目录2", groups=[1], is_build_in=True, build_in_key="k2")
    request = _request("delete", f"/directory/{builtin.id}/", user)
    response = view_module.DirectoryModelViewSet.as_view({"delete": "destroy"})(request, pk=str(builtin.id))
    _render(response)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert Directory.objects.filter(id=builtin.id).exists()


@pytest.mark.django_db
def test_directory_destroy_normal_succeeds(authenticated_user):
    user = _superuser(authenticated_user)
    obj = Directory.objects.create(name="可删目录", groups=[1], created_by="testuser")
    request = _request("delete", f"/directory/{obj.id}/", user)
    response = view_module.DirectoryModelViewSet.as_view({"delete": "destroy"})(request, pk=str(obj.id))
    response.render()

    # CustomRenderer 将 DELETE 的 204 改写为 200
    assert response.status_code == status.HTTP_200_OK
    assert not Directory.objects.filter(id=obj.id).exists()


@pytest.mark.django_db
def test_directory_partial_update_builtin_is_forbidden(authenticated_user):
    user = _superuser(authenticated_user)
    builtin = Directory.objects.create(name="内置目录3", groups=[1], is_build_in=True, build_in_key="k3")
    request = _request("patch", f"/directory/{builtin.id}/", user, data={"name": "x"})
    response = view_module.DirectoryModelViewSet.as_view({"patch": "partial_update"})(request, pk=str(builtin.id))
    _render(response)

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_directory_partial_update_normal_superuser(authenticated_user):
    user = _superuser(authenticated_user)
    obj = Directory.objects.create(name="原名", groups=[1], created_by="testuser")
    request = _request("patch", f"/directory/{obj.id}/", user, data={"desc": "新描述"})
    response = view_module.DirectoryModelViewSet.as_view({"patch": "partial_update"})(request, pk=str(obj.id))
    payload = _render(response)

    assert response.status_code == status.HTTP_200_OK
    assert payload["data"]["desc"] == "新描述"


# --------------------------------------------------------------------------
# Builtin retrieve (BuiltinVisibleMixin.retrieve)
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_retrieve_builtin_returns_serializer_data(authenticated_user):
    user = _superuser(authenticated_user)
    builtin = Directory.objects.create(name="内置可见", groups=[99], is_build_in=True, build_in_key="kr")
    request = _request("get", f"/directory/{builtin.id}/", user)
    response = view_module.DirectoryModelViewSet.as_view({"get": "retrieve"})(request, pk=str(builtin.id))
    payload = _render(response)

    assert response.status_code == status.HTTP_200_OK
    assert payload["data"]["name"] == "内置可见"


# --------------------------------------------------------------------------
# Dashboard / Topology / Architecture serializer create validation
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_dashboard_create_without_directory_returns_400(authenticated_user):
    user = _superuser(authenticated_user)
    request = _request("post", "/dashboard/", user, data={"name": "仪表盘1", "groups": [1]})
    response = view_module.DashboardModelViewSet.as_view({"post": "create"})(request)
    payload = _render(response)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    # _execute_with_clean_validation_error 透出 {detail, data} 或原始错误
    assert "directory" in json.dumps(payload, ensure_ascii=False)


@pytest.mark.django_db
def test_dashboard_create_with_directory_succeeds(authenticated_user):
    user = _superuser(authenticated_user)
    directory = Directory.objects.create(name="父目录", groups=[1], created_by="testuser")
    request = _request("post", "/dashboard/", user, data={"name": "仪表盘2", "groups": [1], "directory": directory.id})
    response = view_module.DashboardModelViewSet.as_view({"post": "create"})(request)
    payload = _render(response)

    assert response.status_code == status.HTTP_201_CREATED
    assert payload["data"]["name"] == "仪表盘2"


@pytest.mark.django_db
def test_topology_create_without_directory_returns_400(authenticated_user):
    user = _superuser(authenticated_user)
    request = _request("post", "/topology/", user, data={"name": "拓扑1", "groups": [1]})
    response = view_module.TopologyModelViewSet.as_view({"post": "create"})(request)
    _render(response)

    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_architecture_create_without_directory_returns_400(authenticated_user):
    user = _superuser(authenticated_user)
    request = _request("post", "/architecture/", user, data={"name": "架构1", "groups": [1]})
    response = view_module.ArchitectureModelViewSet.as_view({"post": "create"})(request)
    _render(response)

    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_dashboard_update_builtin_forbidden(authenticated_user):
    user = _superuser(authenticated_user)
    directory = Directory.objects.create(name="d", groups=[1], created_by="testuser")
    builtin = Dashboard.objects.create(name="内置盘", groups=[1], directory=directory, is_build_in=True, build_in_key="bk")
    request = _request("put", f"/dashboard/{builtin.id}/", user, data={"name": "x", "groups": [1], "directory": directory.id})
    response = view_module.DashboardModelViewSet.as_view({"put": "update"})(request, pk=str(builtin.id))
    _render(response)

    assert response.status_code == status.HTTP_403_FORBIDDEN


# --------------------------------------------------------------------------
# DirectoryChainVisibilityMixin（组织超出目录可见范围）
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_dashboard_create_org_exceeds_directory_scope_returns_400(authenticated_user):
    user = _superuser(authenticated_user)
    # 目录只在组织 1，仪表盘声明组织 2 → 冲突
    directory = Directory.objects.create(name="窄目录", groups=[1], created_by="testuser")
    request = _request("post", "/dashboard/", user, data={"name": "越界盘", "groups": [2], "directory": directory.id})
    response = view_module.DashboardModelViewSet.as_view({"post": "create"})(request)
    payload = _render(response)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "超出目录可见范围" in json.dumps(payload, ensure_ascii=False)


# --------------------------------------------------------------------------
# tree 端点 + DictDirectoryService.get_dict_trees
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_tree_endpoint_builds_nested_structure(authenticated_user):
    user = _superuser(authenticated_user)
    root = Directory.objects.create(name="根", groups=[1], created_by="testuser")
    child = Directory.objects.create(name="子", groups=[1], parent=root, created_by="testuser")
    Dashboard.objects.create(name="盘", groups=[1], directory=child, created_by="testuser")

    request = _request("get", "/directory/tree/", user)
    response = view_module.DirectoryModelViewSet.as_view({"get": "tree"})(request)
    payload = _render(response)

    assert response.status_code == status.HTTP_200_OK
    tree = payload["data"]
    assert isinstance(tree, list)
    root_node = next(n for n in tree if n["data_id"] == root.id)
    assert root_node["type"] == "directory"
    child_node = next(c for c in root_node["children"] if c["data_id"] == child.id)
    assert any(g["type"] == "dashboard" for g in child_node["children"])


@pytest.mark.django_db
@pytest.mark.parametrize("team", [None, "not-a-number"])
def test_tree_endpoint_rejects_missing_or_invalid_current_team(authenticated_user, team):
    user = _superuser(authenticated_user)
    request = _request("get", "/directory/tree/", user, team=team)

    response = view_module.DirectoryModelViewSet.as_view({"get": "tree"})(request)
    payload = _render(response)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "current_team cookie 缺失或格式错误" in payload["message"]


# --------------------------------------------------------------------------
# DictDirectoryService 模块数据
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_get_directory_modules_data_dashboard(authenticated_user):
    directory = Directory.objects.create(name="目录X", groups=[1], created_by="testuser")
    Dashboard.objects.create(name="盘1", groups=[1], directory=directory, created_by="testuser")
    result = DictDirectoryService.get_directory_modules_data("dashboard", page=1, page_size=10, group_id=1)

    assert result["count"] == 1
    assert "【目录X】盘1" == result["items"][0]["name"]


@pytest.mark.django_db
def test_get_directory_modules_data_preloads_directories(authenticated_user, django_assert_num_queries):
    first_directory = Directory.objects.create(name="目录一", groups=[1], created_by="testuser")
    second_directory = Directory.objects.create(name="目录二", groups=[1], created_by="testuser")
    Dashboard.objects.create(name="盘一", groups=[1], directory=first_directory, created_by="testuser")
    Dashboard.objects.create(name="盘二", groups=[1], directory=second_directory, created_by="testuser")

    with django_assert_num_queries(2):
        result = DictDirectoryService.get_directory_modules_data("dashboard", page=1, page_size=10, group_id=1)

    assert result["count"] == 2
    assert {item["name"] for item in result["items"]} == {"【目录一】盘一", "【目录二】盘二"}


@pytest.mark.django_db
def test_get_directory_modules_data_unknown_module_returns_empty():
    result = DictDirectoryService.get_directory_modules_data("unknown", page=1, page_size=10, group_id=1)
    assert result == {"count": 0, "items": []}


@pytest.mark.django_db
def test_get_operation_analysis_module_data_dispatch(authenticated_user):
    from apps.operation_analysis.constants.constants import PERMISSION_DIRECTORY

    Topology.objects.create(name="拓扑Z", groups=[1], created_by="testuser")
    result = DictDirectoryService.get_operation_analysis_module_data(PERMISSION_DIRECTORY, "topology", page=1, page_size=10, group_id=1)
    assert result["count"] == 1


@pytest.mark.django_db
def test_get_operation_analysis_module_data_unknown_returns_empty():
    result = DictDirectoryService.get_operation_analysis_module_data("nope", None, 1, 10, 1)
    assert result == []


# --------------------------------------------------------------------------
# TreeNodeBuilder 直接单测
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_tree_node_builder_directory_and_dashboard_nodes(authenticated_user):
    root = Directory.objects.create(name="r", groups=[1], created_by="testuser")
    child = Directory.objects.create(name="c", groups=[1], parent=root, created_by="testuser")
    dashboard = Dashboard.objects.create(name="db", groups=[1], directory=child, created_by="testuser")

    dir_nodes, parent_map = TreeNodeBuilder.get_directory_nodes(Directory.objects.all().order_by("id"))
    assert f"directory_{root.id}" in dir_nodes
    assert parent_map[None] == [f"directory_{root.id}"]
    assert parent_map[f"directory_{root.id}"] == [f"directory_{child.id}"]

    db_nodes = TreeNodeBuilder.get_dashboard_nodes(Dashboard.objects.all(), parent_map)
    assert db_nodes[f"dashboard_{dashboard.id}"]["type"] == "dashboard"
    assert f"dashboard_{dashboard.id}" in parent_map[f"directory_{child.id}"]


@pytest.mark.django_db
def test_tree_node_builder_topology_and_architecture_nodes(authenticated_user):
    directory = Directory.objects.create(name="r2", groups=[1], created_by="testuser")
    topo = Topology.objects.create(name="t", groups=[1], directory=directory, created_by="testuser")
    arch = Architecture.objects.create(name="a", groups=[1], directory=directory, created_by="testuser")

    parent_map = {}
    topo_nodes = TreeNodeBuilder.get_topology_nodes(Topology.objects.all(), parent_map)
    arch_nodes = TreeNodeBuilder.get_architecture_nodes(Architecture.objects.all(), parent_map)

    assert topo_nodes[f"topology_{topo.id}"]["type"] == "topology"
    assert arch_nodes[f"architecture_{arch.id}"]["type"] == "architecture"


def test_canvas_registry_contains_all_first_class_canvas_types():
    from apps.operation_analysis.services.canvas.registry import CANVAS_TYPE_REGISTRY

    assert set(CANVAS_TYPE_REGISTRY.keys()) == {"dashboard", "topology", "architecture", "screen", "report", "networkTopology"}
    assert CANVAS_TYPE_REGISTRY["screen"].permission_key == "directory.screen"
    assert CANVAS_TYPE_REGISTRY["report"].section_name == "reports"
    assert CANVAS_TYPE_REGISTRY["networkTopology"].model.__name__ == "NetworkTopology"
    assert CANVAS_TYPE_REGISTRY["networkTopology"].section_name == "network_topologies"


def test_all_canvas_serializers_share_canvas_object_base():
    from apps.operation_analysis.serializers.directory_serializers import (
        ArchitectureModelSerializer,
        CanvasObjectSerializer,
        DashboardModelSerializer,
        ReportModelSerializer,
        ScreenModelSerializer,
        TopologyModelSerializer,
    )

    serializers = [
        DashboardModelSerializer,
        TopologyModelSerializer,
        ArchitectureModelSerializer,
        ScreenModelSerializer,
        ReportModelSerializer,
    ]

    assert all(issubclass(serializer, CanvasObjectSerializer) for serializer in serializers)


@pytest.mark.django_db
def test_screen_and_report_create_with_directory_succeed(authenticated_user):
    from apps.operation_analysis.models.models import Report, Screen

    user = _superuser(authenticated_user)
    directory = Directory.objects.create(name="内容目录", groups=[1], created_by="testuser")

    screen_request = _request(
        "post",
        "/screen/",
        user,
        data={
            "name": "值班大屏",
            "groups": [1],
            "directory": directory.id,
            "view_sets": {
                "viewport": {"width": 1920, "height": 1080},
                "items": [],
                "decorations": {},
            },
        },
    )
    screen_response = view_module.ScreenModelViewSet.as_view({"post": "create"})(screen_request)
    screen_payload = _render(screen_response)

    report_request = _request("post", "/report/", user, data={"name": "周报", "groups": [1], "directory": directory.id})
    report_response = view_module.ReportModelViewSet.as_view({"post": "create"})(report_request)
    report_payload = _render(report_response)

    assert screen_response.status_code == status.HTTP_201_CREATED
    assert screen_payload["data"]["name"] == "值班大屏"
    assert report_response.status_code == status.HTTP_201_CREATED
    assert report_payload["data"]["name"] == "周报"
    assert Screen.objects.filter(name="值班大屏", directory=directory).exists()
    assert Report.objects.filter(name="周报", directory=directory).exists()


@pytest.mark.django_db
def test_screen_create_without_view_sets_returns_400(authenticated_user):
    user = _superuser(authenticated_user)
    directory = Directory.objects.create(name="内容目录", groups=[1], created_by="testuser")
    request = _request(
        "post",
        "/screen/",
        user,
        data={"name": "缺配置大屏", "groups": [1], "directory": directory.id},
    )
    response = view_module.ScreenModelViewSet.as_view({"post": "create"})(request)
    payload = _render(response)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "view_sets" in json.dumps(payload, ensure_ascii=False)


@pytest.mark.django_db
def test_screen_create_without_directory_returns_400(authenticated_user):
    user = _superuser(authenticated_user)
    request = _request(
        "post",
        "/screen/",
        user,
        data={
            "name": "无目录大屏",
            "groups": [1],
            "view_sets": {
                "viewport": {"width": 1920, "height": 1080},
                "items": [],
                "decorations": {},
            },
        },
    )
    response = view_module.ScreenModelViewSet.as_view({"post": "create"})(request)
    payload = _render(response)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "directory" in json.dumps(payload, ensure_ascii=False)


@pytest.mark.django_db
def test_report_update_builtin_forbidden(authenticated_user):
    from apps.operation_analysis.models.models import Report

    user = _superuser(authenticated_user)
    directory = Directory.objects.create(name="报表目录", groups=[1], created_by="testuser")
    report = Report.objects.create(name="内置报表", groups=[1], directory=directory, is_build_in=True, build_in_key="builtin-report")
    request = _request("put", f"/report/{report.id}/", user, data={"name": "改名", "groups": [1], "directory": directory.id})
    response = view_module.ReportModelViewSet.as_view({"put": "update"})(request, pk=str(report.id))
    _render(response)

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_tree_endpoint_includes_screen_and_report(authenticated_user):
    from apps.operation_analysis.models.models import Report, Screen

    user = _superuser(authenticated_user)
    directory = Directory.objects.create(name="目录", groups=[1], created_by="testuser")
    Screen.objects.create(name="大屏A", groups=[1], directory=directory, created_by="testuser")
    Report.objects.create(name="报表A", groups=[1], directory=directory, created_by="testuser")

    request = _request("get", "/directory/tree/", user)
    response = view_module.DirectoryModelViewSet.as_view({"get": "tree"})(request)
    payload = _render(response)

    root = next(item for item in payload["data"] if item["data_id"] == directory.id)
    child_types = {child["type"] for child in root["children"]}
    assert {"screen", "report"}.issubset(child_types)


@pytest.mark.django_db
def test_get_directory_modules_data_screen_and_report(authenticated_user):
    from apps.operation_analysis.models.models import Report, Screen

    directory = Directory.objects.create(name="目录Y", groups=[1], created_by="testuser")
    Screen.objects.create(name="屏1", groups=[1], directory=directory, created_by="testuser")
    Report.objects.create(name="表1", groups=[1], directory=directory, created_by="testuser")

    screen_result = DictDirectoryService.get_directory_modules_data("screen", page=1, page_size=10, group_id=1)
    report_result = DictDirectoryService.get_directory_modules_data("report", page=1, page_size=10, group_id=1)

    assert screen_result["items"][0]["name"] == "【目录Y】屏1"
    assert report_result["items"][0]["name"] == "【目录Y】表1"


# --------------------------------------------------------------------------
# 视图层 helper 函数
# --------------------------------------------------------------------------


def test_raise_if_builtin_raises_for_builtin():
    from types import SimpleNamespace

    with pytest.raises(PermissionDenied):
        view_module._raise_if_builtin(SimpleNamespace(is_build_in=True), "删除")


def test_raise_if_builtin_noop_for_normal():
    from types import SimpleNamespace

    # 不抛异常即通过
    view_module._raise_if_builtin(SimpleNamespace(is_build_in=False))


def test_build_validation_error_response_with_structured_detail():
    error = ValidationError({"detail": ["失败原因"], "data": {"conflicts": []}})
    response = view_module._build_validation_error_response(error)
    assert response.status_code == 400
    assert response.data["detail"] == "失败原因"
    assert response.data["data"] == {"conflicts": []}


def test_build_validation_error_response_reraises_plain_error():
    error = ValidationError("普通错误")
    with pytest.raises(ValidationError):
        view_module._build_validation_error_response(error)


def test_execute_with_clean_validation_error_passes_through_success():
    assert view_module._execute_with_clean_validation_error(lambda: "ok") == "ok"


def test_execute_with_clean_validation_error_converts_structured_error():
    def handler():
        raise ValidationError({"detail": "x", "data": {}})

    response = view_module._execute_with_clean_validation_error(handler)
    assert response.status_code == 400
