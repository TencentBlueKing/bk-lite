"""按 KB 串行的资料构建队列。"""

import io
import logging
import traceback
from contextlib import contextmanager

import pytest

from apps.core.logger import SafeLogException, opspilot_logger

pytestmark = pytest.mark.django_db(transaction=True)

_BROKER_FAILURE_SENTINEL = "redis://:hunter2-secret@broker:6379/0 connection refused"


@contextmanager
def _capture_opspilot_formatted_logs():
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    opspilot_logger.addHandler(handler)
    try:
        yield output
    finally:
        opspilot_logger.removeHandler(handler)


def test_enqueue_dedupes_and_kicks_single_runner(monkeypatch, wiki_factory):
    from apps.opspilot.models import BuildRecord, Material
    from apps.opspilot.services.wiki import material_build_queue_service as queue
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base

    kb = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(kb, operator="admin")
    m1 = Material.objects.create(knowledge_base=kb, name="a", material_type="text", status="pending")
    m2 = Material.objects.create(knowledge_base=kb, name="b", material_type="text", status="done")
    m3 = Material.objects.create(knowledge_base=kb, name="c", material_type="text", status="building")

    kicks = []
    monkeypatch.setattr(
        "apps.opspilot.tasks.wiki_process_kb_material_builds_task.delay",
        lambda kb_id, operator="": kicks.append(kb_id),
    )

    first = queue.enqueue_material_builds(
        knowledge_base_id=kb.pk,
        material_ids=[m1.pk, m2.pk, m3.pk, m1.pk],
        operator="u1",
    )
    second = queue.enqueue_material_builds(
        knowledge_base_id=kb.pk,
        material_ids=[m1.pk, m2.pk],
        operator="u1",
    )

    m1.refresh_from_db()
    m2.refresh_from_db()
    assert first["queued"] == [m1.pk, m2.pk]
    assert first["in_progress"] == [m3.pk]
    assert first["kicked"] is True
    assert second["already_queued"] == [m1.pk, m2.pk]
    assert second["kicked"] is False  # 已有 scheduled/running 租约,不再投递
    assert m1.status == "queued"
    assert m2.status == "queued"
    assert BuildRecord.objects.filter(trigger=queue.QUEUE_ITEM_TRIGGER, stage="queued").count() == 2
    assert kicks == [kb.pk]


def test_enqueue_rejects_when_rebuild_running(monkeypatch, wiki_factory):
    from apps.opspilot.models import BuildRecord, Material
    from apps.opspilot.services.wiki import material_build_queue_service as queue

    kb = wiki_factory.knowledge_base()
    material = Material.objects.create(knowledge_base=kb, name="a", material_type="text", status="pending")
    BuildRecord.objects.create(knowledge_base=kb, trigger="rebuild", status="running", stage="generating")
    monkeypatch.setattr("apps.opspilot.tasks.wiki_process_kb_material_builds_task.delay", lambda *args, **kwargs: None)

    with pytest.raises(queue.MaterialBuildQueueError) as exc:
        queue.enqueue_material_builds(knowledge_base_id=kb.pk, material_ids=[material.pk], operator="u1")

    assert exc.value.code == "knowledge_base_build_in_progress"
    assert exc.value.status_code == 409
    material.refresh_from_db()
    assert material.status == "pending"


def test_enqueue_rejects_when_material_update_running(monkeypatch, wiki_factory):
    from apps.opspilot.models import BuildRecord, Material
    from apps.opspilot.services.wiki import material_build_queue_service as queue

    kb = wiki_factory.knowledge_base()
    material = Material.objects.create(knowledge_base=kb, name="a", material_type="text", status="pending")
    BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="material_update",
        status="running",
        stage="generating",
        inputs={"material_id": material.pk},
    )
    monkeypatch.setattr("apps.opspilot.tasks.wiki_process_kb_material_builds_task.delay", lambda *args, **kwargs: None)

    with pytest.raises(queue.MaterialBuildQueueError) as exc:
        queue.enqueue_material_builds(knowledge_base_id=kb.pk, material_ids=[material.pk], operator="u1")

    assert exc.value.code == "knowledge_base_build_in_progress"
    material.refresh_from_db()
    assert material.status == "pending"


def test_enqueue_allows_sibling_material_running(monkeypatch, wiki_factory):
    from apps.opspilot.models import BuildRecord, Material
    from apps.opspilot.services.wiki import material_build_queue_service as queue

    kb = wiki_factory.knowledge_base()
    running = Material.objects.create(knowledge_base=kb, name="live", material_type="text", status="building")
    waiting = Material.objects.create(knowledge_base=kb, name="retry", material_type="text", status="parse_failed")
    BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="material",
        status="running",
        stage="generating",
        inputs={"material_id": running.pk},
    )
    kicks = []
    monkeypatch.setattr(
        "apps.opspilot.tasks.wiki_process_kb_material_builds_task.delay",
        lambda kb_id, operator="": kicks.append(kb_id),
    )

    result = queue.enqueue_material_builds(knowledge_base_id=kb.pk, material_ids=[waiting.pk], operator="u1")

    waiting.refresh_from_db()
    running.refresh_from_db()
    assert result["queued"] == [waiting.pk]
    assert waiting.status == "queued"
    assert running.status == "building"
    assert kicks == [kb.pk]


def test_runner_processes_same_kb_serially(monkeypatch, wiki_factory):
    from apps.opspilot.models import Material
    from apps.opspilot.services.wiki import material_build_queue_service as queue
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base

    kb = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(kb, operator="admin")
    m1 = Material.objects.create(knowledge_base=kb, name="a", material_type="text", status="pending")
    m2 = Material.objects.create(knowledge_base=kb, name="b", material_type="text", status="pending")

    monkeypatch.setattr(
        "apps.opspilot.tasks.wiki_process_kb_material_builds_task.delay",
        lambda *args, **kwargs: None,
    )
    queue.enqueue_material_builds(knowledge_base_id=kb.pk, material_ids=[m1.pk, m2.pk], operator="u1")

    order = []

    def fake_run(material_id, llm_model_id=None, operator="", **kwargs):
        order.append((material_id, kwargs.get("source_status")))
        Material.objects.filter(pk=material_id).update(status="built", error_message="")
        return 1

    monkeypatch.setattr("apps.opspilot.tasks.wiki_build_material_task.run", fake_run)

    result = queue.process_kb_material_builds(kb.pk, operator="u1")

    assert result["processed"] == 2
    assert result["failed"] == 0
    assert order == [(m1.pk, "pending"), (m2.pk, "pending")]
    assert Material.objects.get(pk=m1.pk).status == "built"
    assert Material.objects.get(pk=m2.pk).status == "built"
    assert queue.has_active_runner(kb.pk) is False


def test_second_runner_skips_when_lease_held(monkeypatch, wiki_factory):
    from apps.opspilot.models import Material
    from apps.opspilot.services.wiki import material_build_queue_service as queue
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base

    kb = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(kb, operator="admin")
    Material.objects.create(knowledge_base=kb, name="a", material_type="text", status="pending")
    monkeypatch.setattr(
        "apps.opspilot.tasks.wiki_process_kb_material_builds_task.delay",
        lambda *args, **kwargs: None,
    )
    queue.enqueue_material_builds(
        knowledge_base_id=kb.pk,
        material_ids=list(Material.objects.filter(knowledge_base=kb).values_list("id", flat=True)),
        operator="u1",
    )
    lease = queue.try_acquire_kb_build_runner(kb.pk, operator="u1")
    assert lease is not None
    assert lease.stage == "running"

    result = queue.process_kb_material_builds(kb.pk, operator="u2")
    assert result["skipped"] == "runner_active"

    queue.release_kb_build_runner(lease)


def test_release_runner_marks_partial_or_failed_when_items_fail(wiki_factory):
    from apps.opspilot.models import BuildRecord
    from apps.opspilot.services.wiki import material_build_queue_service as queue

    kb = wiki_factory.knowledge_base()
    lease = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger=queue.RUNNER_TRIGGER,
        stage="running",
        status="running",
        counts={"processed": 0, "failed": 0},
    )
    queue.release_kb_build_runner(lease, processed=2, failed=1)
    lease.refresh_from_db()
    assert lease.status == "partial"
    assert lease.counts["processed"] == 2
    assert lease.counts["failed"] == 1

    all_failed = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger=queue.RUNNER_TRIGGER,
        stage="running",
        status="running",
    )
    queue.release_kb_build_runner(all_failed, processed=0, failed=3)
    all_failed.refresh_from_db()
    assert all_failed.status == "failed"


def test_repair_queue_runner_status_from_counts(wiki_factory):
    from apps.opspilot.models import BuildRecord
    from apps.opspilot.services.wiki import material_build_queue_service as queue

    kb = wiki_factory.knowledge_base()
    dirty = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger=queue.RUNNER_TRIGGER,
        stage="done",
        status="success",
        counts={"processed": 1, "failed": 1},
    )
    clean = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger=queue.RUNNER_TRIGGER,
        stage="done",
        status="success",
        counts={"processed": 2, "failed": 0},
    )
    fixed = queue.repair_queue_runner_status_from_counts(kb.pk)
    dirty.refresh_from_db()
    clean.refresh_from_db()
    assert fixed == 1
    assert dirty.status == "partial"
    assert clean.status == "success"


def test_claim_sets_building_status(monkeypatch, wiki_factory):
    from apps.opspilot.models import BuildRecord, Material
    from apps.opspilot.serializers.wiki_serializers import MaterialSerializer
    from apps.opspilot.services.wiki import material_build_queue_service as queue
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base

    kb = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(kb, operator="admin")
    material = Material.objects.create(knowledge_base=kb, name="a", material_type="text", status="pending")
    monkeypatch.setattr(
        "apps.opspilot.tasks.wiki_process_kb_material_builds_task.delay",
        lambda *args, **kwargs: None,
    )
    queue.enqueue_material_builds(knowledge_base_id=kb.pk, material_ids=[material.pk], operator="u1")

    claimed = queue.claim_next_queued_material(kb.pk, operator="u1")
    material.refresh_from_db()
    assert claimed["material_id"] == material.pk
    assert material.status == "building"
    assert claimed.get("build_record_id")
    build = BuildRecord.objects.get(pk=claimed["build_record_id"])
    assert build.trigger == "material"
    assert build.status == "running"
    assert MaterialSerializer(material).data["build_started_at"]


def test_material_serializer_ignores_queue_build_records(wiki_factory):
    from apps.opspilot.models import BuildRecord, Material
    from apps.opspilot.serializers.wiki_serializers import MaterialSerializer
    from apps.opspilot.services.wiki.material_build_queue_service import QUEUE_ITEM_TRIGGER

    kb = wiki_factory.knowledge_base()
    material = Material.objects.create(knowledge_base=kb, name="a", material_type="text", status="queued")
    BuildRecord.objects.create(
        knowledge_base=kb,
        trigger=QUEUE_ITEM_TRIGGER,
        stage="queued",
        status="running",
        inputs={"material_id": material.pk, "source_status": "pending"},
    )

    data = MaterialSerializer(material).data
    assert data["build_started_at"] is None
    assert data["build_finished_at"] is None


def test_batch_build_api_enqueues(api_client, monkeypatch, wiki_factory):
    from apps.opspilot.models import Material
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base

    kb = wiki_factory.knowledge_base(team=[1])
    bootstrap_knowledge_base(kb, operator="admin")
    m1 = Material.objects.create(knowledge_base=kb, name="a", material_type="text", status="pending")
    m2 = Material.objects.create(knowledge_base=kb, name="b", material_type="text", status="updated")

    kicks = []
    monkeypatch.setattr(
        "apps.opspilot.tasks.wiki_process_kb_material_builds_task.delay",
        lambda kb_id, operator="": kicks.append(kb_id),
    )

    resp = api_client.post(
        "/api/v1/opspilot/wiki_mgmt/material/batch_build/",
        {"knowledge_base": kb.pk, "material_ids": [m1.pk, m2.pk]},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()["data"]
    assert set(body["queued"]) == {m1.pk, m2.pk}
    assert kicks == [kb.pk]
    assert Material.objects.get(pk=m1.pk).status == "queued"


def _broker_failure_raiser(bucket: list):
    def _raise(*args, **kwargs):
        error = RuntimeError(_BROKER_FAILURE_SENTINEL)
        bucket.append(error)
        raise error

    return _raise


def _assert_dispatch_failed_without_broker_detail(resp):
    assert resp.status_code == 503, resp.content
    body = resp.json()
    assert body["result"] is False
    assert body["code"] == "task_dispatch_failed"
    assert body["retryable"] is True
    assert "error" not in body
    assert "hunter2-secret" not in resp.content.decode("utf-8")
    assert "broker:6379" not in resp.content.decode("utf-8")


def _assert_owned_dispatch_traceback(*, caplog, rendered: str, kb_id: int, original: Exception):
    owned = [
        rec
        for rec in caplog.records
        if rec.name == "opspilot" and rec.levelno == logging.ERROR and rec.exc_info and "wiki material build runner 投递失败" in rec.getMessage()
    ]
    assert len(owned) == 1
    rec = owned[0]
    assert rec.exc_info[0] is SafeLogException
    assert rec.exc_info[1] is not original
    assert rec.exc_info[2] is not None
    frame_names = [frame.name for frame in traceback.extract_tb(rec.exc_info[2])]
    assert "kick_kb_material_build_runner" in frame_names
    assert "_raise" in frame_names
    assert str(rec.exc_info[1]) == "RuntimeError"
    assert str(original) == _BROKER_FAILURE_SENTINEL
    message = rec.getMessage()
    assert f"kb={kb_id}" in message
    assert "lease_id=" in message
    assert "failed_stage=task_dispatch" in message
    assert "error_type=RuntimeError" in message
    assert "call_chain=" in message
    assert "hunter2-secret" not in message
    assert "Traceback" in rendered
    assert "kick_kb_material_build_runner" in rendered
    assert "hunter2-secret" not in rendered
    assert "broker:6379" not in rendered
    traceback_errors = [r for r in caplog.records if r.name == "opspilot" and r.levelno >= logging.ERROR and r.exc_info]
    assert traceback_errors == owned
    assert "wiki 批量构建入队失败" not in caplog.text
    assert "wiki 构建入队失败" not in caplog.text
    assert "wiki 构建记录重试入队失败" not in caplog.text


def test_batch_build_api_hides_broker_error_on_dispatch_failure(api_client, monkeypatch, wiki_factory, caplog):
    from apps.opspilot.models import Material
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base

    kb = wiki_factory.knowledge_base(team=[1])
    bootstrap_knowledge_base(kb, operator="admin")
    material = Material.objects.create(knowledge_base=kb, name="a", material_type="text", status="pending")
    raised = []
    monkeypatch.setattr(
        "apps.opspilot.tasks.wiki_process_kb_material_builds_task.delay",
        _broker_failure_raiser(raised),
    )
    caplog.set_level(logging.ERROR, logger="opspilot")

    with _capture_opspilot_formatted_logs() as output:
        resp = api_client.post(
            "/api/v1/opspilot/wiki_mgmt/material/batch_build/",
            {"knowledge_base": kb.pk, "material_ids": [material.pk]},
            format="json",
        )

    _assert_dispatch_failed_without_broker_detail(resp)
    _assert_owned_dispatch_traceback(caplog=caplog, rendered=output.getvalue(), kb_id=kb.pk, original=raised[0])


def test_build_api_hides_broker_error_on_dispatch_failure(api_client, monkeypatch, wiki_factory, caplog):
    from apps.opspilot.models import Material
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base

    kb = wiki_factory.knowledge_base(team=[1])
    bootstrap_knowledge_base(kb, operator="admin")
    material = Material.objects.create(knowledge_base=kb, name="a", material_type="text", status="pending")
    raised = []
    monkeypatch.setattr(
        "apps.opspilot.tasks.wiki_process_kb_material_builds_task.delay",
        _broker_failure_raiser(raised),
    )
    caplog.set_level(logging.ERROR, logger="opspilot")

    with _capture_opspilot_formatted_logs() as output:
        resp = api_client.post(
            f"/api/v1/opspilot/wiki_mgmt/material/{material.pk}/build/",
            {"async": True},
            format="json",
        )

    _assert_dispatch_failed_without_broker_detail(resp)
    _assert_owned_dispatch_traceback(caplog=caplog, rendered=output.getvalue(), kb_id=kb.pk, original=raised[0])


def test_enqueue_rejects_empty_and_oversized_batches(wiki_factory):
    from apps.opspilot.services.wiki import material_build_queue_service as queue

    kb = wiki_factory.knowledge_base()
    with pytest.raises(queue.MaterialBuildQueueError) as empty:
        queue.enqueue_material_builds(knowledge_base_id=kb.pk, material_ids=[])
    assert empty.value.code == "material_ids_required"

    with pytest.raises(queue.MaterialBuildQueueError) as missing_kb:
        queue.enqueue_material_builds(knowledge_base_id=999999, material_ids=[1])
    assert missing_kb.value.code == "knowledge_base_not_found"

    too_many = list(range(1, queue._MAX_BATCH_SIZE + 2))
    with pytest.raises(queue.MaterialBuildQueueError) as oversized:
        queue.enqueue_material_builds(knowledge_base_id=kb.pk, material_ids=too_many)
    assert oversized.value.code == "material_ids_too_many"


def test_enqueue_skips_invalid_and_foreign_materials(monkeypatch, wiki_factory):
    from apps.opspilot.models import Material
    from apps.opspilot.services.wiki import material_build_queue_service as queue
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base

    kb = wiki_factory.knowledge_base()
    other = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(kb, operator="admin")
    valid = Material.objects.create(knowledge_base=kb, name="ok", material_type="text", status="pending")
    invalid = Material.objects.create(knowledge_base=kb, name="bad", material_type="text", status="invalid")
    foreign = Material.objects.create(knowledge_base=other, name="x", material_type="text", status="pending")
    monkeypatch.setattr(
        "apps.opspilot.tasks.wiki_process_kb_material_builds_task.delay",
        lambda *args, **kwargs: None,
    )

    result = queue.enqueue_material_builds(
        knowledge_base_id=kb.pk,
        material_ids=[valid.pk, invalid.pk, foreign.pk, "x", 0, -1],
        operator="u1",
    )

    assert result["queued"] == [valid.pk]
    assert {"id": invalid.pk, "reason": "invalid"} in result["skipped"]
    assert {"id": foreign.pk, "reason": "not_found_in_kb"} in result["skipped"]


def test_batch_build_api_rejects_when_rebuild_running(api_client, monkeypatch, wiki_factory):
    from apps.opspilot.models import BuildRecord, Material
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base

    kb = wiki_factory.knowledge_base(team=[1])
    bootstrap_knowledge_base(kb, operator="admin")
    material = Material.objects.create(knowledge_base=kb, name="a", material_type="text", status="pending")
    BuildRecord.objects.create(knowledge_base=kb, trigger="rebuild", status="running", stage="generating")
    kicks = []
    monkeypatch.setattr(
        "apps.opspilot.tasks.wiki_process_kb_material_builds_task.delay",
        lambda kb_id, operator="": kicks.append(kb_id),
    )

    resp = api_client.post(
        "/api/v1/opspilot/wiki_mgmt/material/batch_build/",
        {"knowledge_base": kb.pk, "material_ids": [material.pk]},
        format="json",
    )

    assert resp.status_code == 409, resp.content
    assert resp.json()["code"] == "knowledge_base_build_in_progress"
    assert Material.objects.get(pk=material.pk).status == "pending"
    assert kicks == []


def test_stale_runner_lease_is_reclaimed(monkeypatch, wiki_factory):
    from datetime import timedelta

    from django.utils import timezone

    from apps.opspilot.models import BuildRecord, Material
    from apps.opspilot.services.wiki import material_build_queue_service as queue
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base

    kb = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(kb, operator="admin")
    material = Material.objects.create(knowledge_base=kb, name="a", material_type="text", status="pending")
    monkeypatch.setattr(
        "apps.opspilot.tasks.wiki_process_kb_material_builds_task.delay",
        lambda *args, **kwargs: None,
    )
    queue.enqueue_material_builds(knowledge_base_id=kb.pk, material_ids=[material.pk], operator="u1")
    lease = queue.try_acquire_kb_build_runner(kb.pk, operator="u1")
    assert lease is not None
    BuildRecord.objects.filter(pk=lease.pk).update(updated_at=timezone.now() - timedelta(hours=3))

    reclaimed = queue.try_acquire_kb_build_runner(kb.pk, operator="u2")
    assert reclaimed is not None
    assert reclaimed.pk == lease.pk
    assert reclaimed.operator == "u2"


def test_fresh_running_lease_is_not_reclaimed_even_with_reclaim_flag(wiki_factory):
    from apps.opspilot.models import BuildRecord
    from apps.opspilot.services.wiki import material_build_queue_service as queue

    kb = wiki_factory.knowledge_base()
    lease = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger=queue.RUNNER_TRIGGER,
        status="running",
        stage="running",
        operator="u1",
        inputs={"kind": "material_build_queue"},
    )

    stolen = queue.try_acquire_kb_build_runner(kb.pk, operator="u2", reclaim_running=True)
    lease.refresh_from_db()
    assert stolen is None
    assert lease.operator == "u1"
    assert lease.status == "running"


def test_claim_falls_back_to_queued_material_without_queue_item(wiki_factory):
    from apps.opspilot.models import Material
    from apps.opspilot.services.wiki import material_build_queue_service as queue

    kb = wiki_factory.knowledge_base()
    material = Material.objects.create(knowledge_base=kb, name="orphan-queue", material_type="text", status="queued")

    claimed = queue.claim_next_queued_material(kb.pk, operator="u1")
    material.refresh_from_db()
    assert claimed["material_id"] == material.pk
    assert material.status == "building"
    assert claimed["build_record_id"]


def test_process_counts_missing_material_and_build_failure(monkeypatch, wiki_factory, caplog):
    from apps.opspilot.models import BuildRecord, Material
    from apps.opspilot.services.wiki import material_build_queue_service as queue
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base

    kb = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(kb, operator="admin")
    material = Material.objects.create(knowledge_base=kb, name="a", material_type="text", status="pending")
    monkeypatch.setattr(
        "apps.opspilot.tasks.wiki_process_kb_material_builds_task.delay",
        lambda *args, **kwargs: None,
    )
    queue.enqueue_material_builds(knowledge_base_id=kb.pk, material_ids=[material.pk], operator="u1")
    BuildRecord.objects.create(
        knowledge_base=kb,
        trigger=queue.QUEUE_ITEM_TRIGGER,
        stage="queued",
        status="running",
        inputs={"material_id": 999999, "source_status": "pending"},
    )

    crashed = []

    def boom(*args, **kwargs):
        error = RuntimeError("build crashed")
        crashed.append(error)
        raise error

    monkeypatch.setattr("apps.opspilot.tasks.wiki_build_material_task.run", boom)
    caplog.set_level(logging.ERROR, logger="opspilot")
    with _capture_opspilot_formatted_logs() as output:
        result = queue.process_kb_material_builds(kb.pk, operator="u1")
    material.refresh_from_db()
    assert result["processed"] == 0
    assert result["failed"] == 2
    assert material.status == "build_failed"
    stuck = BuildRecord.objects.filter(
        knowledge_base=kb,
        trigger="material",
        status="running",
        inputs__material_id=material.pk,
    )
    assert stuck.count() == 0
    failed_build = BuildRecord.objects.filter(
        knowledge_base=kb,
        trigger="material",
        status="failed",
        inputs__material_id=material.pk,
    ).latest("id")
    assert failed_build.stage == "failed"

    owned = [rec for rec in caplog.records if rec.name == "opspilot" and rec.exc_info and "wiki KB 串行构建单条失败" in rec.getMessage()]
    assert len(owned) == 1
    rec = owned[0]
    assert rec.exc_info[0] is SafeLogException
    assert rec.exc_info[1] is not crashed[0]
    assert rec.exc_info[2] is crashed[0].__traceback__
    assert str(rec.exc_info[1]) == "RuntimeError"
    assert str(crashed[0]) == "build crashed"
    message = rec.getMessage()
    assert f"kb={kb.pk}" in message
    assert f"material={material.pk}" in message
    assert "failed_stage=material_build" in message
    assert "error_type=RuntimeError" in message
    assert "call_chain=" in message
    rendered = output.getvalue()
    assert "Traceback" in rendered
    assert "process_kb_material_builds" in rendered
    traceback_errors = [r for r in caplog.records if r.name == "opspilot" and r.levelno >= logging.ERROR and r.exc_info]
    assert traceback_errors == owned


def test_reconcile_closes_orphaned_preparing_builds(wiki_factory):
    from apps.opspilot.models import BuildRecord, Material
    from apps.opspilot.services.wiki import material_build_queue_service as queue

    kb = wiki_factory.knowledge_base()
    material = Material.objects.create(knowledge_base=kb, name="done", material_type="text", status="built")
    orphan = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="material",
        stage="preparing",
        status="running",
        inputs={"material_id": material.pk},
        counts={},
    )
    active = Material.objects.create(knowledge_base=kb, name="busy", material_type="text", status="building")
    keep = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="material",
        stage="preparing",
        status="running",
        inputs={"material_id": active.pk},
    )

    closed = queue.reconcile_orphaned_material_builds(kb.pk)
    orphan.refresh_from_db()
    keep.refresh_from_db()
    assert closed == 1
    assert orphan.status == "failed"
    assert orphan.stage == "failed"
    assert keep.status == "running"


def test_cancel_stale_queue_items_for_missing_materials(wiki_factory):
    from apps.opspilot.models import BuildRecord, Material
    from apps.opspilot.services.wiki import material_build_queue_service as queue

    kb = wiki_factory.knowledge_base()
    material = Material.objects.create(knowledge_base=kb, name="keep", material_type="text", status="queued")
    keep = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger=queue.QUEUE_ITEM_TRIGGER,
        stage="queued",
        status="running",
        inputs={"material_id": material.pk},
    )
    stale = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger=queue.QUEUE_ITEM_TRIGGER,
        stage="queued",
        status="running",
        inputs={"material_id": 888888},
    )

    closed = queue.cancel_stale_queue_items_for_missing_materials(kb.pk)
    keep.refresh_from_db()
    stale.refresh_from_db()
    assert closed == 1
    assert keep.stage == "queued"
    assert stale.stage == "cancelled"
    assert stale.status == "failed"


def test_unstick_cancelled_build_unlocks_material_and_queue_item(wiki_factory):
    from apps.opspilot.models import BuildRecord, Material
    from apps.opspilot.services.wiki import material_build_queue_service as queue

    kb = wiki_factory.knowledge_base()
    material = Material.objects.create(knowledge_base=kb, name="stuck", material_type="text", status="building")
    record = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="material",
        status="cancelled",
        stage="cancelled",
        inputs={"material_id": material.pk},
    )
    item = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger=queue.QUEUE_ITEM_TRIGGER,
        stage="queued",
        status="running",
        inputs={"material_id": material.pk},
    )

    assert queue.unstick_material_for_cancelled_build(record) is True
    material.refresh_from_db()
    item.refresh_from_db()
    assert material.status == "parse_failed"
    assert material.error_message == "构建已取消"
    assert item.stage == "cancelled"
    assert item.status == "failed"


def test_release_idle_runner_lease_skips_when_user_build_running(wiki_factory):
    from apps.opspilot.models import BuildRecord
    from apps.opspilot.services.wiki import material_build_queue_service as queue

    kb = wiki_factory.knowledge_base()
    BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="material",
        status="running",
        stage="generating",
        inputs={"material_id": 1},
    )
    lease = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger=queue.RUNNER_TRIGGER,
        status="running",
        stage="running",
        inputs={"kind": "material_build_queue"},
    )

    assert queue.release_idle_runner_lease(kb.pk) is False
    lease.refresh_from_db()
    assert lease.status == "running"


def test_release_idle_runner_lease_fails_ghost_and_kicks_if_queued(monkeypatch, wiki_factory):
    from apps.opspilot.models import BuildRecord, Material
    from apps.opspilot.services.wiki import material_build_queue_service as queue

    kb = wiki_factory.knowledge_base()
    Material.objects.create(knowledge_base=kb, name="queued", material_type="text", status="queued")
    lease = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger=queue.RUNNER_TRIGGER,
        status="running",
        stage="running",
        inputs={"kind": "material_build_queue"},
    )
    kicks = []
    monkeypatch.setattr(
        "apps.opspilot.tasks.wiki_process_kb_material_builds_task.delay",
        lambda kb_id, operator="": kicks.append((kb_id, operator)),
    )

    assert queue.release_idle_runner_lease(kb.pk, operator="u1") is True
    lease.refresh_from_db()
    assert lease.status == "failed"
    assert lease.stage == "cancelled"
    assert kicks == [(kb.pk, "u1")]
    assert BuildRecord.objects.filter(knowledge_base=kb, trigger=queue.RUNNER_TRIGGER, status="running").exists()


def test_release_idle_runner_lease_can_skip_kick(monkeypatch, wiki_factory):
    from apps.opspilot.models import BuildRecord, Material
    from apps.opspilot.services.wiki import material_build_queue_service as queue

    kb = wiki_factory.knowledge_base()
    Material.objects.create(knowledge_base=kb, name="queued", material_type="text", status="queued")
    lease = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger=queue.RUNNER_TRIGGER,
        status="running",
        stage="running",
        inputs={"kind": "material_build_queue"},
    )
    kicks = []
    monkeypatch.setattr(
        "apps.opspilot.tasks.wiki_process_kb_material_builds_task.delay",
        lambda kb_id, operator="": kicks.append(kb_id),
    )

    assert queue.release_idle_runner_lease(kb.pk, operator="u1", kick_if_queued=False) is True
    lease.refresh_from_db()
    assert lease.status == "failed"
    assert kicks == []
    assert not BuildRecord.objects.filter(knowledge_base=kb, trigger=queue.RUNNER_TRIGGER, status="running").exists()


def test_resume_requeues_building_ahead_of_existing_queue(monkeypatch, wiki_factory, caplog):
    import logging

    from apps.opspilot.models import BuildRecord, Material
    from apps.opspilot.services.wiki import material_build_queue_service as queue

    kb = wiki_factory.knowledge_base()
    interrupted = Material.objects.create(knowledge_base=kb, name="building.pptx", material_type="text", status="building")
    waiting = Material.objects.create(knowledge_base=kb, name="queued.docx", material_type="text", status="queued")
    running = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="material",
        status="running",
        stage="generating",
        inputs={"material_id": interrupted.pk},
    )
    waiting_item = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger=queue.QUEUE_ITEM_TRIGGER,
        stage="queued",
        status="running",
        inputs={"material_id": waiting.pk},
    )
    lease = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger=queue.RUNNER_TRIGGER,
        status="running",
        stage="running",
        inputs={"kind": "material_build_queue"},
    )
    kicks = []
    monkeypatch.setattr(
        "apps.opspilot.tasks.wiki_process_kb_material_builds_task.delay",
        lambda kb_id, operator="": kicks.append((kb_id, operator)),
    )
    caplog.set_level(logging.INFO, logger="opspilot")

    result = queue.resume_kb_material_builds(kb.pk, operator="u1")

    interrupted.refresh_from_db()
    waiting.refresh_from_db()
    running.refresh_from_db()
    lease.refresh_from_db()
    assert result["requeued"] == [interrupted.pk]
    assert result["released"] is True
    assert result["kicked"] is True
    assert interrupted.status == "queued"
    assert waiting.status == "queued"
    assert running.status == "failed"
    assert lease.status == "failed"
    assert kicks == [(kb.pk, "u1")]
    claimed = queue.claim_next_queued_material(kb.pk, operator="u1")
    assert claimed["material_id"] == interrupted.pk
    waiting_item.refresh_from_db()
    assert waiting_item.stage == "queued"
    assert any(
        rec.msg == "wiki material builds resumed kb=%s requeued=%s released=%s kicked=%s" and rec.args == (kb.pk, 1, True, True)
        for rec in caplog.records
    )


def test_requeue_marks_existing_queue_item_resume_interrupted(monkeypatch, wiki_factory):
    from apps.opspilot.models import BuildRecord, Material
    from apps.opspilot.services.wiki import material_build_queue_service as queue

    kb = wiki_factory.knowledge_base()
    waiting = Material.objects.create(knowledge_base=kb, name="queued.docx", material_type="text", status="queued")
    interrupted = Material.objects.create(knowledge_base=kb, name="building.pptx", material_type="text", status="building")
    waiting_item = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger=queue.QUEUE_ITEM_TRIGGER,
        stage="queued",
        status="running",
        inputs={"material_id": waiting.pk},
    )
    interrupted_item = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger=queue.QUEUE_ITEM_TRIGGER,
        stage="queued",
        status="running",
        inputs={"material_id": interrupted.pk, "source_status": "pending"},
    )
    BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="material",
        status="running",
        stage="generating",
        inputs={"material_id": interrupted.pk},
    )
    monkeypatch.setattr("apps.opspilot.tasks.wiki_process_kb_material_builds_task.delay", lambda *args, **kwargs: None)

    queue.requeue_interrupted_materials(kb.pk, operator="u1")

    interrupted_item.refresh_from_db()
    waiting_item.refresh_from_db()
    interrupted.refresh_from_db()
    assert interrupted.status == "queued"
    assert interrupted_item.inputs[queue.QUEUE_RESUME_INPUT_KEY] is True
    assert interrupted_item.inputs["source_status"] == "building"
    assert queue.QUEUE_RESUME_INPUT_KEY not in (waiting_item.inputs or {})
    assert (
        BuildRecord.objects.filter(
            knowledge_base=kb,
            trigger=queue.QUEUE_ITEM_TRIGGER,
            stage="queued",
            status="running",
            inputs__material_id=interrupted.pk,
        ).count()
        == 1
    )
    claimed = queue.claim_next_queued_material(kb.pk, operator="u1")
    assert claimed["material_id"] == interrupted.pk
    waiting_item.refresh_from_db()
    assert waiting_item.stage == "queued"


def test_resume_rejects_when_rebuild_running(monkeypatch, wiki_factory):
    from apps.opspilot.models import BuildRecord, Material
    from apps.opspilot.services.wiki import material_build_queue_service as queue

    kb = wiki_factory.knowledge_base()
    material = Material.objects.create(knowledge_base=kb, name="building.pptx", material_type="text", status="building")
    running = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="material",
        status="running",
        stage="generating",
        inputs={"material_id": material.pk},
    )
    lease = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger=queue.RUNNER_TRIGGER,
        status="running",
        stage="running",
        inputs={"kind": "material_build_queue"},
    )
    BuildRecord.objects.create(knowledge_base=kb, trigger="rebuild", status="running", stage="generating")
    kicks = []
    monkeypatch.setattr(
        "apps.opspilot.tasks.wiki_process_kb_material_builds_task.delay",
        lambda kb_id, operator="": kicks.append(kb_id),
    )

    with pytest.raises(queue.MaterialBuildQueueError) as exc:
        queue.resume_kb_material_builds(kb.pk, operator="u1")

    assert exc.value.code == "knowledge_base_build_in_progress"
    assert exc.value.status_code == 409
    material.refresh_from_db()
    running.refresh_from_db()
    lease.refresh_from_db()
    assert material.status == "building"
    assert running.status == "running"
    assert lease.status == "running"
    assert kicks == []


def test_resume_rejects_when_material_update_running(monkeypatch, wiki_factory):
    from apps.opspilot.models import BuildRecord, Material
    from apps.opspilot.services.wiki import material_build_queue_service as queue

    kb = wiki_factory.knowledge_base()
    material = Material.objects.create(knowledge_base=kb, name="live.md", material_type="text", status="building")
    lease = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger=queue.RUNNER_TRIGGER,
        status="running",
        stage="running",
        inputs={"kind": "material_build_queue"},
    )
    BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="material_update",
        status="running",
        stage="generating",
        inputs={"material_id": material.pk},
    )
    kicks = []
    monkeypatch.setattr(
        "apps.opspilot.tasks.wiki_process_kb_material_builds_task.delay",
        lambda kb_id, operator="": kicks.append(kb_id),
    )

    with pytest.raises(queue.MaterialBuildQueueError) as exc:
        queue.resume_kb_material_builds(kb.pk, operator="u1")

    assert exc.value.code == "knowledge_base_build_in_progress"
    material.refresh_from_db()
    lease.refresh_from_db()
    assert material.status == "building"
    assert lease.status == "running"
    assert kicks == []


def test_process_kb_reclaim_requeues_interrupted_then_continues(monkeypatch, wiki_factory):
    from datetime import timedelta

    from django.utils import timezone

    from apps.opspilot.models import BuildRecord, Material
    from apps.opspilot.services.wiki import material_build_queue_service as queue
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base

    kb = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(kb, operator="admin")
    interrupted = Material.objects.create(knowledge_base=kb, name="building.pptx", material_type="text", status="building")
    waiting = Material.objects.create(knowledge_base=kb, name="queued.docx", material_type="text", status="queued")
    BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="material",
        status="running",
        stage="generating",
        inputs={"material_id": interrupted.pk},
    )
    BuildRecord.objects.create(
        knowledge_base=kb,
        trigger=queue.QUEUE_ITEM_TRIGGER,
        stage="queued",
        status="running",
        inputs={"material_id": waiting.pk},
    )
    lease = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger=queue.RUNNER_TRIGGER,
        status="running",
        stage="running",
        inputs={"kind": "material_build_queue"},
    )
    BuildRecord.objects.filter(pk=lease.pk).update(updated_at=timezone.now() - timedelta(hours=3))
    order = []

    def fake_run(material_id, *args, **kwargs):
        order.append(material_id)
        Material.objects.filter(pk=material_id).update(status="built", error_message="")
        return 1

    monkeypatch.setattr("apps.opspilot.tasks.wiki_build_material_task.run", fake_run)
    monkeypatch.setattr("apps.opspilot.tasks.wiki_process_kb_material_builds_task.delay", lambda *args, **kwargs: None)

    result = queue.process_kb_material_builds(kb.pk, operator="u1")

    assert result["skipped"] is None
    assert order == [interrupted.pk, waiting.pk]
    assert Material.objects.get(pk=interrupted.pk).status == "built"
    assert Material.objects.get(pk=waiting.pk).status == "built"


def test_process_kb_skips_fresh_running_lease_even_when_reclaim_requested(monkeypatch, wiki_factory, caplog):
    import logging

    from apps.opspilot.models import BuildRecord, Material
    from apps.opspilot.services.wiki import material_build_queue_service as queue

    kb = wiki_factory.knowledge_base()
    Material.objects.create(knowledge_base=kb, name="queued.docx", material_type="text", status="queued")
    BuildRecord.objects.create(
        knowledge_base=kb,
        trigger=queue.RUNNER_TRIGGER,
        status="running",
        stage="running",
        inputs={"kind": "material_build_queue"},
    )
    caplog.set_level(logging.INFO, logger="opspilot")
    monkeypatch.setattr("apps.opspilot.tasks.wiki_build_material_task.run", lambda *args, **kwargs: 1)
    monkeypatch.setattr("apps.opspilot.tasks.wiki_process_kb_material_builds_task.delay", lambda *args, **kwargs: None)

    result = queue.process_kb_material_builds(kb.pk, operator="u2", reclaim_running=True)

    assert result == {"skipped": "runner_active", "processed": 0, "failed": 0}
    assert any(rec.msg == "wiki material build runner skipped kb=%s reason=%s" and rec.args == (kb.pk, "runner_active") for rec in caplog.records)


def test_process_kb_skips_when_rebuild_running(monkeypatch, wiki_factory, caplog):
    import logging

    from apps.opspilot.models import BuildRecord, Material
    from apps.opspilot.services.wiki import material_build_queue_service as queue

    kb = wiki_factory.knowledge_base()
    material = Material.objects.create(knowledge_base=kb, name="queued.docx", material_type="text", status="queued")
    BuildRecord.objects.create(
        knowledge_base=kb,
        trigger=queue.RUNNER_TRIGGER,
        status="running",
        stage="scheduled",
        inputs={"kind": "material_build_queue"},
    )
    BuildRecord.objects.create(knowledge_base=kb, trigger="rebuild", status="running", stage="generating")
    kicks = []
    caplog.set_level(logging.INFO, logger="opspilot")
    monkeypatch.setattr(
        "apps.opspilot.tasks.wiki_build_material_task.run", lambda *args, **kwargs: pytest.fail("rebuild must not run material builds")
    )
    monkeypatch.setattr(
        "apps.opspilot.tasks.wiki_process_kb_material_builds_task.delay",
        lambda kb_id, operator="": kicks.append(kb_id),
    )

    result = queue.process_kb_material_builds(kb.pk, operator="u1")

    material.refresh_from_db()
    assert result == {"skipped": "cross_pipeline", "processed": 0, "failed": 0}
    assert material.status == "queued"
    assert kicks == []
    assert any(rec.msg == "wiki material build runner skipped kb=%s reason=%s" and rec.args == (kb.pk, "cross_pipeline") for rec in caplog.records)


def test_try_acquire_does_not_reclaim_stale_lease_while_rebuild_running(wiki_factory):
    from datetime import timedelta

    from django.utils import timezone

    from apps.opspilot.models import BuildRecord
    from apps.opspilot.services.wiki import material_build_queue_service as queue

    kb = wiki_factory.knowledge_base()
    lease = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger=queue.RUNNER_TRIGGER,
        status="running",
        stage="running",
        operator="u1",
        inputs={"kind": "material_build_queue"},
    )
    BuildRecord.objects.filter(pk=lease.pk).update(updated_at=timezone.now() - timedelta(hours=3))
    BuildRecord.objects.create(knowledge_base=kb, trigger="rebuild", status="running", stage="generating")

    stolen = queue.try_acquire_kb_build_runner(kb.pk, operator="u2")
    lease.refresh_from_db()
    assert stolen is None
    assert lease.operator == "u1"
    assert lease.status == "running"


def test_kick_does_not_schedule_while_rebuild_running(monkeypatch, wiki_factory):
    from apps.opspilot.models import BuildRecord, Material
    from apps.opspilot.services.wiki import material_build_queue_service as queue

    kb = wiki_factory.knowledge_base()
    Material.objects.create(knowledge_base=kb, name="queued.docx", material_type="text", status="queued")
    BuildRecord.objects.create(knowledge_base=kb, trigger="rebuild", status="running", stage="generating")
    kicks = []
    monkeypatch.setattr(
        "apps.opspilot.tasks.wiki_process_kb_material_builds_task.delay",
        lambda kb_id, operator="": kicks.append(kb_id),
    )

    assert queue.kick_kb_material_build_runner(kb.pk, operator="u1") is False
    assert kicks == []
    assert not BuildRecord.objects.filter(knowledge_base=kb, trigger=queue.RUNNER_TRIGGER, status="running").exists()


def test_process_kb_stops_claiming_when_rebuild_starts(monkeypatch, wiki_factory, caplog):
    import logging

    from apps.opspilot.models import BuildRecord, Material
    from apps.opspilot.services.wiki import material_build_queue_service as queue
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base

    kb = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(kb, operator="admin")
    first = Material.objects.create(knowledge_base=kb, name="first.md", material_type="text", status="pending")
    second = Material.objects.create(knowledge_base=kb, name="second.md", material_type="text", status="pending")
    kicks = []
    monkeypatch.setattr(
        "apps.opspilot.tasks.wiki_process_kb_material_builds_task.delay",
        lambda kb_id, operator="": kicks.append(kb_id),
    )
    queue.enqueue_material_builds(knowledge_base_id=kb.pk, material_ids=[first.pk, second.pk], operator="u1")
    kicks.clear()
    order = []

    def fake_run(material_id, *args, **kwargs):
        order.append(material_id)
        Material.objects.filter(pk=material_id).update(status="built", error_message="")
        if material_id == first.pk:
            BuildRecord.objects.create(knowledge_base=kb, trigger="rebuild", status="running", stage="generating")
        return 1

    monkeypatch.setattr("apps.opspilot.tasks.wiki_build_material_task.run", fake_run)
    caplog.set_level(logging.INFO, logger="opspilot")

    result = queue.process_kb_material_builds(kb.pk, operator="u1")

    second.refresh_from_db()
    assert order == [first.pk]
    assert second.status == "queued"
    assert result["skipped"] == "cross_pipeline"
    assert result["processed"] == 1
    assert kicks == []
    assert any(
        rec.msg == "wiki material build runner stopped kb=%s reason=%s lease_id=%s" and rec.args[0] == kb.pk and rec.args[1] == "cross_pipeline"
        for rec in caplog.records
    )


def test_process_kb_stops_claiming_after_lease_is_force_released(monkeypatch, wiki_factory, caplog):
    import logging

    from apps.opspilot.models import Material
    from apps.opspilot.services.wiki import material_build_queue_service as queue
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base

    kb = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(kb, operator="admin")
    first = Material.objects.create(knowledge_base=kb, name="first.md", material_type="text", status="pending")
    second = Material.objects.create(knowledge_base=kb, name="second.md", material_type="text", status="pending")
    monkeypatch.setattr(
        "apps.opspilot.tasks.wiki_process_kb_material_builds_task.delay",
        lambda *args, **kwargs: None,
    )
    queue.enqueue_material_builds(knowledge_base_id=kb.pk, material_ids=[first.pk, second.pk], operator="u1")
    order = []

    def fake_run(material_id, *args, **kwargs):
        order.append(material_id)
        Material.objects.filter(pk=material_id).update(status="built", error_message="")
        queue._force_release_runner_lease(kb.pk)
        return 1

    monkeypatch.setattr("apps.opspilot.tasks.wiki_build_material_task.run", fake_run)
    caplog.set_level(logging.INFO, logger="opspilot")

    result = queue.process_kb_material_builds(kb.pk, operator="u1")

    second.refresh_from_db()
    assert order == [first.pk]
    assert second.status == "queued"
    assert result["skipped"] == "lease_lost"
    assert result["processed"] == 1
    assert any(
        rec.msg == "wiki material build runner lost lease kb=%s lease_id=%s" and rec.args[0] == kb.pk and isinstance(rec.args[1], int)
        for rec in caplog.records
    )


def test_kick_returns_false_when_queue_empty(wiki_factory):
    from apps.opspilot.services.wiki import material_build_queue_service as queue

    kb = wiki_factory.knowledge_base()
    assert queue.kick_kb_material_build_runner(kb.pk) is False
    assert queue.kb_has_queued_materials(kb.pk) is False


def test_ensure_running_material_build_record_reuses_existing(wiki_factory):
    from apps.opspilot.models import BuildRecord
    from apps.opspilot.services.wiki import material_build_queue_service as queue

    kb = wiki_factory.knowledge_base()
    first = queue.ensure_running_material_build_record(
        knowledge_base_id=kb.pk,
        material_id=42,
        operator="u1",
        source_status="pending",
        stage="preparing",
    )
    second = queue.ensure_running_material_build_record(
        knowledge_base_id=kb.pk,
        material_id=42,
        operator="u2",
        source_status="done",
        stage="parsing",
    )
    assert first.pk == second.pk
    assert BuildRecord.objects.filter(pk=first.pk).count() == 1
    second.refresh_from_db()
    assert second.stage == "parsing"
    assert second.operator == "u1"
    assert second.inputs["source_status"] == "pending"


def test_resume_wiki_material_builds_command_resumes_specified_kb(monkeypatch, wiki_factory, caplog):
    import logging
    from io import StringIO

    from django.core.management import call_command

    from apps.opspilot.models import BuildRecord, Material

    kb = wiki_factory.knowledge_base()
    material = Material.objects.create(knowledge_base=kb, name="stuck.pptx", material_type="text", status="building")
    BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="material",
        status="running",
        stage="generating",
        inputs={"material_id": material.pk},
    )
    kicks = []
    monkeypatch.setattr(
        "apps.opspilot.tasks.wiki_process_kb_material_builds_task.delay",
        lambda kb_id, operator="": kicks.append((kb_id, operator)),
    )
    caplog.set_level(logging.INFO, logger="opspilot")
    stdout = StringIO()

    call_command("resume_wiki_material_builds", f"--knowledge-base={kb.pk}", stdout=stdout)

    material.refresh_from_db()
    assert material.status == "queued"
    assert kicks == [(kb.pk, "ops-cli")]
    assert f"kb={kb.pk} requeued=1 released=0 kicked=1" in stdout.getvalue()
    assert any(
        rec.msg == "wiki material builds resume command kb=%s requeued=%s released=%s kicked=%s" and rec.args == (kb.pk, 1, False, True)
        for rec in caplog.records
    )


def test_resume_wiki_material_builds_command_dry_run_does_not_mutate(monkeypatch, wiki_factory):
    from io import StringIO

    from django.core.management import call_command

    from apps.opspilot.models import Material

    kb = wiki_factory.knowledge_base()
    material = Material.objects.create(knowledge_base=kb, name="stuck.pptx", material_type="text", status="building")
    kicks = []
    monkeypatch.setattr(
        "apps.opspilot.tasks.wiki_process_kb_material_builds_task.delay",
        lambda *args, **kwargs: kicks.append(args),
    )
    stdout = StringIO()

    call_command("resume_wiki_material_builds", f"--knowledge-base={kb.pk}", "--dry-run", stdout=stdout)

    material.refresh_from_db()
    assert material.status == "building"
    assert kicks == []
    assert f"dry-run kb={kb.pk} stuck=1" in stdout.getvalue()


def test_resume_wiki_material_builds_command_all_skips_idle_kb(monkeypatch, wiki_factory):
    from io import StringIO

    from django.core.management import call_command

    from apps.opspilot.models import Material

    idle = wiki_factory.knowledge_base()
    Material.objects.create(knowledge_base=idle, name="done.md", material_type="text", status="built")
    stuck_kb = wiki_factory.knowledge_base()
    Material.objects.create(knowledge_base=stuck_kb, name="stuck.pptx", material_type="text", status="queued")
    kicks = []
    monkeypatch.setattr(
        "apps.opspilot.tasks.wiki_process_kb_material_builds_task.delay",
        lambda kb_id, operator="": kicks.append(kb_id),
    )
    stdout = StringIO()

    call_command("resume_wiki_material_builds", "--all", stdout=stdout)

    assert kicks == [stuck_kb.pk]
    assert f"kb={stuck_kb.pk}" in stdout.getvalue()
    assert f"kb={idle.pk}" not in stdout.getvalue()


def test_resume_wiki_material_builds_command_requires_target():
    from django.core.management import call_command
    from django.core.management.base import CommandError

    try:
        call_command("resume_wiki_material_builds")
    except CommandError as exc:
        assert "--knowledge-base" in str(exc)
        return
    raise AssertionError("expected CommandError")
