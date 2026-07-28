"""issue #3037 回归测试：include_children 不得把 team 级范围放大成子树全选。

revert 准则：恢复 get_has_permission 中的 allowed_teams.add(current_team) 后，
test_..._denies_subtree_object_without_grant 必失败（无授权用户会被放行）。
"""

from types import SimpleNamespace

from apps.core.utils import viewset_utils
from apps.core.utils.viewset_utils import GenericViewSetFun


class _Fun(GenericViewSetFun):
    ORGANIZATION_FIELD = "team"
    permission_key = "auto_collection"

    def _get_app_name(self):
        return "cmdb"

    @staticmethod
    def extract_child_group_ids(group_tree, current_team_id):
        # 子树 = 当前组织 10 及其子组织 11、12
        return [10, 11, 12]


def _user():
    return SimpleNamespace(
        group_list=[{"id": 10}, {"id": 11}, {"id": 12}],
        group_tree=[],
    )


def _instance():
    # 子组织 12 下的一个任务对象
    return SimpleNamespace(id=999, team=[12])


def test_include_children_denies_subtree_object_without_grant(monkeypatch):
    # 用户对 current_team 及子树均无 team/instance 授权
    monkeypatch.setattr(viewset_utils, "get_permission_rules", lambda *a, **k: {"team": [], "instance": []})

    allowed = _Fun().get_has_permission(_user(), _instance(), current_team=10, include_children=True)

    assert allowed is False  # 无授权 → 子树对象不可越权操作


def test_include_children_allows_when_team_granted_on_current_team(monkeypatch):
    monkeypatch.setattr(viewset_utils, "get_permission_rules", lambda *a, **k: {"team": [10], "instance": []})

    allowed = _Fun().get_has_permission(_user(), _instance(), current_team=10, include_children=True)

    assert allowed is True  # current_team 有 team 授权 → 放行（首段命中）


def test_include_children_allows_when_instance_granted(monkeypatch):
    monkeypatch.setattr(
        viewset_utils,
        "get_permission_rules",
        lambda *a, **k: {"team": [], "instance": [{"id": 999, "permission": ["Operate"]}]},
    )

    allowed = _Fun().get_has_permission(_user(), _instance(), current_team=10, include_children=True)

    assert allowed is True  # 显式实例授权 → 放行
