from typing import Any, Dict, Optional

from langchain_core.runnables import RunnableConfig

from apps.opspilot.services.caller_identity import CALLER_IDENTITY_CONFIG_KEY
from apps.rpc.monitor import MonitorOperationAnaRpc

MONITOR_CALLER_IDENTITY_REQUIRED = (
    "Monitor only supports interactive HTTP calls with an authenticated caller; "
    "the current trigger does not provide caller_identity and is not supported."
)


def resolve_monitor_user_info(config: Optional[RunnableConfig]) -> Dict[str, Any]:
    """Build Monitor RPC identity from the validated runtime snapshot only."""

    configurable = config.get("configurable") if isinstance(config, dict) else None
    if not isinstance(configurable, dict) or CALLER_IDENTITY_CONFIG_KEY not in configurable:
        raise ValueError(MONITOR_CALLER_IDENTITY_REQUIRED)

    identity = configurable[CALLER_IDENTITY_CONFIG_KEY]
    if not isinstance(identity, dict):
        raise ValueError("Monitor caller_identity must be a dictionary")

    username = identity.get("username")
    if not isinstance(username, str) or not username.strip():
        raise ValueError("Monitor caller_identity.username must be a non-empty string")

    domain = identity.get("domain")
    if not isinstance(domain, str) or not domain.strip():
        raise ValueError("Monitor caller_identity.domain must be a non-empty string")

    team_id = identity.get("team_id")
    if type(team_id) is not int or team_id <= 0:
        raise ValueError("Monitor caller_identity.team_id must be a positive integer")

    include_children = identity.get("include_children")
    if type(include_children) is not bool:
        raise ValueError("Monitor caller_identity.include_children must be a boolean")

    return {
        "user": username,
        "domain": domain,
        "team": team_id,
        "include_children": include_children,
    }


def wrap_success(data: Any) -> Dict[str, Any]:
    return {"success": True, "data": data}


def wrap_error(message: str) -> Dict[str, Any]:
    return {"success": False, "error": message}


def call_monitor_rpc(
    method_name: str,
    config: Optional[RunnableConfig],
    **kwargs,
):
    try:
        user_info = resolve_monitor_user_info(config)
        rpc = MonitorOperationAnaRpc()
        method = getattr(rpc, method_name)
        result = method(user_info=user_info, **kwargs)
        if isinstance(result, dict) and result.get("result") is False:
            return wrap_error(result.get("message") or "monitor rpc call failed")
        if isinstance(result, dict) and "data" in result:
            return wrap_success(result.get("data"))
        return wrap_success(result)
    except Exception as exc:
        return wrap_error(str(exc))
