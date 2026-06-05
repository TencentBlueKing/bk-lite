"""GroupPermissionMixin 组织过滤的覆盖测试。

对照 spec/prd/运营分析：数据源/画布按组织分组隔离。
"""

from types import SimpleNamespace

import pytest

from apps.operation_analysis.filters.base_filters import GroupPermissionMixin
from apps.operation_analysis.models.models import Directory


def _request(method="GET", current_team="1", get_params=None):
    return SimpleNamespace(
        method=method,
        GET=get_params or {},
        COOKIES={"current_team": current_team} if current_team is not None else {},
        user=SimpleNamespace(username="testuser", group_list=[1]),
    )


def test_validate_all_groups_permission_with_all_groups_param():
    request = _request(get_params={"all_groups": "1"})
    ok, team = GroupPermissionMixin.validate_all_groups_permission(request)
    assert ok is True


def test_validate_all_groups_permission_without_param():
    request = _request(get_params={})
    ok, _ = GroupPermissionMixin.validate_all_groups_permission(request)
    assert ok is False


def test_validate_group_permission_valid_team():
    request = _request(current_team="2")
    ok, team = GroupPermissionMixin.validate_group_permission(request)
    assert ok is True
    assert team == 2


def test_validate_group_permission_missing_team():
    request = _request(current_team=None)
    ok, team = GroupPermissionMixin.validate_group_permission(request)
    assert ok is False


def test_validate_group_permission_invalid_team():
    request = _request(current_team="notanumber")
    ok, team = GroupPermissionMixin.validate_group_permission(request)
    assert ok is False


@pytest.mark.django_db
def test_apply_group_filter_superuser_no_filter():
    Directory.objects.create(name="d1", groups=[1], created_by="testuser")
    qs = Directory.objects.all()
    # current_team=None 表示超级用户，不过滤
    result = GroupPermissionMixin.apply_group_filter(qs, None)
    assert result.count() == qs.count()


@pytest.mark.django_db
def test_apply_group_filter_by_team():
    Directory.objects.create(name="in-team", groups=[1], created_by="testuser")
    Directory.objects.create(name="other-team", groups=[2], created_by="testuser")
    qs = Directory.objects.all()
    result = GroupPermissionMixin.apply_group_filter(qs, 1)
    names = set(result.values_list("name", flat=True))
    assert "in-team" in names
    assert "other-team" not in names


@pytest.mark.django_db
def test_apply_group_filter_with_user_created_by():
    Directory.objects.create(name="mine", groups=[1], created_by="testuser")
    Directory.objects.create(name="theirs", groups=[1], created_by="someoneelse")
    qs = Directory.objects.all()
    user = SimpleNamespace(username="testuser", domain="domain.com")
    # 提供 user 时叠加 created_by 过滤（permission rules 为空，回退到创建者）
    result = GroupPermissionMixin.apply_group_filter(qs, 1, user=user, permission_key="directory")
    names = set(result.values_list("name", flat=True))
    assert "mine" in names


@pytest.mark.django_db
def test_apply_group_filter_with_group_ids_expansion():
    Directory.objects.create(name="g1", groups=[1], created_by="testuser")
    Directory.objects.create(name="g3", groups=[3], created_by="testuser")
    qs = Directory.objects.all()
    # group_ids 多于一个时使用 OR 查询
    result = GroupPermissionMixin.apply_group_filter(qs, 1, group_ids=[1, 3])
    names = set(result.values_list("name", flat=True))
    assert {"g1", "g3"} <= names
