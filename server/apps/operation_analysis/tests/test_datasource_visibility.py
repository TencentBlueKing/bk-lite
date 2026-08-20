from types import SimpleNamespace

from django.db.models import Q

from apps.operation_analysis.common.datasource_visibility import (
    can_access_datasource_in_org,
    expand_datasource_org_query,
    is_builtin_globally_visible,
)


def _ds(**kwargs):
    defaults = {"is_build_in": False, "groups": [1]}
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_empty_groups_is_global_only_for_builtin():
    assert is_builtin_globally_visible(_ds(is_build_in=True, groups=[])) is True
    assert is_builtin_globally_visible(_ds(is_build_in=True, groups=None)) is True
    assert is_builtin_globally_visible(_ds(is_build_in=True, groups=[2])) is False
    assert is_builtin_globally_visible(_ds(is_build_in=False, groups=[])) is False


def test_access_allows_any_org_for_global_builtin_and_allowlist_otherwise():
    global_builtin = _ds(is_build_in=True, groups=[])
    assert can_access_datasource_in_org(global_builtin, 1) is True
    assert can_access_datasource_in_org(global_builtin, 99) is True

    restricted = _ds(is_build_in=True, groups=[2])
    assert can_access_datasource_in_org(restricted, 2) is True
    assert can_access_datasource_in_org(restricted, 1) is False

    custom = _ds(is_build_in=False, groups=[])
    assert can_access_datasource_in_org(custom, 1) is False


def test_list_query_or_global_builtin_or_all_builtins_for_superuser():
    membership = Q(pk=1)
    expanded = expand_datasource_org_query(membership, include_all_builtins=False)
    assert expanded == membership | (Q(is_build_in=True) & (Q(groups=[]) | Q(groups__isnull=True)))

    superuser_q = expand_datasource_org_query(membership, include_all_builtins=True)
    assert superuser_q == membership | Q(is_build_in=True)
