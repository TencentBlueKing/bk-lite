import pydantic.root_model  # noqa

import pytest

from apps.core.utils import group_query_mixin as gqm
from apps.core.utils.group_query_mixin import GroupQueryMixin


class _Req:
    def __init__(self, cookies=None, api_team=None, user=None):
        self.COOKIES = cookies or {}
        self.user = user
        if api_team is not None:
            self._api_current_team = api_team


class _User:
    def __init__(self, username="u", is_superuser=False, group_list=None):
        self.username = username
        self.is_superuser = is_superuser
        if group_list is not None:
            self.group_list = group_list


class TestGetQueryGroups:
    def test_no_current_team_returns_empty(self):
        m = GroupQueryMixin()
        assert m.get_query_groups(_Req(user=_User())) == []

    def test_invalid_current_team_returns_empty(self):
        m = GroupQueryMixin()
        req = _Req(cookies={"current_team": "abc"}, user=_User(group_list=[1]))
        assert m.get_query_groups(req) == []

    def test_delegates_to_grouputils(self, mocker):
        gu = mocker.patch.object(gqm.GroupUtils, "get_user_authorized_child_groups", return_value=[7, 8])
        m = GroupQueryMixin()
        req = _Req(cookies={"current_team": "7", "include_children": "1"}, user=_User(group_list=[7]))
        assert m.get_query_groups(req) == [7, 8]
        _, kwargs = gu.call_args
        assert kwargs["target_group_id"] == 7
        assert kwargs["include_children"] is True
        assert kwargs["user_group_list"] == [7]

    def test_include_children_default_false(self, mocker):
        gu = mocker.patch.object(gqm.GroupUtils, "get_user_authorized_child_groups", return_value=[])
        m = GroupQueryMixin()
        req = _Req(cookies={"current_team": "7"}, user=_User(group_list=[7]))
        m.get_query_groups(req)
        assert gu.call_args.kwargs["include_children"] is False


class TestGetUserGroupList:
    def test_superuser_returns_all_group_ids(self, mocker):
        from apps.system_mgmt.models import Group as SysGroup

        mocker.patch.object(SysGroup.objects, "values_list", return_value=[10, 20])
        req = _Req(user=_User(is_superuser=True))
        assert GroupQueryMixin._get_user_group_list(req) == [10, 20]

    def test_normal_user_normalizes_group_list(self):
        req = _Req(user=_User(group_list=[{"id": 3}, {"id": "4"}]))
        assert GroupQueryMixin._get_user_group_list(req) == [3, 4]

    def test_user_without_group_list_returns_empty(self):
        req = _Req(user=_User())  # no group_list attr
        assert GroupQueryMixin._get_user_group_list(req) == []


class TestFilterByGroups:
    def test_empty_groups_returns_none_queryset(self, mocker):
        m = GroupQueryMixin()
        mocker.patch.object(m, "get_query_groups", return_value=[])
        qs = mocker.MagicMock()
        qs.none.return_value = "NONE"
        assert m.filter_by_groups(qs, _Req()) == "NONE"

    def test_overlap_filter_used(self, mocker):
        m = GroupQueryMixin()
        mocker.patch.object(m, "get_query_groups", return_value=[1, 2])
        qs = mocker.MagicMock()
        qs.filter.return_value = "FILTERED"
        assert m.filter_by_groups(qs, _Req()) == "FILTERED"
        qs.filter.assert_called_once_with(team__overlap=[1, 2])

    def test_falls_back_to_in_filter(self, mocker):
        m = GroupQueryMixin()
        mocker.patch.object(m, "get_query_groups", return_value=[1, 2])
        qs = mocker.MagicMock()
        qs.filter.side_effect = [Exception("no overlap"), "IN_FILTERED"]
        assert m.filter_by_groups(qs, _Req()) == "IN_FILTERED"
        assert qs.filter.call_args_list[1].kwargs == {"team__in": [1, 2]}
