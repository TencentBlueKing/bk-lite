from datetime import timedelta
from uuid import uuid4

from django.db import transaction
from django.utils.timezone import now

from apps.cmdb.models.scan_model import SCAN_DATABASE_FAMILY, SCAN_DATABASE_TYPES, ScanExecution, ScanFamilyRun, ScanTask, scan_driver_type_for_model
from apps.cmdb.services.collect_credential_pool_service import CollectCredentialPoolService
from apps.cmdb.services.port_fingerprint import scan_database_ports_by_type
from apps.cmdb.services.scan_shot import ScanShot, build_scan_collect_headers, join_ip_ranges
from apps.cmdb.services.stargazer_collect_trigger import StargazerCollectPermanentError, StargazerCollectRetryableError, StargazerCollectTriggerClient
from apps.core.logger import cmdb_logger as logger

SCAN_FINALIZE_POLL_SECONDS = 30
SCAN_WALL_CLOCK_MIN = timedelta(minutes=15)
SCAN_WALL_CLOCK_MAX = timedelta(hours=2)
SCAN_DEFAULT_PLUGIN_TIMEOUT = 60
SCAN_ADMIT_CONCURRENCY = 16

_TERMINAL = frozenset(
    {
        ScanExecution.STATUS_COMPLETED,
        ScanExecution.STATUS_FAILED,
        ScanExecution.STATUS_TIMED_OUT,
    }
)


def estimate_deadline(target_count: int, timeout: int):
    per_target = timeout or SCAN_DEFAULT_PLUGIN_TIMEOUT
    estimated = (max(target_count, 1) * per_target) / SCAN_ADMIT_CONCURRENCY
    bounded = min(max(estimated, SCAN_WALL_CLOCK_MIN.total_seconds()), SCAN_WALL_CLOCK_MAX.total_seconds())
    return now() + timedelta(seconds=bounded)


def _schedule_finalize(execution_id, claim_token):
    from apps.cmdb.tasks.celery_tasks import finalize_scan_execution

    finalize_scan_execution.apply_async(
        args=[execution_id, claim_token],
        countdown=SCAN_FINALIZE_POLL_SECONDS,
    )


def _claim_execution(execution_id) -> ScanExecution:
    with transaction.atomic():
        execution = ScanExecution.objects.select_for_update().select_related("task").filter(pk=execution_id).first()
        if execution is None:
            raise ScanExecution.DoesNotExist(f"ScanExecution {execution_id} 不存在")
        if execution.status in _TERMINAL:
            return execution
        execution.claim_token = str(uuid4())
        execution.status = ScanExecution.STATUS_RUNNING
        execution.started_at = now()
        execution.save(update_fields=["claim_token", "status", "started_at", "updated_at"])
        return execution


def expand_sql_pool_with_ports(pool, ports) -> list:
    expanded = []
    for port in ports:
        for item in pool or []:
            if not isinstance(item, dict):
                continue
            next_item = dict(item)
            next_item["port"] = int(port)
            if next_item.get("username") and not next_item.get("user"):
                next_item["user"] = next_item["username"]
            expanded.append(next_item)
    return expanded


def iter_scan_family_pools(task: ScanTask):
    decrypted = task.decrypt_credentials or {}
    families = list(task.families or [])
    if SCAN_DATABASE_FAMILY in families:
        db_pool = CollectCredentialPoolService.normalize_pool(decrypted.get(SCAN_DATABASE_FAMILY) or [])
        ports_by_type = scan_database_ports_by_type()
        skipped = []
        for model_id in ("mysql", "postgresql", "mssql"):
            ports = ports_by_type.get(model_id) or []
            if not db_pool or not ports:
                skipped.append(model_id)
                continue
            yield model_id, expand_sql_pool_with_ports(db_pool, ports)
        if skipped:
            logger.info(
                "[ScanTrigger] 跳过无端口或无账号的数据库族 task=%s skipped=%s",
                task.id,
                ",".join(skipped),
            )
        for model_id in families:
            if model_id in SCAN_DATABASE_TYPES or model_id == SCAN_DATABASE_FAMILY:
                continue
            yield model_id, CollectCredentialPoolService.normalize_pool(decrypted.get(model_id) or [])
        return
    for model_id in families:
        yield str(model_id), CollectCredentialPoolService.normalize_pool(decrypted.get(model_id) or [])


def _admit_family(task: ScanTask, execution: ScanExecution, model_id: str, pool=None) -> ScanFamilyRun:
    driver_type = scan_driver_type_for_model(model_id)
    family_run, _ = ScanFamilyRun.objects.get_or_create(
        execution=execution,
        model_id=model_id,
        driver_type=driver_type,
    )
    if pool is None:
        decrypted = task.decrypt_credentials or {}
        pool = CollectCredentialPoolService.normalize_pool(decrypted.get(model_id) or [])
    if not pool:
        family_run.admit_status = ScanFamilyRun.ADMIT_FAILED
        family_run.target_count = 0
        family_run.save(update_fields=["admit_status", "target_count", "updated_at"])
        return family_run

    params = {"has_network_topo": False}
    if model_id == "host" and task.cloud_region:
        params["cloud_region"] = task.cloud_region

    shot = ScanShot(
        id=family_run.id,
        model_id=model_id,
        driver_type=driver_type,
        ip_range=join_ip_ranges(task.ip_ranges),
        instances=[],
        credential=pool,
        timeout=task.timeout or 0,
        access_point=task.access_point or [],
        params=params,
    )
    headers = build_scan_collect_headers(shot)
    try:
        result = StargazerCollectTriggerClient().admit(headers)
    except StargazerCollectRetryableError:
        logger.warning("[ScanTrigger] 族接纳可重试失败 execution=%s model_id=%s", execution.id, model_id)
        family_run.admit_status = ScanFamilyRun.ADMIT_FAILED
        family_run.save(update_fields=["admit_status", "updated_at"])
        return family_run
    except StargazerCollectPermanentError:
        logger.warning("[ScanTrigger] 族接纳永久失败 execution=%s model_id=%s", execution.id, model_id)
        family_run.admit_status = ScanFamilyRun.ADMIT_FAILED
        family_run.save(update_fields=["admit_status", "updated_at"])
        return family_run

    family_run.target_count = result.total
    family_run.admit_status = ScanFamilyRun.ADMIT_DUPLICATE if result.status == "duplicate" else ScanFamilyRun.ADMIT_ACCEPTED
    family_run.save(update_fields=["target_count", "admit_status", "updated_at"])
    return family_run


def trigger_scan_execution(execution_id):
    execution = _claim_execution(execution_id)
    if execution.status in _TERMINAL:
        return {"status": execution.status, "execution_id": execution.id}

    task = execution.task
    total = 0
    families = []
    for model_id, pool in iter_scan_family_pools(task):
        family_run = _admit_family(task, execution, str(model_id), pool)
        total += int(family_run.target_count or 0)
        families.append(str(model_id))

    execution.target_count = total
    execution.deadline_at = estimate_deadline(total, task.timeout)
    execution.save(update_fields=["target_count", "deadline_at", "updated_at"])
    _schedule_finalize(execution.id, execution.claim_token)
    logger.info(
        "[ScanTrigger] 已触发 execution=%s families=%s target_count=%s",
        execution.id,
        families,
        total,
    )
    return {
        "status": "triggered",
        "execution_id": execution.id,
        "target_count": total,
        "claim_token": execution.claim_token,
    }


def _finish_execution(execution, claim_token, terminal_status):
    from apps.cmdb.services.scan_finalize_service import write_scan_execution

    execution.status = ScanExecution.STATUS_FINALIZING
    execution.save(update_fields=["status", "updated_at"])
    try:
        write_scan_execution(execution)
    except Exception:
        logger.exception("[ScanTrigger] 收口写 CI 失败 execution=%s", execution.id)
        execution.status = ScanExecution.STATUS_FAILED
        execution.finished_at = now()
        execution.save(update_fields=["status", "finished_at", "updated_at"])
        return {"status": "failed", "execution_id": execution.id}

    execution.refresh_from_db()
    if execution.claim_token != claim_token:
        return {"status": "stale", "execution_id": execution.id}
    execution.status = terminal_status
    execution.finished_at = now()
    execution.save(update_fields=["status", "finished_at", "updated_at"])
    return {"status": terminal_status, "execution_id": execution.id}


def poll_scan_finalize(execution_id, claim_token):
    execution = ScanExecution.objects.filter(pk=execution_id).first()
    if execution is None or execution.claim_token != claim_token:
        return {"status": "stale", "execution_id": execution_id}
    if execution.status in _TERMINAL:
        return {"status": execution.status, "execution_id": execution.id}
    if execution.status == ScanExecution.STATUS_FINALIZING:
        return {"status": execution.status, "execution_id": execution.id}

    timed_out = bool(execution.deadline_at and now() >= execution.deadline_at)
    received_done = execution.target_count > 0 and execution.received_count >= execution.target_count
    empty_shot = execution.target_count == 0

    if empty_shot:
        execution.status = ScanExecution.STATUS_FAILED
        execution.finished_at = now()
        execution.save(update_fields=["status", "finished_at", "updated_at"])
        return {"status": "failed", "execution_id": execution.id}

    if timed_out:
        return _finish_execution(execution, claim_token, ScanExecution.STATUS_TIMED_OUT)

    if received_done:
        return _finish_execution(execution, claim_token, ScanExecution.STATUS_COMPLETED)

    _schedule_finalize(execution.id, claim_token)
    return {"status": "waiting", "execution_id": execution.id}
