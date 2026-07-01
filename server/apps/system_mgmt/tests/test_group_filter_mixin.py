"""group_filter_mixin 的 GroupPermissionMixin / GroupFilterMixin 单元测试。

直接调用 mixin 方法，断言真实分支与 DB 过滤效果；
request 用 SimpleNamespace + cookies dict 构造真实形态。
"""
import types

import pytest
from rest_framework.exceptions import PermissionDenied

from apps.system_mgmt.models import Group, OperationLog, User
from apps.system_mgmt.utils.group_filter_mixin import GroupFilterMixin, GroupPermissionMixin

pytestmark = pytest.mark.django_db


def _user(is_superuser=False, group_list=None):
    return types.SimpleNamespace(
        username="u", domain="domain.com", is_superuser=is_superuser, group_list=group_list or []
    )


# ---------------------------------------------------------------------------
# GroupPermissionMixin
# ---------------------------------------------------------------------------
def test_get_user_group_ids_superuser_returns_none():
    m = GroupPermissionMixin()
    assert m._get_user_group_ids(_user(is_superuser=True)) is None


def test_get_user_group_ids_normal():
    m = GroupPermissionMixin()
    user = _user(group_list=[{"id": 1}, {"id": 2}])
    assert m._get_user_group_ids(user) == {1, 2}


def test_validate_group_permission_superuser_ok():
    m = GroupPermissionMixin()
    ok, resp = m._validate_group_permission(_user(is_superuser=True), 99)
    assert ok is True and resp is None


def test_validate_group_permission_denied():
    m = GroupPermissionMixin()
    user = _user(group_list=[{"id": 1}])
    ok, resp = m._validate_group_permission(user, 2)
    assert ok is False
    assert resp.status_code == 403


def test_validate_group_permission_allowed():
    m = GroupPermissionMixin()
    user = _user(group_list=[{"id": 5}])
    ok, resp = m._validate_group_permission(user, 5)
    assert ok is True and resp is None


def test_validate_user_in_accessible_groups_superuser():
    m = GroupPermissionMixin()
    target = types.SimpleNamespace(group_list=[9])
    ok, resp = m._validate_user_in_accessible_groups(_user(is_superuser=True), target)
    assert ok is True and resp is None


def test_validate_user_in_accessible_groups_intersection():
    m = GroupPermissionMixin()
    current = _user(group_list=[{"id": 3}, {"id": 4}])
    target = types.SimpleNamespace(group_list=[4, 7])
    ok, resp = m._validate_user_in_accessible_groups(current, target)
    assert ok is True


def test_validate_user_in_accessible_groups_no_intersection():
    m = GroupPermissionMixin()
    current = _user(group_list=[{"id": 3}])
    target = types.SimpleNamespace(group_list=[8])
    ok, resp = m._validate_user_in_accessible_groups(current, target)
    assert ok is False
    assert resp.status_code == 403


def test_filter_by_accessible_groups_superuser_returns_all():
    m = GroupPermissionMixin()
    User.objects.create(username="x", password="p", display_name="x", email="x@x.com", group_list=[1])
    qs = User.objects.all()
    result = m._filter_by_accessible_groups(qs, _user(is_superuser=True))
    assert result.count() == qs.count()


def test_filter_by_accessible_groups_empty_groups_returns_none():
    m = GroupPermissionMixin()
    qs = User.objects.all()
    result = m._filter_by_accessible_groups(qs, _user(group_list=[]))
    assert result.count() == 0


def test_filter_by_accessible_groups_filters_by_membership():
    m = GroupPermissionMixin()
    User.objects.create(username="in", password="p", display_name="in", email="i@x.com", group_list=[10])
    User.objects.create(username="out", password="p", display_name="out", email="o@x.com", group_list=[99])
    qs = User.objects.all()
    result = m._filter_by_accessible_groups(qs, _user(group_list=[{"id": 10}]))
    names = set(result.values_list("username", flat=True))
    assert "in" in names and "out" not in names


# ---------------------------------------------------------------------------
# GroupFilterMixin
# ---------------------------------------------------------------------------
class _BaseQS:
    """提供基础 queryset，作为 GroupFilterMixin super().get_queryset() 的目标。"""

    def get_queryset(self):
        return OperationLog.objects.all().order_by("-created_at")


class _DummyOpLogViewSet(GroupFilterMixin, _BaseQS):
    """最小宿主：GroupFilterMixin.get_queryset -> _BaseQS.get_queryset。"""

    def __init__(self, request):
        self.request = request


def _request(current_team="0", include_children="0", is_superuser=True, group_list=None):
    req = types.SimpleNamespace()
    req.user = _user(is_superuser=is_superuser, group_list=group_list)
    req.COOKIES = {"current_team": current_team, "include_children": include_children}
    req.META = {}
    return req


def test_parse_current_team_cookie_valid_and_invalid():
    m = GroupFilterMixin()
    m.request = _request(current_team="5")
    assert m._parse_current_team_cookie(m.request) == 5
    m.request = _request(current_team="notanint")
    assert m._parse_current_team_cookie(m.request) == 0


def test_validate_current_team_permission_zero_raises():
    m = GroupFilterMixin()
    req = _request(current_team="0")
    m.request = req
    with pytest.raises(PermissionDenied):
        m._validate_current_team_permission(req)


def test_validate_current_team_permission_no_access_raises():
    m = GroupFilterMixin()
    req = _request(current_team="5", is_superuser=False, group_list=[{"id": 1}])
    with pytest.raises(PermissionDenied):
        m._validate_current_team_permission(req)


def test_validate_current_team_permission_superuser_ok():
    m = GroupFilterMixin()
    req = _request(current_team="5", is_superuser=True)
    assert m._validate_current_team_permission(req) == 5


def test_validate_current_team_permission_member_ok():
    m = GroupFilterMixin()
    req = _request(current_team="3", is_superuser=False, group_list=[{"id": 3}])
    assert m._validate_current_team_permission(req) == 3


def test_get_child_group_ids_recurses():
    m = GroupFilterMixin()
    g1 = Group.objects.create(name="P", parent_id=0)
    g2 = Group.objects.create(name="C1", parent_id=g1.id)
    g3 = Group.objects.create(name="C2", parent_id=g2.id)
    ids = m._get_child_group_ids(g1.id, Group)
    assert ids == {g1.id, g2.id, g3.id}


def test_get_queryset_filters_logs_by_team_users():
    # 当前组 team_id 内有用户 alice，日志按 username+domain 过滤
    team = Group.objects.create(name="Team", parent_id=0)
    User.objects.create(
        username="alice", password="p", display_name="A", email="a@x.com",
        domain="domain.com", group_list=[team.id],
    )
    OperationLog.objects.create(username="alice", domain="domain.com", source_ip="127.0.0.1", app="cmdb", action_type="create", summary="s1")
    OperationLog.objects.create(username="bob", domain="domain.com", source_ip="127.0.0.1", app="cmdb", action_type="create", summary="s2")

    viewset = _DummyOpLogViewSet(_request(current_team=str(team.id), is_superuser=True))
    qs = viewset.get_queryset()
    usernames = set(qs.values_list("username", flat=True))
    assert usernames == {"alice"}


def test_get_queryset_empty_team_returns_none():
    team = Group.objects.create(name="EmptyTeam", parent_id=0)
    OperationLog.objects.create(username="zzz", domain="domain.com", source_ip="127.0.0.1", app="cmdb", action_type="create", summary="x")
    viewset = _DummyOpLogViewSet(_request(current_team=str(team.id), is_superuser=True))
    qs = viewset.get_queryset()
    assert qs.count() == 0


def test_get_queryset_include_children():
    parent = Group.objects.create(name="PT", parent_id=0)
    child = Group.objects.create(name="CT", parent_id=parent.id)
    User.objects.create(
        username="kid", password="p", display_name="K", email="k@x.com",
        domain="domain.com", group_list=[child.id],
    )
    OperationLog.objects.create(username="kid", domain="domain.com", source_ip="127.0.0.1", app="cmdb", action_type="create", summary="s")
    viewset = _DummyOpLogViewSet(
        _request(current_team=str(parent.id), include_children="1", is_superuser=True)
    )
    qs = viewset.get_queryset()
    assert set(qs.values_list("username", flat=True)) == {"kid"}
