# -*- coding: utf-8 -*-
"""
Ansible Executor NATS RPC 封装

通过 NATS 调用 Ansible Executor 的 adhoc 接口，
实现远程 SSH/WinRM 命令执行。
"""

import asyncio
import json
import time
import uuid
from typing import Any, Dict, Optional

from core.infra.nats_utils import nats_request
from core.logger import logger, safe_log_value
from nats.errors import NoRespondersError

_QUEUED_STATUS = "queued"
_TERMINAL_STATUSES = {"success", "failed", "callback_failed"}
_ACCEPT_TIMEOUT_SECONDS = 30
_QUERY_TIMEOUT_SECONDS = 10
_POLL_BACKOFF_SECONDS = (0.5, 1.0, 2.0, 5.0)
_ADHOC_QUERY_TIMEOUT_LOG = "event=ansible_adhoc_query_timeout task_id=%s failed_stage=adhoc_query error_type=%s"
_ADHOC_QUERY_FAILED_LOG = "event=ansible_adhoc_query_failed task_id=%s failed_stage=adhoc_query error_type=RuntimeError"
_ADHOC_WAIT_TIMEOUT_LOG = "event=ansible_adhoc_wait_timeout task_id=%s failed_stage=adhoc_wait error_type=TimeoutError"


async def ansible_adhoc(
    ansible_node_id: str,
    host_credentials: list,
    module: str = "shell",
    module_args: str = "",
    hosts: str = "all",
    execute_timeout: int = 60,
    extra_vars: Optional[Dict[str, Any]] = None,
    callback: Optional[Dict[str, Any]] = None,
    task_id: Optional[str] = None,
    stream_remote_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    通过 NATS RPC 调用 Ansible Executor 执行 adhoc 命令

    Args:
        ansible_node_id: Ansible Executor 实例 ID（与云区域绑定）
        host_credentials: 主机凭据列表，格式:
            [{"host": "10.0.0.1", "user": "root", "password": "xxx",
              "connection": "ssh", "port": 22}]
        module: Ansible 模块名 (shell / win_shell / raw / ping 等)
        module_args: 模块参数（脚本内容或命令）
        hosts: 主机匹配表达式，默认 all
        execute_timeout: 单次执行超时（秒）
        extra_vars: 额外变量
        task_id: 任务 ID，不传则自动生成

    Returns:
        无 callback 时返回命令执行结果。Executor 先回入队回执时，入队等待最多 30 秒，
        再按 task_id 查询到终态，不把 ``accepted/queued`` 当成采集输出。
        带 callback 时入队等待仍为 ``execute_timeout + 30``，拿到回执后立即返回。

    Raises:
        TimeoutError: 入队或等待执行结果超时
        Exception: 其他异常
    """
    if not task_id:
        task_id = uuid.uuid4().hex

    request_data = {
        "inventory": "",
        "inventory_content": None,
        "host_credentials": host_credentials,
        "private_key_content": None,
        "private_key_passphrase": None,
        "hosts": hosts,
        "module": module,
        "module_args": module_args,
        "extra_vars": extra_vars or {},
        "callback": callback or {},
        "task_id": task_id,
        "execute_timeout": execute_timeout,
    }
    if stream_remote_type:
        request_data["stream_remote_type"] = stream_remote_type

    subject = f"ansible.adhoc.{ansible_node_id}"
    payload = json.dumps({"args": [request_data], "kwargs": {}}).encode()

    wait_timeout = execute_timeout + 30
    # 带 callback 的调用方只等入队回执，预算与改动前一致。
    # 无 callback 需要自己查询终态，入队等待单独封顶。
    accept_timeout = wait_timeout if callback else min(_ACCEPT_TIMEOUT_SECONDS, wait_timeout)

    logger.info(f"Ansible adhoc: node={ansible_node_id}, module={module}, " f"hosts={len(host_credentials)}, timeout={execute_timeout}s")

    try:
        result = await nats_request(subject, payload=payload, timeout=accept_timeout)
    except NoRespondersError:
        # 没有任何 ansible-executor 订阅该 subject：通常是 ansible_node_id 配置错误
        # （例如落到了 "default"）或对应云区域的执行节点离线。立即报错，避免空等超时。
        logger.error(
            f"Ansible adhoc no responders: subject={subject}, node={ansible_node_id}, "
            f"task_id={task_id}. 没有 ansible-executor 订阅该节点，请检查 ansible_node_id "
            f"是否正确以及对应云区域的执行节点是否在线"
        )
        raise RuntimeError(
            f"No ansible executor subscribed for node '{ansible_node_id}' "
            f"(subject={subject}); check ansible_node_id / cloud region binding "
            f"and that the executor is online"
        )
    except TimeoutError:
        logger.error(f"Ansible adhoc NATS timeout: node={ansible_node_id}, task_id={task_id}, " f"timeout={accept_timeout}s")
        raise
    except Exception as e:
        logger.error(f"Ansible adhoc NATS error: node={ansible_node_id}, task_id={task_id}, " f"error={type(e).__name__}: {e}")
        raise

    if callback or not _is_queued_ack(result):
        logger.info(f"Ansible adhoc completed: task_id={task_id}, success={result.get('success')}")
        return result

    queued_task_id = str((result.get("result") or {}).get("task_id") or task_id)
    logger.info(
        "Ansible adhoc queued: node=%s task_id=%s, waiting for execution",
        ansible_node_id,
        queued_task_id,
    )
    result = await _wait_for_adhoc_result(
        ansible_node_id,
        queued_task_id,
        deadline=time.monotonic() + wait_timeout,
    )
    logger.info(f"Ansible adhoc completed: task_id={queued_task_id}, success={result.get('success')}")
    return result


def _is_queued_ack(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    inner = result.get("result")
    return isinstance(inner, dict) and inner.get("accepted") is True and inner.get("status") == _QUEUED_STATUS


def _execution_result_from_task(task: Dict[str, Any], task_id: str) -> Dict[str, Any]:
    stored = task.get("result") or {}
    if isinstance(stored, dict) and "success" in stored and "result" in stored:
        return {
            "success": bool(stored.get("success")),
            "result": stored.get("result"),
            "status": stored.get("status") or task.get("status"),
            "error": stored.get("error") or "",
            "task_id": stored.get("task_id") or task_id,
        }
    status = str(task.get("execution_status") or task.get("status") or "")
    return {
        "success": status == "success",
        "result": stored,
        "status": status,
        "error": "",
        "task_id": task_id,
    }


def _poll_delay(attempt: int) -> float:
    index = min(max(attempt, 0), len(_POLL_BACKOFF_SECONDS) - 1)
    return _POLL_BACKOFF_SECONDS[index]


def _bounded_query_error(response: Any) -> str:
    error = response.get("error") if isinstance(response, dict) else ""
    text = str(error or "ansible task query failed").replace("\r", " ").replace("\n", " ")
    return text[:200]


def _wait_timeout(task_id: str) -> TimeoutError:
    logger.warning(_ADHOC_WAIT_TIMEOUT_LOG, safe_log_value(task_id))
    return TimeoutError(f"Ansible adhoc timed out waiting for task {task_id}")


async def _wait_for_adhoc_result(ansible_node_id: str, task_id: str, deadline: float) -> Dict[str, Any]:
    subject = f"ansible.task.query.{ansible_node_id}"
    payload = json.dumps({"args": [{"task_id": task_id}], "kwargs": {}}).encode()
    attempt = 0
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise _wait_timeout(task_id)
        try:
            response = await nats_request(subject, payload=payload, timeout=min(_QUERY_TIMEOUT_SECONDS, remaining))
        except TimeoutError as exc:
            logger.warning(_ADHOC_QUERY_TIMEOUT_LOG, safe_log_value(task_id), type(exc).__name__)
            if deadline - time.monotonic() <= 0:
                raise TimeoutError(f"Ansible adhoc timed out waiting for task {task_id}") from exc
            await asyncio.sleep(min(_poll_delay(attempt), max(0.0, deadline - time.monotonic())))
            attempt += 1
            continue
        if isinstance(response, dict) and response.get("success") is False:
            logger.warning(_ADHOC_QUERY_FAILED_LOG, safe_log_value(task_id))
            raise RuntimeError(f"Ansible adhoc query failed for task {task_id}: {_bounded_query_error(response)}")
        task = response.get("result") if isinstance(response, dict) else None
        if isinstance(response, dict) and response.get("success") and isinstance(task, dict):
            status = str(task.get("execution_status") or task.get("status") or "")
            if status in _TERMINAL_STATUSES:
                return _execution_result_from_task(task, task_id)
        await asyncio.sleep(min(_poll_delay(attempt), max(0.0, deadline - time.monotonic())))
        attempt += 1
