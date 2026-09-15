from typing import Any, Dict, Optional

from langchain_core.runnables import RunnableConfig

from apps.opspilot.services.caller_identity import CALLER_IDENTITY_CONFIG_KEY

_TRIGGER_SOURCE_LABELS = {
    "unattended": "定时任务/无人值守触发",
    "third_party": "第三方渠道触发",
    "interactive": "当前交互式调用",
}

_ENTRY_SOURCE_LABELS = {
    "celery": "Celery 定时任务",
    "nats": "NATS 触发",
    "enterprise_wechat": "企业微信",
    "enterprise_wechat_aibot": "企业微信智能机器人",
    "dingtalk": "钉钉",
    "wechat_official": "微信公众号",
}


def configurable_from_config(config: Optional[RunnableConfig]) -> Dict[str, Any]:
    if not isinstance(config, dict):
        return {}
    configurable = config.get("configurable")
    return configurable if isinstance(configurable, dict) else {}


def format_caller_identity_required_error(config: Optional[RunnableConfig], tool_label: str) -> str:
    configurable = configurable_from_config(config)
    entry_type = configurable.get("entry_type")
    trigger_type = configurable.get("trigger_type")

    if isinstance(entry_type, str) and entry_type in _ENTRY_SOURCE_LABELS:
        source = _ENTRY_SOURCE_LABELS[entry_type]
    elif isinstance(trigger_type, str) and trigger_type in _TRIGGER_SOURCE_LABELS:
        source = _TRIGGER_SOURCE_LABELS[trigger_type]
    else:
        source = "当前触发方式"

    return f"{tool_label}工具仅支持已登录的交互式 HTTP 调用（Web/Mobile/OpenAPI/Skill 执行等）。" f"{source}未提供调用方身份快照（caller_identity），无法使用{tool_label}工具。"


def resolve_rpc_user_info(config: Optional[RunnableConfig], tool_label: str) -> Dict[str, Any]:
    configurable = configurable_from_config(config)
    if CALLER_IDENTITY_CONFIG_KEY not in configurable:
        raise ValueError(format_caller_identity_required_error(config, tool_label))

    identity = configurable[CALLER_IDENTITY_CONFIG_KEY]
    if not isinstance(identity, dict):
        raise ValueError(f"{tool_label} caller_identity must be a dictionary")

    username = identity.get("username")
    if not isinstance(username, str) or not username.strip():
        raise ValueError(f"{tool_label} caller_identity.username must be a non-empty string")

    domain = identity.get("domain")
    if not isinstance(domain, str) or not domain.strip():
        raise ValueError(f"{tool_label} caller_identity.domain must be a non-empty string")

    team_id = identity.get("team_id")
    if type(team_id) is not int or team_id <= 0:
        raise ValueError(f"{tool_label} caller_identity.team_id must be a positive integer")

    include_children = identity.get("include_children")
    if type(include_children) is not bool:
        raise ValueError(f"{tool_label} caller_identity.include_children must be a boolean")

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


def unwrap_rpc_result(result: Any) -> Any:
    if isinstance(result, dict) and result.get("result") is False:
        raise ValueError(result.get("message") or "rpc call failed")
    if isinstance(result, dict) and "result" in result and "data" in result:
        return result.get("data")
    return result
