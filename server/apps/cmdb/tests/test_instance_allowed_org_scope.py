"""CMDB 实例写路径组织范围：超级管理员不做当前组织裁剪。

对照：实例新增 / 修改 / 导入在计算 allowed_org_ids 时，
超级管理员经 NATS 取可分配组织；普通用户仍限制在当前组织（及可选子组织）与权限交集。
"""

from types import SimpleNamespace

import pytest

from apps.cmdb.views.instance import InstanceViewSet
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.system_mgmt.models import Group

VIEWS = "apps.cmdb.views.instance"


def _request(*, is_superuser: bool, group_ids: list[int], current_team: int, include_children: str = "0"):
    return SimpleNamespace(
        user=SimpleNamespace(
            username="tester",
            domain="domain.com",
            is_superuser=is_superuser,
            group_list=[{"id": gid} for gid in group_ids],
        ),
        COOKIES={
            "current_team": str(current_team),
            "include_children": include_children,
        },
    )


def test_superuser_allowed_org_ids_uses_assignable_groups_via_nats(monkeypatch):
    request = _request(
        is_superuser=True,
        group_ids=[1],
        current_team=1,
        include_children="0",
    )

    monkeypatch.setattr(
        f"{VIEWS}.resolve_assignable_organization_ids",
        lambda req: frozenset({3, 7, 9}),
    )

    allowed = InstanceViewSet._get_allowed_org_ids(request)

    assert set(allowed) == {3, 7, 9}


@pytest.mark.django_db
def test_normal_user_allowed_org_ids_only_current_team():
    root = Group.objects.create(name="__scope_root_n")
    child = Group.objects.create(name="__scope_child_n", parent_id=root.id)
    other = Group.objects.create(name="__scope_other_n")

    request = _request(
        is_superuser=False,
        group_ids=[root.id, child.id, other.id],
        current_team=root.id,
        include_children="0",
    )

    allowed = InstanceViewSet._get_allowed_org_ids(request)

    assert allowed == [root.id]


@pytest.mark.django_db
def test_normal_user_allowed_org_ids_with_children():
    root = Group.objects.create(name="__scope_root_c")
    child = Group.objects.create(name="__scope_child_c", parent_id=root.id)
    other = Group.objects.create(name="__scope_other_c")

    request = _request(
        is_superuser=False,
        group_ids=[root.id, child.id, other.id],
        current_team=root.id,
        include_children="1",
    )

    allowed = set(InstanceViewSet._get_allowed_org_ids(request))

    assert allowed == {root.id, child.id}
    assert other.id not in allowed


@pytest.mark.django_db
def test_normal_user_without_current_team_permission_raises():
    root = Group.objects.create(name="__scope_root_x")
    other = Group.objects.create(name="__scope_other_x")

    request = _request(
        is_superuser=False,
        group_ids=[other.id],
        current_team=root.id,
        include_children="0",
    )

    with pytest.raises(BaseAppException):
        InstanceViewSet._get_allowed_org_ids(request)
