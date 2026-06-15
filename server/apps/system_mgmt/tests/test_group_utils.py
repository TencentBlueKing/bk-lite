"""system_mgmt.utils.group_utils.GroupUtils 生产规格测试。

规格：组织树的子孙遍历（权限范围计算的基础，单次查询内存递归）。
- get_group_with_descendants: 返回自身 + 全部子孙；接受单值或列表；
- get_group_with_descendants_filtered: 支持按 group_list 过滤（[1,2] 或 [{"id":1}]），
  但仍会穿过无权限节点去收集其有权限的子孙。
经真实 DB 构造层级验证。
"""

import pytest

from apps.system_mgmt.models import Group
from apps.system_mgmt.utils.group_utils import GroupUtils

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def tree():
    """root -> child_a -> grandchild; root -> child_b。"""
    root = Group.objects.create(name="root", parent_id=0)
    a = Group.objects.create(name="child_a", parent_id=root.id)
    b = Group.objects.create(name="child_b", parent_id=root.id)
    g = Group.objects.create(name="grandchild", parent_id=a.id)
    return {"root": root.id, "a": a.id, "b": b.id, "g": g.id}


class TestDescendants:
    def test_返回自身及全部子孙(self, tree):
        result = set(GroupUtils.get_group_with_descendants(tree["root"]))
        assert result == {tree["root"], tree["a"], tree["b"], tree["g"]}

    def test_子树只含其下节点(self, tree):
        result = set(GroupUtils.get_group_with_descendants(tree["a"]))
        assert result == {tree["a"], tree["g"]}

    def test_叶子节点只含自身(self, tree):
        assert set(GroupUtils.get_group_with_descendants(tree["g"])) == {tree["g"]}

    def test_接受字符串与列表入参(self, tree):
        assert set(GroupUtils.get_group_with_descendants(str(tree["a"]))) == {tree["a"], tree["g"]}
        both = set(GroupUtils.get_group_with_descendants([tree["a"], tree["b"]]))
        assert both == {tree["a"], tree["g"], tree["b"]}


class TestFiltered:
    def test_无过滤等价于全部子孙(self, tree):
        assert set(GroupUtils.get_group_with_descendants_filtered(tree["root"])) == {
            tree["root"], tree["a"], tree["b"], tree["g"]
        }

    def test_按id列表过滤(self, tree):
        # 只允许 root 与 grandchild：穿过无权限的 a 仍能收集到 g
        allowed = [tree["root"], tree["g"]]
        result = set(GroupUtils.get_group_with_descendants_filtered(tree["root"], group_list=allowed))
        assert result == {tree["root"], tree["g"]}

    def test_按dict列表过滤(self, tree):
        allowed = [{"id": tree["root"]}, {"id": tree["a"]}]
        result = set(GroupUtils.get_group_with_descendants_filtered(tree["root"], group_list=allowed))
        assert result == {tree["root"], tree["a"]}
