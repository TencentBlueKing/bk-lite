"""apps.core.services.user_group.UserGroup 服务层单元测试。

契约：UserGroup 是对 SystemMgmt RPC 的薄封装，仅做数据塑形与异常传播。
仅 mock 真实外部边界（SystemMgmt RPC、Group 工具类），断言：
- 返回值塑形（count/users/group_ids 等）；
- 默认参数填充（groups_list 空参 -> {"search": ""}）；
- RPC 异常向上抛出，user_groups_list 异常吞掉返回安全默认值。
"""

import pytest

from apps.core.services import user_group as ug_module
from apps.core.services.user_group import UserGroup

pytestmark = pytest.mark.unit


class _FakeClient:
    """模拟 SystemMgmt RPC 客户端的真实返回形态。"""

    def __init__(self, **returns):
        self._returns = returns
        self.calls = {}

    def search_users(self, query_params):
        self.calls["search_users"] = query_params
        return self._returns["search_users"]

    def get_all_users(self):
        return self._returns["get_all_users"]

    def search_groups(self, query_params):
        self.calls["search_groups"] = query_params
        return self._returns["search_groups"]

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
        client = _FakeClient(search_users={"data": {"count": 2, "users": [{"id": 1}, {"id": 2}]}})
        result = UserGroup.user_list(client, {"page": 1})
        assert result == {"count": 2, "users": [{"id": 1}, {"id": 2}]}
        assert client.calls["search_users"] == {"page": 1}

    def test_missing_keys_default_to_empty(self):
        client = _FakeClient(search_users={"data": {}})
        assert UserGroup.user_list(client, {}) == {"count": 0, "users": []}

    def test_propagates_rpc_error(self):
        client = _FakeClient(search_users=KeyError)  # not used; trigger via missing key

        class Boom:
            def search_users(self, q):
                raise ConnectionError("rpc down")

        with pytest.raises(ConnectionError):
            UserGroup.user_list(Boom(), {})


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


class TestGroupsList:
    def test_returns_data_field(self):
        client = _FakeClient(search_groups={"data": [{"id": 9}]})
        assert UserGroup.groups_list(client, {"search": "x"}) == [{"id": 9}]
        assert client.calls["search_groups"] == {"search": "x"}

    def test_empty_query_params_default_filled(self):
        client = _FakeClient(search_groups={"data": []})
        UserGroup.groups_list(client, None)
        assert client.calls["search_groups"] == {"search": ""}

    def test_propagates_error(self):
        class Boom:
            def search_groups(self, q):
                raise RuntimeError("nope")

        with pytest.raises(RuntimeError):
            UserGroup.groups_list(Boom(), {"search": ""})


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


class _Req:
    def __init__(self, user):
        self.user = user


class _User:
    def __init__(self, is_superuser=False, group_list=None):
        self.is_superuser = is_superuser
        if group_list is not None:
            self.group_list = group_list


class TestUserGroupsList:
    def test_superuser_is_all_true(self):
        result = UserGroup.user_groups_list(_Req(_User(is_superuser=True)))
        assert result == {"is_all": True, "group_ids": []}

    def test_normal_user_resolves_group_ids(self, mocker):
        fake_group = mocker.MagicMock()
        fake_group.get_user_group_and_subgroup_ids.return_value = [11, 22]
        mocker.patch.object(ug_module, "Group", return_value=fake_group)

        result = UserGroup.user_groups_list(_Req(_User(group_list=[{"id": 11}])))
        assert result == {"is_all": False, "group_ids": [11, 22]}
        fake_group.get_user_group_and_subgroup_ids.assert_called_once_with(user_group_list=[{"id": 11}])

    def test_non_list_group_ids_coerced_to_empty(self, mocker):
        fake_group = mocker.MagicMock()
        fake_group.get_user_group_and_subgroup_ids.return_value = "not-a-list"
        mocker.patch.object(ug_module, "Group", return_value=fake_group)

        result = UserGroup.user_groups_list(_Req(_User(group_list=[{"id": 1}])))
        assert result == {"is_all": False, "group_ids": []}

    def test_exception_returns_safe_default(self, mocker):
        mocker.patch.object(ug_module, "Group", side_effect=RuntimeError("explode"))
        result = UserGroup.user_groups_list(_Req(_User(group_list=[{"id": 1}])))
        assert result == {"is_all": False, "group_ids": []}
