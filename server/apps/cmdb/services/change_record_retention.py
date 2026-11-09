import json
from datetime import timedelta

from django.utils.dateparse import parse_datetime
from django.utils.timezone import is_aware, make_aware, now

from apps.cmdb.models.change_record import ChangeRecord
from apps.cmdb.models.operation import CmdbUniqueWriteLock
from apps.cmdb.services.unique_write_lock import UniqueWriteLockService
from apps.core.exceptions.base_app_exception import ValidationAppException
from apps.core.logger import cmdb_logger as logger
from apps.system_mgmt.models import SystemSettings

POLICY_KEY = "cmdb_change_record_retention_policy"
JOB_KEY = "cmdb_change_record_retention_job"
LOCK_KEY = "cmdb-change-record-retention"
LEASE_SECONDS = 7200
BATCH_SIZE = 1000
MODES = ("off", "by_days", "by_count")

DEFAULT_POLICY = {"mode": "off", "days": None, "count": None}
DEFAULT_JOB = {
    "status": "idle",
    "started_at": None,
    "finished_at": None,
    "deleted_count": 0,
    "error": "",
    "trigger": "",
}


def _load_setting(key: str, default: dict) -> dict:
    row = SystemSettings.objects.filter(key=key).first()
    if row is None or row.value in (None, ""):
        return dict(default)
    try:
        data = json.loads(row.value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return dict(default)
    if not isinstance(data, dict):
        return dict(default)
    return data


def _write_setting(key: str, payload: dict) -> None:
    SystemSettings.objects.update_or_create(key=key, defaults={"value": json.dumps(payload, ensure_ascii=False)})


def read_policy() -> dict:
    raw = _load_setting(POLICY_KEY, DEFAULT_POLICY)
    mode = raw.get("mode")
    if mode not in MODES:
        return dict(DEFAULT_POLICY)
    if mode == "off":
        return dict(DEFAULT_POLICY)
    if mode == "by_days":
        try:
            days = int(raw.get("days"))
        except (TypeError, ValueError):
            return dict(DEFAULT_POLICY)
        if days < 1:
            return dict(DEFAULT_POLICY)
        return {"mode": "by_days", "days": days, "count": None}
    try:
        count = int(raw.get("count"))
    except (TypeError, ValueError):
        return dict(DEFAULT_POLICY)
    if count < 1:
        return dict(DEFAULT_POLICY)
    return {"mode": "by_count", "days": None, "count": count}


def save_policy(payload: dict | None) -> dict:
    data = payload or {}
    mode = data.get("mode")
    if mode not in MODES:
        raise ValidationAppException("保留策略 mode 非法")
    if mode == "off":
        policy = dict(DEFAULT_POLICY)
    elif mode == "by_days":
        try:
            days = int(data.get("days"))
        except (TypeError, ValueError) as exc:
            raise ValidationAppException("保留天数必须是正整数") from exc
        if days < 1:
            raise ValidationAppException("保留天数必须是正整数")
        policy = {"mode": "by_days", "days": days, "count": None}
    else:
        try:
            count = int(data.get("count"))
        except (TypeError, ValueError) as exc:
            raise ValidationAppException("保留条数必须是正整数") from exc
        if count < 1:
            raise ValidationAppException("保留条数必须是正整数")
        policy = {"mode": "by_count", "days": None, "count": count}
    _write_setting(POLICY_KEY, policy)
    return policy


class LostLock(Exception):
    def __init__(self, deleted: int):
        super().__init__("LostLock")
        self.deleted = deleted


def _delete_ids(ids: list[int]) -> int:
    if not ids:
        return 0
    deleted, _ = ChangeRecord.objects.filter(id__in=ids).delete()
    return deleted


def _note_deleted(progress: dict | None, deleted: int) -> None:
    if progress is not None:
        progress["deleted"] = deleted


def _renew_or_stop(owner_token: str | None, deleted: int) -> None:
    if owner_token is None:
        return
    if not _still_owns_lock(owner_token):
        raise LostLock(deleted)


def _still_owns_lock(owner_token: str) -> bool:
    return bool(UniqueWriteLockService.renew(LOCK_KEY, owner_token=owner_token, lease_seconds=LEASE_SECONDS))


def _lost_lock_result(trigger: str, deleted: int, exc: BaseException | None = None) -> dict:
    if exc is None:
        logger.error(
            "change record retention failed trigger=%s error_type=%s failed_stage=cleanup",
            trigger,
            "LostLock",
        )
    else:
        logger.error(
            "change record retention failed trigger=%s error_type=%s failed_stage=cleanup",
            trigger,
            "LostLock",
            exc_info=(type(exc), RuntimeError("LostLock"), exc.__traceback__),
        )
    return {"status": "error", "deleted_count": deleted, "error": "LostLock"}


def delete_by_days(days: int, *, owner_token: str | None = None, progress: dict | None = None) -> int:
    cutoff = now() - timedelta(days=days)
    total = 0
    while True:
        ids = list(ChangeRecord.objects.filter(created_at__lt=cutoff).order_by("created_at", "id").values_list("id", flat=True)[:BATCH_SIZE])
        removed = _delete_ids(ids)
        total += removed
        _note_deleted(progress, total)
        if removed == 0:
            return total
        _renew_or_stop(owner_token, total)


def delete_by_count(count: int, *, owner_token: str | None = None, progress: dict | None = None) -> int:
    total_rows = ChangeRecord.objects.count()
    if total_rows <= count:
        return 0
    remaining = total_rows - count
    deleted = 0
    while remaining > 0:
        batch = min(BATCH_SIZE, remaining)
        ids = list(ChangeRecord.objects.order_by("created_at", "id").values_list("id", flat=True)[:batch])
        removed = _delete_ids(ids)
        if removed == 0:
            _note_deleted(progress, deleted)
            return deleted
        deleted += removed
        remaining -= removed
        _note_deleted(progress, deleted)
        _renew_or_stop(owner_token, deleted)
    return deleted


def read_job() -> dict:
    raw = _load_setting(JOB_KEY, DEFAULT_JOB)
    job = dict(DEFAULT_JOB)
    job.update({k: raw.get(k, job[k]) for k in DEFAULT_JOB})
    if job["status"] not in ("idle", "running"):
        job["status"] = "idle"
    return job


def write_job(job: dict) -> dict:
    payload = dict(DEFAULT_JOB)
    payload.update(job)
    _write_setting(JOB_KEY, payload)
    return payload


def _parse_started(value):
    if not value:
        return None
    parsed = parse_datetime(str(value))
    if parsed is None:
        return None
    if not is_aware(parsed):
        parsed = make_aware(parsed)
    return parsed


def _lock_is_held() -> bool:
    persistable = UniqueWriteLockService._persistable_lock_key(LOCK_KEY)
    return CmdbUniqueWriteLock.objects.filter(lock_key=persistable, lease_expires_at__gt=now()).exists()


def job_is_blocking() -> bool:
    if _lock_is_held():
        return True
    job = read_job()
    if job.get("status") != "running":
        return False
    started = _parse_started(job.get("started_at"))
    if started is None:
        return True
    return now() - started < timedelta(seconds=LEASE_SECONDS)


def present_job() -> dict:
    job = read_job()
    if job.get("status") == "running" and not job_is_blocking():
        return {**job, "status": "idle"}
    return job


def _iso(value):
    return value.isoformat() if value is not None else None


def _run_cleanup_locked(trigger: str, owner_token: str) -> dict:
    previous = read_job()
    if previous["status"] == "running":
        write_job(
            {
                **previous,
                "status": "idle",
                "finished_at": _iso(now()),
                "error": "StaleLock",
            }
        )
    started = now()
    write_job(
        {
            "status": "running",
            "started_at": _iso(started),
            "finished_at": None,
            "deleted_count": 0,
            "error": "",
            "trigger": trigger,
        }
    )
    policy = read_policy()
    logger.info(
        "change record retention started trigger=%s mode=%s days=%s count=%s",
        trigger,
        policy["mode"],
        policy["days"],
        policy["count"],
    )
    progress = {"deleted": 0}
    try:
        if policy["mode"] == "by_days":
            deleted = delete_by_days(policy["days"], owner_token=owner_token, progress=progress)
        elif policy["mode"] == "by_count":
            deleted = delete_by_count(policy["count"], owner_token=owner_token, progress=progress)
        else:
            deleted = 0
        if not _still_owns_lock(owner_token):
            return _lost_lock_result(trigger, deleted)
        finished = now()
        write_job(
            {
                "status": "idle",
                "started_at": _iso(started),
                "finished_at": _iso(finished),
                "deleted_count": deleted,
                "error": "",
                "trigger": trigger,
            }
        )
        logger.info(
            "change record retention finished trigger=%s deleted_count=%s elapsed_ms=%s",
            trigger,
            deleted,
            int((finished - started).total_seconds() * 1000),
        )
        return {"status": "ok", "deleted_count": deleted}
    except Exception as exc:
        deleted = progress["deleted"]
        if not _still_owns_lock(owner_token):
            return _lost_lock_result(trigger, deleted, exc)
        error_type = type(exc).__name__
        write_job(
            {
                "status": "idle",
                "started_at": _iso(started),
                "finished_at": _iso(now()),
                "deleted_count": deleted,
                "error": error_type,
                "trigger": trigger,
            }
        )
        logger.error(
            "change record retention failed trigger=%s error_type=%s failed_stage=cleanup",
            trigger,
            error_type,
            exc_info=(type(exc), RuntimeError(error_type), exc.__traceback__),
        )
        return {"status": "error", "deleted_count": deleted, "error": error_type}


def run_cleanup(trigger: str = "cron") -> dict:
    try:
        with UniqueWriteLockService.serialize(LOCK_KEY, lease_seconds=LEASE_SECONDS) as owner_token:
            return _run_cleanup_locked(trigger, owner_token)
    except TimeoutError:
        logger.info("change record retention skipped lock held trigger=%s", trigger)
        return {"status": "skipped_locked"}
