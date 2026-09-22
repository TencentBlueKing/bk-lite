import pydantic.root_model  # noqa

import json
import logging

import pytest
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from apps.core.logger import SafeLogException
from apps.core.services.user_group import USER_LIST_MAX_PAGE_SIZE
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

    def test_page_size_is_capped(self):
        vs = UserGroupViewSet()
        assert vs.get_pagination_params({"page": "1", "page_size": "99999999"}) == (0, USER_LIST_MAX_PAGE_SIZE)


class TestUserList:
    def test_success(self, factory, mocker):
        mocker.patch.object(ug_view.UserGroup, "user_list", return_value={"count": 1, "users": [{"id": 1}]})
        vs = UserGroupViewSet()
        req = factory.get("/x/?search=foo&page=2&page_size=5")
        resp = vs.user_list(req)
        data = _body(resp)
        assert data["result"] is True
        assert data["data"]["count"] == 1
        _, kwargs = ug_view.UserGroup.user_list.call_args
        assert kwargs["query_params"] == {"page": 2, "page_size": 5, "search": "foo"}
        assert "actor_context" in kwargs

    def test_failure_returns_error_and_owns_safe_traceback(self, factory, mocker, caplog):
        secret = "password=SUPER-SECRET-TOKEN"
        original = RuntimeError(secret)
        mocker.patch.object(ug_view.UserGroup, "user_list", side_effect=original)
        caplog.set_level(logging.ERROR, logger="app")
        vs = UserGroupViewSet()
        resp = vs.user_list(factory.get("/x/"))
        data = _body(resp)
        assert data["result"] is False
        assert resp.status_code == 400
        records = [record for record in caplog.records if record.name == "app" and "event=user_list_query_failed" in record.getMessage()]
        assert len(records) == 1
        record = records[0]
        assert record.levelno == logging.ERROR
        assert record.msg == "event=user_list_query_failed failed_stage=user_list error_type=%s"
        assert record.args == ("RuntimeError",)
        assert record.getMessage() == "event=user_list_query_failed failed_stage=user_list error_type=RuntimeError"
        assert record.exc_info is not None
        assert record.exc_info[0] is SafeLogException
        assert record.exc_info[2] is original.__traceback__
        formatted = logging.Formatter().format(record)
        assert secret not in record.getMessage()
        assert secret not in formatted
        assert secret not in caplog.text
        assert original.args == (secret,)
