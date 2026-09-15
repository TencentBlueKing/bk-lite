from typing import Any, Dict, List, Optional

from langchain_core.runnables import RunnableConfig

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.metis.llm.tools.rpc_identity import resolve_rpc_user_info, unwrap_rpc_result, wrap_error, wrap_success
from apps.rpc.alerts import AlertOperationAnaRpc


def call_alerts_rpc(method_name: str, config: Optional[RunnableConfig], **kwargs: Any) -> Dict[str, Any]:
    try:
        user_info = resolve_rpc_user_info(config, "告警中心")
        rpc = AlertOperationAnaRpc()
        method = getattr(rpc, method_name)
        result = method(user_info=user_info, **kwargs)
        return wrap_success(unwrap_rpc_result(result))
    except Exception as exc:
        logger.exception("alerts llm tool rpc failed: method=%s error_type=%s", method_name, type(exc).__name__)
        return wrap_error(str(exc))
