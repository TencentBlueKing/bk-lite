"""Ansible 回调身份签发、校验与终态收敛。"""

import hashlib
import hmac
import secrets
from uuid import uuid4

from django.db import transaction
from django.utils import timezone

from apps.core.logger import job_logger as logger
from apps.job_mgmt.constants import ExecutionStatus
from apps.job_mgmt.models import JobExecution
from apps.job_mgmt.services.completion_outbox_service import enqueue_terminal_effects, lock_reconcilable_terminal_effects
from apps.rpc.sensitive import sanitize_sensitive_data, summarize_ansible_callback

CALLBACK_CALLER = "ansible-executor"


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_ansible_callback_identity(execution: JobExecution) -> dict:
    """为一次远端提交签发不可复用的回调身份，只持久化令牌摘要。"""
    attempt_id = uuid4().hex
    token = secrets.token_urlsafe(32)
    execution.callback_attempt_id = attempt_id
    execution.callback_token_hash = _token_hash(token)
    execution.save(update_fields=["callback_attempt_id", "callback_token_hash", "updated_at"])
    return {
        "caller": CALLBACK_CALLER,
        "execution_id": execution.id,
        "attempt_id": attempt_id,
        "token": token,
    }


def build_ansible_callback_config(execution: JobExecution, subject: str) -> dict:
    return {
        "subject": subject,
        "timeout": 30,
        "context": issue_ansible_callback_identity(execution),
    }


def _valid_callback_identity(execution: JobExecution, data: dict) -> bool:
    context = data.get("callback_context")
    if not isinstance(context, dict):
        return False
    token = context.get("token")
    return bool(
        context.get("caller") == CALLBACK_CALLER
        and context.get("execution_id") == execution.id
        and context.get("attempt_id") == execution.callback_attempt_id
        and execution.callback_attempt_id
        and execution.callback_token_hash
        and isinstance(token, str)
        and hmac.compare_digest(_token_hash(token), execution.callback_token_hash)
    )


def _failure_results(execution, error_message: str, finished_at) -> list[dict]:
    safe_error = str(sanitize_sensitive_data(error_message))
    return [
        {
            "target_key": str(target.get("target_id", "")),
            "name": target.get("name", ""),
            "ip": target.get("ip", ""),
            "status": ExecutionStatus.FAILED,
            "stdout": "",
            "stderr": safe_error,
            "exit_code": 1,
            "error_message": safe_error,
            "started_at": execution.started_at.isoformat() if execution.started_at else "",
            "finished_at": finished_at.isoformat(),
        }
        for target in execution.target_list or []
    ]


def _target_map(target_list: list[dict]) -> dict[str, dict]:
    result = {}
    for target in target_list:
        result[str(target.get("ip", ""))] = target
        result[str(target.get("target_id", ""))] = target
    return result


def _host_execution_result(execution, target, host_result, finished_at: str) -> dict:
    host_key = str(host_result.get("host", ""))
    return {
        "target_key": str(target.get("target_id", "")),
        "name": target.get("name", host_key),
        "ip": target.get("ip", host_key),
        "status": ExecutionStatus.SUCCESS if host_result.get("status") == "success" else ExecutionStatus.FAILED,
        "stdout": str(sanitize_sensitive_data(str(host_result.get("stdout", "")))),
        "stderr": str(sanitize_sensitive_data(str(host_result.get("stderr", "")))),
        "exit_code": host_result.get("exit_code", 0),
        "error_message": str(sanitize_sensitive_data(str(host_result.get("error_message", "")))),
        "started_at": execution.started_at.isoformat() if execution.started_at else "",
        "finished_at": finished_at,
    }


def _missing_execution_result(execution, target, error_output: str, finished_at: str) -> dict:
    message = error_output or "未收到该目标执行结果"
    return {
        "target_key": str(target.get("target_id", "")),
        "name": target.get("name", ""),
        "ip": target.get("ip", ""),
        "status": ExecutionStatus.FAILED,
        "stdout": "",
        "stderr": message,
        "exit_code": 1,
        "error_message": message,
        "started_at": execution.started_at.isoformat() if execution.started_at else "",
        "finished_at": finished_at,
    }


def _normalize_results(execution, data: dict, finished_at) -> tuple[list[dict], str]:
    raw_result = data.get("result", [])
    if not (isinstance(raw_result, list) and raw_result and all(isinstance(item, dict) for item in raw_result)):
        error = f"回调结果格式非法: {sanitize_sensitive_data(raw_result)}"
        return _failure_results(execution, error, finished_at), "非法的新版本结果格式"

    target_list = execution.target_list or []
    targets_by_key = _target_map(target_list)
    seen_target_keys = set()
    results = []
    callback_finished_at = data.get("finished_at") or finished_at.isoformat()
    for host_result in raw_result:
        host_key = str(host_result.get("host", ""))
        target = targets_by_key.get(host_key)
        if not target:
            error = f"结果中的主机未匹配到目标: {host_key}"
            return _failure_results(execution, error, finished_at), error
        target_key = str(target.get("target_id", ""))
        if target_key in seen_target_keys:
            error = f"结果中的主机重复: {host_key}"
            return _failure_results(execution, error, finished_at), error
        seen_target_keys.add(target_key)
        results.append(_host_execution_result(execution, target, host_result, callback_finished_at))

    error_output = str(sanitize_sensitive_data(data.get("error", "")))
    for target in target_list:
        if str(target.get("target_id", "")) not in seen_target_keys:
            results.append(_missing_execution_result(execution, target, error_output, callback_finished_at))
    return results, ""


def _write_terminal(execution, data: dict, *, reconcile_cancel_timeout: bool):
    finished_at = timezone.now()
    results, validation_error = _normalize_results(execution, data, finished_at)
    was_cancelling = execution.status == ExecutionStatus.CANCELLING or reconcile_cancel_timeout
    if was_cancelling:
        final_status = ExecutionStatus.CANCELLED
    elif validation_error or any(item["status"] == ExecutionStatus.FAILED for item in results):
        final_status = ExecutionStatus.FAILED
    else:
        final_status = ExecutionStatus.SUCCESS

    execution.status = final_status
    execution.execution_results = results
    execution.finished_at = finished_at
    execution.success_count = sum(1 for item in results if item["status"] == ExecutionStatus.SUCCESS)
    execution.failed_count = sum(1 for item in results if item["status"] == ExecutionStatus.FAILED)
    execution.terminal_source = JobExecution.TerminalSource.ANSIBLE_CALLBACK
    execution.cancel_finalize_at = None
    execution.save(
        update_fields=[
            "status",
            "terminal_source",
            "cancel_finalize_at",
            "execution_results",
            "finished_at",
            "success_count",
            "failed_count",
            "updated_at",
        ]
    )
    enqueue_terminal_effects(execution, refresh_undelivered=reconcile_cancel_timeout)
    return validation_error


def handle_ansible_task_callback(data: dict):
    if not isinstance(data, dict):
        return {"success": False, "message": "回调数据必须为对象"}
    logger.info("[ansible_task_callback] %s", summarize_ansible_callback(data))
    task_id = data.get("task_id")
    if isinstance(task_id, str) and task_id.strip().isdecimal():
        task_id = int(task_id.strip())
    if isinstance(task_id, bool) or not isinstance(task_id, int) or task_id <= 0:
        message = "缺少 task_id" if task_id is None else "task_id 必须为正整数或其字符串形式"
        return {"success": False, "message": message}

    with transaction.atomic():
        execution = JobExecution.objects.select_for_update().filter(id=task_id).first()
        if execution is None:
            return {"success": False, "message": f"执行记录不存在: {task_id}"}
        if not _valid_callback_identity(execution, data):
            logger.warning("[ansible_task_callback] 回调身份校验失败: task_id=%s", task_id)
            return {"success": False, "message": "回调身份校验失败"}
        reconcile_cancel_timeout = (
            execution.status == ExecutionStatus.CANCELLED
            and execution.terminal_source == JobExecution.TerminalSource.CANCEL_TIMEOUT
        )
        if reconcile_cancel_timeout and not lock_reconcilable_terminal_effects(execution.id):
            return {"success": True, "message": "任务已处理"}
        if execution.status in ExecutionStatus.TERMINAL_STATES and not reconcile_cancel_timeout:
            return {"success": True, "message": "任务已处理"}
        validation_error = _write_terminal(execution, data, reconcile_cancel_timeout=reconcile_cancel_timeout)
        final_status = execution.status

    if validation_error:
        return {"success": False, "message": f"{validation_error}，已收敛到 {final_status.upper()}"}
    return {"success": True, "message": "回调处理成功"}
