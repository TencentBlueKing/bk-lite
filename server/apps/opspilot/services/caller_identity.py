"""Capture the validated caller scope before an OpsPilot execution starts."""

import re
from typing import Any

from apps.core.utils.team_utils import get_current_team

CALLER_IDENTITY_CONFIG_KEY = "caller_identity"
_API_SECRET_AUTHENTICATED_ATTR = "_opspilot_api_secret_authenticated"


class CallerIdentityError(ValueError):
    """A caller identity cannot be safely converted to a runtime snapshot."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def mark_api_secret_identity(identity: Any) -> Any:
    """Record that ``identity`` came from a validated API Secret lookup."""

    setattr(identity, _API_SECRET_AUTHENTICATED_ATTR, True)
    return identity


def _require_identity(identity: Any) -> tuple[str, str]:
    if identity is None or not getattr(identity, "is_authenticated", True):
        raise CallerIdentityError("Caller authenticated identity is required", status_code=401)

    username = getattr(identity, "username", None)
    if not isinstance(username, str) or not username.strip():
        raise CallerIdentityError("Caller identity username is required", status_code=401)

    domain = getattr(identity, "domain", None)
    if not isinstance(domain, str) or not domain.strip():
        raise CallerIdentityError("Caller identity domain is required", status_code=401)

    return username, domain


def _positive_team_id(value: Any, source: str) -> int:
    if type(value) is int and value > 0:
        return value
    if isinstance(value, str) and re.fullmatch(r"[1-9][0-9]*", value):
        try:
            return int(value)
        except (ValueError, OverflowError):
            pass
    raise CallerIdentityError(f"{source} must be a positive integer", status_code=400)


def _member_team_ids(identity: Any) -> set[int]:
    team_ids: set[int] = set()
    for group in getattr(identity, "group_list", None) or []:
        group_id = group.get("id") if isinstance(group, dict) else group
        if type(group_id) is int and group_id > 0:
            team_ids.add(group_id)
    return team_ids


def _api_secret_bound_team(request: Any, identity: Any) -> tuple[bool, Any]:
    explicitly_authenticated = getattr(identity, _API_SECRET_AUTHENTICATED_ATTR, False) is True
    if explicitly_authenticated:
        return True, getattr(identity, "team", None)

    # APISecretAuthBackend stores the validated bound team on request.user.
    if getattr(request, "api_pass", False):
        return True, getattr(identity, "_api_secret_team", None)

    return False, None


def capture_caller_identity(request: Any, authenticated_identity: Any = None) -> dict:
    """Return a credential-free snapshot of the validated caller and team."""

    request_user = getattr(request, "user", None)
    if getattr(request, "api_pass", False) and authenticated_identity is not None and authenticated_identity is not request_user:
        raise CallerIdentityError("conflicting authenticated identities for API Secret request", status_code=401)

    identity = authenticated_identity if authenticated_identity is not None else request_user
    username, domain = _require_identity(identity)

    is_api_secret, bound_team = _api_secret_bound_team(request, identity)
    if is_api_secret:
        team_id = _positive_team_id(bound_team, "API Secret bound team")
        include_children = False
    else:
        current_team = get_current_team(request)
        if current_team is None or current_team == "":
            raise CallerIdentityError("Caller current team is required", status_code=400)
        team_id = _positive_team_id(current_team, "Caller current team")
        if team_id not in _member_team_ids(identity):
            raise CallerIdentityError("Caller is not a member of the current team", status_code=403)
        include_children = getattr(request, "COOKIES", {}).get("include_children") == "1"

    return {
        "username": username,
        "domain": domain,
        "team_id": team_id,
        "include_children": include_children,
    }
