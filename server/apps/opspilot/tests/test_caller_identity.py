import importlib
from types import SimpleNamespace

import pytest

from apps.base.models.user import UserAPISecret

MODULE_NAME = "apps.opspilot.services.caller_identity"


def _contract():
    try:
        return importlib.import_module(MODULE_NAME)
    except ModuleNotFoundError as exc:
        if exc.name != MODULE_NAME:
            raise
        pytest.fail("caller identity contract is not implemented")


def _user(
    *,
    username="alice",
    domain="domain.com",
    group_list=None,
    is_authenticated=True,
    is_superuser=False,
    **extra,
):
    return SimpleNamespace(
        username=username,
        domain=domain,
        group_list=[] if group_list is None else group_list,
        is_authenticated=is_authenticated,
        is_superuser=is_superuser,
        **extra,
    )


def _request(*, user=None, cookies=None, api_pass=False, include_user=True, **extra):
    values = {
        "COOKIES": {} if cookies is None else cookies,
        "api_pass": api_pass,
        **extra,
    }
    if include_user:
        values["user"] = user
    return SimpleNamespace(**values)


def _assert_error(contract, expected_status, message_part, request, authenticated_identity=None):
    with pytest.raises(contract.CallerIdentityError, match=message_part) as exc_info:
        contract.capture_caller_identity(request, authenticated_identity)

    assert exc_info.value.status_code == expected_status


def test_exports_stable_config_key():
    contract = _contract()

    assert contract.CALLER_IDENTITY_CONFIG_KEY == "caller_identity"


def test_mark_api_secret_identity_enables_bound_team_scope():
    contract = _contract()
    identity = _user(team=23)
    request = _request(
        user=_user(group_list=[999]),
        cookies={"current_team": "999", "include_children": "1"},
    )

    marked_identity = contract.mark_api_secret_identity(identity)
    result = contract.capture_caller_identity(request, marked_identity)

    assert marked_identity is identity
    assert result == {
        "username": "alice",
        "domain": "domain.com",
        "team_id": 23,
        "include_children": False,
    }


@pytest.mark.parametrize(
    ("group_list", "include_children_cookie", "expected_include_children"),
    [
        ([7], "1", True),
        ([{"id": 7}], "0", False),
        ([7, {"id": 8}], None, False),
    ],
)
def test_regular_login_captures_current_team_and_include_children(
    group_list,
    include_children_cookie,
    expected_include_children,
):
    contract = _contract()
    cookies = {"current_team": "7"}
    if include_children_cookie is not None:
        cookies["include_children"] = include_children_cookie
    request = _request(user=_user(group_list=group_list), cookies=cookies)

    result = contract.capture_caller_identity(request)

    assert result == {
        "username": "alice",
        "domain": "domain.com",
        "team_id": 7,
        "include_children": expected_include_children,
    }


def test_authenticated_identity_takes_precedence_over_request_user():
    contract = _contract()
    request = _request(
        user=_user(username="request-user", group_list=[7]),
        cookies={"current_team": "7"},
    )
    authenticated_identity = _user(username="validated-user", group_list=[7])

    result = contract.capture_caller_identity(request, authenticated_identity)

    assert result["username"] == "validated-user"


def test_regular_login_requires_an_authenticated_identity():
    contract = _contract()
    request = _request(include_user=False, cookies={"current_team": "7"})

    _assert_error(contract, 401, "authenticated identity", request)


def test_regular_login_rejects_anonymous_identity():
    contract = _contract()
    request = _request(
        user=_user(group_list=[7], is_authenticated=False),
        cookies={"current_team": "7"},
    )

    _assert_error(contract, 401, "authenticated identity", request)


def test_regular_login_requires_current_team():
    contract = _contract()
    request = _request(user=_user(group_list=[7]))

    _assert_error(contract, 400, "current team", request)


@pytest.mark.parametrize("current_team", ["0", "-1", "1.5", "not-a-team", " 7"])
def test_regular_login_rejects_invalid_current_team(current_team):
    contract = _contract()
    request = _request(
        user=_user(group_list=[7]),
        cookies={"current_team": current_team},
    )

    _assert_error(contract, 400, "positive integer", request)


def test_regular_login_wraps_extremely_long_current_team_as_contract_error():
    contract = _contract()
    request = _request(
        user=_user(group_list=[]),
        cookies={"current_team": "9" * 4301},
    )

    _assert_error(contract, 400, "positive integer", request)


@pytest.mark.parametrize(
    "group_list",
    [
        [8],
        [{"id": 8}],
        ["7"],
        [{"id": "7"}],
        [True],
        [{"id": True}],
    ],
)
def test_regular_login_rejects_current_team_outside_membership(group_list):
    contract = _contract()
    request = _request(
        user=_user(group_list=group_list),
        cookies={"current_team": "7"},
    )

    _assert_error(contract, 403, "not a member", request)


def test_superuser_cannot_bypass_current_team_membership():
    contract = _contract()
    request = _request(
        user=_user(group_list=[8], is_superuser=True),
        cookies={"current_team": "7"},
    )

    _assert_error(contract, 403, "not a member", request)


@pytest.mark.parametrize(("missing_field", "message_part"), [("username", "username"), ("domain", "domain")])
def test_identity_requires_username_and_domain(missing_field, message_part):
    contract = _contract()
    values = {
        "username": "alice",
        "domain": "domain.com",
        "group_list": [7],
    }
    values[missing_field] = ""
    request = _request(
        user=SimpleNamespace(**values),
        cookies={"current_team": "7"},
    )

    _assert_error(contract, 401, message_part, request)


def test_api_secret_identity_uses_bound_team_and_never_leaks_credentials():
    contract = _contract()
    request = _request(
        user=_user(username="request-user", group_list=[999]),
        cookies={"current_team": "999", "include_children": "1"},
        include_children=True,
    )
    authenticated_secret = SimpleNamespace(
        username="api-user",
        domain="api.example",
        team=23,
        _opspilot_api_secret_authenticated=True,
        api_secret="raw-secret-must-not-leak",
        token="raw-token-must-not-leak",
    )

    result = contract.capture_caller_identity(request, authenticated_secret)

    assert result == {
        "username": "api-user",
        "domain": "api.example",
        "team_id": 23,
        "include_children": False,
    }
    assert set(result) == {"username", "domain", "team_id", "include_children"}
    assert all("secret" not in key and "token" not in key for key in result)


def test_unsaved_user_api_secret_uses_bound_team_and_ignores_cookies():
    contract = _contract()
    request = _request(cookies={"current_team": "7", "include_children": "1"})
    bearer_identity = UserAPISecret(username="bearer-user", domain="api.example", team=999)
    bearer_identity.group_list = [7]

    result = contract.capture_caller_identity(request, bearer_identity)

    assert result == {
        "username": "bearer-user",
        "domain": "api.example",
        "team_id": 999,
        "include_children": False,
    }


def test_unsaved_user_api_secret_rejects_invalid_bound_team():
    contract = _contract()
    request = _request(cookies={"current_team": "7", "include_children": "1"})
    bearer_identity = UserAPISecret(username="bearer-user", domain="api.example", team=0)
    bearer_identity.group_list = [7]

    _assert_error(contract, 400, "API Secret bound team", request, bearer_identity)


def test_persisted_user_api_secret_without_auth_source_uses_bound_team():
    contract = _contract()
    request = _request(cookies={"current_team": "7", "include_children": "1"})
    bearer_identity = UserAPISecret(
        id=41,
        username="bearer-user",
        domain="api.example",
        team=23,
    )
    bearer_identity.group_list = [7]

    result = contract.capture_caller_identity(request, bearer_identity)

    assert result == {
        "username": "bearer-user",
        "domain": "api.example",
        "team_id": 23,
        "include_children": False,
    }


def test_api_pass_identity_uses_backend_bound_team_and_ignores_cookies():
    contract = _contract()
    user = _user(
        username="api-user",
        domain="api.example",
        group_list=[999],
        _api_secret_team=31,
    )
    request = _request(
        user=user,
        api_pass=True,
        cookies={"current_team": "999", "include_children": "1"},
    )

    result = contract.capture_caller_identity(request)

    assert result == {
        "username": "api-user",
        "domain": "api.example",
        "team_id": 31,
        "include_children": False,
    }


def test_api_pass_rejects_a_different_explicit_identity():
    contract = _contract()
    request_user = _user(
        username="api-user",
        domain="api.example",
        _api_secret_team=31,
    )
    request = _request(
        user=request_user,
        api_pass=True,
        cookies={"current_team": "7"},
    )
    other_identity = _user(
        username="other-user",
        domain="other.example",
        group_list=[7],
    )

    _assert_error(contract, 401, "conflicting authenticated identities", request, other_identity)


@pytest.mark.parametrize("bound_team", [None, 0, -1, "1.5", True])
def test_api_secret_identity_rejects_invalid_bound_team(bound_team):
    contract = _contract()
    request = _request(
        user=_user(group_list=[7]),
        cookies={"current_team": "7"},
    )
    authenticated_secret = SimpleNamespace(
        username="api-user",
        domain="api.example",
        team=bound_team,
        _opspilot_api_secret_authenticated=True,
    )

    _assert_error(contract, 400, "positive integer", request, authenticated_secret)


def test_api_secret_wraps_extremely_long_bound_team_as_contract_error():
    contract = _contract()
    request = _request(cookies={"current_team": "7"})
    authenticated_secret = _user(team="9" * 4301)
    contract.mark_api_secret_identity(authenticated_secret)

    _assert_error(contract, 400, "positive integer", request, authenticated_secret)
