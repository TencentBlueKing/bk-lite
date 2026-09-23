from datetime import timedelta
from uuid import uuid4

from django.db import transaction
from django.utils.dateparse import parse_datetime
from django.utils.timezone import now

from apps.cmdb.constants.constants import CollectDriverTypes
from apps.cmdb.models.scan_model import (
    SCAN_DATABASE_FAMILY,
    SCAN_DATABASE_TYPES,
    SCAN_MIDDLEWARE_FAMILY,
    SCAN_MIDDLEWARE_TYPES,
    ScanExecution,
    ScanFamilyRun,
    ScanTask,
    agent_placeholder_pool,
    default_scan_snmp_pool,
    is_agent_credential,
    scan_driver_type_for_model,
)
from apps.cmdb.services import scan_schedule_service as scan_schedule
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
SCAN_JOB_BATCH_STUCK_FACTOR = 3

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


def _batch_deadline(task: ScanTask):
    plugin_timeout = task.timeout or SCAN_DEFAULT_PLUGIN_TIMEOUT
    seconds = max(SCAN_WALL_CLOCK_MIN.total_seconds(), plugin_timeout * SCAN_JOB_BATCH_STUCK_FACTOR)
    return now() + timedelta(seconds=seconds)


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
                next_item["user"] = next_item.get("username")
            expanded.append(next_item)
    return expanded


def _job_ssh_port(raw_port) -> int:
    try:
        port = int(raw_port)
    except (TypeError, ValueError):
        return 22
    if port <= 0 or port in set(scan_schedule.middleware_listen_ports()):
        return 22
    return port


def _coerce_job_ssh_pool(pool: list) -> list:
    coerced = []
    for item in pool or []:
        if not isinstance(item, dict):
            coerced.append(item)
            continue
        next_item = dict(item)
        next_item["port"] = _job_ssh_port(next_item.get("port"))
        coerced.append(next_item)
    return coerced


def _job_ssh_pool_ready(pool: list) -> bool:
    for item in pool or []:
        if not isinstance(item, dict):
            continue
        if item.get("credential_source") == "vault" and item.get("vault_credential_id"):
            return True
        if is_agent_credential(item):
            return True
        if item.get("password") or item.get("private_key") or item.get("key"):
            return True
    return False


def _middleware_scan_pool(task: ScanTask, decrypted) -> list:
    pool = CollectCredentialPoolService.normalize_pool(decrypted.get(SCAN_MIDDLEWARE_FAMILY) or [])
    if not _job_ssh_pool_ready(pool) and "host" in (task.families or []):
        logger.debug("[ScanTrigger] 中间件 SSH 凭据不完整，改用主机凭据 task=%s", task.id)
        pool = CollectCredentialPoolService.normalize_pool(decrypted.get("host") or [])
    if not _job_ssh_pool_ready(pool):
        pool = agent_placeholder_pool()
    return _coerce_job_ssh_pool(pool)


def _iter_other_family_pools(task: ScanTask, decrypted, families, skip):
    for model_id in families:
        if model_id in skip or model_id in SCAN_MIDDLEWARE_TYPES:
            continue
        if model_id == SCAN_MIDDLEWARE_FAMILY:
            pool = _middleware_scan_pool(task, decrypted)
            for mw_type in sorted(SCAN_MIDDLEWARE_TYPES):
                yield str(mw_type), pool
            continue
        yield str(model_id), CollectCredentialPoolService.normalize_pool(decrypted.get(model_id) or [])


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
        yield from _iter_other_family_pools(
            task,
            decrypted,
            families,
            skip={SCAN_DATABASE_FAMILY, *SCAN_DATABASE_TYPES},
        )
        return
    yield from _iter_other_family_pools(task, decrypted, families, skip=set())


def _split_family_pools(task: ScanTask):
    protocol = []
    for model_id, pool in iter_scan_family_pools(task):
        if scan_schedule.is_scan_job_model(str(model_id)):
            continue
        protocol.append((str(model_id), pool))
    return protocol


def _pool_for_model(task: ScanTask, model_id: str) -> list:
    decrypted = task.decrypt_credentials or {}
    if model_id in SCAN_MIDDLEWARE_TYPES:
        return _middleware_scan_pool(task, decrypted)
    if model_id == "network":
        return default_scan_snmp_pool(CollectCredentialPoolService.normalize_pool(decrypted.get(model_id) or []))
    pool = CollectCredentialPoolService.normalize_pool(decrypted.get(model_id) or [])
    if not pool and model_id == "host":
        pool = agent_placeholder_pool()
    return pool


def _admit_family(task: ScanTask, execution: ScanExecution, model_id: str, pool=None, ip_ranges=None, batch_index=0) -> ScanFamilyRun:
    driver_type = scan_driver_type_for_model(model_id)
    family_run, _created = ScanFamilyRun.objects.get_or_create(
        execution=execution,
        model_id=model_id,
        driver_type=driver_type,
        batch_index=batch_index,
    )
    if family_run.admit_status in {ScanFamilyRun.ADMIT_ACCEPTED, ScanFamilyRun.ADMIT_DUPLICATE, ScanFamilyRun.ADMIT_FAILED}:
        return family_run
    if pool is None:
        pool = _pool_for_model(task, model_id)
    if model_id == "network":
        pool = default_scan_snmp_pool(pool)
    if not pool and model_id in {"host", *SCAN_MIDDLEWARE_TYPES}:
        pool = agent_placeholder_pool()
    if not pool:
        family_run.admit_status = ScanFamilyRun.ADMIT_FAILED
        family_run.target_count = 0
        family_run.save(update_fields=["admit_status", "target_count", "updated_at"])
        return family_run

    params = {"has_network_topo": False}
    if driver_type == CollectDriverTypes.JOB:
        params["ip_precheck"] = True
    if task.cloud_region and (model_id == "host" or model_id in SCAN_MIDDLEWARE_TYPES):
        params["cloud_region"] = task.cloud_region

    shot = ScanShot(
        id=family_run.id,
        model_id=model_id,
        driver_type=driver_type,
        ip_range=join_ip_ranges(ip_ranges if ip_ranges is not None else task.ip_ranges),
        instances=[],
        credential=pool,
        timeout=task.timeout or SCAN_DEFAULT_PLUGIN_TIMEOUT,
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


def _jobs_selected(schedule) -> bool:
    return bool(schedule.get("host_selected") or schedule.get("middleware_selected"))


def _protocol_released(execution: ScanExecution) -> bool:
    protocol_runs = [family_run for family_run in execution.family_runs.all() if not scan_schedule.is_scan_job_model(family_run.model_id)]
    if not protocol_runs:
        return True
    if all(scan_schedule.family_run_finished(family_run) for family_run in protocol_runs):
        return True
    return bool(execution.deadline_at and now() >= execution.deadline_at)


def _host_queue_finished(execution: ScanExecution, schedule) -> bool:
    if not schedule.get("host_selected"):
        return True
    if not schedule.get("host_enqueued"):
        return False
    cursor = int(schedule.get("job_cursor") or 0)
    queue = schedule.get("job_queue") or []
    host_pending = any(index >= cursor and item.get("model_id") == "host" for index, item in enumerate(queue))
    if host_pending:
        return False
    in_flight_id = schedule.get("in_flight_family_run_id")
    if in_flight_id:
        family_run = ScanFamilyRun.objects.filter(pk=in_flight_id).first()
        if family_run and family_run.model_id == "host" and not scan_schedule.family_run_finished(family_run):
            return False
    return all(scan_schedule.family_run_finished(family_run) for family_run in execution.family_runs.filter(model_id="host"))


def _ensure_job_queue(task: ScanTask, execution: ScanExecution) -> dict:
    schedule = dict(execution.schedule or {})
    hosts = scan_schedule.expand_scan_ip_ranges(task.ip_ranges)
    excluded = scan_schedule.snmp_success_hosts(execution)
    job_hosts = [host for host in hosts if host not in excluded]
    if schedule.get("host_selected") and not schedule.get("host_enqueued"):
        added = scan_schedule.append_job_batches(schedule, "host", job_hosts)
        schedule["host_enqueued"] = True
        logger.info("[ScanTrigger] 主机 JOB 已入队 execution=%s batches=%s hosts=%s", execution.id, added, len(job_hosts))
    if schedule.get("middleware_selected") and not schedule.get("middleware_enqueued"):
        if schedule.get("host_selected") and not _host_queue_finished(execution, schedule):
            execution.schedule = schedule
            execution.save(update_fields=["schedule", "updated_at"])
            return schedule
        if schedule.get("host_selected"):
            middleware_hosts = [host for host in scan_schedule.host_success_hosts(execution) if host not in excluded]
        else:
            middleware_hosts = job_hosts
        open_ports = scan_schedule.probe_open_ports(middleware_hosts, scan_schedule.middleware_listen_ports())
        by_type = scan_schedule.middleware_hosts_by_type(middleware_hosts, open_ports)
        added = 0
        for model_id, type_hosts in by_type.items():
            added += scan_schedule.append_job_batches(schedule, model_id, type_hosts)
        schedule["middleware_enqueued"] = True
        logger.info(
            "[ScanTrigger] 中间件 JOB 已入队 execution=%s batches=%s types=%s hosts=%s probed=%s",
            execution.id,
            added,
            len(by_type),
            len(middleware_hosts),
            int(bool(open_ports)),
        )
    execution.schedule = schedule
    execution.save(update_fields=["schedule", "updated_at"])
    return schedule


def _batch_stuck(schedule) -> bool:
    raw = schedule.get("batch_deadline_at")
    if not raw:
        return False
    deadline = parse_datetime(str(raw))
    if deadline is None:
        return False
    return now() >= deadline


def _clear_in_flight(schedule) -> dict:
    schedule["in_flight_family_run_id"] = None
    schedule["batch_deadline_at"] = None
    schedule["job_cursor"] = int(schedule.get("job_cursor") or 0) + 1
    return schedule


def _admit_queue_item(task: ScanTask, execution: ScanExecution, item) -> ScanFamilyRun:
    model_id = str(item.get("model_id") or "")
    batch_index = int(item.get("batch_index") or 0)
    pool = _pool_for_model(task, model_id)
    previous_status = None
    existing = ScanFamilyRun.objects.filter(
        execution=execution,
        model_id=model_id,
        driver_type=scan_driver_type_for_model(model_id),
        batch_index=batch_index,
    ).first()
    if existing is not None:
        previous_status = existing.admit_status
    family_run = _admit_family(
        task,
        execution,
        model_id,
        pool,
        ip_ranges=item.get("ip_ranges") or [],
        batch_index=batch_index,
    )
    if previous_status in {ScanFamilyRun.ADMIT_ACCEPTED, ScanFamilyRun.ADMIT_DUPLICATE, ScanFamilyRun.ADMIT_FAILED}:
        added = 0
    else:
        added = int(family_run.target_count or 0)
    if added:
        execution.target_count = int(execution.target_count or 0) + added
    deadline = _batch_deadline(task)
    schedule = dict(execution.schedule or {})
    schedule["in_flight_family_run_id"] = family_run.id
    schedule["batch_deadline_at"] = deadline.isoformat()
    execution.schedule = schedule
    execution.deadline_at = deadline
    execution.save(update_fields=["target_count", "deadline_at", "schedule", "updated_at"])
    logger.info(
        "[ScanTrigger] 接纳 JOB 批次 execution=%s model_id=%s batch_index=%s target_count=%s",
        execution.id,
        model_id,
        batch_index,
        execution.target_count,
    )
    return family_run


def _advance_scan_jobs(task: ScanTask, execution: ScanExecution) -> bool:
    if not _jobs_selected(execution.schedule or {}):
        return False
    if not _protocol_released(execution):
        return False
    schedule = dict(execution.schedule or {})
    in_flight_id = schedule.get("in_flight_family_run_id")
    if in_flight_id:
        family_run = ScanFamilyRun.objects.filter(pk=in_flight_id).first()
        if family_run and not scan_schedule.family_run_finished(family_run):
            if not _batch_stuck(schedule):
                return True
            logger.info("[ScanTrigger] 跳过卡住的 JOB 批次 execution=%s family_run=%s", execution.id, family_run.id)
        schedule = _clear_in_flight(schedule)
        execution.schedule = schedule
        execution.save(update_fields=["schedule", "updated_at"])
    schedule = _ensure_job_queue(task, execution)
    cursor = int(schedule.get("job_cursor") or 0)
    queue = schedule.get("job_queue") or []
    if cursor >= len(queue):
        schedule = _ensure_job_queue(task, execution)
        cursor = int(schedule.get("job_cursor") or 0)
        queue = schedule.get("job_queue") or []
    if cursor >= len(queue):
        return False
    _admit_queue_item(task, execution, queue[cursor])
    return True


def _job_work_pending(execution: ScanExecution) -> bool:
    schedule = execution.schedule or {}
    if not _jobs_selected(schedule):
        return False
    if schedule.get("host_selected") and not schedule.get("host_enqueued"):
        return True
    if schedule.get("middleware_selected") and not schedule.get("middleware_enqueued"):
        return True
    cursor = int(schedule.get("job_cursor") or 0)
    queue = schedule.get("job_queue") or []
    if cursor < len(queue):
        return True
    in_flight_id = schedule.get("in_flight_family_run_id")
    if not in_flight_id:
        return False
    family_run = ScanFamilyRun.objects.filter(pk=in_flight_id).first()
    if family_run is None:
        return False
    return not scan_schedule.family_run_finished(family_run) and not _batch_stuck(schedule)


def trigger_scan_execution(execution_id):
    execution = _claim_execution(execution_id)
    if execution.status in _TERMINAL:
        return {"status": execution.status, "execution_id": execution.id}

    task = execution.task
    total = 0
    families = []
    for model_id, pool in _split_family_pools(task):
        family_run = _admit_family(task, execution, str(model_id), pool)
        total += int(family_run.target_count or 0)
        families.append(str(model_id))

    execution.target_count = total
    execution.deadline_at = estimate_deadline(total, task.timeout)
    execution.schedule = scan_schedule.initial_scan_schedule(task)
    execution.save(update_fields=["target_count", "deadline_at", "schedule", "updated_at"])
    if _protocol_released(execution):
        _advance_scan_jobs(task, execution)
        execution.refresh_from_db()
        total = int(execution.target_count or 0)
    _schedule_finalize(execution.id, execution.claim_token)
    logger.info(
        "[ScanTrigger] 已触发 execution=%s protocol=%s job_pending=%s target_count=%s",
        execution.id,
        families,
        int(_job_work_pending(execution)),
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
    terminal_status = None
    with transaction.atomic():
        execution = ScanExecution.objects.select_for_update().filter(pk=execution_id).first()
        if execution is None or execution.claim_token != claim_token:
            return {"status": "stale", "execution_id": execution_id}
        if execution.status in _TERMINAL:
            return {"status": execution.status, "execution_id": execution.id}
        if execution.status == ScanExecution.STATUS_FINALIZING:
            return {"status": execution.status, "execution_id": execution.id}

        task = execution.task
        _advance_scan_jobs(task, execution)
        execution.refresh_from_db()

        if _job_work_pending(execution):
            _schedule_finalize(execution.id, execution.claim_token)
            return {"status": "waiting", "execution_id": execution.id}

        timed_out = bool(execution.deadline_at and now() >= execution.deadline_at)
        received_done = execution.target_count > 0 and execution.received_count >= execution.target_count
        empty_shot = execution.target_count == 0
        jobs_selected = _jobs_selected(execution.schedule or {})

        if empty_shot:
            execution.status = ScanExecution.STATUS_FAILED
            execution.finished_at = now()
            execution.save(update_fields=["status", "finished_at", "updated_at"])
            return {"status": "failed", "execution_id": execution.id}

        if received_done or jobs_selected:
            terminal_status = ScanExecution.STATUS_COMPLETED
        elif timed_out:
            terminal_status = ScanExecution.STATUS_TIMED_OUT
        else:
            _schedule_finalize(execution.id, execution.claim_token)
            return {"status": "waiting", "execution_id": execution.id}

    return _finish_execution(execution, claim_token, terminal_status)
