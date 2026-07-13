# -- coding: utf-8 --
# Tests for apps.operation_analysis.common.get_nats_source_data
# Regression tests for issue #3702: int(get_current_team()) has no guard,
# cookie anomaly triggers 500.
import types

import pytest
from rest_framework.exceptions import ValidationError

from apps.operation_analysis.common.get_nats_source_data import GetNatsData


def _make_request(current_team_cookie=None, api_team=None, username="testuser"):
    """Build a minimal fake request object."""
    user = types.SimpleNamespace(
        username=username,
        domain="domain.com",
        timezone="Asia/Shanghai",
        permission={},
        group_tree=[],
        is_superuser=False,
    )
    cookies = {}
    if current_team_cookie is not None:
        cookies["current_team"] = current_team_cookie

    request = types.SimpleNamespace(
        user=user,
        COOKIES=cookies,
    )
    if api_team is not None:
        request._api_current_team = api_team
    return request


def _make_get_nats_data(request):
    """Instantiate GetNatsData without calling __init__ so we can call
    update_request_params() in isolation with full control."""
    obj = GetNatsData.__new__(GetNatsData)
    obj.request = request
    obj.params = {}
    return obj


class TestUpdateRequestParamsGuard:
    """
    Regression: int(get_current_team()) must not raise TypeError/ValueError.
    If this fix is reverted (the try/except removed), calling int(None) will
    raise TypeError and all tests in this class will fail — confirming coverage.
    """

    def test_valid_cookie_sets_team_int(self):
        """Normal flow: valid current_team cookie produces an integer team."""
        request = _make_request(current_team_cookie="7")
        obj = _make_get_nats_data(request)
        obj.update_request_params()
        assert obj.params["user_info"]["team"] == 7

    def test_api_key_injected_team_sets_team_int(self):
        """API key path: _api_current_team attribute is used and converted to int."""
        request = _make_request(api_team="42")
        obj = _make_get_nats_data(request)
        obj.update_request_params()
        assert obj.params["user_info"]["team"] == 42

    def test_missing_cookie_raises_validation_error_not_type_error(self):
        """
        Core regression: when current_team cookie is absent, update_request_params()
        must raise ValidationError (400-serialisable) instead of letting
        int(None) bubble up as a TypeError (which becomes a 500).

        Reverting the fix restores `team = int(get_current_team(self.request))`
        which raises TypeError for None → this test will fail.
        """
        request = _make_request(current_team_cookie=None)
        obj = _make_get_nats_data(request)

        with pytest.raises(ValidationError):
            obj.update_request_params()

    def test_non_numeric_cookie_raises_validation_error_not_value_error(self):
        """
        Edge case: a corrupt/tampered current_team cookie that is not numeric.
        Must raise ValidationError instead of raw ValueError.
        """
        request = _make_request(current_team_cookie="not-a-number")
        obj = _make_get_nats_data(request)

        with pytest.raises(ValidationError):
            obj.update_request_params()

    def test_empty_string_cookie_raises_validation_error(self):
        """Empty string for current_team is also invalid."""
        request = _make_request(current_team_cookie="")
        obj = _make_get_nats_data(request)

        with pytest.raises(ValidationError):
            obj.update_request_params()

    def test_valid_team_user_info_structure(self):
        """Sanity check: user_info dict is correctly populated on success."""
        request = _make_request(current_team_cookie="5")
        obj = _make_get_nats_data(request)
        obj.update_request_params()

        info = obj.params["user_info"]
        assert info["team"] == 5
        assert info["user"] == "testuser"
        assert info["domain"] == "domain.com"
        assert isinstance(info["permission"], dict)
        assert isinstance(info["group_tree"], list)
        assert info["is_superuser"] is False
        assert isinstance(info["include_children"], bool)
