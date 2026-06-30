from types import SimpleNamespace

import pytest
from rest_framework import serializers

from apps.mlops.utils.group_scope import validate_requested_teams

pytestmark = pytest.mark.unit


def _request(group_list, is_superuser=False):
    return SimpleNamespace(user=SimpleNamespace(group_list=group_list, is_superuser=is_superuser))


def test_validate_requested_teams_accepts_owned_teams():
    request = _request([{"id": 1}, {"id": "2"}])

    assert validate_requested_teams(request, ["1", 2]) == [1, 2]


def test_validate_requested_teams_rejects_unowned_team():
    request = _request([{"id": 1}])

    with pytest.raises(serializers.ValidationError) as exc:
        validate_requested_teams(request, [1, 3])

    assert exc.value.detail == {"team": ["只能选择当前用户所属组织"]}


def test_validate_requested_teams_allows_superuser_to_assign_any_team():
    request = _request([], is_superuser=True)

    assert validate_requested_teams(request, [99]) == [99]
