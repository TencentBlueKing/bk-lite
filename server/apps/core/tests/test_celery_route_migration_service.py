"""使用真实 Beat ORM 验证只更新路由和并发冲突下的原子恢复。"""

import json

import pytest
from django_celery_beat.models import IntervalSchedule, PeriodicTask

from apps.core.celery_runtime.periodic_routes import migrate_routes, restore_routes

pytestmark = pytest.mark.django_db
NAME = "apps.monitor.tasks.monitor_policy.scan_policy_task"


@pytest.fixture
def periodic():
    interval = IntervalSchedule.objects.create(every=30, period="seconds")
    return PeriodicTask.objects.create(name="runtime-route-test", task=NAME, interval=interval, args='["keep"]', queue="celery")


def test_default_dry_run_never_writes_database_or_snapshot(periodic, tmp_path):
    snapshot = tmp_path / "routes.json"
    changes = migrate_routes([periodic.pk], registered={NAME}, snapshot=snapshot)
    periodic.refresh_from_db()
    assert periodic.queue == "celery"
    assert not snapshot.exists()
    assert changes[0]["after"]["queue"] == "critical"


def test_apply_and_restore_preserve_business_fields(periodic, tmp_path):
    snapshot = tmp_path / "routes.json"
    before = {key: getattr(periodic, key) for key in ("task", "interval_id", "args", "enabled", "name")}
    migrate_routes([periodic.pk], registered={NAME}, snapshot=snapshot, apply=True)
    periodic.refresh_from_db()
    assert periodic.queue == "critical"
    assert before == {key: getattr(periodic, key) for key in before}
    assert json.loads(snapshot.read_text())["changes"][0]["before"]["queue"] == "celery"
    restore_routes(snapshot, apply=True)
    periodic.refresh_from_db()
    assert periodic.queue == "celery"


def test_restore_refuses_concurrent_changes(periodic, tmp_path):
    snapshot = tmp_path / "routes.json"
    migrate_routes([periodic.pk], registered={NAME}, snapshot=snapshot, apply=True)
    PeriodicTask.objects.filter(pk=periodic.pk).update(queue="notification")
    with pytest.raises(ValueError, match="冲突"):
        restore_routes(snapshot, apply=True)
    periodic.refresh_from_db()
    assert periodic.queue == "notification"


def test_batch_restore_conflict_never_partially_restores_other_rows(periodic, tmp_path):
    another = PeriodicTask.objects.create(name="another-runtime-task", task=NAME, interval=periodic.interval, queue="celery")
    snapshot = tmp_path / "batch.json"
    migrate_routes([periodic.pk, another.pk], registered={NAME}, snapshot=snapshot, apply=True)
    PeriodicTask.objects.filter(pk=another.pk).update(queue="notification")
    with pytest.raises(ValueError, match="冲突"):
        restore_routes(snapshot, apply=True)
    periodic.refresh_from_db()
    another.refresh_from_db()
    assert periodic.queue == "critical"
    assert another.queue == "notification"


def test_unregistered_task_is_not_silently_repaired(periodic, tmp_path):
    with pytest.raises(ValueError, match="注册"):
        migrate_routes([periodic.pk], registered=set(), snapshot=tmp_path / "routes.json", apply=True)
    periodic.refresh_from_db()
    assert periodic.queue == "celery"


def test_existing_snapshot_is_never_overwritten(periodic, tmp_path):
    snapshot = tmp_path / "routes.json"
    snapshot.write_text("previous")
    with pytest.raises(FileExistsError):
        migrate_routes([periodic.pk], registered={NAME}, snapshot=snapshot, apply=True)
    periodic.refresh_from_db()
    assert periodic.queue == "celery"
    assert snapshot.read_text() == "previous"
