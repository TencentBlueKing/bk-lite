"""log.views.search 与 log.views.system_mgmt 的视图分支真实行为测试。

仅对视图的外部协作者打桩（SearchService / LogAccessScopeService / SystemMgmt RPC），
其余走真实序列化器校验、真实分支逻辑与真实 DB（SearchCondition CRUD）。
直接用 APIRequestFactory 构造请求并包装成 DRF Request 调用 ViewSet 方法，
避免依赖 URL 路由与鉴权中间件。
"""
import pydantic.root_model  # noqa

import json

import pytest
from rest_framework.parsers import JSONParser
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from apps.log.models.log_group import SearchCondition
from apps.log.services.access_scope import LogAccessScope
from apps.log.views.search import LogSearchViewSet, SearchConditionViewSet
from apps.log.views.system_mgmt import SystemMgmtView

pytestmark = pytest.mark.django_db

factory = APIRequestFactory()


class _User:
    username = "tester"
    is_authenticated = True


def _drf(wsgi_request, cookies=None, user=None):
    """把 WSGIRequest 包装成 DRF Request，设置 cookie / user。"""
    if cookies:
        wsgi_request.COOKIES.update(cookies)
    drf_request = Request(wsgi_request, parsers=[JSONParser()])
    drf_request.COOKIES = wsgi_request.COOKIES
    if user is not None:
        drf_request.user = user
    return drf_request


def get_req(params=None, cookies=None, user=None, raw=None):
    wsgi = factory.get(raw or "/x", params or {})
    return _drf(wsgi, cookies=cookies, user=user)


def post_req(data=None, cookies=None, user=None):
    wsgi = factory.post("/x", data or {}, format="json")
    return _drf(wsgi, cookies=cookies, user=user)


def _json(response):
    return json.loads(response.content.decode("utf-8"))


def _fake_scope(ids=None, objs=None):
    return LogAccessScope(
        log_groups=ids or ["g-1"],
        queryset=None,
        permission={},
        resolved_group_objects=objs or [],
    )


# --------------------------------------------------------------------------- #
# LogSearchViewSet._field_values_response 分支
# --------------------------------------------------------------------------- #
def test_field_values_missing_log_groups_returns_400():
    response = LogSearchViewSet().field_values(get_req({"filed": "host", "query": "*"}))

    assert response.status_code == 400
    body = _json(response)
    assert body["result"] is False
    assert body["message"] == "缺少日志分组"


def test_field_values_scope_value_error_returns_403(mocker):
    mocker.patch(
        "apps.log.views.search.LogAccessScopeService.resolve_scope",
        side_effect=ValueError("无权限"),
    )
    response = LogSearchViewSet().field_values(get_req({"filed": "host", "log_groups": "g-1"}))

    assert response.status_code == 403
    assert _json(response)["message"] == "无权限"


def test_field_values_success_passes_scope_to_service(mocker):
    scope = _fake_scope(ids=["g-9"], objs=[object()])
    mocker.patch("apps.log.views.search.LogAccessScopeService.resolve_scope", return_value=scope)
    svc = mocker.patch("apps.log.views.search.SearchService.field_values", return_value=["v1", "v2"])

    response = LogSearchViewSet().field_values(get_req({"filed": "host", "log_groups": "g-9", "limit": 7}))

    assert response.status_code == 200
    assert _json(response)["data"] == ["v1", "v2"]
    # 视图把解析出的 scope.log_groups / resolved_group_objects 透传给 service
    _, kwargs = svc.call_args
    assert kwargs["log_groups"] == ["g-9"]
    assert kwargs["resolved_groups"] == scope.resolved_group_objects


def test_field_names_alias_uses_same_handler(mocker):
    mocker.patch("apps.log.views.search.LogAccessScopeService.resolve_scope", return_value=_fake_scope())
    mocker.patch("apps.log.views.search.SearchService.field_values", return_value=["x"])

    response = LogSearchViewSet().field_names(get_req({"filed": "host", "log_groups": "g-1"}))

    assert response.status_code == 200
    assert _json(response)["data"] == ["x"]


def test_field_values_reads_bracketed_log_groups_param(mocker):
    mocker.patch("apps.log.views.search.LogAccessScopeService.resolve_scope", return_value=_fake_scope())
    mocker.patch("apps.log.views.search.SearchService.field_values", return_value=[])

    # 使用 log_groups[] 形式（getlist 的第二分支）
    response = LogSearchViewSet().field_values(get_req(raw="/x?filed=host&log_groups[]=a&log_groups[]=b"))

    assert response.status_code == 200


# --------------------------------------------------------------------------- #
# LogSearchViewSet.search / hits / top_stats 分支
# --------------------------------------------------------------------------- #
def test_search_scope_value_error_returns_403(mocker):
    mocker.patch(
        "apps.log.views.search.LogAccessScopeService.resolve_scope",
        side_effect=ValueError("禁止"),
    )
    response = LogSearchViewSet().search(post_req({"query": "level:error", "log_groups": ["g-1"]}))

    assert response.status_code == 403
    assert _json(response)["message"] == "禁止"


def test_search_success_forwards_query_and_scope(mocker):
    scope = _fake_scope(ids=["g-2"], objs=[object()])
    mocker.patch("apps.log.views.search.LogAccessScopeService.resolve_scope", return_value=scope)
    svc = mocker.patch("apps.log.views.search.SearchService.search_logs", return_value={"hits": []})

    response = LogSearchViewSet().search(post_req({"query": "level:error", "log_groups": ["g-2"], "limit": 33}))

    assert response.status_code == 200
    assert _json(response)["data"] == {"hits": []}
    args, kwargs = svc.call_args
    assert args[0] == "level:error"  # query 位置参
    assert kwargs["resolved_groups"] == scope.resolved_group_objects


def test_hits_success_forwards_field_and_step(mocker):
    mocker.patch("apps.log.views.search.LogAccessScopeService.resolve_scope", return_value=_fake_scope())
    svc = mocker.patch("apps.log.views.search.SearchService.search_hits", return_value={"hits": [1]})

    response = LogSearchViewSet().hits(
        post_req({"query": "*", "field": "_stream", "log_groups": ["g-1"], "step": "10m"})
    )

    assert response.status_code == 200
    assert _json(response)["data"] == {"hits": [1]}
    # field 是必填位置参之一
    assert "_stream" in svc.call_args.args


def test_top_stats_success_forwards_attr(mocker):
    mocker.patch("apps.log.views.search.LogAccessScopeService.resolve_scope", return_value=_fake_scope())
    svc = mocker.patch(
        "apps.log.views.search.SearchService.top_stats",
        return_value={"attr": "host", "items": []},
    )

    response = LogSearchViewSet().top_stats(
        post_req({"attr": "host", "query": "*", "log_groups": ["g-1"], "top_num": 3})
    )

    assert response.status_code == 200
    assert _json(response)["data"]["attr"] == "host"
    assert svc.call_args.kwargs["attr"] == "host"
    assert svc.call_args.kwargs["top_num"] == 3


# --------------------------------------------------------------------------- #
# LogSearchViewSet.tail_logs 分支
# --------------------------------------------------------------------------- #
def test_tail_missing_query_returns_error():
    response = LogSearchViewSet().tail_logs(get_req({"log_groups": "g-1"}))

    assert response.status_code == 400
    assert _json(response)["result"] is False


def test_tail_missing_log_groups_returns_400():
    response = LogSearchViewSet().tail_logs(get_req({"query": "*"}))

    assert response.status_code == 400
    assert _json(response)["message"] == "缺少日志分组"


def test_tail_value_error_returns_403(mocker):
    mocker.patch(
        "apps.log.views.search.LogAccessScopeService.resolve_scope",
        side_effect=ValueError("无权访问"),
    )
    response = LogSearchViewSet().tail_logs(get_req({"query": "*", "log_groups": "g-1,g-2"}))

    assert response.status_code == 403
    assert _json(response)["message"] == "无权访问"


def test_tail_parses_comma_separated_groups_and_streams(mocker):
    captured = {}

    def fake_resolve(request, log_groups):
        captured["log_groups"] = log_groups
        return _fake_scope(ids=log_groups)

    mocker.patch("apps.log.views.search.LogAccessScopeService.resolve_scope", side_effect=fake_resolve)
    sentinel = object()
    mocker.patch("apps.log.views.search.SearchService.tail", return_value=sentinel)

    # 含空白与空段，应被去除
    response = LogSearchViewSet().tail_logs(get_req({"query": "*", "log_groups": " a , b , , c "}))

    assert response is sentinel
    assert captured["log_groups"] == ["a", "b", "c"]


# --------------------------------------------------------------------------- #
# SearchConditionViewSet._is_accessible_search_condition 纯逻辑分支
# --------------------------------------------------------------------------- #
def _instance_with_condition(condition):
    return SearchCondition(name="n", condition=condition, organization=1)


def test_is_accessible_non_dict_condition_is_inaccessible():
    view = SearchConditionViewSet()
    inst = _instance_with_condition("not-a-dict")
    # condition 非 dict -> log_groups 取默认 [] -> 需有可访问分组
    assert view._is_accessible_search_condition(inst, set()) is False
    assert view._is_accessible_search_condition(inst, {"g-1"}) is True


def test_is_accessible_non_list_log_groups_is_inaccessible():
    view = SearchConditionViewSet()
    inst = _instance_with_condition({"log_groups": "g-1"})
    assert view._is_accessible_search_condition(inst, {"g-1"}) is False


def test_is_accessible_empty_log_groups_requires_any_accessible():
    view = SearchConditionViewSet()
    inst = _instance_with_condition({"log_groups": []})
    assert view._is_accessible_search_condition(inst, set()) is False
    assert view._is_accessible_search_condition(inst, {"g-1"}) is True


def test_is_accessible_all_groups_must_be_in_scope():
    view = SearchConditionViewSet()
    inst = _instance_with_condition({"log_groups": ["g-1", "g-2"]})
    assert view._is_accessible_search_condition(inst, {"g-1", "g-2"}) is True
    assert view._is_accessible_search_condition(inst, {"g-1"}) is False


def test_is_accessible_ignores_blank_group_ids():
    view = SearchConditionViewSet()
    inst = _instance_with_condition({"log_groups": ["g-1", "  ", ""]})
    # 仅 g-1 需要在范围内，空白被忽略
    assert view._is_accessible_search_condition(inst, {"g-1"}) is True


# --------------------------------------------------------------------------- #
# SearchConditionViewSet.get_queryset 真实 DB + 组织过滤
# --------------------------------------------------------------------------- #
def _build_view(request):
    view = SearchConditionViewSet()
    view.request = request
    view.format_kwarg = None
    return view


def test_get_queryset_returns_none_without_current_team():
    view = _build_view(get_req())
    assert list(view.get_queryset()) == []


def test_get_queryset_filters_by_team_and_accessibility(mocker):
    sc1 = SearchCondition.objects.create(name="t1", condition={"log_groups": ["g-1"]}, organization=771)
    sc2 = SearchCondition.objects.create(name="t2", condition={"log_groups": ["g-9"]}, organization=771)
    SearchCondition.objects.create(name="other", condition={"log_groups": ["g-1"]}, organization=881)

    view = _build_view(get_req(cookies={"current_team": "771"}))
    # 只有 g-1 可访问 -> sc1 命中，sc2(g-9) 与 881 组织被排除
    mocker.patch.object(view, "_get_accessible_group_ids", return_value={"g-1"})

    result = list(view.get_queryset())
    ids = {obj.id for obj in result}
    assert ids == {sc1.id}
    assert sc2.id not in ids


def test_get_queryset_returns_none_when_nothing_accessible(mocker):
    SearchCondition.objects.create(name="t", condition={"log_groups": ["g-1"]}, organization=991)
    view = _build_view(get_req(cookies={"current_team": "991"}))
    mocker.patch.object(view, "_get_accessible_group_ids", return_value=set())

    assert list(view.get_queryset()) == []


def test_get_accessible_group_ids_handles_value_error(mocker):
    mocker.patch(
        "apps.log.views.search.LogAccessScopeService.get_accessible_group_queryset",
        side_effect=ValueError("no team"),
    )
    view = _build_view(get_req())
    assert view._get_accessible_group_ids() == set()


# --------------------------------------------------------------------------- #
# SearchConditionViewSet CRUD: 缺少 current_team 分支 + happy path（真实 DB）
# --------------------------------------------------------------------------- #
def test_create_without_team_returns_error():
    response = SearchConditionViewSet().create(post_req({"name": "c", "condition": {}}))
    assert response.status_code == 400
    assert _json(response)["result"] is False


def test_create_persists_with_creator_and_org(mocker):
    mocker.patch("apps.log.serializers.log_group.LogAccessScopeService.resolve_scope", return_value=_fake_scope())
    request = post_req(
        {"name": "保存条件", "condition": {"query": "*", "log_groups": ["g-1"]}},
        cookies={"current_team": "551"},
        user=_User(),
    )
    view = _build_view(request)

    response = view.create(request)

    assert response.status_code == 200
    new_id = _json(response)["data"]["id"]
    saved = SearchCondition.objects.get(id=new_id)
    assert saved.name == "保存条件"
    assert saved.organization == 551
    assert saved.created_by == "tester"


def test_list_without_team_returns_error():
    request = get_req()
    view = _build_view(request)
    response = view.list(request)
    assert response.status_code == 400
    assert _json(response)["result"] is False


def test_retrieve_without_team_returns_error():
    request = get_req()
    view = _build_view(request)
    response = view.retrieve(request)
    assert response.status_code == 400


def test_update_without_team_returns_error():
    request = post_req({"name": "n"})
    view = _build_view(request)
    response = view.update(request)
    assert response.status_code == 400


def test_destroy_without_team_returns_error():
    request = get_req()
    view = _build_view(request)
    response = view.destroy(request)
    assert response.status_code == 400


def test_update_changes_name_and_sets_updater(mocker):
    mocker.patch("apps.log.serializers.log_group.LogAccessScopeService.resolve_scope", return_value=_fake_scope())
    sc = SearchCondition.objects.create(
        name="old", condition={"query": "*", "log_groups": ["g-1"]}, organization=552, created_by="creator"
    )

    request = post_req(
        {"name": "新名字", "condition": {"query": "*", "log_groups": ["g-1"]}},
        cookies={"current_team": "552"},
        user=_User(),
    )
    view = _build_view(request)
    view.kwargs = {"pk": sc.pk}
    mocker.patch.object(view, "get_object", return_value=sc)

    response = view.update(request)

    assert response.status_code == 200
    sc.refresh_from_db()
    assert sc.name == "新名字"
    assert sc.updated_by == "tester"
    # 组织不被更新逻辑修改
    assert sc.organization == 552


def test_destroy_deletes_instance(mocker):
    sc = SearchCondition.objects.create(name="待删", condition={}, organization=553)
    request = get_req(cookies={"current_team": "553"})
    view = _build_view(request)
    mocker.patch.object(view, "get_object", return_value=sc)

    response = view.destroy(request)

    assert response.status_code == 200
    assert "待删" in _json(response)["data"]["message"]
    assert not SearchCondition.objects.filter(id=sc.id).exists()


# --------------------------------------------------------------------------- #
# SystemMgmtView: 真实 cookie 解析，仅 mock RPC 边界
# --------------------------------------------------------------------------- #
def test_get_user_all_passes_team_and_include_children(mocker):
    rpc = mocker.patch("apps.log.views.system_mgmt.SystemMgmt")
    rpc.return_value.get_group_users.return_value = {"data": [{"id": 1}]}

    request = get_req(cookies={"current_team": "12", "include_children": "1"})
    response = SystemMgmtView().get_user_all(request)

    assert response.status_code == 200
    assert _json(response)["data"] == [{"id": 1}]
    rpc.return_value.get_group_users.assert_called_once_with(group="12", include_children=True)


def test_get_user_all_defaults_include_children_false(mocker):
    rpc = mocker.patch("apps.log.views.system_mgmt.SystemMgmt")
    rpc.return_value.get_group_users.return_value = {"data": []}

    # 无 include_children cookie -> 默认 "0" -> False
    response = SystemMgmtView().get_user_all(get_req())

    assert response.status_code == 200
    assert rpc.return_value.get_group_users.call_args.kwargs["include_children"] is False


def test_search_channel_list_builds_teams_from_team_cookie(mocker):
    rpc = mocker.patch("apps.log.views.system_mgmt.SystemMgmt")
    rpc.return_value.search_channel_list.return_value = {"data": [{"id": "ch"}]}

    request = get_req({"channel_type": "email"}, cookies={"current_team": "8"})
    response = SystemMgmtView().search_channel_list(request)

    assert response.status_code == 200
    assert _json(response)["data"] == [{"id": "ch"}]
    rpc.return_value.search_channel_list.assert_called_once_with(
        channel_type="email", teams=[8], include_children=False
    )


def test_search_channel_list_teams_none_without_team_cookie(mocker):
    rpc = mocker.patch("apps.log.views.system_mgmt.SystemMgmt")
    rpc.return_value.search_channel_list.return_value = {"data": []}

    SystemMgmtView().search_channel_list(get_req())

    assert rpc.return_value.search_channel_list.call_args.kwargs["teams"] is None
