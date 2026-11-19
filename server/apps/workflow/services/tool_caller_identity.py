"""Build the caller snapshot workflow agents hand to OpsPilot tools.

The snapshot key and fields match OpsPilot ``caller_identity``. This module
does not import OpsPilot, so the worker can build it while that app is absent.
"""

from typing import Any

_NON_USER_ACTORS = {"", "system", "workflow-scheduler"}


def accepted_tool_caller_identity(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    username = value.get("username")
    domain = value.get("domain")
    team_id = value.get("team_id")
    include_children = value.get("include_children")
    if not isinstance(username, str) or len(username.strip()) > 150 or username.strip() in _NON_USER_ACTORS:
        return None
    if not isinstance(domain, str) or not domain.strip() or len(domain.strip()) > 100:
        return None
    if type(team_id) is not int or team_id <= 0:
        return None
    if type(include_children) is not bool:
        return None
    return {
        "username": username.strip(),
        "domain": domain.strip(),
        "team_id": team_id,
        "include_children": include_children,
    }
