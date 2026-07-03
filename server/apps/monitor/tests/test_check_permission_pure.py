"""check_permission 纯函数单元测试 — 校验监控实例权限判定的真实分支行为。"""
import pytest

from apps.monitor.utils.check_permission import check_permission

pytestmark = pytest.mark.unit

OBJ = 10


def test_admin_with_matching_team_passes():
    # 超管 all.team 与实例 teams 有交集 → 直接放行
    perms = {"all": {"team": [1, 2]}}
    assert check_permission(OBJ, "inst-1", teams={2}, permissions=perms, cur_team=[99]) is True


def test_admin_without_matching_team_falls_through_to_normal():
    # 超管组不匹配，落到普通用户逻辑：无对象级权限且当前组与实例组无交集 → 拒绝
    perms = {"all": {"team": [1]}}
    assert check_permission(OBJ, "inst-1", teams={5}, permissions=perms, cur_team=[6]) is False


def test_normal_user_no_object_permission_cur_team_match():
    # 无对象级权限，cur_team 与实例 teams 有交集 → 放行
    assert check_permission(OBJ, "inst-1", teams={3}, permissions={}, cur_team=[3, 4]) is True


def test_normal_user_no_object_permission_cur_team_no_match():
    assert check_permission(OBJ, "inst-1", teams={3}, permissions={}, cur_team=[7]) is False


def test_object_permission_present_but_all_empty_denies():
    # 对象级权限存在但 instance/team 均为空 → 当前组对该类对象无任何实例权限
    perms = {OBJ: {"instance": [], "team": []}}
    assert check_permission(OBJ, "inst-1", teams={3}, permissions=perms, cur_team=[3]) is False


def test_instance_permission_hit_returns_true():
    perms = {OBJ: {"instance": [{"id": "inst-1"}], "team": []}}
    assert check_permission(OBJ, "inst-1", teams=set(), permissions=perms, cur_team=[]) is True


def test_team_permission_hit_returns_true():
    perms = {OBJ: {"instance": [{"id": "other"}], "team": [{"id": 8}]}}
    assert check_permission(OBJ, "inst-1", teams={8}, permissions=perms, cur_team=[]) is True


def test_object_permission_present_but_no_hit_denies():
    perms = {OBJ: {"instance": [{"id": "other"}], "team": [{"id": 8}]}}
    assert check_permission(OBJ, "inst-1", teams={9}, permissions=perms, cur_team=[9]) is False
