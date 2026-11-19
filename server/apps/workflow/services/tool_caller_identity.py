"""Build the caller snapshot workflow agents hand to OpsPilot tools.

The snapshot key and fields match OpsPilot ``caller_identity``. This module
does not import OpsPilot, so the worker can build it while that app is absent.
"""

from typing import Any

from apps.system_mgmt.models import User

_NON_USER_ACTORS = {"", "system", "workflow-scheduler"}
_INVOKER_TRIGGER_TYPES = {"WEBHOOK", "FORM"}


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


def _organization_id(team: Any) -> int | None:
    if not isinstance(team, list) or not team:
        return None
    value = team[0]
    if type(value) is int and value > 0:
        return value
    if isinstance(value, str) and value.isdecimal():
        parsed = int(value)
        if parsed > 0:
            return parsed
    return None


def _caller_account(execution) -> tuple[str, str] | None:
    """定时执行用流程创建者。人工启动、调试和 Webhook 用本次启动人。"""

    trigger_type = str(getattr(execution, "trigger_type", "") or "")
    mode = str(getattr(execution, "mode", "") or "")
    if trigger_type == "SCHEDULE" and mode != "DEBUG":
        workflow = getattr(execution, "workflow", None)
        username = str(getattr(workflow, "created_by", "") or "").strip()
        domain = str(getattr(workflow, "domain", "") or "").strip()
    elif trigger_type in _INVOKER_TRIGGER_TYPES or mode == "DEBUG":
        username = str(getattr(execution, "started_by", "") or "").strip()
        domain = str(getattr(execution, "domain", "") or "").strip()
    else:
        return None
    if username in _NON_USER_ACTORS or not domain or len(username) > 150 or len(domain) > 100:
        return None
    return username, domain


def tool_caller_identity(execution) -> dict[str, Any] | None:
    """这些入口没有 include_children cookie，快照只覆盖流程所属组织。"""

    account = _caller_account(execution)
    team_id = _organization_id(getattr(execution, "team", None))
    if account is None or team_id is None:
        return None
    username, domain = account
    return accepted_tool_caller_identity(
        {
            "username": username,
            "domain": domain,
            "team_id": team_id,
            "include_children": False,
        }
    )


def tool_caller_locale(execution) -> str | None:
    """把账号上保存的语言交给智能体。查不到账号时不补默认值。"""

    account = _caller_account(execution)
    if account is None:
        return None
    username, domain = account
    user = User.objects.filter(username=username, domain=domain).only("locale").first()
    if user is None:
        return None
    locale = str(getattr(user, "locale", "") or "").strip()
    if not locale or len(locale) > 32:
        return None
    return locale
