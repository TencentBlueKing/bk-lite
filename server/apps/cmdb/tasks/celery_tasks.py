# -- coding: utf-8 --
# @File: tasks.py
# @Time: 2025/3/3 15:34
# @Author: windyzhao
import os
import time
from datetime import timedelta
from uuid import uuid4

from celery import shared_task
from django.db import transaction
from django.db.models import Q
from django.utils.timezone import now

from apps.cmdb.collection.collect_plugin.base import is_failed_vm_metric
from apps.cmdb.collection.collect_tasks.job_collect import JobCollect
from apps.cmdb.collection.collect_tasks.protocol_collect import ProtocolCollect
from apps.cmdb.constants.constants import CollectPluginTypes, CollectRunStatusType
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.services.collect_dispatch_service import CollectDispatchService
from apps.cmdb.services.collect_tool_service import CollectToolService
from apps.cmdb.services.subscription_task import SubscriptionTaskService
from apps.cmdb.tasks.node_mgmt_sync import run_collect, run_sync
from apps.core.logger import cmdb_logger as logger

_COLLECT_TERMINAL_STATUSES = (
    CollectRunStatusType.SUCCESS,
    CollectRunStatusType.ERROR,
    CollectRunStatusType.TIME_OUT,
    CollectRunStatusType.FORCE_STOP,
    CollectRunStatusType.PARTIAL_SUCCESS,
)


def _read_bounded_int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    raw_value = os.getenv(name)
    try:
        value = default if raw_value is None else int(raw_value)
    except (TypeError, ValueError):
        logger.warning("%s must be an integer; using default=%s", name, default)
        return default

    bounded_value = min(max(value, minimum), maximum)
    if bounded_value != value:
        logger.warning("%s is outside [%s, %s]; using %s", name, minimum, maximum, bounded_value)
    return bounded_value


PUBLIC_ENUM_SNAPSHOT_MAX_RETRIES = _read_bounded_int_env(
    "CMDB_PUBLIC_ENUM_SNAPSHOT_MAX_RETRIES", 3, 0, 10
)
PUBLIC_ENUM_SNAPSHOT_RETRY_BASE_SECONDS = _read_bounded_int_env(
    "CMDB_PUBLIC_ENUM_SNAPSHOT_RETRY_BASE_SECONDS", 10, 1, 3600
)
PUBLIC_ENUM_SNAPSHOT_RETRY_MAX_SECONDS = 3600


def _is_unhelpful_error_message(message: str) -> bool:
    text = str(message or "").strip()
    return text in {"0", "1", "None", "null", "False", "True"}


def _build_exception_args_message(err: Exception) -> str:
    args = getattr(err, "args", ()) or ()
    if not args:
        return ""
    rendered = ", ".join(repr(arg) for arg in args)
    return f"{err.__class__.__name__}({rendered})"


def _build_safe_error_message(err: Exception) -> str:
    message = str(err).strip()
    if message and not _is_unhelpful_error_message(message):
        return message

    attr_message = getattr(err, "message", None)
    if isinstance(attr_message, str) and attr_message.strip():
        return attr_message.strip()

    detail = getattr(err, "detail", None)
    if isinstance(detail, str) and detail.strip():
        return detail.strip()

    args_message = _build_exception_args_message(err)
    if args_message:
        return args_message

    return err.__class__.__name__


def _build_traceback_excerpt(traceback_text: str, max_lines: int = 16) -> str:
    if not traceback_text:
        return ""
    lines = [line.rstrip() for line in str(traceback_text).splitlines() if line.strip()]
    if not lines:
        return ""
    return "\n".join(lines[-max_lines:])


def _build_traceback_location(traceback_text: str) -> str:
    if not traceback_text:
        return ""
    lines = [line.strip() for line in str(traceback_text).splitlines() if line.strip()]
    file_lines = [line for line in lines if line.startswith('File "')]
    return file_lines[-1] if file_lines else ""


def _claim_collect_task_execution(instance_id, start_time, execution_id=None):
    """以数据库 CAS 领取一次采集执行。

    ``RUNNING + execution_id + 空摘要 + 无 claim`` 表示生产者已排队但尚未领取；
    execution_id 标识业务执行，独立的 execution_claim_token 标识唯一 worker。
    Beat 每轮使用不同 request.id，新一轮仅能从上一轮终态进入；同 request.id 重投
    不能重开终态，也不能共享 owner 身份。
    """
    queryset = CollectModels._default_manager.filter(id=instance_id)
    execution_id = execution_id or str(uuid4())
    claim_token = f"{execution_id}:{uuid4().hex}"
    update_fields = {
        "exec_status": CollectRunStatusType.RUNNING,
        "exec_time": start_time,
        "task_id": execution_id,
        "execution_claim_token": claim_token,
    }
    queued_execution = (
        Q(exec_status=CollectRunStatusType.NOT_START)
        | (
            Q(
                exec_status=CollectRunStatusType.RUNNING,
                task_id=execution_id,
                collect_digest={},
            )
            & (Q(execution_claim_token__isnull=True) | ~Q(execution_claim_token__startswith=f"{execution_id}:"))
        )
        | (Q(exec_status__in=_COLLECT_TERMINAL_STATUSES) & ~Q(task_id=execution_id))
    )
    updated = queryset.filter(queued_execution).update(**update_fields)
    if not updated:
        return None
    instance = CollectModels._default_manager.filter(
        id=instance_id,
        exec_status=CollectRunStatusType.RUNNING,
        task_id=execution_id,
        execution_claim_token=claim_token,
    )
    instance = instance.first()
    if instance:
        instance.claim_token = claim_token
    return instance


def _save_collect_result_if_current(instance_id, execution_id, claim_token, values):
    """仅允许当前 execution 的唯一 owner 提交结果。"""
    terminal_values = {**values, "execution_claim_token": None}
    updated = bool(
        CollectModels._default_manager.filter(
            id=instance_id,
            task_id=execution_id,
            exec_status=CollectRunStatusType.RUNNING,
            execution_claim_token=claim_token,
        ).update(**terminal_values)
    )
    if not updated:
        # 外部回调可能先一步写入终态；仅释放同 execution、同 owner 的内部 claim，
        # 不触碰回调已经提交的业务结果。旧 worker 无法匹配新 execution 的 token。
        CollectModels._default_manager.filter(
            id=instance_id,
            task_id=execution_id,
            execution_claim_token=claim_token,
            exec_status__in=_COLLECT_TERMINAL_STATUSES,
        ).update(execution_claim_token=None)
    return updated


def _resolve_execution_timeout_seconds(task):
    configured = (task.params or {}).get("task_job_timeout")
    for value in (configured, os.getenv("TASK_JOB_TIMEOUT"), 600):
        try:
            timeout_seconds = int(value)
        except (TypeError, ValueError):
            continue
        if timeout_seconds > 0:
            return timeout_seconds
    return 600


def _timeout_collect_task_if_current(task, checked_at):
    if not task.exec_time:
        return False
    deadline_seconds = _resolve_execution_timeout_seconds(task)
    if checked_at <= task.exec_time + timedelta(seconds=deadline_seconds):
        return False

    collect_digest = {
        "message": "采集执行已超过 deadline，状态置为超时",
        "execution_id": task.task_id,
        "deadline_seconds": deadline_seconds,
        "started_at": task.exec_time.isoformat(),
    }
    return bool(
        CollectModels._default_manager.filter(
            id=task.id,
            task_id=task.task_id,
            exec_status=CollectRunStatusType.RUNNING,
            exec_time=task.exec_time,
            execution_claim_token=task.execution_claim_token,
        ).update(
            exec_status=CollectRunStatusType.TIME_OUT,
            execution_claim_token=None,
            collect_digest=collect_digest,
            updated_at=checked_at,
        )
    )


def _node_mgmt_collect_version_allowed(instance_id, execution_id, config_id, config_version):
    if config_id is None or config_version is None:
        return True
    from apps.cmdb.models.node_mgmt_sync import NodeMgmtSyncConfig

    with transaction.atomic():
        config = NodeMgmtSyncConfig.objects.select_for_update().filter(pk=config_id).first()
        if config and config.auto_collect_enabled and config.version == config_version:
            return True
        CollectModels._default_manager.filter(
            id=instance_id,
            task_id=execution_id,
            exec_status=CollectRunStatusType.RUNNING,
        ).update(
            exec_status=CollectRunStatusType.ERROR,
            execution_claim_token=None,
            collect_digest={"message": "NODE_MGMT_CONFIG_STALE"},
            updated_at=now(),
        )
        return False


def _count_raw_collection_outcomes(raw_data) -> tuple[int, int]:
    """统计已经扁平化到原始详情中的 VM 成功、失败指标行数。"""
    rows = [row for row in (raw_data or []) if isinstance(row, dict)]
    failed = sum(1 for row in rows if is_failed_vm_metric({"metric": row}))
    return len(rows) - failed, failed


@shared_task(
    bind=True,
    max_retries=2,
    name="apps.cmdb.tasks.celery_tasks.trigger_first_collection",
)
def trigger_first_collection(self, task_id, expected_fingerprint, reason):
    from apps.cmdb.constants import constants as cmdb_constants
    from apps.cmdb.services.first_collection_policy import FirstCollectionPolicy
    from apps.cmdb.services.stargazer_collect_trigger import (
        StargazerCollectPermanentError,
        StargazerCollectRetryableError,
        StargazerCollectTriggerClient,
    )

    started_at = time.monotonic()
    if not cmdb_constants.CMDB_FIRST_COLLECTION_ENABLED:
        return {"status": "disabled", "task_id": task_id, "reason": reason}

    task = CollectModels._default_manager.filter(id=task_id).first()
    if not task:
        return {"status": "missing", "task_id": task_id, "reason": reason}
    if not FirstCollectionPolicy.is_eligible(task):
        return {"status": "ineligible", "task_id": task_id, "reason": reason}

    cycle_minutes = int(task.cycle_value)
    attempt = int(self.request.retries) + 1
    current_fingerprint = FirstCollectionPolicy.fingerprint(task)
    fingerprint_short = current_fingerprint[:12]
    if current_fingerprint != expected_fingerprint:
        logger.info(
            "[FirstCollection] 跳过过期配置 task_id=%s fingerprint=%s reason=%s "
            "cycle=%s attempt=%s elapsed_ms=%s result=stale",
            task_id,
            fingerprint_short,
            reason,
            cycle_minutes,
            attempt,
            int((time.monotonic() - started_at) * 1000),
        )
        return {"status": "stale", "task_id": task_id, "reason": reason}

    try:
        result = StargazerCollectTriggerClient().trigger(task)
    except StargazerCollectRetryableError as exc:
        retry_number = int(self.request.retries)
        if retry_number >= self.max_retries:
            logger.warning(
                "[FirstCollection] 可重试次数耗尽 task_id=%s fingerprint=%s reason=%s "
                "cycle=%s attempt=%s elapsed_ms=%s error_type=%s "
                "result=failed retry_exhausted=true",
                task_id,
                fingerprint_short,
                reason,
                cycle_minutes,
                attempt,
                int((time.monotonic() - started_at) * 1000),
                exc.__class__.__name__,
            )
            return {
                "status": "failed",
                "task_id": task_id,
                "reason": reason,
                "retry_exhausted": True,
            }

        countdown = 10 * (2**retry_number)
        logger.warning(
            "[FirstCollection] 可重试失败 task_id=%s fingerprint=%s reason=%s "
            "cycle=%s attempt=%s elapsed_ms=%s error_type=%s",
            task_id,
            fingerprint_short,
            reason,
            cycle_minutes,
            attempt,
            int((time.monotonic() - started_at) * 1000),
            exc.__class__.__name__,
        )
        raise self.retry(exc=exc, countdown=countdown)
    except StargazerCollectPermanentError as exc:
        logger.warning(
            "[FirstCollection] 永久失败 task_id=%s fingerprint=%s reason=%s "
            "cycle=%s attempt=%s elapsed_ms=%s error_type=%s",
            task_id,
            fingerprint_short,
            reason,
            cycle_minutes,
            attempt,
            int((time.monotonic() - started_at) * 1000),
            exc.__class__.__name__,
        )
        return {"status": "failed", "task_id": task_id, "reason": reason}

    logger.info(
        "[FirstCollection] 已接收 task_id=%s fingerprint=%s reason=%s "
        "cycle=%s attempt=%s elapsed_ms=%s result=%s",
        task_id,
        fingerprint_short,
        reason,
        cycle_minutes,
        attempt,
        int((time.monotonic() - started_at) * 1000),
        result.status,
    )
    return {
        "status": result.status,
        "task_id": task_id,
        "reason": reason,
        "total": result.total,
        "accepted": result.accepted,
    }


@shared_task(bind=True)
def sync_collect_task(self, instance_id, execution_id=None, node_config_id=None, node_config_version=None):
    """
    同步采集任务
    """
    logger.info("[CollectTask] 开始采集任务 task_id=%s", instance_id)
    start_time = now()
    execution_id = execution_id or self.request.id or str(uuid4())
    if not _node_mgmt_collect_version_allowed(
        instance_id,
        execution_id,
        node_config_id,
        node_config_version,
    ):
        logger.info("[CollectTask] 节点同步配置已变化，跳过旧版本任务 task_id=%s", instance_id)
        return
    instance = _claim_collect_task_execution(instance_id, start_time, execution_id=execution_id)
    if not instance:
        exists = CollectModels._default_manager.filter(id=instance_id).exists()
        if exists:
            logger.info("[CollectTask] 采集任务已在执行中，跳过重复执行 task_id=%s", instance_id)
        else:
            logger.warning("[CollectTask] 采集任务不存在，跳过执行 task_id=%s", instance_id)
        return
    execution_id = instance.task_id
    claim_token = instance.claim_token
    from apps.cmdb.services.collect_service import CollectModelService

    exec_error_message = ""
    exec_traceback_excerpt = ""
    exec_traceback_location = ""
    task_exec_status = CollectRunStatusType.SUCCESS
    config_file_pending = False
    try:
        CollectModelService.repair_host_cloud_snapshot(instance)
        if CollectDispatchService.should_dispatch(instance):
            result, format_data = CollectDispatchService.execute_task(instance)
        else:
            if instance.is_job:
                collect = JobCollect(task=instance)
                result, format_data = collect.main()
            else:
                collect = ProtocolCollect(task=instance)
                result, format_data = collect.main()

        config_file_pending = instance.task_type == CollectPluginTypes.CONFIG_FILE and (result.get("config_file") or {}).get("status") == "pending"
        if config_file_pending:
            instance.exec_status = CollectRunStatusType.RUNNING
        else:
            instance.exec_status = CollectRunStatusType.SUCCESS

    except Exception as err:
        import traceback

        traceback_text = traceback.format_exc()
        logger.error(
            "[CollectTask] 同步采集数据失败 task_id=%s, error=%s",
            instance_id,
            traceback_text,
        )
        exec_error_message = "采集任务执行失败（task_id={}）：{}".format(instance_id, _build_safe_error_message(err))
        exec_traceback_excerpt = _build_traceback_excerpt(traceback_text)
        exec_traceback_location = _build_traceback_location(traceback_text)
        if exec_traceback_location:
            exec_error_message = f"{exec_error_message} @ {exec_traceback_location}"
        result = {}
        format_data = {}
        instance.exec_status = CollectRunStatusType.ERROR
        task_exec_status = CollectRunStatusType.ERROR

    try:
        instance.collect_data = result
        instance.format_data = format_data
        collect_digest = {
            "add": len(format_data.get("add", [])),
            "add_error": len([i for i in format_data.get("add", []) if i.get("_status") != "success"]),
            "update": len(format_data.get("update", [])),
            "update_error": len([i for i in format_data.get("update", []) if i.get("_status") != "success"]),
            "delete": len(format_data.get("delete", [])),
            "delete_error": len([i for i in format_data.get("delete", []) if i.get("_status") != "success"]),
            "association": len(format_data.get("association", [])),
            "association_error": len([i for i in format_data.get("association", []) if i.get("_status") != "success"]),
            "all": format_data.get("all", 0),  # 总数是发现的正常数据总数，例如：扫描了10个ip，其中6个是真的ip，4个ip不存在，总数为6
        }
        raw_data = format_data.get("__raw_data__", [])
        collect_success, collect_failed = _count_raw_collection_outcomes(raw_data)
        collect_digest["collect_success"] = collect_success
        collect_digest["collect_failed"] = collect_failed
        # add是需要新增的数据，add_success是实际新增成功的数据（实际到cmdb的数据），add_error是新增失败的数据，其他以此类推
        collect_digest["add_success"] = collect_digest["add"] - collect_digest["add_error"]
        collect_digest["update_success"] = collect_digest["update"] - collect_digest["update_error"]
        collect_digest["delete_success"] = collect_digest["delete"] - collect_digest["delete_error"]
        collect_digest["association_success"] = collect_digest["association"] - collect_digest["association_error"]
        # 如果任务执行失败，添加错误信息提示
        if task_exec_status == CollectRunStatusType.ERROR:
            collect_digest["message"] = exec_error_message
            if exec_traceback_excerpt:
                collect_digest["traceback"] = exec_traceback_excerpt
        elif config_file_pending:
            collect_digest["message"] = "配置文件采集已触发，等待回传中"
        elif len(raw_data) == 0:
            collect_digest["message"] = "未发现任何有效数据，请检查采集目标连通性、凭据与采集范围配置"
            instance.exec_status = CollectRunStatusType.ERROR
        else:
            # 计算最后数据的最后上报时间
            last_time = ""
            for i in raw_data:
                if i.get("__time__"):
                    if i["__time__"] > last_time:
                        last_time = i["__time__"]
            collect_digest["last_time"] = last_time

            # 任务状态判定以"整体成败"为口径，而非单个操作类型是否全挂：
            # - 实例数据(add/update/delete)有要写、但成功 0 条 → ERROR（写库整体失败，最危险）
            # - 否则只要存在任意失败(含 association) → PARTIAL_SUCCESS（部分成功，需运维感知）
            # - 全部成功 → 保持 SUCCESS
            # 注：association 失败不单独升级为 ERROR（目标实例未采到等场景常见且非致命）。
            data_keys = ("add", "update", "delete")
            data_total = sum(collect_digest.get(k, 0) for k in data_keys)
            data_error = sum(collect_digest.get(f"{k}_error", 0) for k in data_keys)
            data_success = data_total - data_error
            any_failure = any(
                collect_digest.get(f"{k}_error", 0) > 0 for k in ("add", "update", "delete", "association")
            )
            if collect_success == 0 and collect_failed > 0:
                instance.exec_status = CollectRunStatusType.ERROR
                collect_digest["message"] = "本轮采集结果全部失败，请检查原始数据中的采集错误"
            elif data_total > 0 and data_success == 0:
                instance.exec_status = CollectRunStatusType.ERROR
                collect_digest["message"] = "实例数据写入全部失败，请检查 add/update/delete 错误数"
            elif any_failure or collect_failed > 0:
                instance.exec_status = CollectRunStatusType.PARTIAL_SUCCESS
                collect_digest["message"] = "部分采集或数据写入失败，请检查原始数据及错误数"
        update_values = {
            "collect_data": result,
            "format_data": format_data,
            "collect_digest": collect_digest,
            "exec_status": instance.exec_status,
            "updated_at": now(),
        }
        updated = _save_collect_result_if_current(
            instance_id,
            execution_id,
            claim_token,
            update_values,
        )
        if not updated:
            logger.info(
                "[CollectTask] 忽略旧执行结果 stale_execution_result " "task_id=%s, execution_id=%s",
                instance_id,
                execution_id,
            )
    except Exception as err:
        import traceback

        logger.error(
            "[CollectTask] 保存采集结果失败 task_id=%s, error=%s",
            instance_id,
            traceback.format_exc(),
        )
        _save_collect_result_if_current(
            instance_id,
            execution_id,
            claim_token,
            {
                "exec_status": CollectRunStatusType.ERROR,
                "collect_digest": {
                    "message": "采集结果写入失败（task_id={}）：{}".format(
                        instance_id,
                        _build_safe_error_message(err),
                    )
                },
                "updated_at": now(),
            },
        )

    logger.info("[CollectTask] 采集任务执行结束 task_id=%s", instance_id)


@shared_task
def sync_periodic_update_task_status():
    """按每次 execution 的 deadline 收敛超时状态。"""
    checked_at = now()
    logger.info("[CollectTask] 开始周期巡检超时采集任务")
    CollectModels._default_manager.filter(
        exec_status__in=_COLLECT_TERMINAL_STATUSES,
        execution_claim_token__isnull=False,
    ).update(execution_claim_token=None)
    timeout_count = 0
    tasks = (
        CollectModels._default_manager.filter(
            exec_status=CollectRunStatusType.RUNNING,
        )
        .only("id", "task_id", "exec_status", "exec_time", "execution_claim_token", "params")
        .iterator(chunk_size=200)
    )
    for task in tasks:
        timeout_count += int(_timeout_collect_task_if_current(task, checked_at))
    logger.info(
        "[CollectTask] 周期巡检超时采集任务完成，超时任务数 rows=%s",
        timeout_count,
    )


@shared_task
def sync_collect_credential_results_task():
    logger.info("Skip legacy credential pull task because CMDB now receives Stargazer pushes via NATS")
    return {
        "result": True,
        "skipped": True,
        "message": "collect credential results are received via NATS push",
    }


@shared_task
def sync_cmdb_display_fields_task(data: dict):
    """
    同步 CMDB 实例的 _display 字段（Celery 任务）

    当系统管理模块修改组织或用户信息时，触发此任务同步更新 CMDB 所有实例的 _display 字段

    Args:
        data: 变更数据字典
            格式: {
                "organizations": [{"id": 1, "name": "新组织名"}],
                "users": [{"id": 1, "display_name": "新显示名"}]
            }

    Returns:
        dict: 执行结果
            格式: {
                "result": True,
                "data": {"organizations": 10, "users": 5}
            }
    """
    try:
        from apps.cmdb.display_field import DisplayFieldSynchronizer

        logger.info(f"[SyncCMDBDisplayFields] 开始同步 CMDB _display 字段, 组织数: {len(data.get('organizations', []))}, 用户数: {len(data.get('users', []))}")

        # 执行同步
        result = DisplayFieldSynchronizer.sync_all(data)

        logger.info(f"[SyncCMDBDisplayFields] 同步完成, 组织更新实例数: {result.get('organizations', 0)}, 用户更新实例数: {result.get('users', 0)}")

        return {
            "result": True,
            "message": "CMDB display fields synced successfully",
            "data": result,
        }

    except Exception as exc:
        logger.error(f"[SyncCMDBDisplayFields] 同步失败: {str(exc)}", exc_info=True)
        return {
            "result": False,
            "message": f"Failed to sync CMDB display fields: {str(exc)}",
        }


@shared_task
def execute_collect_tool_debug_task(debug_id: str, payload: dict, service_name: str, timeout: int):
    logger.info(f"开始执行采集工具调试任务 debug_id={debug_id}, action={payload.get('action')}")
    try:
        return CollectToolService.run_debug_task(debug_id, payload, service_name, timeout)
    except Exception as exc:
        logger.error(f"采集工具调试任务失败 debug_id={debug_id}, error={exc}", exc_info=True)
        result = CollectToolService.build_error_result(
            debug_id=debug_id,
            payload=payload,
            stage="unknown",
            summary=f"调试任务执行失败: {exc}",
            raw_log=str(exc),
        )
        CollectToolService.save_debug_state(debug_id, "error", result)
        return result


@shared_task(bind=True, max_retries=PUBLIC_ENUM_SNAPSHOT_MAX_RETRIES)
def sync_public_enum_library_snapshots_task(
    self, library_id: str, trigger: str, operator: str | None = None
) -> dict:
    from apps.cmdb.services.public_enum_library import sync_library_snapshots

    logger.info(f"[SyncPublicEnumSnapshots] task started library_id={library_id}, trigger={trigger}, operator={operator}")
    result = sync_library_snapshots(library_id, trigger, operator)
    failed_count = int(result.get("failed_count") or 0)
    if not failed_count:
        return result

    retry_number = int(self.request.retries)
    failure_summary = "; ".join(
        f"model_id={item.get('model_id')}, error_type={item.get('error_type', 'UnknownError')}, error={item.get('error', '')}"
        for item in result.get("failed_items", [])
    )
    error = RuntimeError(
        f"公共枚举快照同步存在失败项: library_id={library_id}, failed_count={failed_count}, failures=[{failure_summary}]"
    )
    if retry_number >= self.max_retries:
        logger.error(
            "[SyncPublicEnumSnapshots] retries exhausted library_id=%s, failed_count=%s, attempts=%s, failures=%s",
            library_id,
            failed_count,
            retry_number + 1,
            failure_summary,
        )
        raise error

    countdown = min(
        PUBLIC_ENUM_SNAPSHOT_RETRY_MAX_SECONDS,
        PUBLIC_ENUM_SNAPSHOT_RETRY_BASE_SECONDS * (2**retry_number),
    )
    logger.warning(
        "[SyncPublicEnumSnapshots] retry partial failure library_id=%s, "
        "failed_count=%s, attempt=%s, countdown=%s",
        library_id,
        failed_count,
        retry_number + 1,
        countdown,
    )
    raise self.retry(exc=error, countdown=countdown)


@shared_task
def check_subscription_rules() -> None:
    SubscriptionTaskService.check_rules()


@shared_task
def send_subscription_notifications(
    delivery_ids: list[int] | None = None,
) -> None:
    SubscriptionTaskService.send_notifications(delivery_ids=delivery_ids)


@shared_task
def daily_data_cleanup_task() -> dict:
    from apps.cmdb.services.data_cleanup_service import DataCleanupService

    logger.info("[DataCleanup] 启动每日过期数据清理任务")
    return DataCleanupService.run_daily_cleanup()


@shared_task
def reconcile_instance_auto_association_task(instance_id: int) -> dict:
    from apps.cmdb.services.auto_relation_reconcile import AutoRelationRuleReconcileService

    logger.info("[AutoRelationRule] start instance reconcile, instance_id=%s", instance_id)
    return AutoRelationRuleReconcileService.reconcile_for_instance(instance_id)


@shared_task
def reconcile_instances_auto_association_task(instance_ids: list[int]) -> dict:
    """批量重算实例关联，并在服务层合并重复的目标侧规则。"""
    from apps.cmdb.services.auto_relation_reconcile import AutoRelationRuleReconcileService

    logger.info(
        "[AutoRelationRule] start batch instance reconcile, count=%s",
        len(instance_ids or []),
    )
    return AutoRelationRuleReconcileService.reconcile_for_instances(instance_ids)


@shared_task
def full_sync_auto_association_rule_task(model_asst_id: str) -> dict:
    from apps.cmdb.services.auto_relation_reconcile import AutoRelationRuleReconcileService

    logger.info("[AutoRelationRule] start rule full sync, model_asst_id=%s", model_asst_id)
    return AutoRelationRuleReconcileService.full_sync_rule(model_asst_id)


@shared_task
def sync_node_mgmt_hosts() -> dict:
    logger.info("[NodeMgmtSync] 开始同步节点管理主机信息")
    try:
        data = run_sync()
    except Exception as exc:
        logger.error(
            "[NodeMgmtSync] 同步节点管理主机信息失败, error_type=%s",
            type(exc).__name__,
        )
        raise
    logger.info("[NodeMgmtSync] 同步节点管理主机信息完成")
    return data


@shared_task
def collect_node_mgmt_hosts():
    logger.info("[NodeMgmtSync] 开始采集节点管理主机信息")
    try:
        run_collect()
    except Exception as exc:
        logger.error(
            "[NodeMgmtSync] 采集节点管理主机信息失败, error_type=%s",
            type(exc).__name__,
        )
        raise
    logger.info("[NodeMgmtSync] 采集节点管理主机信息结束")


@shared_task
def reconcile_ipam_task() -> dict:
    """创建或恢复一个 IPAM 周期对账作业。"""
    from apps.cmdb.services.ipam_reconcile_job import IPAMReconcileJob

    result = IPAMReconcileJob.enqueue(trigger="scheduled")
    return {"run_id": str(result.run.run_id), "status": result.run.status, "reused": result.reused}


@shared_task
def execute_ipam_reconcile_task(run_id: str) -> dict:
    from apps.cmdb.services.ipam_reconcile_job import IPAMReconcileJob

    logger.info("[IPAM] 开始执行对账作业 run_id=%s", run_id)
    result = IPAMReconcileJob.execute(run_id)
    logger.info("[IPAM] 对账作业结束 run_id=%s result=%s", run_id, result)
    return result


@shared_task
def reconcile_config_file_content_task() -> dict:
    from apps.cmdb.services.config_file_content_lifecycle import ConfigFileContentLifecycle

    recovery = ConfigFileContentLifecycle.recover_stale()
    orphans_deleted = ConfigFileContentLifecycle.cleanup_orphan_temp_objects()
    result = {**recovery, "orphans_deleted": orphans_deleted}
    logger.info("[ConfigFileContent] 周期补偿完成: %s", result)
    return result


@shared_task
def reconcile_cmdb_operations_task() -> dict:
    from apps.cmdb.services.operation_service import OperationService

    result = {
        "graph_writes": OperationService.recover_stale_graph_writes(),
        "outbox": OperationService.process_outbox_batch(),
    }
    logger.info("[CmdbOperation] 周期补偿完成: %s", result)
    return result


@shared_task
def consume_change_record_mirror_outbox(event_id: str) -> bool:
    from apps.cmdb.services.change_record_mirror import ChangeRecordMirrorService

    return ChangeRecordMirrorService.consume(event_id)


@shared_task
def recover_change_record_mirror_outbox_task() -> dict:
    from apps.cmdb.services.change_record_mirror import ChangeRecordMirrorService

    dispatched = ChangeRecordMirrorService.recover_ready()
    logger.info("[ChangeRecordMirror] 周期补偿派发完成: dispatched=%s", dispatched)
    return {"dispatched": dispatched}
