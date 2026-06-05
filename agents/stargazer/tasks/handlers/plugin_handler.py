# -- coding: utf-8 --
# @File: plugin_handler.py
# @Time: 2025/12/19
# @Author: AI Assistant
"""
插件采集任务处理器
处理各种插件（MySQL、Redis、Nginx等）的数据采集任务
"""

import time
import traceback
import ntpath
import posixpath
from datetime import datetime, timezone, timedelta
from typing import Dict, Any
from sanic.log import logger


def _is_config_file_callback(params: Dict[str, Any]) -> bool:
    return (
        str(params.get("callback_subject") or "") == "receive_config_file_result"
        or str(params.get("plugin_name") or "") == "config_file_info"
        or str(params.get("model_id") or "") == "config_file"
    )


def _resolve_callback_identity(params: Dict[str, Any]) -> Dict[str, str]:
    host = str(params.get("host") or params.get("instance_name") or "")

    return {
        "instance_id": host,
        "instance_name": host,
        "model_id": str(
            params.get("target_model_id")
            or params.get("model_id")
            or "host"
        ),
    }


def _extract_file_name(file_path: str) -> str:
    normalized_path = str(file_path or "").strip()
    if not normalized_path:
        return ""
    if ":\\" in normalized_path or "\\" in normalized_path:
        return ntpath.basename(normalized_path)
    return posixpath.basename(normalized_path)


async def collect_plugin_task(
    ctx: Dict, params: Dict[str, Any], task_id: str
) -> Dict[str, Any]:
    """
    插件采集任务处理器

    Args:
        ctx: ARQ 上下文
        params: 采集参数，包含 plugin_name 等
        task_id: 任务ID

    Returns:
        任务执行结果
    """
    plugin_name = params.get("plugin_name")
    metrics_published = False
    execution_result = None
    logger.info(f"[Plugin Task] Processing: {task_id}, plugin: {plugin_name}")

    try:
        # 导入服务和工具（延迟导入避免循环依赖）
        from core.credential_state_cache import CredentialStateCache
        from core.task_queue import get_task_queue
        from service.collection_service import CollectionService
        from tasks.utils.nats_helper import publish_metrics_to_nats
        from tasks.utils.nats_helper import publish_callback_to_nats

        # 执行采集
        collect_service = CollectionService(params)
        metrics_data = await collect_service.collect()
        execution_result = _build_credential_execution_result(params, metrics_data)

        logger.info(f"[Plugin Task] {task_id} completed successfully")

        if params.get("callback_subject"):
            await _handle_multicred_pre_callback(
                params, task_id, execution_result, CredentialStateCache, get_task_queue
            )
            await publish_callback_to_nats(metrics_data, params, task_id)
        else:
            delivered_count = await publish_metrics_to_nats(ctx, metrics_data, params, task_id)
            metrics_published = delivered_count > 0
            await _handle_multicred_post_execute(
                params, task_id, execution_result, CredentialStateCache, get_task_queue
            )

        return {
            "task_id": task_id,
            "status": "success",
            "plugin_name": plugin_name,
            "completed_at": int(time.time() * 1000),
        }

    except Exception as e:
        logger.error(
            f"[Plugin Task] {task_id} failed: {str(e)}\n{traceback.format_exc()}"
        )

        # 导入工具函数
        from tasks.utils.nats_helper import MetricsPublishError
        from tasks.utils.nats_helper import publish_metrics_to_nats
        from tasks.utils.nats_helper import publish_callback_to_nats
        from tasks.utils.metrics_helper import generate_plugin_error_metrics
        from core.credential_state_cache import CredentialStateCache
        from core.task_queue import get_task_queue

        real_metrics_delivered = metrics_published or (
            isinstance(e, MetricsPublishError) and getattr(e, "success_count", 0) > 0
        )
        preserved_execution_result = (
            execution_result
            if isinstance(execution_result, dict) and not execution_result.get("success", True)
            else None
        )
        execution_result = preserved_execution_result or _build_credential_execution_result(params, None, e)
        await _handle_multicred_post_execute(
            params, task_id, execution_result, CredentialStateCache, get_task_queue
        )

        if params.get("callback_subject"):
            identity = _resolve_callback_identity(params) if _is_config_file_callback(params) else {
                "instance_id": str(params.get("instance_id") or params.get("host") or ""),
                "model_id": str(params.get("target_model_id") or params.get("model_id") or "host"),
            }
            await publish_callback_to_nats(
                {
                    "collect_task_id": params.get("collect_task_id"),
                    "instance_id": identity["instance_id"],
                    "instance_name": identity["instance_name"],
                    "model_id": identity["model_id"],
                    "file_path": params.get("config_file_path", ""),
                    "file_name": _extract_file_name(params.get("config_file_path", "")),
                    "version": str(int(time.time())),
                    "status": "error",
                    "size": 0,
                    "error": str(e),
                    "content_base64": "",
                },
                params,
                task_id,
            )
        elif not real_metrics_delivered:
            error_metrics = generate_plugin_error_metrics(params, e)
            await publish_metrics_to_nats(ctx, error_metrics, params, task_id)

        return {
            "task_id": task_id,
            "status": "failed",
            "error": str(e),
            "plugin_name": plugin_name,
            "completed_at": int(time.time() * 1000),
        }


def _build_credential_execution_result(params: Dict[str, Any], metrics_data: Any, error: Exception | None = None) -> Dict[str, Any]:
    host = str(params.get("host") or "")
    credential_id = str(params.get("credential_id") or "")
    success = error is None and not _is_failed_metrics_payload(metrics_data)
    error_message = ""
    if error is not None:
        error_message = str(error)
    elif not success:
        error_message = _extract_metrics_error(metrics_data)

    failure_kind = ""
    if not success:
        failure_kind = _classify_failure_kind(error_message)

    return {
        "collect_task_id": params.get("collect_task_id"),
        "host": host,
        "credential_id": credential_id,
        "credential_index": params.get("credential_index"),
        "model_id": params.get("model_id"),
        "plugin_name": params.get("plugin_name"),
        "success": success,
        "failure_kind": failure_kind,
        "error_message": error_message,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "snapshot": {"host": host, "model_id": params.get("model_id")},
    }


async def _handle_multicred_pre_callback(params, task_id, execution_result, cache_cls, get_queue_func):
    await _handle_multicred_post_execute(params, task_id, execution_result, cache_cls, get_queue_func)


async def _handle_multicred_post_execute(params, task_id, execution_result, cache_cls, get_queue_func):
    credentials_pool = params.get("credentials_pool") or []
    collect_task_id = params.get("collect_task_id")
    host = params.get("host")
    credential_id = params.get("credential_id")
    credential_index = int(params.get("credential_index") or 0)
    if not credentials_pool or collect_task_id in (None, "") or not host or not credential_id:
        return

    await cache_cls.append_result_event(execution_result)

    if execution_result["success"]:
        await cache_cls.mark_success(collect_task_id, host, credential_id)
        return

    if execution_result["failure_kind"] != "credential":
        await cache_cls.clear_success(collect_task_id, host)
        return

    await cache_cls.clear_success(collect_task_id, host)

    consecutive_failures = int(params.get("credential_failures", 0)) + 1
    cooldown_level = 1 if consecutive_failures == 1 else 2 if consecutive_failures == 2 else 3
    cooldown_hours = _cooldown_hours_for_failure(consecutive_failures)
    next_retry_at = (datetime.now(timezone.utc) + timedelta(hours=cooldown_hours)).isoformat()
    await cache_cls.mark_failure(
        collect_task_id,
        host,
        credential_id,
        execution_result["error_message"],
        cooldown_level,
        consecutive_failures,
        next_retry_at,
    )
    next_task = await _build_next_credential_task(params, credential_index, consecutive_failures, cache_cls)
    if not next_task:
        return
    queue = get_queue_func()
    await queue.enqueue_collect_task(next_task)


async def _build_next_credential_task(
    params: Dict[str, Any],
    current_index: int,
    consecutive_failures: int,
    cache_cls,
) -> Dict[str, Any] | None:
    credentials_pool = params.get("credentials_pool") or []
    collect_task_id = params.get("collect_task_id")
    host = params.get("host")
    for next_index in range(current_index + 1, len(credentials_pool)):
        next_credential = dict(credentials_pool[next_index])
        failure_state = await cache_cls.get_failure_state(collect_task_id, host, next_credential.get("credential_id"))
        if failure_state.get("is_cooled"):
            continue
        return {
            **{k: v for k, v in params.items() if k not in next_credential and k != "credential_failures"},
            **next_credential,
            "credential_index": next_index,
            "credentials_pool": credentials_pool,
            "credential_failures": consecutive_failures,
        }
    return None


def _is_failed_metrics_payload(metrics_data: Any) -> bool:
    if metrics_data is None:
        return True
    if isinstance(metrics_data, dict):
        return str(metrics_data.get("status") or "").lower() == "error"
    text = str(metrics_data)
    return 'status="error"' in text or "cmdb_collect_error" in text


def _extract_metrics_error(metrics_data: Any) -> str:
    if isinstance(metrics_data, dict):
        return str(metrics_data.get("error") or metrics_data.get("cmdb_collect_error") or "")
    text = str(metrics_data or "")
    if "cmdb_collect_error" in text:
        return text
    return "collection failed"


def _classify_failure_kind(error_message: str) -> str:
    text = str(error_message or "").lower()
    credential_keywords = ("auth", "password", "credential", "denied", "unauthorized", "community", "authkey", "privkey")
    if any(keyword in text for keyword in credential_keywords):
        return "credential"
    return "task"


def _cooldown_hours_for_failure(consecutive_failures: int) -> int:
    if consecutive_failures <= 1:
        return 1
    if consecutive_failures == 2:
        return 4
    return 24
