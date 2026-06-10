"""job_mgmt.utils.team_authz 纯单元测试（BL-NEW-002 水平越权修复）。

规格：用户只能引用自己授权团队内的对象；无团队归属的对象对非超管一律拒绝；
超管（authorized_team_ids=None）放行一切。
"""
import pytest

from apps.job_mgmt.utils.team_authz import is_team_authorized, normalize_authorized_team_ids, normalize_team

pytestmark = pytest.mark.unit


def test_normalize_team_支持list_int_none():
    assert normalize_team([1, 2, "3"]) == {1, 2, 3}
    assert normalize_team(5) == {5}
    assert normalize_team(None) == set()
    assert normalize_team([]) == set()
    assert normalize_team("bad") == set()


def test_normalize_authorized_team_ids_从group_list提取():
    group_list = [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}, {"name": "无id"}]
    assert normalize_authorized_team_ids(group_list) == {1, 2}
    assert normalize_authorized_team_ids([]) == set()
    assert normalize_authorized_team_ids(None) == set()


def test_超管放行一切():
    assert is_team_authorized([999], None) is True
    assert is_team_authorized(None, None) is True


def test_对象团队在授权范围内则放行():
    # Script/Playbook/Target 的 team 是 list
    assert is_team_authorized([1, 2], {1}) is True
    assert is_team_authorized([2], {1, 2}) is True
    # DistributionFile 的 team 是单个 int
    assert is_team_authorized(1, {1, 2}) is True


def test_跨团队引用被拒绝():
    """BL-NEW-002 核心：Team A 用户（授权 {1}）引用 Team B（team=[2]）对象被拒。"""
    assert is_team_authorized([2], {1}) is False
    assert is_team_authorized(2, {1}) is False


def test_无团队归属对象对非超管一律拒绝():
    """历史遗留的无 team 文件（team=None/[]）不能被任意用户引用。"""
    assert is_team_authorized(None, {1, 2}) is False
    assert is_team_authorized([], {1, 2}) is False
