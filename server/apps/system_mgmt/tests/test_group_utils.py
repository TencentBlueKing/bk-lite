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


class TestGetAllChildGroups:
    """旧的递归实现（N+1），仍需保证行为正确。"""

    def test_包含自身与全部子孙(self, tree):
        result = set(GroupUtils.get_all_child_groups(tree["root"], include_self=True))
        assert result == {tree["root"], tree["a"], tree["b"], tree["g"]}

    def test_不含自身时排除根(self, tree):
        result = set(GroupUtils.get_all_child_groups(tree["root"], include_self=False))
        assert tree["root"] not in result
        assert {tree["a"], tree["b"], tree["g"]} <= result

    def test_按group_list过滤子组织(self, tree):
        # 仅授权 root 与 a（不含 b/g）：b 被裁掉，a 保留；g 是 a 的子但不在 list -> 不收集
        allowed = [tree["root"], tree["a"]]
        result = set(GroupUtils.get_all_child_groups(tree["root"], include_self=True, group_list=allowed))
        assert tree["b"] not in result
        assert tree["root"] in result and tree["a"] in result


class TestUserAuthorizedChildGroups:
    def test_目标组织不在权限列表返回空(self, tree):
        assert GroupUtils.get_user_authorized_child_groups([tree["a"]], tree["root"]) == []

    def test_不含子组织仅返回当前(self, tree):
        assert GroupUtils.get_user_authorized_child_groups([tree["root"]], tree["root"], include_children=False) == [tree["root"]]

    def test_含子组织返回授权子孙(self, tree):
        # 权限列表含 root/a/g（不含 b）
        allowed = [tree["root"], tree["a"], tree["g"]]
        result = set(GroupUtils.get_user_authorized_child_groups(allowed, tree["root"], include_children=True))
        assert result == {tree["root"], tree["a"], tree["g"]}
        assert tree["b"] not in result


class TestBuildGroupTree:
    def test_超管返回完整树并按id排序(self, tree):
        groups = Group.objects.filter(id__in=tree.values())
        result = GroupUtils.build_group_tree(groups, is_superuser=True)
        # 仅一个根节点 root
        assert len(result) == 1
        root_node = result[0]
        assert root_node["id"] == tree["root"]
        assert root_node["hasAuth"] is True
        # root 下两个子组 a、b（按 id 正序）
        sub_ids = [s["id"] for s in root_node["subGroups"]]
        assert sub_ids == sorted([tree["a"], tree["b"]])
        assert root_node["subGroupCount"] == 2
        # a 下含 grandchild
        node_a = next(s for s in root_node["subGroups"] if s["id"] == tree["a"])
        assert [s["id"] for s in node_a["subGroups"]] == [tree["g"]]

    def test_普通用户仅见有权限组及其父级(self, tree):
        groups = Group.objects.filter(id__in=tree.values())
        # 用户仅在 grandchild：应看到 root -> a -> g 链路，b 不可见
        result = GroupUtils.build_group_tree(groups, is_superuser=False, user_groups=[tree["g"]])
        assert len(result) == 1
        root_node = result[0]
        assert root_node["id"] == tree["root"]
        assert root_node["hasAuth"] is False  # root 非用户直属组
        node_a = root_node["subGroups"][0]
        assert node_a["id"] == tree["a"]
        node_g = node_a["subGroups"][0]
        assert node_g["id"] == tree["g"]
        assert node_g["hasAuth"] is True
        # b 不在可见树中
        all_ids = {root_node["id"], node_a["id"], node_g["id"]}
        assert tree["b"] not in all_ids


class TestBuildGroupPaths:
    def test_构建从根到用户组的路径(self, tree):
        groups = Group.objects.filter(id__in=tree.values())
        paths = GroupUtils.build_group_paths(groups, user_groups=[tree["g"], tree["b"]])
        assert "root/child_a/grandchild" in paths
        assert "root/child_b" in paths

    def test_未知用户组被忽略(self, tree):
        groups = Group.objects.filter(id__in=tree.values())
        paths = GroupUtils.build_group_paths(groups, user_groups=[999999])
        assert paths == []
