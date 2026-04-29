from typing import Any, Dict, Optional

from django.contrib.auth.hashers import check_password
from langchain_core.runnables import RunnableConfig

from apps.cmdb.utils.base import get_default_group_id
from apps.core.mixinx import EncryptMixin
from apps.rpc.monitor import MonitorOperationAnaRpc
from apps.system_mgmt.models import User


def _extract_group_ids(user) -> list[int]:
    group_list = getattr(user, "group_list", []) or []
    if not group_list:
        return []
    if isinstance(group_list, list) and isinstance(group_list[0], dict):
        return [int(item["id"]) for item in group_list if "id" in item]
    return [int(item) for item in group_list]


def _get_configurable(config: Optional[RunnableConfig]) -> Dict[str, Any]:
    if not config:
        return {}
    if isinstance(config, dict):
        return config.get("configurable", {})
    return getattr(config, "configurable", {})


def resolve_monitor_runtime_params(
    config: Optional[RunnableConfig],
    username: Optional[str] = None,
    password: Optional[str] = None,
    domain: Optional[str] = None,
    team_id: Optional[int] = None,
) -> Dict[str, Any]:
    configurable = _get_configurable(config)
    return {
        "username": username or configurable.get("username"),
        "password": password or configurable.get("password"),
        "domain": domain or configurable.get("domain"),
        "team_id": team_id if team_id not in (None, "") else configurable.get("team_id"),
    }


def _describe_password_source(password: Optional[str], resolved_password: Optional[str]) -> str:
    if not password:
        return "empty"
    if not isinstance(password, str):
        return type(password).__name__
    if resolved_password != password:
        return "encrypted"
    return "plain"


def _resolve_plaintext_password(password: Optional[str]) -> Optional[str]:
    if not password or not isinstance(password, str):
        return password
    payload = {"value": password}
    EncryptMixin.decrypt_field("value", payload)
    return payload.get("value")


def authenticate_monitor_user(
    username: Optional[str], password: Optional[str], team_id: Optional[int] = None, domain: Optional[str] = None
) -> Dict[str, Any]:
    if not username:
        raise ValueError("username is required")
    if not password:
        raise ValueError("password is required")

    resolved_password = _resolve_plaintext_password(password)
    resolved_domain = domain or "domain.com"
    user = User.objects.filter(username=username, domain=resolved_domain).first()
    password_ok = bool(user) and check_password(resolved_password, user.password)
    if not user or not password_ok:
        raise ValueError("Username or password is incorrect")

    if team_id in (None, ""):
        group_ids = _extract_group_ids(user)
        resolved_team = group_ids[0] if group_ids else get_default_group_id()[0]
    else:
        try:
            resolved_team = int(team_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("team_id must be an integer") from exc

    return {"user": user.username, "domain": resolved_domain, "team": int(resolved_team), "include_children": False}


def wrap_success(data: Any) -> Dict[str, Any]:
    return {"success": True, "data": data}


def wrap_error(message: str) -> Dict[str, Any]:
    return {"success": False, "error": message}


def call_monitor_rpc(
    method_name: str,
    username: Optional[str],
    password: Optional[str],
    team_id: Optional[int] = None,
    domain: Optional[str] = None,
    **kwargs,
):
    try:
        user_info = authenticate_monitor_user(username=username, password=password, team_id=team_id, domain=domain)
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
