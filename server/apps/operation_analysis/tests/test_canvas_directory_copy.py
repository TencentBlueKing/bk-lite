"""画布跨目录复制 API。"""

import json

import pytest
from django.utils import translation
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.operation_analysis.models.models import Architecture, Dashboard, Directory, NetworkTopology, Report, Screen, Topology
from apps.operation_analysis.models.share_models import DashboardShareLink
from apps.operation_analysis.serializers.network_topology_serializers import decrypt_token
from apps.operation_analysis.views import view as view_module
from apps.operation_analysis.views.network_topology_view import NetworkTopologyViewSet

VALID_SCREEN_VIEW_SETS = {
    "viewport": {"width": 1920, "height": 1080},
    "items": [{"i": "w1", "valueConfig": {"dataSource": 7}}],
    "decorations": {},
}

COPY_CASES = [
    (
        Dashboard,
        view_module.DashboardModelViewSet,
        "/dashboard/",
        {"filters": [{"id": "env"}], "other": {"theme": "dark"}, "view_sets": [{"i": "w1"}], "refresh_interval": 60000},
    ),
    (
        Topology,
        view_module.TopologyModelViewSet,
        "/topology/",
        {"other": {"layout": "force"}, "view_sets": {"nodes": [{"id": "n1"}], "edges": [], "filters": []}, "refresh_interval": 0},
    ),
    (
        Architecture,
        view_module.ArchitectureModelViewSet,
        "/architecture/",
        {"other": {"zoom": 1}, "view_sets": {"items": [{"id": "a1"}], "views": []}},
    ),
    (
        Screen,
        view_module.ScreenModelViewSet,
        "/screen/",
        {"other": {}, "view_sets": VALID_SCREEN_VIEW_SETS, "refresh_interval": 60000},
    ),
    (
        Report,
        view_module.ReportModelViewSet,
        "/report/",
        {"other": {}, "view_sets": {"schema_version": 1, "filters": [], "sections": []}, "refresh_interval": 0},
    ),
]


def _request(method, path, user, data=None, team="1"):
    factory = APIRequestFactory()
    fn = getattr(factory, method)
    request = fn(path, data=data, format="json") if data is not None else fn(path)
    if team is not None:
        request.COOKIES["current_team"] = team
    request.COOKIES["include_children"] = "0"
    force_authenticate(request, user=user)
    return request


def _superuser(authenticated_user):
    authenticated_user.is_superuser = True
    return authenticated_user


def _render(response):
    if hasattr(response, "render") and not getattr(response, "rendered", False):
        response.render()
    content = response.content if hasattr(response, "content") else b"{}"
    return json.loads(content)


def _copy(viewset_cls, user, object_id, data, path_prefix, language="en"):
    request = _request("post", f"{path_prefix}{object_id}/copy/", user, data=data)
    with translation.override(language):
        response = viewset_cls.as_view({"post": "copy"})(request, pk=str(object_id))
    return response, _render(response)


def _copy_dashboard(user, dashboard_id, data, language="en"):
    return _copy(
        view_module.DashboardModelViewSet,
        user,
        dashboard_id,
        data,
        "/dashboard/",
        language=language,
    )


@pytest.mark.django_db
def test_copy_dashboard_to_another_directory_keeps_original(authenticated_user):
    user = _superuser(authenticated_user)
    source_dir = Directory.objects.create(name="源目录", groups=[1], created_by="owner")
    target_dir = Directory.objects.create(name="目标目录", groups=[1], created_by="owner")
    source = Dashboard.objects.create(
        name="运营盘",
        desc="源描述",
        groups=[1],
        directory=source_dir,
        created_by="owner",
        filters=[{"id": "env"}],
        other={"theme": "dark"},
        view_sets=[{"i": "w1", "valueConfig": {"dataSource": 42}}],
        refresh_interval=60000,
    )

    response, payload = _copy_dashboard(user, source.id, {"directory": target_dir.id, "groups": [1]})

    assert response.status_code == status.HTTP_201_CREATED
    copied = Dashboard.objects.get(id=payload["data"]["id"])
    source.refresh_from_db()
    assert source.directory_id == source_dir.id
    assert source.name == "运营盘"
    assert copied.directory_id == target_dir.id
    assert copied.name == "运营盘-copy"
    assert copied.id != source.id
    assert copied.desc == "源描述"
    assert copied.filters == [{"id": "env"}]
    assert copied.other == {"theme": "dark"}
    assert copied.view_sets == [{"i": "w1", "valueConfig": {"dataSource": 42}}]
    assert copied.refresh_interval == 60000
    assert copied.created_by == "testuser"
    assert copied.is_build_in is False
    assert copied.build_in_key is None


@pytest.mark.django_db
def test_copy_dashboard_uses_chinese_suffix_for_zh_locale(authenticated_user):
    user = _superuser(authenticated_user)
    source_dir = Directory.objects.create(name="中文源目录", groups=[1], created_by="owner")
    source = Dashboard.objects.create(name="中文盘", groups=[1], directory=source_dir, created_by="owner")

    response, payload = _copy_dashboard(
        user,
        source.id,
        {"directory": source_dir.id, "groups": [1]},
        language="zh-Hans",
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert payload["data"]["name"] == "中文盘-副本"


@pytest.mark.django_db
def test_copy_dashboard_increments_suffix_on_name_conflict(authenticated_user):
    user = _superuser(authenticated_user)
    source_dir = Directory.objects.create(name="冲突目录", groups=[1], created_by="owner")
    source = Dashboard.objects.create(name="冲突盘", groups=[1], directory=source_dir, created_by="owner")
    Dashboard.objects.create(name="冲突盘-copy", groups=[1], directory=source_dir, created_by="owner")

    response, payload = _copy_dashboard(user, source.id, {"directory": source_dir.id, "groups": [1]})

    assert response.status_code == status.HTTP_201_CREATED
    assert payload["data"]["name"] == "冲突盘-copy2"


@pytest.mark.django_db
def test_copy_dashboard_mutating_copy_does_not_change_original(authenticated_user):
    user = _superuser(authenticated_user)
    source_dir = Directory.objects.create(name="独立目录", groups=[1], created_by="owner")
    source = Dashboard.objects.create(
        name="独立盘",
        groups=[1],
        directory=source_dir,
        created_by="owner",
        view_sets=[{"i": "w1", "valueConfig": {"title": "源"}}],
    )

    _, payload = _copy_dashboard(user, source.id, {"directory": source_dir.id, "groups": [1]})
    copied = Dashboard.objects.get(id=payload["data"]["id"])
    copied.view_sets = [{"i": "w1", "valueConfig": {"title": "副本"}}]
    copied.save(update_fields=["view_sets"])
    source.refresh_from_db()

    assert source.view_sets == [{"i": "w1", "valueConfig": {"title": "源"}}]


@pytest.mark.django_db
def test_copy_builtin_dashboard_clears_builtin_identity(authenticated_user):
    user = _superuser(authenticated_user)
    source_dir = Directory.objects.create(name="内置画布目录", groups=[1], created_by="system")
    target_dir = Directory.objects.create(name="用户目录", groups=[1], created_by="owner")
    source = Dashboard.objects.create(
        name="内置运营盘",
        groups=[1],
        directory=source_dir,
        is_build_in=True,
        build_in_key="builtin-ops-board",
    )

    response, payload = _copy_dashboard(user, source.id, {"directory": target_dir.id, "groups": [1]})

    assert response.status_code == status.HTTP_201_CREATED
    copied = Dashboard.objects.get(id=payload["data"]["id"])
    source.refresh_from_db()
    assert source.is_build_in is True
    assert source.build_in_key == "builtin-ops-board"
    assert copied.is_build_in is False
    assert copied.build_in_key is None


@pytest.mark.django_db
def test_copy_dashboard_rejects_builtin_target_directory(authenticated_user):
    user = _superuser(authenticated_user)
    source_dir = Directory.objects.create(name="普通源", groups=[1], created_by="owner")
    builtin_dir = Directory.objects.create(
        name="内置目录",
        groups=[1],
        is_build_in=True,
        build_in_key="__builtin__",
    )
    source = Dashboard.objects.create(name="待复制盘", groups=[1], directory=source_dir, created_by="owner")

    response, payload = _copy_dashboard(user, source.id, {"directory": builtin_dir.id, "groups": [1]})

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "不能复制到内置目录" in json.dumps(payload, ensure_ascii=False)
    assert Dashboard.objects.filter(directory=builtin_dir).count() == 0


@pytest.mark.django_db
def test_copy_dashboard_rejects_groups_outside_directory_chain(authenticated_user):
    user = _superuser(authenticated_user)
    source_dir = Directory.objects.create(name="窄源", groups=[1], created_by="owner")
    target_dir = Directory.objects.create(name="窄目标", groups=[1], created_by="owner")
    source = Dashboard.objects.create(name="越界复制盘", groups=[1], directory=source_dir, created_by="owner")

    response, payload = _copy_dashboard(user, source.id, {"directory": target_dir.id, "groups": [2]})

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "超出目录可见范围" in json.dumps(payload, ensure_ascii=False)


@pytest.mark.django_db
def test_copy_dashboard_requires_add_chart_permission(authenticated_user):
    authenticated_user.is_superuser = False
    authenticated_user.permission = {"ops-analysis": {"view-View"}}
    source_dir = Directory.objects.create(name="权限源", groups=[1], created_by="owner")
    source = Dashboard.objects.create(name="无新建权盘", groups=[1], directory=source_dir, created_by="owner")

    response, payload = _copy_dashboard(
        authenticated_user,
        source.id,
        {"directory": source_dir.id, "groups": [1]},
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert Dashboard.objects.exclude(id=source.id).filter(name__startswith="无新建权盘").count() == 0


@pytest.mark.django_db
def test_copy_dashboard_rejects_invisible_source(authenticated_user):
    authenticated_user.is_superuser = False
    authenticated_user.permission = {"ops-analysis": {"view-View", "view-AddChart"}}
    source_dir = Directory.objects.create(name="他组织目录", groups=[99], created_by="owner")
    target_dir = Directory.objects.create(name="本组织目录", groups=[1], created_by="owner")
    source = Dashboard.objects.create(name="他组织盘", groups=[99], directory=source_dir, created_by="owner")

    response, payload = _copy_dashboard(
        authenticated_user,
        source.id,
        {"directory": target_dir.id, "groups": [1]},
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "源画布不可见" in json.dumps(payload, ensure_ascii=False)


@pytest.mark.django_db
def test_copy_dashboard_rejects_invisible_target_directory(authenticated_user):
    authenticated_user.is_superuser = False
    authenticated_user.permission = {"ops-analysis": {"view-View", "view-AddChart"}}
    source_dir = Directory.objects.create(name="可见源目录", groups=[1], created_by="owner")
    target_dir = Directory.objects.create(name="不可见目标", groups=[99], created_by="owner")
    source = Dashboard.objects.create(name="可见源盘", groups=[1], directory=source_dir, created_by="owner")

    response, payload = _copy_dashboard(
        authenticated_user,
        source.id,
        {"directory": target_dir.id, "groups": [1]},
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "目标目录不可见" in json.dumps(payload, ensure_ascii=False)


@pytest.mark.django_db
def test_copy_dashboard_rejects_forged_current_team_cookie(authenticated_user):
    """只属于组织 1 时，伪造 current_team=99 不得复制仅属于 99 的画布（即便目标目录同时挂了 1 与 99）。"""
    authenticated_user.is_superuser = False
    authenticated_user.group_list = [{"id": 1, "name": "org1"}]
    authenticated_user.permission = {"ops-analysis": {"view-View", "view-AddChart"}}
    source_dir = Directory.objects.create(name="伪造源目录", groups=[99], created_by="other")
    target_dir = Directory.objects.create(name="跨组织目录", groups=[1, 99], created_by="other")
    source = Dashboard.objects.create(
        name="伪造源盘",
        groups=[99],
        directory=source_dir,
        created_by="other",
        view_sets=[{"i": "secret"}],
        filters=[],
        other={},
    )

    forged = _request(
        "post",
        f"/dashboard/{source.id}/copy/",
        authenticated_user,
        data={"directory": target_dir.id, "groups": [1]},
        team="99",
    )
    with translation.override("en"):
        response = view_module.DashboardModelViewSet.as_view({"post": "copy"})(forged, pk=str(source.id))
    payload = _render(response)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert Dashboard.objects.filter(name__startswith="伪造源盘").count() == 1
    assert Dashboard.objects.exclude(id=source.id).filter(name__startswith="伪造源盘").count() == 0
    assert payload.get("result") is False


@pytest.mark.django_db
def test_copy_network_topology_rejects_forged_current_team_cookie(authenticated_user):
    authenticated_user.is_superuser = False
    authenticated_user.group_list = [{"id": 1, "name": "org1"}]
    authenticated_user.permission = {"ops-analysis": {"view-View", "view-AddChart"}}
    source_dir = Directory.objects.create(name="NT伪造源目录", groups=[99], created_by="other")
    target_dir = Directory.objects.create(name="NT跨组织目录", groups=[1, 99], created_by="other")
    source = NetworkTopology.objects.create(
        name="NT伪造源",
        groups=[99],
        directory=source_dir,
        created_by="other",
        base_url="https://example.com",
        token="",
        view_sets={},
    )

    forged = _request(
        "post",
        f"/network_topology/{source.id}/copy/",
        authenticated_user,
        data={"directory": target_dir.id, "groups": [1]},
        team="99",
    )
    with translation.override("en"):
        response = NetworkTopologyViewSet.as_view({"post": "copy"})(forged, pk=str(source.id))
    payload = _render(response)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert NetworkTopology.objects.exclude(id=source.id).filter(name__startswith="NT伪造源").count() == 0
    assert payload.get("result") is False


@pytest.mark.django_db
def test_copy_dashboard_does_not_clone_share_links(authenticated_user):
    user = _superuser(authenticated_user)
    source_dir = Directory.objects.create(name="分享源目录", groups=[1], created_by="owner")
    source = Dashboard.objects.create(name="分享盘", groups=[1], directory=source_dir, created_by="owner")
    DashboardShareLink.objects.create(
        resource_type=DashboardShareLink.ResourceType.DASHBOARD,
        dashboard=source,
        dashboard_instance_id=source.id,
        tenant_domain="domain.com",
        space_id=1,
        sharer_username="owner",
        sharer_domain="domain.com",
    )

    _, payload = _copy_dashboard(user, source.id, {"directory": source_dir.id, "groups": [1]})

    assert DashboardShareLink.objects.filter(dashboard_instance_id=source.id).count() == 1
    assert DashboardShareLink.objects.filter(dashboard_instance_id=payload["data"]["id"]).count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize("model, viewset_cls, path_prefix, extra", COPY_CASES)
def test_copy_supported_canvas_types_to_target_directory(authenticated_user, model, viewset_cls, path_prefix, extra):
    user = _superuser(authenticated_user)
    source_dir = Directory.objects.create(name=f"{model.__name__}-源", groups=[1], created_by="owner")
    target_dir = Directory.objects.create(name=f"{model.__name__}-目标", groups=[1], created_by="owner")
    source = model.objects.create(
        name=f"{model.__name__}-画布",
        groups=[1],
        directory=source_dir,
        created_by="owner",
        **extra,
    )

    response, payload = _copy(viewset_cls, user, source.id, {"directory": target_dir.id, "groups": [1]}, path_prefix)

    assert response.status_code == status.HTTP_201_CREATED
    copied = model.objects.get(id=payload["data"]["id"])
    assert copied.directory_id == target_dir.id
    assert copied.name == f"{model.__name__}-画布-copy"
    assert model.objects.filter(id=source.id, directory=source_dir).exists()


@pytest.mark.django_db
def test_copy_network_topology_copies_token_without_exposing_it(authenticated_user):
    user = _superuser(authenticated_user)
    source_dir = Directory.objects.create(name="网络源", groups=[1], created_by="owner")
    target_dir = Directory.objects.create(name="网络目标", groups=[1], created_by="owner")
    source = NetworkTopology.objects.create(
        name="核心网",
        directory=source_dir,
        groups=[1],
        created_by="owner",
        base_url="https://weops.example.com",
        token="service-token-value",
        view_sets={"nodes": [], "links": []},
        last_runtime_cache={"n1": {"color": "red"}},
        refresh_interval=60000,
        status="published",
    )

    response, payload = _copy(
        NetworkTopologyViewSet,
        user,
        source.id,
        {"directory": target_dir.id, "groups": [1]},
        "/network_topology/",
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert "token" not in payload["data"]
    assert payload["data"]["token_set"] is True
    copied = NetworkTopology.objects.get(id=payload["data"]["id"])
    source.refresh_from_db()
    assert copied.directory_id == target_dir.id
    assert copied.base_url == source.base_url
    assert copied.view_sets == source.view_sets
    assert copied.status == "published"
    assert copied.last_runtime_cache in (None, {})
    assert source.last_runtime_cache == {"n1": {"color": "red"}}
    assert decrypt_token(copied.token) == "service-token-value"
    assert copied.is_build_in is False
    assert copied.build_in_key is None
