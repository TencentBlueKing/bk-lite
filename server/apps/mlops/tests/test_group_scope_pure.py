import pydantic.root_model  # noqa

from types import SimpleNamespace

import pytest
from rest_framework import serializers
from rest_framework.test import APIRequestFactory

from apps.mlops.utils import group_scope as gs

pytestmark = pytest.mark.unit


def _req(team=None, user=None):
    request = APIRequestFactory().get("/")
    if team is not None:
        request._api_current_team = team
    if user is not None:
        request.user = user
    return request


# ---------- get_current_team ----------

def test_get_current_team_parses_int():
    assert gs.get_current_team(_req(team="7")) == 7


def test_get_current_team_missing_returns_default():
    assert gs.get_current_team(_req(), default=99) == 99


def test_get_current_team_non_numeric_returns_default():
    assert gs.get_current_team(_req(team="abc"), default=0) == 0


# ---------- get_allowed_team_ids ----------

def test_get_allowed_team_ids_no_user_returns_empty_set():
    request = APIRequestFactory().get("/")
    request.user = None
    assert gs.get_allowed_team_ids(request) == set()


def test_get_allowed_team_ids_superuser_returns_none():
    user = SimpleNamespace(is_superuser=True)
    assert gs.get_allowed_team_ids(_req(user=user)) is None


def test_get_allowed_team_ids_dict_group_list():
    user = SimpleNamespace(
        is_superuser=False,
        group_list=[{"id": 1}, {"id": "2"}, {"id": None}, {"id": "x"}],
    )
    assert gs.get_allowed_team_ids(_req(user=user)) == {1, 2}


def test_get_allowed_team_ids_scalar_group_list():
    user = SimpleNamespace(is_superuser=False, group_list=[3, "4", None])
    assert gs.get_allowed_team_ids(_req(user=user)) == {3, 4}


def test_get_allowed_team_ids_no_group_list_empty():
    user = SimpleNamespace(is_superuser=False, group_list=None)
    assert gs.get_allowed_team_ids(_req(user=user)) == set()


# ---------- validate_requested_teams ----------

def test_validate_requested_teams_normalizes():
    assert gs.validate_requested_teams(_req(), [1, "2", 3]) == [1, 2, 3]


def test_validate_requested_teams_empty_raises():
    with pytest.raises(serializers.ValidationError) as exc:
        gs.validate_requested_teams(_req(), [])
    assert "team" in exc.value.detail


def test_validate_requested_teams_not_list_raises():
    with pytest.raises(serializers.ValidationError):
        gs.validate_requested_teams(_req(), "1")


def test_validate_requested_teams_non_int_raises():
    with pytest.raises(serializers.ValidationError) as exc:
        gs.validate_requested_teams(_req(), [1, "bad"], field_name="grp")
    assert "grp" in exc.value.detail


# ---------- assert_team_ownership ----------

def test_assert_team_ownership_superuser_skips():
    user = SimpleNamespace(is_superuser=True)
    obj = SimpleNamespace(team=[])
    # current_team not in team but superuser -> no raise
    gs.assert_team_ownership(obj, 5, "team", request=_req(user=user))


def test_assert_team_ownership_member_ok():
    obj = SimpleNamespace(team=[1, 5])
    gs.assert_team_ownership(obj, 5, "team")


def test_assert_team_ownership_not_member_raises():
    obj = SimpleNamespace(team=[1, 2])
    with pytest.raises(serializers.ValidationError) as exc:
        gs.assert_team_ownership(obj, 9, "team")
    assert "team" in exc.value.detail


def test_assert_team_ownership_none_team_raises():
    obj = SimpleNamespace(team=None)
    with pytest.raises(serializers.ValidationError):
        gs.assert_team_ownership(obj, 1, "team")


# ---------- assert_parent_team_matches ----------

def test_assert_parent_team_matches_equal_ok():
    owner = SimpleNamespace(team=[1, 2])
    parent = SimpleNamespace(team=[1, 2])
    gs.assert_parent_team_matches(owner, parent, "ds")


def test_assert_parent_team_matches_differ_raises():
    owner = SimpleNamespace(team=[1])
    parent = SimpleNamespace(team=[2])
    with pytest.raises(serializers.ValidationError) as exc:
        gs.assert_parent_team_matches(owner, parent, "ds")
    assert "ds" in exc.value.detail


# ---------- assert_dataset_version_scope ----------

def test_assert_dataset_version_scope_none_noop():
    gs.assert_dataset_version_scope(None, [1], _req())


def test_assert_dataset_version_scope_no_dataset_raises():
    dsv = SimpleNamespace(dataset=None)
    with pytest.raises(serializers.ValidationError) as exc:
        gs.assert_dataset_version_scope(dsv, [1], _req(team="1"))
    assert "dataset_version" in exc.value.detail


def test_assert_dataset_version_scope_ownership_fail_raises():
    dataset = SimpleNamespace(team=[2])
    dsv = SimpleNamespace(dataset=dataset)
    request = _req(team="1")
    request.user = SimpleNamespace(is_superuser=False)
    with pytest.raises(serializers.ValidationError):
        gs.assert_dataset_version_scope(dsv, None, request)


def test_assert_dataset_version_scope_parent_mismatch_raises():
    dataset = SimpleNamespace(team=[1])
    dsv = SimpleNamespace(dataset=dataset)
    request = _req(team="1")
    request.user = SimpleNamespace(is_superuser=False)
    # team binding [2] != dataset team [1]
    with pytest.raises(serializers.ValidationError):
        gs.assert_dataset_version_scope(dsv, [2], request)


def test_assert_dataset_version_scope_all_match_ok():
    dataset = SimpleNamespace(team=[1])
    dsv = SimpleNamespace(dataset=dataset)
    request = _req(team="1")
    request.user = SimpleNamespace(is_superuser=False)
    gs.assert_dataset_version_scope(dsv, [1], request)
