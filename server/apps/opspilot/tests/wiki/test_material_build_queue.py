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
