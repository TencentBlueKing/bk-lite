import pytest


def _kb():
    from apps.opspilot.models import WikiKnowledgeBase

    return WikiKnowledgeBase.objects.create(name="kb", team=[1])


def _page(kb, title="Page", body="# Title\n\ncontent"):
    from apps.opspilot.services.wiki.page_service import create_manual_page

    return create_manual_page(kb, page_type="concept", title=title, body=body, created_by="tester")


@pytest.mark.django_db
def test_cascade_returns_stage_statuses_and_errors(monkeypatch):
    from apps.opspilot.services.wiki import cascade_service

    kb = _kb()
    page = _page(kb)

    def fail_relations(*args, **kwargs):
        raise RuntimeError("relation backend unavailable")

    logged = []
    monkeypatch.setattr(cascade_service, "sync_relations_for_pages", fail_relations)
    monkeypatch.setattr(cascade_service, "index_version", lambda *args, **kwargs: True)
    monkeypatch.setattr(cascade_service, "reindex_page_chunks", lambda *args, **kwargs: 2)
    monkeypatch.setattr(cascade_service, "sweep_open_checks", lambda *args, **kwargs: 1)
    monkeypatch.setattr(cascade_service.logger, "exception", lambda *args, **kwargs: logged.append(args))

    result = cascade_service.cascade(kb, [page.id], event="build")

    assert logged
    assert result["status"] == "partial"
    assert result["relations"] == 0
    assert result["indexed_pages"] == 1
    assert result["indexed_chunks"] == 2
    assert result["auto_resolved"] == 1
    assert result["stages"]["relations"]["status"] == "failed"
    assert result["stages"]["relations"]["error"] == "relation backend unavailable"
    assert result["stages"]["page_embedding"] == {"status": "success", "count": 1}
    assert result["stages"]["chunk_embedding"] == {"status": "success", "count": 2}
    assert result["stages"]["check_sweep"] == {"status": "success", "count": 1}


@pytest.mark.django_db
def test_cascade_reports_index_failures_for_page_and_chunk_stages(monkeypatch):
    from apps.opspilot.services.wiki import cascade_service

    kb = _kb()
    page = _page(kb)

    def fail_index(*args, **kwargs):
        raise RuntimeError("embedding endpoint down")

    logged = []
    monkeypatch.setattr(cascade_service, "sync_relations_for_pages", lambda *args, **kwargs: [])
    monkeypatch.setattr(cascade_service, "index_version", fail_index)
    monkeypatch.setattr(cascade_service, "sweep_open_checks", lambda *args, **kwargs: 0)
    monkeypatch.setattr(cascade_service.logger, "exception", lambda *args, **kwargs: logged.append(args))

    result = cascade_service.cascade(kb, [page.id], event="build")

    assert logged
    assert result["status"] == "partial"
    assert result["stages"]["page_embedding"] == {"status": "failed", "error": "embedding endpoint down"}
    assert result["stages"]["chunk_embedding"] == {"status": "failed", "error": "embedding endpoint down"}


@pytest.mark.django_db
def test_cascade_can_retry_only_selected_maintenance_stage(monkeypatch):
    from apps.opspilot.services.wiki import cascade_service

    kb = _kb()
    page = _page(kb)
    calls = []

    monkeypatch.setattr(cascade_service, "sync_relations_for_pages", lambda *args, **kwargs: pytest.fail("relations should not run"))
    monkeypatch.setattr(cascade_service, "reindex_page_chunks", lambda *args, **kwargs: pytest.fail("chunk index should not run"))
    monkeypatch.setattr(cascade_service, "sweep_open_checks", lambda *args, **kwargs: pytest.fail("check sweep should not run"))

    def fake_index(version, embed_provider):
        calls.append((version.id, embed_provider))
        return True

    monkeypatch.setattr(cascade_service, "index_version", fake_index)

    result = cascade_service.cascade(kb, [page.id], event="maintenance_retry", stages=["page_embedding"])

    assert calls == [(page.current_version_id, None)]
    assert result["status"] == "success"
    assert result["indexed_pages"] == 1
    assert result["indexed_chunks"] == 0
    assert result["stages"] == {"page_embedding": {"status": "success", "count": 1}}


@pytest.mark.django_db
def test_cascade_reports_check_sweep_failure(monkeypatch):
    from apps.opspilot.services.wiki import cascade_service

    kb = _kb()
    page = _page(kb)

    def fail_sweep(*args, **kwargs):
        raise RuntimeError("check scan failed")

    logged = []
    monkeypatch.setattr(cascade_service, "sync_relations_for_pages", lambda *args, **kwargs: [])
    monkeypatch.setattr(cascade_service, "index_version", lambda *args, **kwargs: True)
    monkeypatch.setattr(cascade_service, "reindex_page_chunks", lambda *args, **kwargs: 1)
    monkeypatch.setattr(cascade_service, "sweep_open_checks", fail_sweep)
    monkeypatch.setattr(cascade_service.logger, "exception", lambda *args, **kwargs: logged.append(args))

    result = cascade_service.cascade(kb, [page.id], event="build")

    assert logged
    assert result["status"] == "partial"
    assert result["stages"]["check_sweep"] == {"status": "failed", "error": "check scan failed"}


@pytest.mark.django_db
def test_cascade_reports_deleted_page_prune_failure(monkeypatch):
    from apps.opspilot.services.wiki import cascade_service

    kb = _kb()
    page = _page(kb)

    def fail_prune(*args, **kwargs):
        raise RuntimeError("prune failed")

    logged = []
    monkeypatch.setattr(cascade_service, "sync_relations_for_pages", lambda *args, **kwargs: [])
    monkeypatch.setattr(cascade_service, "clear_page_vectors", lambda *args, **kwargs: 1)
    monkeypatch.setattr(cascade_service, "sweep_open_checks", lambda *args, **kwargs: 0)
    monkeypatch.setattr(cascade_service, "drop_page_references", fail_prune)
    monkeypatch.setattr(cascade_service.logger, "exception", lambda *args, **kwargs: logged.append(args))

    result = cascade_service.cascade(kb, [page.id], event="page_delete", prune_deleted_pages=True)

    assert logged
    assert result["status"] == "partial"
    assert result["stages"]["deleted_page_prune"] == {"status": "failed", "error": "prune failed"}


@pytest.mark.django_db
def test_build_from_material_persists_cascade_maintenance(monkeypatch):
    from apps.opspilot.models import Material, WikiKnowledgeBase
    from apps.opspilot.services.wiki import build_service

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1], purpose_md="# P", schema_md="# S")
    material = Material.objects.create(knowledge_base=kb, name="source", material_type="text", text_content="body")
    maintenance = {
        "status": "success",
        "event": "build",
        "stages": {"relations": {"status": "success", "count": 1}},
    }

    monkeypatch.setattr(build_service, "_llm_extract_facts", lambda *args, **kwargs: "facts")
    monkeypatch.setattr(
        build_service,
        "_llm_generate_pages",
        lambda *args, **kwargs: [{"page_type": "concept", "title": "Generated", "tags": [], "body": "Body"}],
    )
    monkeypatch.setattr(build_service, "cascade", lambda *args, **kwargs: maintenance)

    record = build_service.build_from_material(material, llm_model_id=1)

    record.refresh_from_db()
    assert record.maintenance == maintenance


@pytest.mark.django_db
def test_rebuild_knowledge_base_persists_cascade_maintenance(monkeypatch):
    from apps.opspilot.models import Material, WikiKnowledgeBase
    from apps.opspilot.services.wiki import rebuild_service

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1], purpose_md="# P", schema_md="# S")
    Material.objects.create(knowledge_base=kb, name="source", material_type="text", text_content="body")
    maintenance = {
        "status": "success",
        "event": "build",
        "stages": {"chunk_embedding": {"status": "success", "count": 3}},
    }

    monkeypatch.setattr(rebuild_service, "cascade", lambda *args, **kwargs: maintenance)

    record = rebuild_service.rebuild_knowledge_base(
        kb,
        llm_model_id=1,
        generator=lambda material: [{"page_type": "concept", "title": "Rebuilt", "tags": [], "body": "Body"}],
    )

    record.refresh_from_db()
    assert record.maintenance == maintenance


@pytest.mark.django_db
def test_material_deletion_persists_cascade_maintenance(monkeypatch):
    from apps.opspilot.models import Material, PageEvidence
    from apps.opspilot.services.wiki import update_service

    kb = _kb()
    material = Material.objects.create(knowledge_base=kb, name="source", material_type="text", text_content="body")
    page = _page(kb)
    PageEvidence.objects.create(page=page, material=material)
    maintenance = {
        "status": "partial",
        "event": "material_delete",
        "stages": {"chunk_embedding": {"status": "failed", "error": "embed failed"}},
    }

    monkeypatch.setattr(update_service, "cascade", lambda *args, **kwargs: maintenance)

    record = update_service.handle_material_deletion(material)

    record.refresh_from_db()
    assert record.maintenance == maintenance


@pytest.mark.django_db
def test_accept_candidate_persists_cascade_maintenance_on_source_build_record(monkeypatch):
    from apps.opspilot.models import BuildRecord
    from apps.opspilot.services.wiki import check_service

    kb = _kb()
    page = _page(kb, body="old body")
    record = BuildRecord.objects.create(knowledge_base=kb, trigger="material_update", status="success", stage="done")
    check = check_service.create_candidate(
        page,
        body="new body",
        reason="资料更新",
        check_type="material_update",
        build_record=record,
    )
    maintenance = {
        "status": "success",
        "event": "accept",
        "stages": {"page_embedding": {"status": "success", "count": 1}},
    }

    monkeypatch.setattr(check_service, "cascade", lambda *args, **kwargs: maintenance)

    check_service.accept_candidate(check)

    record.refresh_from_db()
    assert record.maintenance == maintenance


@pytest.mark.django_db
def test_build_record_serializer_exposes_maintenance(api_client):
    from apps.opspilot.models import BuildRecord

    kb = _kb()
    record = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="material",
        status="success",
        stage="done",
        maintenance={"status": "success", "stages": {"relations": {"status": "success", "count": 2}}},
    )

    response = api_client.get(f"/api/v1/opspilot/wiki_mgmt/build_record/{record.id}/")

    assert response.status_code == 200, response.content
    assert response.json()["data"]["maintenance"] == record.maintenance


@pytest.mark.django_db
def test_build_record_retry_maintenance_replays_cascade_and_updates_record(api_client, monkeypatch):
    from apps.opspilot.models import BuildRecord
    from apps.opspilot.viewsets import wiki_page_view

    kb = _kb()
    page = _page(kb, "RetryTarget")
    record = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="material",
        status="partial",
        stage="done",
        affected_pages=[page.id],
        maintenance={
            "status": "partial",
            "event": "build",
            "affected_page_ids": [page.id],
            "stages": {"page_embedding": {"status": "failed", "error": "embed failed"}},
        },
    )
    calls = []
    maintenance = {
        "status": "success",
        "event": "maintenance_retry",
        "affected_page_ids": [page.id],
        "stages": {"page_embedding": {"status": "success", "count": 1}},
    }

    def fake_cascade(knowledge_base, affected_page_ids, event, **kwargs):
        calls.append((knowledge_base.id, affected_page_ids, event, kwargs))
        return maintenance

    monkeypatch.setattr(wiki_page_view, "cascade", fake_cascade)

    response = api_client.post(f"/api/v1/opspilot/wiki_mgmt/build_record/{record.id}/retry_maintenance/", {}, format="json")

    assert response.status_code == 200, response.content
    data = response.json()["data"]
    assert data["status"] == "success"
    assert data["maintenance"] == maintenance
    assert data["inputs"]["maintenance_retry_of"] == "build"
    assert calls == [(kb.id, [page.id], "maintenance_retry", {})]
    record.refresh_from_db()
    assert record.status == "success"
    assert record.maintenance == maintenance


@pytest.mark.django_db
def test_build_record_retry_maintenance_retries_selected_stages_and_preserves_other_stage_status(api_client, monkeypatch):
    from apps.opspilot.models import BuildRecord
    from apps.opspilot.viewsets import wiki_page_view

    kb = _kb()
    page = _page(kb, "RetryTarget")
    previous_maintenance = {
        "status": "partial",
        "event": "build",
        "affected_page_ids": [page.id],
        "stages": {
            "relations": {"status": "success", "count": 3},
            "page_embedding": {"status": "failed", "error": "page embed failed"},
            "chunk_embedding": {"status": "failed", "error": "chunk embed failed"},
        },
        "relations": 3,
        "indexed_pages": 0,
        "indexed_chunks": 0,
    }
    record = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="material",
        status="partial",
        stage="done",
        affected_pages=[page.id],
        maintenance=previous_maintenance,
    )
    calls = []
    retry_maintenance = {
        "status": "success",
        "event": "maintenance_retry",
        "affected_page_ids": [page.id],
        "stages": {"page_embedding": {"status": "success", "count": 1}},
        "indexed_pages": 1,
        "indexed_chunks": 0,
    }

    def fake_cascade(knowledge_base, affected_page_ids, event, **kwargs):
        calls.append((knowledge_base.id, affected_page_ids, event, kwargs))
        return retry_maintenance

    monkeypatch.setattr(wiki_page_view, "cascade", fake_cascade)

    response = api_client.post(
        f"/api/v1/opspilot/wiki_mgmt/build_record/{record.id}/retry_maintenance/",
        {"stages": ["page_embedding"]},
        format="json",
    )

    assert response.status_code == 200, response.content
    data = response.json()["data"]
    assert calls == [(kb.id, [page.id], "maintenance_retry", {"stages": ["page_embedding"]})]
    assert data["status"] == "partial"
    assert data["maintenance"]["status"] == "partial"
    assert data["maintenance"]["stages"]["relations"] == {"status": "success", "count": 3}
    assert data["maintenance"]["stages"]["page_embedding"] == {"status": "success", "count": 1}
    assert data["maintenance"]["stages"]["chunk_embedding"] == {"status": "failed", "error": "chunk embed failed"}
    assert data["maintenance"]["indexed_pages"] == 1
    assert data["maintenance"]["indexed_chunks"] == 0
    assert data["inputs"]["maintenance_retry_stages"] == ["page_embedding"]
    record.refresh_from_db()
    assert record.status == "partial"
    assert record.maintenance["stages"]["chunk_embedding"]["status"] == "failed"


@pytest.mark.django_db
def test_build_record_batch_retry_maintenance_retries_selected_records_and_skips_empty_records(api_client, monkeypatch):
    from apps.opspilot.models import BuildRecord
    from apps.opspilot.viewsets import wiki_page_view

    kb = _kb()
    page_one = _page(kb, "BatchRetryOne")
    page_two = _page(kb, "BatchRetryTwo")
    retry_one = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="material",
        status="partial",
        stage="done",
        affected_pages=[page_one.id],
        maintenance={
            "status": "partial",
            "event": "build",
            "affected_page_ids": [page_one.id],
            "stages": {"chunk_embedding": {"status": "failed", "error": "chunk one"}},
        },
    )
    retry_two = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="material",
        status="partial",
        stage="done",
        affected_pages=[page_two.id],
        maintenance={
            "status": "partial",
            "event": "build",
            "affected_page_ids": [page_two.id],
            "stages": {"chunk_embedding": {"status": "failed", "error": "chunk two"}},
        },
    )
    skipped = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="material",
        status="partial",
        stage="done",
        maintenance={"status": "partial", "stages": {"chunk_embedding": {"status": "failed", "error": "empty"}}},
    )
    calls = []

    def fake_cascade(knowledge_base, affected_page_ids, event, **kwargs):
        calls.append((knowledge_base.id, affected_page_ids, event, kwargs))
        return {
            "status": "success",
            "event": "maintenance_retry",
            "affected_page_ids": affected_page_ids,
            "stages": {"chunk_embedding": {"status": "success", "count": len(affected_page_ids)}},
            "indexed_chunks": len(affected_page_ids),
        }

    monkeypatch.setattr(wiki_page_view, "cascade", fake_cascade)

    response = api_client.post(
        "/api/v1/opspilot/wiki_mgmt/build_record/batch_retry_maintenance/",
        {"knowledge_base": kb.id, "ids": [retry_one.id, retry_two.id, skipped.id], "stages": ["chunk_embedding"]},
        format="json",
    )

    assert response.status_code == 200, response.content
    data = response.json()["data"]
    assert data["retried"] == 2
    assert data["skipped"] == 1
    assert data["skipped_ids"] == [skipped.id]
    assert [item["id"] for item in data["items"]] == [retry_one.id, retry_two.id]
    assert calls == [
        (kb.id, [page_one.id], "maintenance_retry", {"stages": ["chunk_embedding"]}),
        (kb.id, [page_two.id], "maintenance_retry", {"stages": ["chunk_embedding"]}),
    ]
    retry_one.refresh_from_db()
    retry_two.refresh_from_db()
    skipped.refresh_from_db()
    assert retry_one.status == "success"
    assert retry_two.maintenance["stages"]["chunk_embedding"] == {"status": "success", "count": 1}
    assert retry_one.inputs["maintenance_retry_stages"] == ["chunk_embedding"]
    assert skipped.status == "partial"


@pytest.mark.django_db
def test_build_record_retry_maintenance_rejects_record_without_affected_pages(api_client, monkeypatch):
    from apps.opspilot.models import BuildRecord
    from apps.opspilot.viewsets import wiki_page_view

    kb = _kb()
    record = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="material",
        status="partial",
        stage="done",
        maintenance={"status": "partial", "stages": {"relations": {"status": "failed", "error": "boom"}}},
    )
    monkeypatch.setattr(wiki_page_view, "cascade", lambda *args, **kwargs: pytest.fail("empty retry should not cascade"))

    response = api_client.post(f"/api/v1/opspilot/wiki_mgmt/build_record/{record.id}/retry_maintenance/", {}, format="json")

    assert response.status_code == 400
    assert "受影响页面" in response.json()["message"]
