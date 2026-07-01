import pydantic.root_model  # noqa
"""apps/core/utils/user_group.py 剩余未覆盖容错分支的真实行为测试。

补充 test_user_group_util.py 未触达的分支：
- SubGroup.get_subgroup: subGroups 列表中混入非 dict 元素 -> 跳过该项 (65-66)
- SubGroup.get_group_id_and_subgroup_id: get_subgroup 抛异常 -> 记日志并 continue (35-37)
- SubGroup.get_group_id_and_subgroup_id: get_all_group_id_by_subgroups 抛异常 -> 容错 (47-48)
- Group.get_user_group_and_subgroup_ids: 慢速路径中 group_info 非 dict -> 跳过 (131-132)
- Group.get_user_group_and_subgroup_ids: SubGroup 处理抛异常 -> continue (142-144)

策略：真实执行被测方法，通过构造畸形输入或对内部协作者打桩使其抛异常，
断言被测方法的真实返回值（容错后不冒泡、跳过坏数据）。
"""
from unittest.mock import patch

import pytest

from apps.core.utils.user_group import Group, SubGroup

pytestmark = pytest.mark.unit


# ============================================================================
# SubGroup.get_subgroup —— 列表中含非 dict 元素
# ============================================================================


class TestGetSubgroupNonDictItem:
    def test_subgroups_list_with_non_dict_item_skipped(self):
        sg = SubGroup(2, [])
        # subGroups 是 list，但首元素非 dict -> 跳过，命中第二个 dict
        group = {"id": 1, "subGroups": ["junk", {"id": 2}]}
        assert sg.get_subgroup(group, 2) == {"id": 2}

    def test_subgroups_only_non_dict_returns_none(self):
        sg = SubGroup(2, [])
        group = {"id": 1, "subGroups": ["a", 5, None]}
        assert sg.get_subgroup(group, 2) is None


# ============================================================================
# SubGroup.get_group_id_and_subgroup_id —— 内部异常容错
# ============================================================================


class TestGetGroupIdSubgroupIdErrorTolerance:
    def test_get_subgroup_raises_is_caught_and_continues(self):
        """遍历 group_list 时 get_subgroup 抛异常 -> 捕获后 continue，
        最终未找到子组 -> 仅返回自身 id (35-37)。"""
        tree = [{"id": 1}, {"id": 2}]
        sg = SubGroup(5, tree)
        with patch.object(sg, "get_subgroup", side_effect=RuntimeError("boom")):
            result = sg.get_group_id_and_subgroup_id()
        assert result == [5]

    def test_get_all_group_id_raises_is_caught(self):
        """找到 sub_group 后，展开子组时抛异常 -> 捕获，返回已有的自身 id (47-48)。"""
        tree = [{"id": 1, "subGroups": [{"id": 2}]}]
        sg = SubGroup(1, tree)
        with patch.object(sg, "get_all_group_id_by_subgroups", side_effect=RuntimeError("boom")):
            result = sg.get_group_id_and_subgroup_id()
        # 异常发生前 group_id_list 已含自身 1
        assert result == [1]


# ============================================================================
# Group.get_user_group_and_subgroup_ids —— 慢速路径坏数据 / 异常容错
# ============================================================================


class TestSlowPathErrorTolerance:
    def _group(self):
        with patch("apps.core.utils.user_group.SystemMgmt"):
            return Group()

    def test_non_dict_group_info_skipped_in_slow_path(self):
        """慢速路径中遇到非 dict 的 group_info -> 跳过 (131-132)。
        构造：含一个无 id 的 dict 迫使走慢速路径，再混入一个非 dict 项。"""
        g = self._group()
        all_groups = [{"id": 1, "subGroups": [{"id": 2}]}]
        # "not-a-dict" 非 dict；{"name": "x"} 让 normalize 数量不一致 -> 慢速路径
        user_groups = [{"id": 1}, "not-a-dict", {"name": "x"}]
        with patch.object(g, "get_group_list", return_value=all_groups):
            result = g.get_user_group_and_subgroup_ids(user_groups)
        # 非 dict 项与无 id 项被跳过，仅 id=1 展开为 [1,2]
        assert sorted(result) == [1, 2]

    def test_subgroup_processing_exception_is_skipped(self):
        """慢速路径中 SubGroup 处理抛异常 -> continue，不影响其它组 (142-144)。"""
        g = self._group()
        all_groups = [{"id": 1}]
        user_groups = [{"id": 1}, {"name": "no-id"}]  # 数量不一致 -> 慢速路径

        with patch.object(g, "get_group_list", return_value=all_groups), patch(
            "apps.core.utils.user_group.SubGroup"
        ) as mock_subgroup:
            mock_subgroup.return_value.get_group_id_and_subgroup_id.side_effect = RuntimeError("boom")
            result = g.get_user_group_and_subgroup_ids(user_groups)
        # 唯一有效组的处理抛异常被吞 -> 结果为空
        assert result == []
