import pytest

pytestmark = pytest.mark.django_db(transaction=True)


def test_async_build_defers_generation_identity_until_parse_finishes(
    api_client,
    monkeypatch,
    wiki_factory,
):
    from apps.opspilot.models import Material
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base

    knowledge_base = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(knowledge_base, operator="admin")
    material = Material.objects.create(
        knowledge_base=knowledge_base,
        name="pending.md",
        material_type="text",
        text_content="待解析正文",
        source_identity="text:pending.md",
        status="pending",
    )
    kicks = []

    monkeypatch.setattr(
        "apps.opspilot.tasks.wiki_process_kb_material_builds_task.delay",
        lambda kb_id, operator="": kicks.append((kb_id, operator)),
    )

    response = api_client.post(
        f"/api/v1/opspilot/wiki_mgmt/material/{material.pk}/build/",
        {"async": True},
        format="json",
    )

    material.refresh_from_db()
    assert response.status_code == 200
    assert material.status == "queued"
    assert len(kicks) == 1
    assert kicks[0][0] == knowledge_base.pk


def test_unified_task_records_parse_failure_without_starting_generation(
    monkeypatch,
    wiki_factory,
):
    from apps.opspilot.models import BuildRecord, Material
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base
    from apps.opspilot.tasks import wiki_build_material_task

    knowledge_base = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(knowledge_base, operator="admin")
    material = Material.objects.create(
        knowledge_base=knowledge_base,
        name="broken.pdf",
        material_type="file",
        source_identity="file:broken.pdf",
        status="pending",
    )

    def fail_parse(item, llm_model_id=None):
        item.status = "parse_failed"
        item.error_message = "无法解析"
        item.save(update_fields=["status", "error_message", "updated_at"])
        return item

    monkeypatch.setattr(
        "apps.opspilot.services.wiki.material_service.ingest_material",
        fail_parse,
    )
    monkeypatch.setattr(
        "apps.opspilot.services.wiki.generation_material_build_service.build_material_with_generation",
        lambda *_args, **_kwargs: pytest.fail("generation must not start after parse failure"),
    )

    build_id = wiki_build_material_task.run(
        material.pk,
        operator="admin",
        ensure_parsed=True,
    )

    material.refresh_from_db()
    build = BuildRecord.objects.get(pk=build_id)
    assert material.status == "parse_failed"
    assert build.status == "failed"
    assert build.stage == "parse_failed"
    assert build.errors[0]["code"] == "material_parse_failed"


def test_unchanged_build_is_not_skipped_when_previous_pages_are_not_active(
    monkeypatch,
    wiki_factory,
):
    from apps.opspilot.models import BuildRecord, Material, MaterialVersion
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base
    from apps.opspilot.tasks import _material_pipeline_fingerprints, wiki_build_material_task

    knowledge_base = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(knowledge_base, operator="admin")
    knowledge_base.refresh_from_db()
    material = Material.objects.create(
        knowledge_base=knowledge_base,
        name="built.md",
        material_type="file",
        source_identity="file:built.md",
        content_hash="a" * 64,
        status="built",
    )
    version = MaterialVersion.objects.create(
        material=material,
        content_hash=material.content_hash,
    )
    material.current_version = version
    material.save(update_fields=["current_version", "updated_at"])
    parse_fingerprint, build_fingerprint = _material_pipeline_fingerprints(
        knowledge_base,
        material,
    )
    BuildRecord.objects.create(
        knowledge_base=knowledge_base,
        trigger="material",
        status="success",
        stage="done",
        progress=100,
        inputs={
            "material_id": material.pk,
            "parse_fingerprint": parse_fingerprint,
            "build_fingerprint": build_fingerprint,
        },
        affected_pages=[999999],
    )

    monkeypatch.setattr(
        "apps.opspilot.services.wiki.generation_material_build_service.build_material_with_generation",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("rebuild attempted")),
    )

    build_id = wiki_build_material_task.run(
        material.pk,
        operator="admin",
        ensure_parsed=True,
        source_status="built",
    )

    material.refresh_from_db()
    build = BuildRecord.objects.get(pk=build_id)
    assert (build.inputs or {}).get("outcome") != "skipped_unchanged"
    assert material.status == "build_failed"


def test_unchanged_successful_build_skips_parse_and_generation(
    monkeypatch,
    wiki_factory,
):
    from apps.opspilot.models import BuildRecord, Material, MaterialVersion
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base
    from apps.opspilot.tasks import _material_pipeline_fingerprints, wiki_build_material_task

    knowledge_base = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(knowledge_base, operator="admin")
    knowledge_base.refresh_from_db()
    material = Material.objects.create(
        knowledge_base=knowledge_base,
        name="unchanged.md",
        material_type="file",
        source_identity="file:unchanged.md",
        content_hash="b" * 64,
        status="built",
    )
    version = MaterialVersion.objects.create(
        material=material,
        content_hash=material.content_hash,
    )
    material.current_version = version
    material.save(update_fields=["current_version", "updated_at"])
    parse_fingerprint, build_fingerprint = _material_pipeline_fingerprints(
        knowledge_base,
        material,
    )
    BuildRecord.objects.create(
        knowledge_base=knowledge_base,
        trigger="material",
        status="success",
        stage="done",
        progress=100,
        inputs={
            "material_id": material.pk,
            "parse_fingerprint": parse_fingerprint,
            "build_fingerprint": build_fingerprint,
        },
        affected_pages=[],
    )

    monkeypatch.setattr(
        "apps.opspilot.services.wiki.material_service.ingest_material",
        lambda *_args, **_kwargs: pytest.fail("unchanged material must not parse"),
    )
    monkeypatch.setattr(
        "apps.opspilot.services.wiki.generation_material_build_service.build_material_with_generation",
        lambda *_args, **_kwargs: pytest.fail("unchanged material must not invoke generation"),
    )

    build_id = wiki_build_material_task.run(
        material.pk,
        operator="admin",
        ensure_parsed=True,
        source_status="built",
    )

    material.refresh_from_db()
    build = BuildRecord.objects.get(pk=build_id)
    assert material.status == "built"
    assert build.status == "success"
    assert build.stage == "done"
    assert build.inputs["outcome"] == "skipped_unchanged"
    assert build.counts == {"skipped_unchanged": 1}


def test_invalid_generation_json_marks_material_as_build_failed(
    monkeypatch,
    wiki_factory,
):
    from apps.opspilot.models import BuildRecord, Material, MaterialVersion
    from apps.opspilot.services.wiki.build_service import BuildOutputInvalid
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base
    from apps.opspilot.tasks import wiki_build_material_task

    knowledge_base = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(knowledge_base, operator="admin")
    material = Material.objects.create(
        knowledge_base=knowledge_base,
        name="invalid-json.md",
        material_type="text",
        text_content="正文",
        source_identity="text:invalid-json.md",
        content_hash="c" * 64,
        status="done",
    )
    version = MaterialVersion.objects.create(
        material=material,
        content_hash=material.content_hash,
    )
    material.current_version = version
    material.save(update_fields=["current_version", "updated_at"])

    monkeypatch.setattr(
        "apps.opspilot.services.wiki.generation_material_build_service.build_material_with_generation",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(BuildOutputInvalid("build_output_invalid_json")),
    )

    build_id = wiki_build_material_task.run(
        material.pk,
        operator="admin",
        ensure_parsed=True,
        source_status="done",
    )

    material.refresh_from_db()
    build = BuildRecord.objects.get(pk=build_id)
    assert material.status == "build_failed"
    assert build.status == "failed"
    assert build.errors[0]["code"] == "build_output_invalid_json"


def test_in_flight_task_does_not_revive_cancelled_build_record(monkeypatch, wiki_factory, caplog):
    import logging

    from apps.opspilot.models import BuildRecord, Material
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base
    from apps.opspilot.tasks import wiki_build_material_task

    knowledge_base = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(knowledge_base, operator="admin")
    material = Material.objects.create(
        knowledge_base=knowledge_base,
        name="cancelled.md",
        material_type="text",
        text_content="正文",
        status="parse_failed",
        error_message="构建已取消",
    )
    record = BuildRecord.objects.create(
        knowledge_base=knowledge_base,
        trigger="material",
        status="cancelled",
        stage="cancelled",
        inputs={"material_id": material.pk},
    )
    caplog.set_level(logging.INFO, logger="opspilot")
    monkeypatch.setattr(
        "apps.opspilot.services.wiki.generation_material_build_service.build_material_with_generation",
        lambda *_args, **_kwargs: pytest.fail("cancelled build must not start generation"),
    )

    result = wiki_build_material_task.run(
        material.pk,
        operator="admin",
        ensure_parsed=True,
        source_status="building",
        build_record_id=record.pk,
    )

    material.refresh_from_db()
    record.refresh_from_db()
    assert result is None
    assert record.status == "cancelled"
    assert material.status == "parse_failed"
    assert material.error_message == "构建已取消"
    assert not BuildRecord.objects.filter(
        knowledge_base=knowledge_base,
        trigger="material",
        status="running",
    ).exists()
    assert any(
        rec.msg == "wiki material build discarded cancelled record=%s material=%s" and rec.args == (record.pk, material.pk) for rec in caplog.records
    )


def test_generation_publish_discards_writes_when_build_cancelled(monkeypatch, wiki_factory):
    from apps.opspilot.models import BuildRecord, Material, MaterialVersion
    from apps.opspilot.services.wiki.build_service import MaterialPageGeneration
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base
    from apps.opspilot.tasks import wiki_build_material_task

    knowledge_base = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(knowledge_base, operator="admin")
    knowledge_base.refresh_from_db()
    material = Material.objects.create(
        knowledge_base=knowledge_base,
        name="live.md",
        material_type="text",
        text_content="正文",
        source_identity="text:live.md",
        content_hash="d" * 64,
        status="building",
    )
    version = MaterialVersion.objects.create(material=material, content_hash=material.content_hash)
    material.current_version = version
    material.save(update_fields=["current_version", "updated_at"])
    record = BuildRecord.objects.create(
        knowledge_base=knowledge_base,
        trigger="material",
        status="running",
        stage="generating",
        inputs={"material_id": material.pk},
    )

    monkeypatch.setattr(
        "apps.opspilot.services.wiki.generation_material_build_service.generate_material_pages_with_budget",
        lambda *_args, **_kwargs: MaterialPageGeneration([], []),
    )

    def cancel_during_overview(*_args, **_kwargs):
        BuildRecord.objects.filter(pk=record.pk).update(status="cancelled", stage="cancelled")
        Material.objects.filter(pk=material.pk).update(status="parse_failed", error_message="构建已取消")
        return {}

    monkeypatch.setattr(
        "apps.opspilot.services.wiki.generation_navigation_service.enhance_generation_overviews",
        cancel_during_overview,
    )

    result = wiki_build_material_task.run(
        material.pk,
        operator="admin",
        ensure_parsed=True,
        source_status="done",
        build_record_id=record.pk,
    )

    material.refresh_from_db()
    record.refresh_from_db()
    assert result is None
    assert record.status == "cancelled"
    assert material.status == "parse_failed"
    assert material.error_message == "构建已取消"


def test_strict_page_output_rejects_invalid_json():
    from apps.opspilot.services.wiki.build_service import _parse_pages

    with pytest.raises(ValueError, match="build_output_invalid_json"):
        _parse_pages("this is not json", strict=True)
