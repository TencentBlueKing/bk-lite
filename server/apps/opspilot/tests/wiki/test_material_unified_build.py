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
    calls = []

    monkeypatch.setattr(
        "apps.opspilot.tasks.wiki_build_material_task.delay",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    response = api_client.post(
        f"/api/v1/opspilot/wiki_mgmt/material/{material.pk}/build/",
        {"async": True},
        format="json",
    )

    material.refresh_from_db()
    assert response.status_code == 200
    assert material.status == "parsing"
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[0] == material.pk
    assert args[1] == knowledge_base.llm_model_id
    assert kwargs == {
        "classification_root_id": None,
        "ensure_parsed": True,
        "source_status": "pending",
    }


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


def test_strict_page_output_rejects_invalid_json():
    from apps.opspilot.services.wiki.build_service import _parse_pages

    with pytest.raises(ValueError, match="build_output_invalid_json"):
        _parse_pages("this is not json", strict=True)
