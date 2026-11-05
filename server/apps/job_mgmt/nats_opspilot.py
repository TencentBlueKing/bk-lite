"""OpsPilot 作业的 NATS 入口。未签名的请求体不能指定组织或执行人。"""

import nats_client
from apps.job_mgmt.services.opspilot_gateway import run_opspilot_action, run_opspilot_distribute
from apps.rpc.job_opspilot import ACTION_DISTRIBUTE


@nats_client.register
def job_opspilot_action(data: dict):
    """签名校验后执行查询、脚本或文件分发。文件字节不放在这条消息里。"""

    payload = data if isinstance(data, dict) else {}
    if payload.get("action") == ACTION_DISTRIBUTE:
        return run_opspilot_distribute(
            payload.get("_internal_auth"),
            payload.get("user_info"),
            payload.get("body") or {},
            payload.get("files") or [],
        )
    return run_opspilot_action(
        payload.get("action"),
        payload.get("_internal_auth"),
        payload.get("user_info"),
        payload.get("body") or {},
    )
