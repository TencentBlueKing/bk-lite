"""按 KB 串行的资料构建队列。"""

import pytest

pytestmark = pytest.mark.django_db(transaction=True)


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


def test_process_counts_missing_material_and_build_failure(monkeypatch, wiki_factory):
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

    def boom(*args, **kwargs):
        raise RuntimeError("build crashed")

    monkeypatch.setattr("apps.opspilot.tasks.wiki_build_material_task.run", boom)
    result = queue.process_kb_material_builds(kb.pk, operator="u1")
    material.refresh_from_db()
    assert result["processed"] == 0
    assert result["failed"] == 2
    assert material.status == "build_failed"


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
