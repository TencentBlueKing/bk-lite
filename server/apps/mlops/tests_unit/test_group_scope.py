from types import SimpleNamespace

import pytest
from rest_framework.exceptions import PermissionDenied

from apps.mlops.utils.group_scope import filter_queryset_by_parent_team


class RecordingQuerySet:
    def __init__(self):
        self.filters = []

    def filter(self, **kwargs):
        self.filters.append(kwargs)
        return self


def make_request(current_team, group_list=None, *, is_superuser=False):
    return SimpleNamespace(
        COOKIES={"current_team": current_team} if current_team is not None else {},
        user=SimpleNamespace(
            is_superuser=is_superuser,
            group_list=group_list if group_list is not None else [{"id": 1}, {"id": "2"}],
        ),
    )


def test_filter_queryset_by_parent_team_rejects_forged_current_team():
    queryset = RecordingQuerySet()
    request = make_request("99", group_list=[{"id": 1}, {"id": 2}])

    with pytest.raises(PermissionDenied):
        filter_queryset_by_parent_team(queryset, request, "dataset__team")

    assert queryset.filters == []


def test_filter_queryset_by_parent_team_filters_allowed_current_team():
    queryset = RecordingQuerySet()
    request = make_request("2", group_list=[{"id": 1}, {"id": "2"}])

    result = filter_queryset_by_parent_team(queryset, request, "dataset__team")

    assert result is queryset
    assert queryset.filters == [{"dataset__team__contains": 2}]


def test_filter_queryset_by_parent_team_keeps_superuser_bypass():
    queryset = RecordingQuerySet()
    request = make_request("99", group_list=[], is_superuser=True)

    result = filter_queryset_by_parent_team(queryset, request, "dataset__team")

    assert result is queryset
    assert queryset.filters == []
