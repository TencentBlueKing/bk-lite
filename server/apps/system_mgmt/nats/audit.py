# flake8: noqa
from .common import *  # noqa: F401,F403


@nats_client.register
def save_error_log(username, app, module, error_message, domain="domain.com"):
    """
    保存错误日志
    :param username: 用户名
    :param app: 应用模块
    :param module: 功能模块
    :param error_message: 错误信息
    :param domain: 域名
    """
    try:
        ErrorLog.objects.create(
            username=username,
            app=app,
            module=module,
            error_message=error_message,
            domain=domain,
        )
        return {"result": True, "message": "Error log saved successfully"}
    except Exception as e:
        logger.exception(f"Failed to save error log: {e}")
        return {"result": False, "message": str(e)}


@nats_client.register
def save_operation_log(username, source_ip, app, action_type, summary="", domain="domain.com", target_type="", target_id="", detail=None):
    """
    保存操作日志
    :param username: 用户名
    :param source_ip: 源IP地址
    :param app: 应用模块
    :param action_type: 操作类型 (create/update/delete/execute)
    :param summary: 操作概要
    :param domain: 域名
    :param target_type: 操作目标类型（可选）
    :param target_id: 操作目标ID（可选）
    :param detail: 操作详情 JSON（可选，默认空字典）
    """
    try:
        # 验证 action_type 是否合法
        valid_actions = [
            OperationLog.ACTION_CREATE,
            OperationLog.ACTION_UPDATE,
            OperationLog.ACTION_DELETE,
            OperationLog.ACTION_EXECUTE,
        ]
        if action_type not in valid_actions:
            return {
                "result": False,
                "message": f"Invalid action_type. Must be one of: {', '.join(valid_actions)}",
            }

        OperationLog.objects.create(
            username=username,
            source_ip=source_ip,
            app=app,
            action_type=action_type,
            summary=summary,
            domain=domain,
            target_type=target_type or "",
            target_id=str(target_id or ""),
            detail=detail or {},
        )
        return {"result": True, "message": "Operation log saved successfully"}
    except Exception as e:
        logger.exception(f"Failed to save operation log: {e}")
        return {"result": False, "message": str(e)}


def _operation_log_from_payload(item: dict):
    valid_actions = [
        OperationLog.ACTION_CREATE,
        OperationLog.ACTION_UPDATE,
        OperationLog.ACTION_DELETE,
        OperationLog.ACTION_EXECUTE,
    ]
    action_type = item.get("action_type")
    idempotency_key = str(item.get("idempotency_key") or "").strip()
    if action_type not in valid_actions or not idempotency_key:
        return None
    return OperationLog(
        username=item.get("username") or "",
        source_ip=item.get("source_ip") or "127.0.0.1",
        app=item.get("app") or "",
        action_type=action_type,
        summary=item.get("summary") or "",
        domain=item.get("domain") or "domain.com",
        target_type=item.get("target_type") or "",
        target_id=str(item.get("target_id") or ""),
        detail=item.get("detail") or {},
        idempotency_key=idempotency_key,
    )


@nats_client.register
def save_operation_logs(logs=None):
    """按幂等键批量写入操作日志。已存在的键不再插入。"""
    if not isinstance(logs, list):
        return {"result": False, "message": "logs must be a list"}
    rows = []
    for item in logs:
        if not isinstance(item, dict):
            return {"result": False, "message": "invalid operation log"}
        row = _operation_log_from_payload(item)
        if row is None:
            return {"result": False, "message": "invalid operation log"}
        rows.append(row)
    if not rows:
        return {"result": True, "saved": 0, "duplicates": 0}
    keys = [row.idempotency_key for row in rows]
    existing = set(OperationLog.objects.filter(idempotency_key__in=keys).values_list("idempotency_key", flat=True))
    to_create = [row for row in rows if row.idempotency_key not in existing]
    try:
        OperationLog.objects.bulk_create(to_create, ignore_conflicts=True)
    except Exception as exc:
        logger.exception("Failed to save operation logs: %s", exc.__class__.__name__)
        return {"result": False, "message": "failed to save operation logs"}
    return {"result": True, "saved": len(to_create), "duplicates": len(rows) - len(to_create)}
