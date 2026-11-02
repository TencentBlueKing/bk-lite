"""自动关联待重算名单：写入后能查到，5 分钟任务排空并建成关联。"""

import pytest

from apps.cmdb.models.auto_relation_pending import AutoRelationPending
from apps.cmdb.services import auto_relation_reconcile as mod
from apps.cmdb.services.auto_relation_reconcile import (
    drain_auto_relation_pending,
    schedule_instance_auto_relation_reconcile,
    schedule_rule_auto_relation_full_sync,
)
from apps.cmdb.tests.test_auto_relation_reconcile_regression_service import MemoryGraph, association, instance

pytestmark = pytest.mark.django_db


def test_recording_an_instance_can_be_queried_and_repeat_writes_stay_one_row():
    schedule_instance_auto_relation_reconcile([3, "3", 0, -1, "bad", 5])
    schedule_instance_auto_relation_reconcile([5, 9])

    assert list(AutoRelationPending.objects.order_by("instance_id").values_list("instance_id", flat=True)) == [3, 5, 9]
    assert AutoRelationPending.objects.filter(model_asst_id__isnull=False).count() == 0


def test_empty_instance_schedule_writes_nothing():
    schedule_instance_auto_relation_reconcile([])
    schedule_instance_auto_relation_reconcile([0, -1, "bad"])

    assert AutoRelationPending.objects.count() == 0


def test_recording_a_rule_trims_blanks_and_keeps_one_row():
    schedule_rule_auto_relation_full_sync(["r1", " r1 ", "", None, "r2"])
    schedule_rule_auto_relation_full_sync(["r1"])

    assert list(AutoRelationPending.objects.order_by("model_asst_id").values_list("model_asst_id", flat=True)) == ["r1", "r2"]


def test_five_minute_task_is_a_singleton_with_lock_expiry():
    from celery.schedules import crontab

    from apps.cmdb.config import CELERY_BEAT_SCHEDULE
    from apps.cmdb.tasks.celery_tasks import reconcile_auto_relation_pending_task

    entry = CELERY_BEAT_SCHEDULE["reconcile_auto_relation_pending_task"]
    assert entry["task"] == "apps.cmdb.tasks.celery_tasks.reconcile_auto_relation_pending_task"
    assert entry["schedule"] == crontab(minute="*/5")
    assert reconcile_auto_relation_pending_task.lock_expiry == 30 * 60
    assert reconcile_auto_relation_pending_task.raise_on_duplicate is False


def test_drain_builds_associations_then_pending_rows_are_gone(monkeypatch):
    graph = MemoryGraph(
        [
            instance(1, "source", "a"),
            instance(2, "source", "b"),
            instance(11, "target", "a"),
            instance(12, "target", "b"),
        ]
    )
    associations = [association("r1"), dict(association("incoming"), src_model_id="elsewhere", dst_model_id="source")]
    monkeypatch.setattr(mod, "GraphClient", lambda: graph)
    monkeypatch.setattr(mod, "model_association_search", lambda model: associations)
    monkeypatch.setattr("apps.cmdb.services.instance.InstanceManage.check_asso_mapping", lambda data: None)
    synced = []
    monkeypatch.setattr(
        mod.AutoRelationRuleReconcileService,
        "full_sync_rule",
        classmethod(lambda cls, model_asst_id: synced.append((model_asst_id, len(graph.edges))) or {"success": True}),
    )

    schedule_instance_auto_relation_reconcile([1, 2])
    assert AutoRelationPending.objects.filter(instance_id__isnull=False).count() == 2

    result = drain_auto_relation_pending()

    assert result["instances"] == 2
    assert len(graph.edges) == 2
    assert synced == [("incoming", 2)]
    assert AutoRelationPending.objects.count() == 0


def test_failed_instance_stays_pending_for_the_next_run(monkeypatch):
    monkeypatch.setattr(
        mod.AutoRelationRuleReconcileService,
        "reconcile_for_instances",
        classmethod(
            lambda cls, ids, schedule_incoming=True: {
                "success": False,
                "failed": [{"instance_id": ids[0], "error": "graph unavailable"}],
            }
        ),
    )
    monkeypatch.setattr(
        mod.AutoRelationRuleReconcileService,
        "incoming_rule_ids",
        classmethod(lambda cls, ids: []),
    )

    schedule_instance_auto_relation_reconcile([7, 8])
    result = drain_auto_relation_pending()

    assert result["instances"] == 1
    assert list(AutoRelationPending.objects.values_list("instance_id", flat=True)) == [7]


def test_drain_failure_restores_the_batch_and_logs_one_traceback(monkeypatch, caplog):
    def explode(cls, ids, schedule_incoming=True):
        raise RuntimeError("graph unavailable")

    monkeypatch.setattr(mod.AutoRelationRuleReconcileService, "reconcile_for_instances", classmethod(explode))
    schedule_instance_auto_relation_reconcile([4])

    with caplog.at_level("ERROR", logger="cmdb"), pytest.raises(RuntimeError, match="graph unavailable"):
        drain_auto_relation_pending()

    assert list(AutoRelationPending.objects.values_list("instance_id", flat=True)) == [4]
    error_records = [record for record in caplog.records if record.levelname == "ERROR"]
    assert len(error_records) == 1
    assert error_records[0].exc_info[1].__traceback__ is not None
    message = error_records[0].getMessage()
    assert "failed_stage=reconcile_instances" in message
    assert "error_type=RuntimeError" in message


def test_legacy_tasks_only_record_pending_rows():
    from apps.cmdb.tasks.celery_tasks import (
        full_sync_auto_association_rule_task,
        reconcile_instance_auto_association_task,
        reconcile_instances_auto_association_task,
        sync_incoming_auto_association_task,
    )

    assert reconcile_instance_auto_association_task(9) == {"recorded": True, "instance_id": 9}
    assert reconcile_instances_auto_association_task([9, 10]) == {"recorded": True, "count": 2}
    assert sync_incoming_auto_association_task([10, 11]) == {"recorded": True, "count": 2}
    assert full_sync_auto_association_rule_task("vm_run_host") == {"recorded": True, "model_asst_id": "vm_run_host"}
    assert list(AutoRelationPending.objects.filter(instance_id__isnull=False).order_by("instance_id").values_list("instance_id", flat=True)) == [
        9,
        10,
        11,
    ]
    assert list(AutoRelationPending.objects.filter(model_asst_id__isnull=False).values_list("model_asst_id", flat=True)) == ["vm_run_host"]
