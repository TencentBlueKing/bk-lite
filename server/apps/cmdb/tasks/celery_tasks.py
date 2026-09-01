# -- coding: utf-8 --
# @File: tasks.py
# @Time: 2025/3/3 15:34
# @Author: windyzhao
import json
import os
import time
from datetime import timedelta
from uuid import uuid4

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.db.models import Q
from django.utils.dateparse import parse_datetime
from django.utils.timezone import is_aware, now

from apps.cmdb.collection.collect_plugin.base import is_failed_vm_metric
from apps.cmdb.collection.collect_tasks.job_collect import JobCollect
from apps.cmdb.collection.collect_tasks.protocol_collect import ProtocolCollect
from apps.cmdb.collection.round_sync import (
    GATE_PAGE_SIZE,
    LAST_SYNCED_ROUND_KEY,
    ORPHAN_BEAT_PURGE_LIMIT,
    SNAPSHOT_CONTRACT_LABEL,
    SYNC_BEAT_NAME_PREFIX,
    cap_completed_round_lookback_seconds,
    cmdb_instance_id,
    completed_round_lookback_seconds,
    decide_gate_action,
    get_last_synced_round,
    query_instance_ids_with_vm_data,
    query_latest_completed_rounds,
    query_latest_round_ts,
    uses_vm_reconciliation,
)
from apps.cmdb.constants.constants import CollectPluginTypes, CollectRunStatusType
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.services.collect_dispatch_service import CollectDispatchService
from apps.cmdb.services.collect_tool_service import CollectToolService
from apps.cmdb.services.subscription_task import SubscriptionTaskService
from apps.cmdb.tasks.node_mgmt_sync import run_collect, run_sync
from apps.core.logger import cmdb_logger as logger
from apps.core.logger import safe_exception_info
from apps.core.utils.celery_utils import CeleryUtils

_COLLECT_TERMINAL_STATUSES = (
    CollectRunStatusType.SUCCESS,
    CollectRunStatusType.ERROR,
    CollectRunStatusType.TIME_OUT,
    CollectRunStatusType.FORCE_STOP,
    CollectRunStatusType.PARTIAL_SUCCESS,
)
_COLLECT_STATUS_LOG_NAMES = {
    CollectRunStatusType.NOT_START: "NOT_START",
    CollectRunStatusType.RUNNING: "RUNNING",
    CollectRunStatusType.SUCCESS: "SUCCESS",
    CollectRunStatusType.ERROR: "ERROR",
    CollectRunStatusType.TIME_OUT: "TIME_OUT",
    CollectRunStatusType.WRITING: "WRITING",
    CollectRunStatusType.FORCE_STOP: "FORCE_STOP",
    CollectRunStatusType.PARTIAL_SUCCESS: "PARTIAL_SUCCESS",
}
_COLLECT_WARNING_LOG_STATUSES = {
    CollectRunStatusType.ERROR,
    CollectRunStatusType.TIME_OUT,
    CollectRunStatusType.FORCE_STOP,
    CollectRunStatusType.PARTIAL_SUCCESS,
}
_NODE_MGMT_RAW_DATA_MAX_ROWS = 50_000
_NODE_MGMT_RAW_DATA_MAX_BYTES = 64 * 1024 * 1024
_NODE_MGMT_RAW_METRIC_TYPES = {
    "host_info_gauge": "host",
    "host_proc_usage_info_gauge": "process",
}


def _bound_node_mgmt_raw_data(instance: CollectModels, format_data):
    """在节点同步结果持久化前裁剪逐行指标，同时保留裁剪前真实计数。"""
    if not instance.is_system or not str(instance.system_code or "").startswith("node_mgmt_sync_host_collect_") or not isinstance(format_data, dict):
        return {}
    raw_rows = format_data.get("__raw_data__", [])
    if not isinstance(raw_rows, list):
        format_data["__raw_data__"] = []
        return {
            "raw_total": 0,
            "raw_host": 0,
            "raw_process": 0,
            "raw_dropped": 0,
            "raw_input_truncated": False,
        }

    retained = []
    retained_bytes = 0
    counts = {"host": 0, "process": 0}
    raw_dropped = 0
    latest_metric_time = None
    from apps.cmdb.services.node_mgmt_sync_raw import sanitize_node_mgmt_raw_data_item

    for row in raw_rows:
        metric_type = _NODE_MGMT_RAW_METRIC_TYPES.get(row.get("__name__")) if isinstance(row, dict) else None
        if metric_type is None:
            raw_dropped += 1
            continue
        counts[metric_type] += 1
        metric_time = parse_datetime(str(row.get("__time__") or ""))
        if metric_time is not None and is_aware(metric_time):
            if latest_metric_time is None or metric_time > latest_metric_time:
                latest_metric_time = metric_time
        safe_row = sanitize_node_mgmt_raw_data_item(row)
        encoded_size = len(json.dumps(safe_row, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode())
        if len(retained) < _NODE_MGMT_RAW_DATA_MAX_ROWS and retained_bytes + encoded_size <= _NODE_MGMT_RAW_DATA_MAX_BYTES:
            retained.append(safe_row)
            retained_bytes += encoded_size
    format_data["__raw_data__"] = retained
    return {
        "raw_total": len(raw_rows),
        "raw_host": counts["host"],
        "raw_process": counts["process"],
        "raw_dropped": raw_dropped,
        "raw_input_truncated": len(retained) < counts["host"] + counts["process"],
        "raw_input_last_time": latest_metric_time.isoformat() if latest_metric_time is not None else "",
        "raw_input_retained_bytes": retained_bytes,
    }


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


PUBLIC_ENUM_SNAPSHOT_MAX_RETRIES = _read_bounded_int_env("CMDB_PUBLIC_ENUM_SNAPSHOT_MAX_RETRIES", 3, 0, 10)
PUBLIC_ENUM_SNAPSHOT_RETRY_BASE_SECONDS = _read_bounded_int_env("CMDB_PUBLIC_ENUM_SNAPSHOT_RETRY_BASE_SECONDS", 10, 1, 3600)
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

    allowed = NodeMgmtSyncConfig.objects.filter(
        pk=config_id,
        auto_collect_enabled=True,
        version=config_version,
    ).exists()
    if allowed:
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


def _apply_pc_digest(collect_digest, format_data):
    """把 PC 插件的 pc_summary 复制进任务摘要；非 PC 任务返回 None。"""
    pc_summary = (format_data or {}).get("pc_summary")
    if isinstance(pc_summary, dict):
        collect_digest["pc_summary"] = pc_summary
        return pc_summary
    return None


def _decide_collect_exec_status(collect_digest, raw_data, pc_summary=None):
    """任务状态判定：全部失败 ERROR / 混合 PARTIAL_SUCCESS / 全成功 SUCCESS。

    PC 任务以逐 PC 行（add/update/delete/association 计数）为口径；
    完整空软件快照 raw_data 为空但有 pc_summary 时，不以空原始数据误判 ERROR。
    """
    if len(raw_data) == 0 and not pc_summary:
        return CollectRunStatusType.ERROR
    data_keys = ("add", "update", "delete")
    data_total = sum(collect_digest.get(k, 0) for k in data_keys)
    data_error = sum(collect_digest.get(f"{k}_error", 0) for k in data_keys)
    data_success = data_total - data_error
    any_failure = any(collect_digest.get(f"{k}_error", 0) > 0 for k in ("add", "update", "delete", "association"))
    collect_success = collect_digest.get("collect_success", 0)
    collect_failed = collect_digest.get("collect_failed", 0)
    if isinstance(pc_summary, dict):
        pc_failed = int(pc_summary.get("pc_failed", 0) or 0)
        pc_partial = int(pc_summary.get("pc_partial", 0) or 0)
        pc_complete = int(pc_summary.get("pc_complete", 0) or 0)
        pc_total = int(pc_summary.get("pc_total", 0) or 0) or pc_complete + pc_partial + pc_failed
        if pc_total == 0:
            return CollectRunStatusType.ERROR
        if pc_total > 0 and pc_failed >= pc_total:
            return CollectRunStatusType.ERROR
        if pc_partial > 0 or pc_failed > 0:
            return CollectRunStatusType.PARTIAL_SUCCESS
    if collect_success == 0 and collect_failed > 0:
        return CollectRunStatusType.ERROR
    if data_total > 0 and data_success == 0:
        return CollectRunStatusType.ERROR
    if any_failure or collect_failed > 0:
        return CollectRunStatusType.PARTIAL_SUCCESS
    return CollectRunStatusType.SUCCESS


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
            "[FirstCollection] 跳过过期配置 task_id=%s fingerprint=%s reason=%s " "cycle=%s attempt=%s elapsed_ms=%s result=stale",
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
            "[FirstCollection] 可重试失败 task_id=%s fingerprint=%s reason=%s " "cycle=%s attempt=%s elapsed_ms=%s error_type=%s",
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
            "[FirstCollection] 永久失败 task_id=%s fingerprint=%s reason=%s " "cycle=%s attempt=%s elapsed_ms=%s error_type=%s",
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
        "[FirstCollection] 已接收 task_id=%s fingerprint=%s reason=%s " "cycle=%s attempt=%s elapsed_ms=%s result=%s",
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
def sync_collect_task(  # noqa: C901
    self,
    instance_id,
    execution_id=None,
    node_config_id=None,
    node_config_version=None,
    sync_round_ts=None,
    sync_round_completed_at=None,
    sync_snapshot_complete=None,
):
    """
    同步采集任务
    """
    run_started_at = time.monotonic()
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
    # 领取前保留游标：对账失败时不得丢失 last_synced_round，否则守门会误判进兼容路径。
    prev_digest = CollectModels._default_manager.filter(id=instance_id).values_list("collect_digest", flat=True).first()
    prev_synced_round = get_last_synced_round(prev_digest)
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
    resolved_round_ts = None
    resolved_round_completed_at = None
    resolved_snapshot_complete = None
    if sync_round_ts not in (None, ""):
        try:
            resolved_round_ts = int(sync_round_ts)
        except (TypeError, ValueError):
            logger.warning(
                "[CollectTask] sync_round_ts 非法，忽略轮次过滤 task_id=%s value=%s",
                instance_id,
                sync_round_ts,
            )
            resolved_round_ts = None
    if resolved_round_ts is not None:
        instance._sync_round_ts = resolved_round_ts
        try:
            resolved_round_completed_at = float(sync_round_completed_at)
        except (TypeError, ValueError):
            resolved_round_completed_at = None
        if resolved_round_completed_at is not None and resolved_round_completed_at >= resolved_round_ts:
            instance._sync_round_completed_at = resolved_round_completed_at
    if isinstance(sync_snapshot_complete, bool):
        resolved_snapshot_complete = bool(
            sync_snapshot_complete
            and resolved_round_ts is not None
            and resolved_round_completed_at is not None
            and resolved_round_completed_at >= resolved_round_ts
        )
        instance._sync_snapshot_complete = resolved_snapshot_complete
    logger.info(
        "event=collect_task_execution_started task_id=%s execution_id=%s",
        instance_id,
        execution_id,
    )
    from apps.cmdb.services.collect_service import CollectModelService

    exec_error_message = ""
    exec_traceback_excerpt = ""
    exec_traceback_location = ""
    task_exec_status = CollectRunStatusType.SUCCESS
    config_file_pending = False
    failed_stage = "-"
    result_persisted = False
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
        failed_stage = "collection"
        logger.exception(
            "event=collect_task_stage_failed task_id=%s execution_id=%s " "failed_stage=%s error_type=%s",
            instance_id,
            execution_id,
            failed_stage,
            type(err).__name__,
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
        node_mgmt_raw_summary = _bound_node_mgmt_raw_data(instance, format_data)
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
        pc_summary = _apply_pc_digest(collect_digest, format_data)
        raw_data = format_data.get("__raw_data__", [])
        collect_digest.update(node_mgmt_raw_summary)
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
        elif len(raw_data) == 0 and not pc_summary and not (collect_digest.get("raw_host", 0) or collect_digest.get("raw_process", 0)):
            collect_digest["message"] = "未发现任何有效数据，请检查采集目标连通性、凭据与采集范围配置"
            instance.exec_status = CollectRunStatusType.ERROR
        else:
            # 计算最后数据的最后上报时间
            last_time = ""
            for i in raw_data:
                if i.get("__time__"):
                    if i["__time__"] > last_time:
                        last_time = i["__time__"]
            collect_digest["last_time"] = node_mgmt_raw_summary.get("raw_input_last_time") or last_time

            # 任务状态判定以"整体成败"为口径，而非单个操作类型是否全挂：
            # - 实例数据(add/update/delete)有要写、但成功 0 条 → ERROR（写库整体失败，最危险）
            # - 否则只要存在任意失败(含 association) → PARTIAL_SUCCESS（部分成功，需运维感知）
            # - 全部成功 → 保持 SUCCESS
            # 注：association 失败不单独升级为 ERROR（目标实例未采到等场景常见且非致命）。
            has_unretained_node_metrics = bool(collect_digest.get("raw_host", 0) or collect_digest.get("raw_process", 0))
            decided = _decide_collect_exec_status(
                collect_digest,
                raw_data,
                pc_summary or has_unretained_node_metrics,
            )
            if decided == CollectRunStatusType.ERROR:
                instance.exec_status = CollectRunStatusType.ERROR
                if isinstance(pc_summary, dict) and int(pc_summary.get("pc_total", 0) or 0) == 0:
                    collect_digest["message"] = "未发现 PC 最新上报结果，请检查目标采集是否已完成及数据上报时间"
                elif collect_success == 0 and collect_failed > 0:
                    collect_digest["message"] = "本轮采集结果全部失败，请检查原始数据中的采集错误"
                else:
                    collect_digest["message"] = "实例数据写入全部失败，请检查 add/update/delete 错误数"
            elif decided == CollectRunStatusType.PARTIAL_SUCCESS:
                instance.exec_status = CollectRunStatusType.PARTIAL_SUCCESS
                collect_digest["message"] = "部分采集或数据写入失败，请检查原始数据及错误数"
        _apply_last_synced_round(
            collect_digest,
            instance_id=instance_id,
            exec_status=instance.exec_status,
            sync_round_ts=resolved_round_ts,
            snapshot_complete=resolved_snapshot_complete,
            prev_synced_round=prev_synced_round,
        )
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
        result_persisted = updated
        if not updated:
            logger.info(
                "[CollectTask] 忽略旧执行结果 stale_execution_result " "task_id=%s, execution_id=%s",
                instance_id,
                execution_id,
            )
        elif instance.exec_status in (
            CollectRunStatusType.SUCCESS,
            CollectRunStatusType.PARTIAL_SUCCESS,
        ) and (getattr(instance, "model_id", None) == "network" or getattr(instance, "task_type", None) == CollectPluginTypes.SNMP):
            try:
                from apps.cmdb.services.topology_replay_service import wake_pending_topology_replay

                wake_pending_topology_replay(instance_id)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "[CollectTask] 唤醒拓扑 pending 重放失败 task_id=%s",
                    instance_id,
                )
    except Exception as err:
        failed_stage = "result_persistence"
        logger.exception(
            "event=collect_task_stage_failed task_id=%s execution_id=%s " "failed_stage=%s error_type=%s",
            instance_id,
            execution_id,
            failed_stage,
            type(err).__name__,
        )
        error_digest = {
            "message": "采集结果写入失败（task_id={}）：{}".format(
                instance_id,
                _build_safe_error_message(err),
            )
        }
        if prev_synced_round is not None:
            error_digest[LAST_SYNCED_ROUND_KEY] = prev_synced_round
        result_persisted = _save_collect_result_if_current(
            instance_id,
            execution_id,
            claim_token,
            {
                "exec_status": CollectRunStatusType.ERROR,
                "collect_digest": error_digest,
                "updated_at": now(),
            },
        )

    terminal_status = CollectRunStatusType.ERROR if failed_stage == "result_persistence" else instance.exec_status
    log_terminal = logger.warning if terminal_status in _COLLECT_WARNING_LOG_STATUSES else logger.info
    log_terminal(
        "event=collect_task_execution_finished task_id=%s execution_id=%s "
        "status=%s failed_stage=%s result_persisted=%s callback_pending=%s duration_ms=%.2f",
        instance_id,
        execution_id,
        _COLLECT_STATUS_LOG_NAMES.get(terminal_status, str(terminal_status)),
        failed_stage,
        result_persisted,
        config_file_pending,
        (time.monotonic() - run_started_at) * 1000,
    )


def _apply_last_synced_round(
    collect_digest: dict,
    *,
    instance_id,
    exec_status,
    sync_round_ts,
    snapshot_complete,
    prev_synced_round,
):
    """成功对账后写入游标；失败时保留旧游标。手动路径无 sync_round_ts 时从标记刷新。"""
    success_statuses = (
        CollectRunStatusType.SUCCESS,
        CollectRunStatusType.PARTIAL_SUCCESS,
    )
    if exec_status in success_statuses:
        round_to_store = sync_round_ts
        if round_to_store is None and snapshot_complete is not False:
            round_to_store = query_latest_round_ts(cmdb_instance_id(instance_id))
        if round_to_store is not None:
            collect_digest[LAST_SYNCED_ROUND_KEY] = int(round_to_store)
            return
    if prev_synced_round is not None:
        collect_digest[LAST_SYNCED_ROUND_KEY] = prev_synced_round


def _purge_legacy_vm_sync_beats(limit: int = ORPHAN_BEAT_PURGE_LIMIT) -> int:
    """运行期幂等清理 VM 对账任务残留的按任务 beat（不在启动期执行）。"""
    from django_celery_beat.models import PeriodicTask

    purged = 0
    qs = PeriodicTask.objects.filter(name__startswith=SYNC_BEAT_NAME_PREFIX).order_by("id").values_list("id", "name")[:limit]
    for beat_id, name in qs:
        suffix = name[len(SYNC_BEAT_NAME_PREFIX) :]
        try:
            task_id = int(suffix)
        except (TypeError, ValueError):
            continue
        task_type = CollectModels._default_manager.filter(id=task_id).values_list("task_type", flat=True).first()
        # 任务已删除，或仍为 VM 对账类型：清理旧 beat。
        if task_type is None or uses_vm_reconciliation(task_type):
            CeleryUtils.delete_periodic_task(name)
            purged += 1
            logger.info("[RoundGate] 清理遗留对账 beat name=%s beat_id=%s", name, beat_id)
    return purged


def _log_round_gate_marker_query_failure(error: BaseException, *, failed_stage: str, rows: int) -> None:
    logger.error(
        "event=round_gate_marker_query_failed failed_stage=%s rows=%s error_type=%s",
        failed_stage,
        rows,
        type(error).__name__,
        exc_info=safe_exception_info(error),
    )


@shared_task(soft_time_limit=240, time_limit=270)
def sync_collect_tasks_gate():
    """全局 5 分钟守门：仅在出现新完整轮次时触发对账。"""
    from apps.cmdb.models.collect_model import COLLECTION_ROLE_DEVICE, COLLECTION_ROLE_TOPOLOGY, normalize_topology_contract
    from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService
    from apps.cmdb.services.topology_replay_service import maybe_replay_topology_from_gate

    logger.info("[RoundGate] 开始扫描采集对账守门")
    purged = _purge_legacy_vm_sync_beats()
    scanned = 0
    dispatched = 0
    skipped = 0
    topo_replayed = 0
    retention_limited = 0
    vm_query_failed = 0
    topology_query_failed = 0
    after_id = 0
    while True:
        page = list(
            CollectModels._default_manager.filter(id__gt=after_id)
            .exclude(task_type__in=(CollectPluginTypes.CONFIG_FILE, CollectPluginTypes.K8S))
            .exclude(
                is_system=True,
                system_code__startswith=NodeMgmtSyncService.SYSTEM_TASK_PREFIX,
            )  # NodeMgmtSync 认领 child execution；守门重派会冲掉 task_id
            .order_by("id")
            .values(
                "id",
                "exec_status",
                "collect_digest",
                "params",
                "model_id",
                "task_type",
                "is_interval",
                "cycle_value_type",
                "cycle_value",
            )[:GATE_PAGE_SIZE]
        )
        if not page:
            break
        completed_rounds = {}
        topology_rounds = {}
        compat_data_instance_ids = set()
        marker_query_failed_ids = set()
        eligible_rows = [row for row in page if row["exec_status"] != CollectRunStatusType.RUNNING]
        if eligible_rows:
            requested_lookbacks = {
                row["id"]: completed_round_lookback_seconds(
                    is_interval=bool(row.get("is_interval")),
                    cycle_value_type=row.get("cycle_value_type"),
                    cycle_value=row.get("cycle_value"),
                )
                for row in eligible_rows
            }
            retention_limited += sum(cap_completed_round_lookback_seconds(value)[1] for value in requested_lookbacks.values())
            capped_lookbacks = {row_id: cap_completed_round_lookback_seconds(value)[0] for row_id, value in requested_lookbacks.items()}
            marker_lookback = max(capped_lookbacks.values())
            instance_ids = [cmdb_instance_id(row["id"]) for row in eligible_rows]
            marker_evaluation_time = time.time()
            minimum_completed_at_by_instance = {
                cmdb_instance_id(row_id): marker_evaluation_time - lookback for row_id, lookback in capped_lookbacks.items()
            }
            try:
                completed_rounds = query_latest_completed_rounds(
                    instance_ids,
                    collection_role=COLLECTION_ROLE_DEVICE,
                    lookback_seconds=marker_lookback,
                    minimum_completed_at_by_instance=minimum_completed_at_by_instance,
                )
            except Exception as exc:  # noqa: BLE001 - 页级故障隔离，下一轮 Gate 自动重试
                marker_query_failed_ids.update(instance_ids)
                _log_round_gate_marker_query_failure(
                    exc,
                    failed_stage="device_marker_query",
                    rows=len(instance_ids),
                )
            else:
                legacy_ids = [instance_id for instance_id in instance_ids if instance_id not in completed_rounds]
                if legacy_ids:
                    try:
                        # collection_role='' 只兼容旧无 role 标记，不混入新拓扑通道标记。
                        completed_rounds.update(
                            query_latest_completed_rounds(
                                legacy_ids,
                                collection_role="",
                                lookback_seconds=marker_lookback,
                                minimum_completed_at_by_instance=minimum_completed_at_by_instance,
                            )
                        )
                    except Exception as exc:  # noqa: BLE001 - 已取得的新标记仍可继续处理
                        marker_query_failed_ids.update(legacy_ids)
                        _log_round_gate_marker_query_failure(
                            exc,
                            failed_stage="legacy_marker_query",
                            rows=len(legacy_ids),
                        )
            compat_probe_ids = [
                cmdb_instance_id(row["id"])
                for row in eligible_rows
                if cmdb_instance_id(row["id"]) not in completed_rounds
                and cmdb_instance_id(row["id"]) not in marker_query_failed_ids
                and get_last_synced_round(row.get("collect_digest")) is None
            ]
            if compat_probe_ids:
                try:
                    compat_data_instance_ids = query_instance_ids_with_vm_data(compat_probe_ids)
                except Exception as exc:  # noqa: BLE001 - 兼容探测失败时不得误判为无数据
                    marker_query_failed_ids.update(compat_probe_ids)
                    _log_round_gate_marker_query_failure(
                        exc,
                        failed_stage="compat_data_query",
                        rows=len(compat_probe_ids),
                    )
            vm_query_failed += len(marker_query_failed_ids)
            topology_rows = [
                row
                for row in eligible_rows
                if (row.get("model_id") == "network" or row.get("task_type") == CollectPluginTypes.SNMP)
                and normalize_topology_contract(row.get("params") or {}).get("has_network_topo")
            ]
            if topology_rows:
                topology_lookbacks = {}
                for row in topology_rows:
                    topology_contract = normalize_topology_contract(
                        row.get("params") or {},
                        device_cycle_minutes=(row.get("cycle_value") if row.get("cycle_value_type") == "cycle" else None),
                    )
                    requested = completed_round_lookback_seconds(
                        is_interval=True,
                        cycle_value_type="cycle",
                        cycle_value=topology_contract.get("topology_interval_minutes"),
                    )
                    topology_lookbacks[row["id"]] = cap_completed_round_lookback_seconds(requested)[0]
                    retention_limited += int(cap_completed_round_lookback_seconds(requested)[1])
                topology_instance_ids = [cmdb_instance_id(row["id"]) for row in topology_rows]
                topology_marker_lookback = max(topology_lookbacks.values())
                topology_minimum_completed_at = {
                    cmdb_instance_id(row_id): marker_evaluation_time - lookback for row_id, lookback in topology_lookbacks.items()
                }
                try:
                    topology_rounds = query_latest_completed_rounds(
                        topology_instance_ids,
                        collection_role=COLLECTION_ROLE_TOPOLOGY,
                        lookback_seconds=topology_marker_lookback,
                        minimum_completed_at_by_instance=topology_minimum_completed_at,
                    )
                except Exception as exc:  # noqa: BLE001 - 拓扑失败不阻断设备对账
                    topology_query_failed += len(topology_instance_ids)
                    _log_round_gate_marker_query_failure(
                        exc,
                        failed_stage="topology_marker_query",
                        rows=len(topology_instance_ids),
                    )

        for row in page:
            scanned += 1
            task_id = row["id"]
            if row["exec_status"] == CollectRunStatusType.RUNNING:
                skipped += 1
                logger.debug("[RoundGate] 跳过运行中任务 task_id=%s action=skip_running", task_id)
                continue
            instance_id = cmdb_instance_id(task_id)
            if instance_id in marker_query_failed_ids:
                skipped += 1
                logger.debug("[RoundGate] 跳过标记查询失败任务 task_id=%s", task_id)
                continue
            last_synced = get_last_synced_round(row.get("collect_digest"))
            completed_round = completed_rounds.get(instance_id)
            round_ts = completed_round.started_at if completed_round is not None else None
            has_data = instance_id in compat_data_instance_ids
            action = decide_gate_action(
                exec_status=row["exec_status"],
                round_ts=round_ts,
                last_synced_round=last_synced,
                has_vm_data=has_data,
            )
            if action == "sync_round":
                sync_collect_task.delay(
                    task_id,
                    sync_round_ts=round_ts,
                    sync_round_completed_at=completed_round.completed_at,
                    sync_snapshot_complete=completed_round.snapshot_complete,
                )
                dispatched += 1
                logger.info(
                    "[RoundGate] 派发轮次对账 task_id=%s round_ts=%s last_synced=%s",
                    task_id,
                    round_ts,
                    last_synced,
                )
            elif action == "sync_compat":
                # 无完成标记只能证明“有数据”，不能证明快照完整；兼容轮次禁止差集删除。
                sync_collect_task.delay(task_id, sync_snapshot_complete=False)
                dispatched += 1
                logger.info("[RoundGate] 兼容回退对账 task_id=%s", task_id)
            else:
                skipped += 1
                logger.debug(
                    "[RoundGate] 跳过 task_id=%s action=%s round_ts=%s last_synced=%s",
                    task_id,
                    action,
                    round_ts,
                    last_synced,
                )

            if row.get("model_id") == "network" or row.get("task_type") == CollectPluginTypes.SNMP:
                topology_round = topology_rounds.get(instance_id)
                topology_marker = None
                if topology_round is not None:
                    topology_marker = {
                        "round_ts": topology_round.started_at,
                        "round_completed_at": topology_round.completed_at,
                        "channel_config_version": topology_round.labels.get("channel_config_version", ""),
                        SNAPSHOT_CONTRACT_LABEL: topology_round.labels.get(SNAPSHOT_CONTRACT_LABEL),
                    }
                topo_status = maybe_replay_topology_from_gate(
                    task_id,
                    row.get("params"),
                    row.get("collect_digest"),
                    marker=topology_marker,
                )
                if topo_status == "played":
                    topo_replayed += 1
        after_id = page[-1]["id"]
        if len(page) < GATE_PAGE_SIZE:
            break
    logger.info(
        "[RoundGate] 守门扫描完成 scanned=%s dispatched=%s skipped=%s "
        "topo_replayed=%s purged_beats=%s retention_limited=%s vm_query_failed=%s "
        "topology_query_failed=%s",
        scanned,
        dispatched,
        skipped,
        topo_replayed,
        purged,
        retention_limited,
        vm_query_failed,
        topology_query_failed,
    )
    return {
        "scanned": scanned,
        "dispatched": dispatched,
        "skipped": skipped,
        "topo_replayed": topo_replayed,
        "purged_beats": purged,
        "retention_limited": retention_limited,
        "vm_query_failed": vm_query_failed,
        "topology_query_failed": topology_query_failed,
    }


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


@shared_task(bind=True, max_retries=3, default_retry_delay=5, soft_time_limit=240, time_limit=300)
def sync_cmdb_display_fields_task(self, data: dict):
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
    from apps.cmdb.display_field import DisplayFieldSynchronizer
    from apps.cmdb.display_field.sync import refresh_display_sync_data
    from apps.cmdb.services.unique_write_lock import UniqueWriteLockService

    logger.info(f"[SyncCMDBDisplayFields] 开始同步 CMDB _display 字段, " f"组织数: {len(data.get('organizations', []))}, 用户数: {len(data.get('users', []))}")

    try:
        # 同步域使用稳定的数据库租约跨进程串行。租期长于任务硬时限，进程崩溃后可过期接管；
        # owner token 防止旧任务误释放接管者的租约。后发任务取得租约后才读取权威 ORM，
        # 因此旧任务不能在新任务之后继续写旧快照，后发变更最终会覆盖全量实例。
        with UniqueWriteLockService.serialize("cmdb-display-field-sync", lease_seconds=310):
            # 图写按字段分批提交，瞬时失败前可能已有部分字段落图。全量同步本身幂等，
            # 因此在同一锁内有界重跑一次，既补齐部分写，又保持既有 Celery 返回结构。
            for attempt in range(2):
                try:
                    result = DisplayFieldSynchronizer.sync_all(refresh_display_sync_data(data))
                    logger.info(f"[SyncCMDBDisplayFields] 同步完成, 组织更新实例数: {result.get('organizations', 0)}, " f"用户更新实例数: {result.get('users', 0)}")
                    return {
                        "result": True,
                        "message": "CMDB display fields synced successfully",
                        "data": result,
                    }
                except SoftTimeLimitExceeded:
                    # 不在剩余硬时限内重扫全量；先退出 context 释放租约，再交给 Celery 有界重试。
                    raise
                except Exception as exc:
                    if attempt == 0:
                        logger.warning("[SyncCMDBDisplayFields] 同步失败，将从头重试一次: %s", exc)
                        continue
                    raise
    except (TimeoutError, SoftTimeLimitExceeded) as exc:
        if self.request.retries < self.max_retries:
            logger.warning("[SyncCMDBDisplayFields] 同步繁忙或超时，任务将有界重试: %s", exc)
            # 锁竞争的三次等待总跨度需覆盖 310s 租期，确保占锁者即使硬退出，后发任务也能接管；
            # soft timeout 已释放租约，沿用短延迟即可。
            countdown = 105 if isinstance(exc, TimeoutError) else self.default_retry_delay
            raise self.retry(exc=exc, countdown=countdown)
        logger.error("[SyncCMDBDisplayFields] 同步重试已耗尽: %s", exc, exc_info=True)
        return {
            "result": False,
            "message": f"Failed to sync CMDB display fields: {str(exc)}",
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
def sync_public_enum_library_snapshots_task(self, library_id: str, trigger: str, operator: str | None = None) -> dict:
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
    error = RuntimeError(f"公共枚举快照同步存在失败项: library_id={library_id}, failed_count={failed_count}, failures=[{failure_summary}]")
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
        "[SyncPublicEnumSnapshots] retry partial failure library_id=%s, " "failed_count=%s, attempt=%s, countdown=%s",
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
def consume_cmdb_operation_outbox(event_id: str) -> bool:
    from apps.cmdb.services.operation_service import OperationService

    return OperationService.consume_outbox(event_id)


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


@shared_task(bind=True, name="apps.cmdb.tasks.celery_tasks.trigger_scan_execution")
def trigger_scan_execution(self, execution_id):
    from apps.cmdb.services.scan_trigger_service import trigger_scan_execution as run_trigger

    return run_trigger(execution_id)


@shared_task(bind=True, name="apps.cmdb.tasks.celery_tasks.finalize_scan_execution")
def finalize_scan_execution(self, execution_id, claim_token):
    from apps.cmdb.services.scan_trigger_service import poll_scan_finalize

    return poll_scan_finalize(execution_id, claim_token)
