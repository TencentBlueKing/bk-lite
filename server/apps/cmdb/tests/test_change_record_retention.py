import json
import logging
from datetime import timedelta

import pytest
from django.utils.timezone import now

from apps.cmdb.models.change_record import UPDATE_INST, ChangeRecord
from apps.cmdb.models.operation import CmdbUniqueWriteLock
from apps.cmdb.services.change_record_retention import (
    DEFAULT_POLICY,
    JOB_KEY,
    LEASE_SECONDS,
    LOCK_KEY,
    POLICY_KEY,
    delete_by_count,
    delete_by_days,
    job_is_blocking,
    read_job,
    read_policy,
    run_cleanup,
    save_policy,
    write_job,
)
from apps.cmdb.services.unique_write_lock import UniqueWriteLockService
from apps.core.exceptions.base_app_exception import ValidationAppException
from apps.system_mgmt.models import SystemSettings
from apps.system_mgmt.models.operation_log import OperationLog

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_change_records():
    # Shared --reuse-db can already contain committed rows. Count-based deletes
    # observe the whole table, so each test starts from an empty ChangeRecord set.
    # Policy, job, and the retention lock likewise survive reuse.
    ChangeRecord.objects.all().delete()
    SystemSettings.objects.filter(key__in=(POLICY_KEY, JOB_KEY)).delete()
    CmdbUniqueWriteLock.objects.filter(lock_key=LOCK_KEY).delete()


def test_read_policy_defaults_to_off_when_missing():
    assert read_policy() == DEFAULT_POLICY


def test_read_policy_treats_invalid_json_as_off():
    SystemSettings.objects.create(key="cmdb_change_record_retention_policy", value="not-json")
    assert read_policy()["mode"] == "off"


def test_save_policy_rejects_zero_days():
    with pytest.raises(ValidationAppException):
        save_policy({"mode": "by_days", "days": 0})


def test_save_policy_off_ignores_numbers():
    saved = save_policy({"mode": "off", "days": 9, "count": 9})
    assert saved == {"mode": "off", "days": None, "count": None}
    row = SystemSettings.objects.get(key="cmdb_change_record_retention_policy")
    assert json.loads(row.value)["mode"] == "off"


def test_save_policy_by_count():
    saved = save_policy({"mode": "by_count", "count": "10"})
    assert saved == {"mode": "by_count", "days": None, "count": 10}


def _record(created_at):
    row = ChangeRecord.objects.create(model_id="host", label="host", type=UPDATE_INST, operator="t")
    ChangeRecord.objects.filter(pk=row.pk).update(created_at=created_at)
    return row


def test_delete_by_days_keeps_recent():
    old = now() - timedelta(days=200)
    recent = now() - timedelta(days=10)
    gone = _record(old)
    kept = _record(recent)
    deleted = delete_by_days(180)
    assert deleted == 1
    assert not ChangeRecord.objects.filter(pk=gone.pk).exists()
    assert ChangeRecord.objects.filter(pk=kept.pk).exists()


def test_delete_by_count_keeps_newest():
    base = now()
    rows = [_record(base - timedelta(days=i)) for i in range(5, 0, -1)]
    deleted = delete_by_count(3)
    assert deleted == 2
    remaining = list(ChangeRecord.objects.order_by("created_at", "id").values_list("id", flat=True))
    assert remaining == [rows[2].id, rows[3].id, rows[4].id]


def test_delete_by_count_noop_when_under_limit():
    _record(now())
    assert delete_by_count(10) == 0
    assert ChangeRecord.objects.count() == 1


def test_delete_does_not_touch_operation_log():
    OperationLog.objects.create(
        username="t",
        source_ip="127.0.0.1",
        app="cmdb",
        action_type=OperationLog.ACTION_UPDATE,
        summary="keep",
    )
    _record(now() - timedelta(days=400))
    delete_by_days(180)
    assert OperationLog.objects.count() == 1


def test_job_defaults_idle():
    assert read_job()["status"] == "idle"
    assert job_is_blocking() is False


def test_job_is_blocking_while_fresh_running():
    write_job({**read_job(), "status": "running", "started_at": now().isoformat()})
    assert job_is_blocking() is True


def test_stale_running_job_is_not_blocking():
    started = (now() - timedelta(seconds=LEASE_SECONDS + 10)).isoformat()
    write_job({**read_job(), "status": "running", "started_at": started})
    assert job_is_blocking() is False


def test_job_is_blocking_when_lock_held_even_if_started_stale():
    started = (now() - timedelta(seconds=LEASE_SECONDS + 10)).isoformat()
    write_job({**read_job(), "status": "running", "started_at": started})
    UniqueWriteLockService.acquire(LOCK_KEY, owner_token="retention-owner", lease_seconds=LEASE_SECONDS)
    assert job_is_blocking() is True


def test_run_cleanup_off_deletes_nothing():
    _record(now() - timedelta(days=400))
    result = run_cleanup("cron")
    assert result["status"] == "ok"
    assert result["deleted_count"] == 0
    assert ChangeRecord.objects.count() == 1
    assert read_job()["status"] == "idle"


def test_run_cleanup_by_days_and_returns_idle():
    save_policy({"mode": "by_days", "days": 180})
    _record(now() - timedelta(days=400))
    _record(now() - timedelta(days=1))
    result = run_cleanup("save")
    assert result["deleted_count"] == 1
    assert ChangeRecord.objects.count() == 1
    job = read_job()
    assert job["status"] == "idle"
    assert job["trigger"] == "save"
    assert job["error"] == ""


def test_run_cleanup_skips_when_lock_held():
    UniqueWriteLockService.acquire("cmdb-change-record-retention", owner_token="other", lease_seconds=60)
    try:
        result = run_cleanup("cron")
        assert result["status"] == "skipped_locked"
    finally:
        UniqueWriteLockService.release("cmdb-change-record-retention", owner_token="other")


def test_run_cleanup_logs_lifecycle_and_error_without_payload(monkeypatch, caplog):
    sentinel = "PAYLOAD-SENTINEL-retention-secret"
    save_policy({"mode": "by_days", "days": 180})
    _record(now() - timedelta(days=400))
    _record(now() - timedelta(days=1))
    caplog.set_level(logging.INFO, logger="cmdb")

    result = run_cleanup("save")

    assert result == {"status": "ok", "deleted_count": 1}
    assert read_job()["status"] == "idle"
    started = [record for record in caplog.records if record.msg == "change record retention started trigger=%s mode=%s days=%s count=%s"]
    finished = [record for record in caplog.records if record.msg == "change record retention finished trigger=%s deleted_count=%s elapsed_ms=%s"]
    assert len(started) == 1
    assert started[0].args == ("save", "by_days", 180, None)
    assert started[0].getMessage() == "change record retention started trigger=save mode=by_days days=180 count=None"
    assert len(finished) == 1
    assert finished[0].args[0] == "save"
    assert finished[0].args[1] == 1
    assert isinstance(finished[0].args[2], int)
    rendered = "\n".join(record.getMessage() for record in caplog.records)
    assert sentinel not in rendered

    raised = {}

    def boom(_days, **_kwargs):
        try:
            raise RuntimeError(sentinel)
        except RuntimeError as exc:
            raised["error"] = exc
            raise

    monkeypatch.setattr("apps.cmdb.services.change_record_retention.delete_by_days", boom)
    caplog.clear()
    failed_result = run_cleanup("cron")
    assert failed_result == {"status": "error", "deleted_count": 0, "error": "RuntimeError"}
    job = read_job()
    assert job["status"] == "idle"
    assert job["error"] == "RuntimeError"
    assert job["trigger"] == "cron"
    failed = [record for record in caplog.records if record.levelno == logging.ERROR]
    assert len(failed) == 1
    assert failed[0].msg == "change record retention failed trigger=%s error_type=%s failed_stage=cleanup"
    assert failed[0].args == ("cron", "RuntimeError")
    assert failed[0].getMessage() == "change record retention failed trigger=cron error_type=RuntimeError failed_stage=cleanup"
    assert failed[0].exc_info[2] is raised["error"].__traceback__
    assert failed[0].exc_info[1] is not raised["error"]
    assert sentinel not in failed[0].getMessage()
    assert sentinel not in str(failed[0].args)
    assert sentinel not in str(failed[0].exc_info[1])
    formatted = logging.Formatter().format(failed[0])
    assert sentinel not in formatted
    assert "RuntimeError" in formatted


def test_run_cleanup_takes_over_stale_running_job(monkeypatch):
    started = (now() - timedelta(seconds=LEASE_SECONDS + 10)).isoformat()
    write_job(
        {
            **read_job(),
            "status": "running",
            "started_at": started,
            "trigger": "save",
            "deleted_count": 4,
        }
    )
    writes = []
    real_write = write_job

    def spy(job):
        writes.append(dict(job))
        return real_write(job)

    monkeypatch.setattr("apps.cmdb.services.change_record_retention.write_job", spy)
    result = run_cleanup("cron")
    assert result["status"] == "ok"
    assert result["deleted_count"] == 0
    job = read_job()
    assert job["status"] == "idle"
    assert job["trigger"] == "cron"
    assert job["error"] == ""
    closed = writes[0]
    assert closed["status"] == "idle"
    assert closed["error"] == "StaleLock"
    assert closed["trigger"] == "save"
    assert closed["started_at"] == started
    assert closed["deleted_count"] == 4
    assert closed["finished_at"]


def test_run_cleanup_stops_when_renew_fails(monkeypatch):
    save_policy({"mode": "by_days", "days": 180})
    old = now() - timedelta(days=400)
    for offset in range(3):
        _record(old - timedelta(minutes=offset))
    monkeypatch.setattr("apps.cmdb.services.change_record_retention.BATCH_SIZE", 1)

    def deny_renew(lock_key, *, owner_token, lease_seconds):
        assert lock_key == LOCK_KEY
        assert owner_token
        assert lease_seconds == LEASE_SECONDS
        return False

    monkeypatch.setattr(UniqueWriteLockService, "renew", deny_renew)
    result = run_cleanup("cron")
    assert result["status"] == "error"
    assert result["error"] == "LostLock"
    assert result["deleted_count"] == 1
    assert ChangeRecord.objects.count() == 2
    job = read_job()
    assert job["status"] == "running"
    assert job["error"] == ""
    assert job["deleted_count"] == 0
    assert job["trigger"] == "cron"


def test_lost_lock_does_not_write_terminal_job(monkeypatch):
    save_policy({"mode": "by_days", "days": 180})
    _record(now() - timedelta(days=400))

    def deny_renew(lock_key, *, owner_token, lease_seconds):
        assert lock_key == LOCK_KEY
        assert owner_token
        assert lease_seconds == LEASE_SECONDS
        return False

    monkeypatch.setattr(UniqueWriteLockService, "renew", deny_renew)
    result = run_cleanup("cron")
    assert result == {"status": "error", "deleted_count": 1, "error": "LostLock"}
    assert ChangeRecord.objects.count() == 0
    job = read_job()
    assert job["status"] == "running"
    assert job["error"] == ""
    assert job["deleted_count"] == 0
    assert job["trigger"] == "cron"


def test_beat_registers_retention_cleanup():
    from apps.cmdb.config import CELERY_BEAT_SCHEDULE
    from apps.core.celery_runtime.manifest import TASK_ROUTES

    entry = CELERY_BEAT_SCHEDULE["cleanup_change_record_retention"]
    assert entry["task"] == "apps.cmdb.tasks.change_record_retention.cleanup_change_record_retention"
    assert TASK_ROUTES[entry["task"]] == "background"


def test_celery_task_runs_cleanup_off(monkeypatch):
    from apps.cmdb.tasks.change_record_retention import cleanup_change_record_retention

    monkeypatch.setattr(
        "apps.cmdb.tasks.change_record_retention.run_cleanup",
        lambda trigger: {"status": "ok", "deleted_count": 0, "trigger": trigger},
    )
    assert cleanup_change_record_retention() == {"status": "ok", "deleted_count": 0, "trigger": "cron"}
    assert cleanup_change_record_retention(trigger="save")["trigger"] == "save"
