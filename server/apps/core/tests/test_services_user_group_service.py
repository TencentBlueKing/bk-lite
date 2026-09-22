"""apps.core.services.user_group.UserGroup 服务层单元测试。

契约：UserGroup 是对 SystemMgmt RPC 的薄封装，仅做数据塑形与异常传播。
仅 mock 真实外部边界（SystemMgmt RPC），断言：
- 返回值塑形（count/users）；
- user_list 走 scoped RPC，并截断 page_size。
"""

import pytest

from apps.core.services import user_group as ug_module
from apps.core.services.user_group import USER_LIST_MAX_PAGE_SIZE, UserGroup

pytestmark = pytest.mark.unit


class _FakeClient:
    """模拟 SystemMgmt RPC 客户端的真实返回形态。"""

    def __init__(self, **returns):
        self._returns = returns
        self.calls = {}

    def get_group_users_scoped(self, actor_context, group=None, include_children=False, search=""):
        self.calls["get_group_users_scoped"] = {
            "actor_context": actor_context,
            "group": group,
            "include_children": include_children,
            "search": search,
        }
        return self._returns["get_group_users_scoped"]

    def get_all_users(self):
        return self._returns["get_all_users"]

    def get_all_groups(self):
        return self._returns["get_all_groups"]


class TestGetSystemMgmtClient:
    def test_returns_systemmgmt_instance(self, mocker):
        sentinel = object()
        mocker.patch.object(ug_module, "SystemMgmt", return_value=sentinel)
        assert UserGroup.get_system_mgmt_client() is sentinel

    def test_raises_when_construction_fails(self, mocker):
        mocker.patch.object(ug_module, "SystemMgmt", side_effect=RuntimeError("boom"))
        with pytest.raises(RuntimeError):
            UserGroup.get_system_mgmt_client()


class TestUserList:
    def test_shapes_count_and_users(self):
        client = _FakeClient(get_group_users_scoped={"result": True, "data": [{"id": 1}, {"id": 2}]})
        actor_context = {"username": "alice", "current_team": 7, "include_children": False}
        result = UserGroup.user_list(client, actor_context, {"page": 1, "search": "al"})
        assert result == {"count": 2, "users": [{"id": 1}, {"id": 2}]}
        assert client.calls["get_group_users_scoped"] == {
            "actor_context": actor_context,
            "group": None,
            "include_children": False,
            "search": "al",
        }

    def test_missing_keys_default_to_empty(self):
        client = _FakeClient(get_group_users_scoped={"result": True, "data": []})
        assert UserGroup.user_list(client, {}, {}) == {"count": 0, "users": []}

    def test_caps_page_size(self):
        client = _FakeClient(get_group_users_scoped={"result": True, "data": [{"id": i} for i in range(3)]})
        result = UserGroup.user_list(client, {}, {"page": 1, "page_size": 99999999})
        assert result["count"] == 3
        assert result["users"] == [{"id": 0}, {"id": 1}, {"id": 2}]
        assert USER_LIST_MAX_PAGE_SIZE == 10000

    def test_propagates_rpc_error(self):
        class Boom:
            def get_group_users_scoped(self, actor_context, group=None, include_children=False, search=""):
                raise ConnectionError("rpc down")

        with pytest.raises(ConnectionError):
            UserGroup.user_list(Boom(), {}, {})


class TestGetAllUsers:
    def test_count_is_len_of_data(self):
        client = _FakeClient(get_all_users={"data": [{"id": 1}, {"id": 2}, {"id": 3}]})
        result = UserGroup.get_all_users(client)
        assert result == {"count": 3, "users": [{"id": 1}, {"id": 2}, {"id": 3}]}

    def test_propagates_error(self):
        class Boom:
            def get_all_users(self):
                raise ValueError("bad")

        with pytest.raises(ValueError):
            UserGroup.get_all_users(Boom())


class TestGetAllGroups:
    def test_returns_data_field(self):
        client = _FakeClient(get_all_groups={"data": [{"id": 1}]})
        assert UserGroup.get_all_groups(client) == [{"id": 1}]

    def test_propagates_error(self):
        class Boom:
            def get_all_groups(self):
                raise RuntimeError("down")

        with pytest.raises(RuntimeError):
            UserGroup.get_all_groups(Boom())
