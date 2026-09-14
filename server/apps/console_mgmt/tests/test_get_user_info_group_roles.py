"""get_user_info 所属组角色收集：prefetch 后不得再对每组发 values_list 查询。"""
import inspect

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.console_mgmt import views
from apps.console_mgmt.user_info_roles import collect_prefetched_group_role_ids
from apps.system_mgmt.models import Group, Role

pytestmark = [pytest.mark.django_db]


def _prefetch_groups(group_ids):
    return list(Group.objects.filter(id__in=group_ids).prefetch_related("roles"))


def _create_groups_with_roles(group_count, *, empty=False, shared_role=None):
    groups = []
    expected_ids = set()
    for index in range(group_count):
        group = Group.objects.create(name=f"issue5188-g{index}", parent_id=0)
        groups.append(group)
        if empty:
            continue
        role = Role.objects.create(name=f"issue5188-r{index}", app="console")
        group.roles.add(role)
        expected_ids.add(role.id)
        if shared_role is not None:
            group.roles.add(shared_role)
            expected_ids.add(shared_role.id)
    return groups, expected_ids


def test_empty_groups_do_not_query_roles():
    with CaptureQueriesContext(connection) as captured:
        role_ids = collect_prefetched_group_role_ids([])

    assert role_ids == set()
    assert len(captured.captured_queries) == 0


@pytest.mark.parametrize("group_count", [1, 10, 100])
def test_prefetched_role_collection_query_count_does_not_grow_with_groups(group_count):
    groups, expected_ids = _create_groups_with_roles(group_count)
    prefetched = _prefetch_groups([group.id for group in groups])

    with CaptureQueriesContext(connection) as captured:
        role_ids = collect_prefetched_group_role_ids(prefetched)

    assert role_ids == expected_ids
    assert len(captured.captured_queries) == 0, (
        f"G={group_count} 预取后仍发出 {len(captured.captured_queries)} 次查询，"
        "说明未消费 prefetch 缓存。"
    )


def test_duplicate_roles_across_groups_are_deduped():
    shared = Role.objects.create(name="issue5188-shared", app="console")
    only_first = Role.objects.create(name="issue5188-only-first", app="console")
    first = Group.objects.create(name="issue5188-dup-a", parent_id=0)
    second = Group.objects.create(name="issue5188-dup-b", parent_id=0)
    first.roles.add(shared, only_first)
    second.roles.add(shared)
    prefetched = _prefetch_groups([first.id, second.id])

    with CaptureQueriesContext(connection) as captured:
        role_ids = collect_prefetched_group_role_ids(prefetched)

    assert role_ids == {shared.id, only_first.id}
    assert len(captured.captured_queries) == 0


def test_empty_role_groups_return_empty_set_without_queries():
    empty_group = Group.objects.create(name="issue5188-empty-roles", parent_id=0)
    prefetched = _prefetch_groups([empty_group.id])

    with CaptureQueriesContext(connection) as captured:
        role_ids = collect_prefetched_group_role_ids(prefetched)

    assert role_ids == set()
    assert len(captured.captured_queries) == 0


def test_get_user_info_uses_extracted_collector_without_values_list():
    source = inspect.getsource(views.get_user_info)
    assert "collect_prefetched_group_role_ids" in source
    assert "values_list" not in source
