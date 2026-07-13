import pydantic.root_model  # noqa
"""apps/core/utils/permission_utils.py 真实行为单元测试。

覆盖：
- set_rules_module_params / get_permission_rules / get_permissions_rules / delete_instance_rules
  （仅在 SystemMgmt RPC 与权限缓存这两个真实跨进程边界打桩，断言真实入参契约与返回值）
- permission_filter（真实 ORM queryset 过滤逻辑，使用真实 Group 表）
- 纯逻辑函数：_normalize_permission_ids / _normalize_instance_permissions /
  get_instance_permission_map / get_instance_permissions / check_instance_permission /
  filter_instances_with_permissions

策略：纯函数全部真实执行并断言真实输出；RPC/cache 边界打桩，返回真实形态假数据。
"""
from types import SimpleNamespace

import pytest

from apps.core import constants
from apps.core.utils import permission_utils as pu

pytestmark = pytest.mark.unit


def _user(username="u", domain="domain.com"):
    return SimpleNamespace(username=username, domain=domain)


# ---------------------------------------------------------------------------
# set_rules_module_params
# ---------------------------------------------------------------------------


class TestSetRulesModuleParams:
    def test_maps_known_app_and_splits_permission_key(self, mocker):
        mocker.patch.object(pu, "SystemMgmt", return_value="CLIENT")
        app, child, client, module = pu.set_rules_module_params("system_mgmt", "policy.child")
        assert app == "system-manager"
        assert module == "policy"
        assert child == "child"
        assert client == "CLIENT"

    def test_unknown_app_passthrough_no_child(self, mocker):
        mocker.patch.object(pu, "SystemMgmt", return_value="C")
        app, child, client, module = pu.set_rules_module_params("cmdb", "instance")
        assert app == "cmdb"
        assert module == "instance"
        assert child == ""

    def test_constructs_local_client(self, mocker):
        mock_sm = mocker.patch.object(pu, "SystemMgmt", return_value="C")
        pu.set_rules_module_params("node_mgmt", "view")
        mock_sm.assert_called_once_with(is_local_client=True)


# ---------------------------------------------------------------------------
# get_permission_rules
# ---------------------------------------------------------------------------


class TestGetPermissionRules:
    def test_cache_hit_returns_cached_without_rpc(self, mocker):
        cached = {"team": [1], "instance": []}
        mocker.patch.object(pu, "get_cached_permission_rules", return_value=cached)
        mock_set = mocker.patch.object(pu, "set_cached_permission_rules")
        mock_params = mocker.patch.object(pu, "set_rules_module_params")
        result = pu.get_permission_rules(_user(), "5", "cmdb", "instance")
        assert result == cached
        mock_params.assert_not_called()
        mock_set.assert_not_called()

    def test_cache_miss_calls_rpc_and_caches(self, mocker):
        mocker.patch.object(pu, "get_cached_permission_rules", return_value=None)
        mock_set = mocker.patch.object(pu, "set_cached_permission_rules")
        client = mocker.MagicMock()
        client.get_user_rules_by_app.return_value = {"team": [2], "instance": []}
        mocker.patch.object(pu, "set_rules_module_params", return_value=("cmdb", "", client, "instance"))

        result = pu.get_permission_rules(_user(username="alice"), "5", "cmdb", "instance", include_children=True)

        assert result == {"team": [2], "instance": []}
        # RPC 入参契约
        client.get_user_rules_by_app.assert_called_once_with(5, "alice", "cmdb", "instance", "", "domain.com", True)
        mock_set.assert_called_once()

    def test_rpc_exception_returns_empty_dict(self, mocker):
        mocker.patch.object(pu, "get_cached_permission_rules", return_value=None)
        mocker.patch.object(pu, "set_cached_permission_rules")
        client = mocker.MagicMock()
        client.get_user_rules_by_app.side_effect = RuntimeError("nats down")
        mocker.patch.object(pu, "set_rules_module_params", return_value=("cmdb", "", client, "instance"))
        assert pu.get_permission_rules(_user(), "5", "cmdb", "instance") == {}


# ---------------------------------------------------------------------------
# get_permissions_rules
# ---------------------------------------------------------------------------


class TestGetPermissionsRules:
    def test_maps_app_and_calls_rpc(self, mocker):
        client = mocker.MagicMock()
        client.get_user_rules_by_module.return_value = {"team": [9]}
        mocker.patch.object(pu, "SystemMgmt", return_value=client)
        result = pu.get_permissions_rules(_user(username="bob"), "3", "operation_analysis", "dash", include_children=False)
        assert result == {"team": [9]}
        client.get_user_rules_by_module.assert_called_once_with(3, "bob", "ops-analysis", "dash", "domain.com", False)

    def test_exception_returns_empty(self, mocker):
        client = mocker.MagicMock()
        client.get_user_rules_by_module.side_effect = ValueError("boom")
        mocker.patch.object(pu, "SystemMgmt", return_value=client)
        assert pu.get_permissions_rules(_user(), "3", "cmdb", "x") == {}


# ---------------------------------------------------------------------------
# delete_instance_rules
# ---------------------------------------------------------------------------


class TestDeleteInstanceRules:
    def test_forwards_to_client_delete_rules(self, mocker):
        client = mocker.MagicMock()
        client.delete_rules.return_value = {"result": True}
        mocker.patch.object(pu, "set_rules_module_params", return_value=("cmdb", "child", client, "module"))
        result = pu.delete_instance_rules("cmdb", "module.child", 7, [1, 2])
        assert result == {"result": True}
        client.delete_rules.assert_called_once_with([1, 2], 7, "cmdb", "module", "child")


# ---------------------------------------------------------------------------
# permission_filter（真实 ORM）
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPermissionFilter:
    def _make_groups(self):
        from apps.system_mgmt.models import Group

        g1 = Group.objects.create(name="g1", parent_id=0)
        g2 = Group.objects.create(name="g2", parent_id=0)
        g3 = Group.objects.create(name="g3", parent_id=0)
        return g1, g2, g3

    def test_empty_permission_returns_none_queryset(self):
        from apps.system_mgmt.models import Group

        self._make_groups()
        qs = pu.permission_filter(Group, {"instance": [], "team": []})
        assert list(qs) == []

    def test_instance_only_filter(self):
        from apps.system_mgmt.models import Group

        g1, g2, g3 = self._make_groups()
        qs = pu.permission_filter(Group, {"instance": [{"id": g1.id}], "team": []})
        assert set(qs.values_list("id", flat=True)) == {g1.id}

    def test_team_only_filter(self):
        from apps.system_mgmt.models import Group

        g1, g2, g3 = self._make_groups()
        # team_key 默认 teams__id__in 对 Group 无效，改用 id__in 充当 team_key 验证 OR 逻辑
        qs = pu.permission_filter(Group, {"instance": [], "team": [g2.id]}, team_key="id__in")
        assert set(qs.values_list("id", flat=True)) == {g2.id}

    def test_instance_and_team_union(self):
        from apps.system_mgmt.models import Group

        g1, g2, g3 = self._make_groups()
        qs = pu.permission_filter(
            Group,
            {"instance": [{"id": g1.id}], "team": [g2.id]},
            team_key="id__in",
        )
        assert set(qs.values_list("id", flat=True)) == {g1.id, g2.id}


# ---------------------------------------------------------------------------
# _normalize_permission_ids
# ---------------------------------------------------------------------------


class TestNormalizePermissionIds:
    def test_non_list_returns_empty_set(self):
        assert pu._normalize_permission_ids("nope") == set()
        assert pu._normalize_permission_ids(None) == set()

    def test_ints_and_str_forms_both_added(self):
        result = pu._normalize_permission_ids([1, 2])
        assert result == {1, 2, "1", "2"}

    def test_dict_values_use_id(self):
        result = pu._normalize_permission_ids([{"id": 3}, {"id": None}, {"other": 9}])
        # id=3 -> {3, "3"}; id=None 跳过; 无 id -> .get("id")=None 跳过
        assert result == {3, "3"}


# ---------------------------------------------------------------------------
# _normalize_instance_permissions / get_instance_permission_map
# ---------------------------------------------------------------------------


class TestNormalizeInstancePermissions:
    def test_non_list_returns_empty(self):
        assert pu._normalize_instance_permissions("x") == {}

    def test_skips_entries_without_id(self):
        assert pu._normalize_instance_permissions([{"permission": ["View"]}, "bad"]) == {}

    def test_default_permission_when_missing(self):
        result = pu._normalize_instance_permissions([{"id": 1}])
        assert result == {"1": constants.DEFAULT_PERMISSION}

    def test_merges_duplicate_instance_permissions(self):
        result = pu._normalize_instance_permissions(
            [
                {"id": 5, "permission": ["View"]},
                {"id": 5, "permission": ["Operate", "View"]},
            ]
        )
        assert result == {"5": ["View", "Operate"]}

    def test_get_instance_permission_map_non_dict(self):
        assert pu.get_instance_permission_map("nope") == {}

    def test_get_instance_permission_map_extracts_instance(self):
        result = pu.get_instance_permission_map({"instance": [{"id": 2, "permission": ["Operate"]}]})
        assert result == {"2": ["Operate"]}


# ---------------------------------------------------------------------------
# get_instance_permissions / check_instance_permission
# ---------------------------------------------------------------------------


class TestGetInstancePermissions:
    def test_admin_all_team_intersection_grants_default(self):
        perms = {"all": {"team": [1]}}
        result = pu.get_instance_permissions("obj", "inst", {1}, perms, [99])
        assert result == constants.DEFAULT_PERMISSION

    def test_no_object_permission_but_team_in_cur_team(self):
        result = pu.get_instance_permissions("obj", "inst", {7}, {}, [7])
        assert result == constants.DEFAULT_PERMISSION

    def test_no_object_permission_and_no_cur_team_returns_empty(self):
        result = pu.get_instance_permissions("obj", "inst", {7}, {}, [8])
        assert result == []

    def test_instance_specific_permission_returned(self):
        perms = {"obj": {"instance": [{"id": "inst", "permission": ["View"]}]}}
        result = pu.get_instance_permissions("obj", "inst", {1}, perms, [1])
        assert result == ["View"]

    def test_team_level_permission_grants_default(self):
        perms = {"obj": {"instance": [], "team": [3]}}
        result = pu.get_instance_permissions("obj", "other_inst", {3}, perms, [1])
        assert result == constants.DEFAULT_PERMISSION

    def test_no_match_returns_empty(self):
        perms = {"obj": {"instance": [], "team": [99]}}
        result = pu.get_instance_permissions("obj", "inst", {1}, perms, [2])
        assert result == []

    def test_none_team_filtered_out(self):
        perms = {"all": {"team": [5]}}
        # teams 含 None，应被过滤；5 在 admin team -> 命中
        result = pu.get_instance_permissions("obj", "inst", {None, 5}, perms, [])
        assert result == constants.DEFAULT_PERMISSION

    def test_check_instance_permission_bool(self):
        perms = {"obj": {"instance": [{"id": "inst", "permission": ["View"]}]}}
        assert pu.check_instance_permission("obj", "inst", {1}, perms, [1]) is True
        assert pu.check_instance_permission("obj", "missing", {1}, {}, [99]) is False


# ---------------------------------------------------------------------------
# filter_instances_with_permissions
# ---------------------------------------------------------------------------


class TestFilterInstancesWithPermissions:
    def test_returns_only_permitted_instances(self):
        instances = [
            {"instance_id": "a", "organizations": [1], "collect_type_id": 10},
            {"instance_id": "b", "organizations": [99], "collect_type_id": 10},
        ]
        # collect_type 10 授予实例 a 的 View 权限；b 既无实例权限也无团队权限
        perms = {"10": {"instance": [{"id": "a", "permission": ["View"]}], "team": []}}
        result = pu.filter_instances_with_permissions(instances, perms, [1])
        assert result == {"a": ["View"]}

    def test_team_level_grants_via_organizations(self):
        instances = [{"instance_id": "x", "organizations": [2], "collect_type_id": 5}]
        perms = {"5": {"instance": [], "team": [2]}}
        result = pu.filter_instances_with_permissions(instances, perms, [99])
        assert result == {"x": constants.DEFAULT_PERMISSION}

    def test_empty_when_no_permissions(self):
        instances = [{"instance_id": "x", "organizations": [3], "collect_type_id": 5}]
        result = pu.filter_instances_with_permissions(instances, {}, [99])
        assert result == {}
