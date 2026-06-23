import pydantic.root_model  # noqa

from apps.core.utils import user_group as ug
from apps.core.utils.user_group import Group, SubGroup, normalize_user_group_ids


class TestNormalizeUserGroupIds:
    def test_dicts(self):
        assert normalize_user_group_ids([{"id": 1}, {"id": "2"}]) == [1, 2]

    def test_plain_ints_and_strs(self):
        assert normalize_user_group_ids([3, "4"]) == [3, 4]

    def test_skips_invalid(self):
        assert normalize_user_group_ids([{"id": "x"}, None, {"no": 1}]) == []

    def test_none_input(self):
        assert normalize_user_group_ids(None) == []


class TestSubGroup:
    def test_empty_group_list_returns_self(self):
        assert SubGroup(5, []).get_group_id_and_subgroup_id() == [5]

    def test_collects_nested_subgroup_ids(self):
        groups = [
            {
                "id": 1,
                "subGroups": [
                    {"id": 2, "subGroups": [{"id": 3, "subGroups": []}]},
                    {"id": 4, "subGroups": []},
                ],
            }
        ]
        result = SubGroup(1, groups).get_group_id_and_subgroup_id()
        assert sorted(result) == [1, 2, 3, 4]

    def test_target_not_found_returns_self_only(self):
        groups = [{"id": 1, "subGroups": []}]
        assert SubGroup(99, groups).get_group_id_and_subgroup_id() == [99]

    def test_get_subgroup_nondict_returns_none(self):
        sg = SubGroup(1, [])
        assert sg.get_subgroup("not-a-dict", 1) is None

    def test_get_subgroup_finds_deeply_nested(self):
        sg = SubGroup(3, [])
        group = {"id": 1, "subGroups": [{"id": 2, "subGroups": [{"id": 3, "subGroups": []}]}]}
        found = sg.get_subgroup(group, 3)
        assert found["id"] == 3

    def test_get_all_group_id_skips_non_list_and_non_dict(self):
        sg = SubGroup(1, [])
        ids = []
        sg.get_all_group_id_by_subgroups("not-list", ids)
        assert ids == []
        ids2 = []
        sg.get_all_group_id_by_subgroups([{"id": 7}, "bad", {"no_id": 1}], ids2)
        assert ids2 == [7]


class TestGroup:
    def test_get_group_list_success(self, mocker):
        client = mocker.MagicMock()
        client.get_all_groups.return_value = {"data": [{"id": 1}]}
        mocker.patch.object(ug, "SystemMgmt", return_value=client)
        assert Group().get_group_list() == [{"id": 1}]

    def test_get_group_list_empty(self, mocker):
        client = mocker.MagicMock()
        client.get_all_groups.return_value = {}
        mocker.patch.object(ug, "SystemMgmt", return_value=client)
        assert Group().get_group_list() == []

    def test_get_group_list_non_list_data(self, mocker):
        client = mocker.MagicMock()
        client.get_all_groups.return_value = {"data": "oops"}
        mocker.patch.object(ug, "SystemMgmt", return_value=client)
        assert Group().get_group_list() == []

    def test_get_group_list_exception_returns_empty(self, mocker):
        client = mocker.MagicMock()
        client.get_all_groups.side_effect = RuntimeError("rpc down")
        mocker.patch.object(ug, "SystemMgmt", return_value=client)
        assert Group().get_group_list() == []

    def test_fast_path_when_all_ids_numeric(self, mocker):
        # 所有元素都能直接转 int，走快速路径，不调用 get_group_list
        mocker.patch.object(ug, "SystemMgmt", return_value=mocker.MagicMock())
        g = Group()
        spy = mocker.spy(g, "get_group_list")
        result = g.get_user_group_and_subgroup_ids([{"id": 1}, {"id": 2}])
        assert sorted(result) == [1, 2]
        spy.assert_not_called()

    def test_resolves_subgroups_when_not_fast_path(self, mocker):
        client = mocker.MagicMock()
        client.get_all_groups.return_value = {
            "data": [{"id": 1, "subGroups": [{"id": 2, "subGroups": []}]}]
        }
        mocker.patch.object(ug, "SystemMgmt", return_value=client)
        g = Group()
        # 传入一个 dict 无 id 的脏元素破坏快速路径长度匹配
        result = g.get_user_group_and_subgroup_ids([{"id": 1}, {"name": "no-id"}])
        assert sorted(result) == [1, 2]

    def test_no_groups_returns_empty(self, mocker):
        client = mocker.MagicMock()
        client.get_all_groups.return_value = {"data": []}
        mocker.patch.object(ug, "SystemMgmt", return_value=client)
        g = Group()
        assert g.get_user_group_and_subgroup_ids([{"name": "x"}]) == []

    def test_none_user_group_list(self, mocker):
        mocker.patch.object(ug, "SystemMgmt", return_value=mocker.MagicMock())
        g = Group()
        # None 走到 get_group_list；mock 返回空
        g.get_group_list = lambda: []
        assert g.get_user_group_and_subgroup_ids(None) == []
