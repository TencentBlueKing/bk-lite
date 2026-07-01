import pydantic.root_model  # noqa

import json

import pytest
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from apps.core.views import user_group as ug_view
from apps.core.views.user_group import UserGroupViewSet

pytestmark = pytest.mark.django_db


class _Factory:
    """生成 DRF Request（带 query_params），绕过 ViewSet.initialize_request 的 action_map 依赖。"""

    def __init__(self):
        self._f = APIRequestFactory()

    def get(self, url):
        return Request(self._f.get(url))


@pytest.fixture
def factory():
    return _Factory()


@pytest.fixture(autouse=True)
def _patch_systemmgmt(mocker):
    # 视图 __init__ 内实例化 SystemMgmt，统一桩掉外部 RPC 边界
    mocker.patch.object(ug_view, "SystemMgmt", return_value=mocker.MagicMock())


def _body(response):
    return json.loads(response.content)


class TestPaginationParams:
    def test_defaults(self):
        vs = UserGroupViewSet()
        assert vs.get_pagination_params({}) == (0, 20)

    def test_computed_offset(self):
        vs = UserGroupViewSet()
        assert vs.get_pagination_params({"page": "3", "page_size": "10"}) == (20, 10)

    def test_invalid_returns_default(self):
        vs = UserGroupViewSet()
        assert vs.get_pagination_params({"page": "abc"}) == (0, 20)


class TestUserList:
    def test_success(self, factory, mocker):
        mocker.patch.object(ug_view.UserGroup, "user_list", return_value={"count": 1, "users": [{"id": 1}]})
        vs = UserGroupViewSet()
        req = factory.get("/x/?search=foo&page=2&page_size=5")
        resp = vs.user_list(req)
        data = _body(resp)
        assert data["result"] is True
        assert data["data"]["count"] == 1
        # 校验透传的 query_params 契约
        _, kwargs = ug_view.UserGroup.user_list.call_args
        assert kwargs["query_params"] == {"page": 2, "page_size": 5, "search": "foo"}

    def test_failure_returns_error(self, factory, mocker):
        mocker.patch.object(ug_view.UserGroup, "user_list", side_effect=RuntimeError("boom"))
        vs = UserGroupViewSet()
        resp = vs.user_list(factory.get("/x/"))
        data = _body(resp)
        assert data["result"] is False
        assert resp.status_code == 400


class TestGroupList:
    def test_success(self, factory, mocker):
        mocker.patch.object(ug_view.UserGroup, "groups_list", return_value=[{"id": 1, "name": "g"}])
        vs = UserGroupViewSet()
        resp = vs.group_list(factory.get("/x/?search=g"))
        data = _body(resp)
        assert data["result"] is True
        assert data["data"] == [{"id": 1, "name": "g"}]
        assert ug_view.UserGroup.groups_list.call_args.kwargs["query_params"] == "g"

    def test_failure(self, factory, mocker):
        mocker.patch.object(ug_view.UserGroup, "groups_list", side_effect=ValueError("x"))
        vs = UserGroupViewSet()
        resp = vs.group_list(factory.get("/x/"))
        assert _body(resp)["result"] is False


class TestUserGroups:
    def test_success(self, factory, mocker):
        mocker.patch.object(ug_view.UserGroup, "user_groups_list", return_value={"groups": [1, 2]})
        vs = UserGroupViewSet()
        resp = vs.user_groups(factory.get("/x/"))
        data = _body(resp)
        assert data["result"] is True
        assert data["data"] == {"groups": [1, 2]}

    def test_failure(self, factory, mocker):
        mocker.patch.object(ug_view.UserGroup, "user_groups_list", side_effect=RuntimeError("x"))
        vs = UserGroupViewSet()
        resp = vs.user_groups(factory.get("/x/"))
        assert _body(resp)["result"] is False
