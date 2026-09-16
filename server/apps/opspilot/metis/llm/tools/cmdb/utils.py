from typing import Any, Dict, List, Optional

from langchain_core.runnables import RunnableConfig

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.metis.llm.tools.rpc_identity import resolve_rpc_user_info, unwrap_rpc_result, wrap_error, wrap_success
from apps.rpc.cmdb import CMDB


def normalize_query_list(query_list: Any) -> List[Dict[str, Any]]:
    if query_list is None:
        return []
    if isinstance(query_list, dict):
        query_list = [query_list]
    if not isinstance(query_list, list):
        return []

    normalized: List[Dict[str, Any]] = []

    def add_condition(item: Any) -> None:
        if not item or not isinstance(item, dict):
            return
        field = item.get("field")
        _type = item.get("type")
        if not field or not _type:
            return

        if _type == "time":
            start = item.get("start")
            end = item.get("end")
            if not start or not end:
                return
            normalized.append({"field": field, "type": _type, "start": start, "end": end})
            return

        if "value" not in item:
            return
        value = item.get("value")
        if value is None:
            return
        if isinstance(value, str) and value == "":
            return
        if isinstance(value, list) and not value:
            return
        normalized.append({"field": field, "type": _type, "value": value})

    def walk(node: Any) -> None:
        if node is None:
            return
        if isinstance(node, dict):
            add_condition(node)
            return
        if isinstance(node, list):
            for sub in node:
                walk(sub)

    walk(query_list)
    return normalized


def call_cmdb_params(method_name: str, config: Optional[RunnableConfig], **payload: Any) -> Dict[str, Any]:
    try:
        user_info = resolve_rpc_user_info(config, "CMDB")
        rpc = CMDB()
        method = getattr(rpc, method_name)
        result = method(
            params={
                "protocol_version": "2",
                **payload,
                "user_info": user_info,
                "operator": user_info["user"],
                "organization_ids": [user_info["team"]],
            }
        )
        return wrap_success(unwrap_rpc_result(result))
    except Exception as exc:
        logger.exception("cmdb llm tool rpc failed: method=%s error_type=%s", method_name, type(exc).__name__)
        return wrap_error(str(exc))


def call_cmdb_kwargs(method_name: str, config: Optional[RunnableConfig], **kwargs: Any) -> Dict[str, Any]:
    try:
        user_info = resolve_rpc_user_info(config, "CMDB")
        rpc = CMDB()
        method = getattr(rpc, method_name)
        result = method(user_info=user_info, **kwargs)
        return wrap_success(unwrap_rpc_result(result))
    except Exception as exc:
        logger.exception("cmdb llm tool rpc failed: method=%s error_type=%s", method_name, type(exc).__name__)
        return wrap_error(str(exc))
