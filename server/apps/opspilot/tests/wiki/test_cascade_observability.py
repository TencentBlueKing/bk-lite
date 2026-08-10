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
def test_material_deletion_persists_cascade_maintenance(monkeypatch, django_capture_on_commit_callbacks):
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

    with django_capture_on_commit_callbacks(execute=True):
        record = update_service.handle_material_deletion(material)

    record.refresh_from_db()
    assert record.status == "partial"
    assert record.maintenance["status"] == "partial"
    assert record.maintenance["event"] == "material_delete"
    assert record.maintenance["affected_page_ids"] == [page.id]
    assert record.maintenance["invalidated"] == maintenance
    assert record.maintenance["stages"] == maintenance["stages"]


@pytest.mark.django_db
def test_material_deletion_commits_core_state_when_cascade_crashes(monkeypatch, django_capture_on_commit_callbacks):
    from apps.opspilot.models import CheckItem, Material, PageEvidence
    from apps.opspilot.services.wiki import update_service
    from apps.opspilot.services.wiki.decision_service import create_rule_if_eligible

    kb = _kb()
    removed = Material.objects.create(
        knowledge_base=kb,
        name="removed",
        material_type="text",
        text_content="body",
        content_hash="removed-hash",
    )
    remaining = Material.objects.create(
        knowledge_base=kb,
        name="remaining",
        material_type="text",
        text_content="body",
    )
    invalidated_page = _page(kb, title="Invalidated")
    shared_page = _page(kb, title="Shared")
    PageEvidence.objects.create(page=invalidated_page, material=removed)
    PageEvidence.objects.create(page=shared_page, material=removed)
    PageEvidence.objects.create(page=shared_page, material=remaining)
    source_check = CheckItem.objects.create(
        knowledge_base=kb,
        check_type="source_invalid",
        status="auto_resolved",
        related={
            "pages": [invalidated_page.id],
            "resolution": {"action": "automatic_maintenance", "operator": "system"},
        },
    )
    conflict_check = CheckItem.objects.create(
        knowledge_base=kb,
        check_type="cannot_merge",
        status="open",
        related={"pages": [shared_page.id], "materials": [removed.id]},
    )
    rule = create_rule_if_eligible(
        knowledge_base=kb,
        decision_type="knowledge_conflict",
        subject_key="page::concept::invalidated",
        schema_fingerprint="schema",
        participants=[{"material_id": removed.id, "content_hash": removed.content_hash}],
        action="keep_current",
        result_page=invalidated_page,
        result_version=invalidated_page.current_version,
    )
    material_id = removed.id
    calls = []

    def fail_cascade(knowledge_base, affected_page_ids, event, **kwargs):
        calls.append((list(affected_page_ids), event, kwargs))
        raise RuntimeError(f"cascade crashed: {event}")

    monkeypatch.setattr(update_service, "cascade", fail_cascade)

    with django_capture_on_commit_callbacks(execute=True):
        record = update_service.handle_material_deletion(removed, operator="admin")

    invalidated_page.refresh_from_db()
    shared_page.refresh_from_db()
    source_check.refresh_from_db()
    conflict_check.refresh_from_db()
    rule.refresh_from_db()
    record.refresh_from_db()
    assert calls == [
        ([invalidated_page.id], "material_delete", {}),
        ([shared_page.id], "build", {}),
    ]
    assert not Material.objects.filter(pk=material_id).exists()
    assert invalidated_page.status == "source_invalid"
    assert shared_page.status == "active"
    assert PageEvidence.objects.filter(page=shared_page, material=remaining).exists()
    assert source_check.status == "auto_resolved"
    assert conflict_check.status == "auto_resolved"
    assert rule.status == "revoked"
    assert record.counts["pending_review"] == 0
    assert record.stage == "done"
    assert record.status == "partial"
    assert record.progress == 100
    assert record.maintenance["invalidated"]["stages"]["cascade"]["status"] == "failed"
    assert record.maintenance["shared"]["stages"]["cascade"]["status"] == "failed"
    assert len(record.errors) == 2


@pytest.mark.django_db
def test_accept_candidate_defers_cascade_and_persists_partial_retry_record(
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    from apps.opspilot.models import BuildRecord
    from apps.opspilot.services.wiki import check_service
    from apps.opspilot.viewsets import wiki_page_view

    kb = _kb()
    page = _page(kb, body="old body")
    source_record = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="material_update",
        status="success",
        stage="done",
    )
    check = check_service.create_candidate(
        page,
        body="new body",
        reason="资料更新",
        check_type="material_update",
        build_record=source_record,
    )
    partial_maintenance = {
        "status": "partial",
        "event": "accept",
        "affected_page_ids": [page.id],
        "stages": {"page_embedding": {"status": "failed", "error": "embed failed"}},
    }
    cascade_calls = []

    def fake_cascade(knowledge_base, affected_page_ids, event, **kwargs):
        cascade_calls.append((knowledge_base.id, affected_page_ids, event, kwargs))
        return partial_maintenance

    monkeypatch.setattr(check_service, "cascade", fake_cascade)

    with django_capture_on_commit_callbacks(execute=True):
        check_service.accept_candidate(check)

        assert cascade_calls == []
        decision_record = BuildRecord.objects.get(trigger="decision")
        assert decision_record.status == "running"
        assert decision_record.maintenance["status"] == "pending"
        check.refresh_from_db()
        assert check.related["maintenance"] == {
            "build_record_id": decision_record.id,
            "status": "pending",
        }

    assert cascade_calls == [(kb.id, [page.id], "accept", {})]
    decision_record.refresh_from_db()
    source_record.refresh_from_db()
    check.refresh_from_db()
    assert decision_record.status == "partial"
    assert decision_record.stage == "done"
    assert decision_record.affected_pages == [page.id]
    assert decision_record.inputs["decision_check_id"] == check.id
    assert decision_record.inputs["source_build_record_id"] == source_record.id
    assert decision_record.maintenance == partial_maintenance
    assert source_record.maintenance == {
        "decision_children": {
            str(check.id): {
                "check_id": check.id,
                "build_record_id": decision_record.id,
                "status": "partial",
                "event": "accept",
                "affected_page_ids": [page.id],
                "maintenance": partial_maintenance,
            }
        }
    }
    assert check.related["maintenance"] == {
        "build_record_id": decision_record.id,
        "status": "partial",
    }

    retry_calls = []
    retry_maintenance = {
        "status": "success",
        "event": "maintenance_retry",
        "affected_page_ids": [page.id],
        "stages": {"page_embedding": {"status": "success", "count": 1}},
        "indexed_pages": 1,
    }

    def fake_retry(knowledge_base, affected_page_ids, event, **kwargs):
        retry_calls.append((knowledge_base.id, affected_page_ids, event, kwargs))
        return retry_maintenance

    monkeypatch.setattr(wiki_page_view, "cascade", fake_retry)
    retried = wiki_page_view._retry_build_record_maintenance(
        decision_record,
        selected_stages=["page_embedding"],
    )

    assert retried.id == decision_record.id
    assert retry_calls == [(kb.id, [page.id], "maintenance_retry", {"stages": ["page_embedding"]})]
    retried.refresh_from_db()
    assert retried.status == "success"
    assert retried.maintenance["stages"]["page_embedding"]["status"] == "success"


@pytest.mark.django_db
def test_decision_maintenance_callback_failure_is_contained(
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    from apps.opspilot.models import BuildRecord, Material
    from apps.opspilot.services.wiki import check_service

    kb = _kb()
    page = _page(kb, body="old body")
    incoming_material = Material.objects.create(
        knowledge_base=kb,
        name="incoming",
        material_type="text",
        content_hash="incoming-v1",
    )
    check = check_service.create_candidate(
        page,
        body="new body",
        reason="new material",
        check_type="material_update",
        incoming_material=incoming_material,
    )

    def fail_cascade(*args, **kwargs):
        raise RuntimeError("maintenance crashed")

    monkeypatch.setattr(check_service, "cascade", fail_cascade)

    with django_capture_on_commit_callbacks(execute=True):
        rule = check_service.decide_check(check, action="use_new", operator="reviewer")

    assert rule is not None
    page.refresh_from_db()
    check.refresh_from_db()
    decision_record = BuildRecord.objects.get(trigger="decision")
    assert page.current_version_id == check.candidate_version_id
    assert check.status == "resolved"
    assert decision_record.status == "failed"
    assert decision_record.stage == "done"
    assert decision_record.errors == ["maintenance crashed"]
    assert decision_record.maintenance["status"] == "partial"
    assert decision_record.maintenance["stages"]["cascade"] == {
        "status": "failed",
        "error": "maintenance crashed",
    }
    assert check.related["maintenance"] == {
        "build_record_id": decision_record.id,
        "status": "partial",
    }


@pytest.mark.django_db
def test_page_identity_merge_defers_and_persists_partial_maintenance(
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    from apps.opspilot.models import BuildRecord
    from apps.opspilot.services.wiki import check_service

    kb = _kb()
    target = _page(kb, title="Canonical", body="target")
    source = _page(kb, title="Alias", body="source")
    check = check_service.ensure_check(
        kb,
        "duplicate",
        target,
        related={"pages": [source.id, target.id], "canonical_title": target.title},
    )[0]
    partial_maintenance = {
        "status": "partial",
        "event": "merge_duplicate",
        "affected_page_ids": [target.id, source.id],
        "stages": {"relations": {"status": "failed", "error": "relation failed"}},
    }
    cascade_calls = []

    def fake_cascade(knowledge_base, affected_page_ids, event, **kwargs):
        cascade_calls.append((knowledge_base.id, affected_page_ids, event, kwargs))
        return partial_maintenance

    monkeypatch.setattr(check_service, "cascade", fake_cascade)

    with django_capture_on_commit_callbacks(execute=True):
        rule = check_service.decide_check(check, action="merge", operator="reviewer")
        assert cascade_calls == []

    assert rule is not None
    assert len(cascade_calls) == 1
    kb_id, affected_page_ids, event, kwargs = cascade_calls[0]
    assert kb_id == kb.id
    assert affected_page_ids == [target.id, source.id]
    assert event == "merge_duplicate"
    assert kwargs == {"deleted_titles": [source.title]}

    decision_record = BuildRecord.objects.get(trigger="decision")
    check.refresh_from_db()
    source.refresh_from_db()
    assert source.status == "archived"
    assert decision_record.status == "partial"
    assert decision_record.affected_pages == [target.id, source.id]
    assert decision_record.maintenance == partial_maintenance
    assert check.related["maintenance"] == {
        "build_record_id": decision_record.id,
        "status": "partial",
    }


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


@pytest.mark.django_db
def test_rebuild_retry_maintenance_retries_archived_pages_as_delete(api_client, monkeypatch):
    from apps.opspilot.models import KnowledgePage, Material
    from apps.opspilot.services.wiki import rebuild_service
    from apps.opspilot.viewsets import wiki_page_view

    kb = _kb()
    Material.objects.create(
        knowledge_base=kb,
        name="source",
        material_type="text",
        text_content="facts",
    )
    archived_page = _page(kb, title="ArchivedAI")
    archived_page.contribution = "ai"
    archived_page.save(update_fields=["contribution", "updated_at"])

    def initial_cascade(knowledge_base, affected_page_ids, event, **kwargs):
        if event == "page_delete":
            return {
                "status": "partial",
                "event": event,
                "affected_page_ids": list(affected_page_ids),
                "stages": {
                    "relations": {"status": "success", "count": 1},
                    "page_embedding": {"status": "failed", "error": "clear failed"},
                },
                "relations": 1,
                "cleared_pages": 0,
            }
        assert event == "build"
        return {
            "status": "success",
            "event": event,
            "affected_page_ids": list(affected_page_ids),
            "stages": {
                "relations": {"status": "success", "count": 1},
                "page_embedding": {"status": "success", "count": 1},
            },
            "relations": 1,
            "indexed_pages": 1,
        }

    monkeypatch.setattr(rebuild_service, "cascade", initial_cascade)
    record = rebuild_service.rebuild_knowledge_base(
        kb,
        generator=lambda material: [
            {
                "page_type": "concept",
                "title": "Generated",
                "tags": [],
                "body": "fresh",
            }
        ],
    )
    generated_page = KnowledgePage.objects.get(knowledge_base=kb, title="Generated")

    assert set(record.affected_pages) == {archived_page.id, generated_page.id}
    assert record.maintenance["status"] == "partial"
    assert record.status == "partial"
    assert record.maintenance["stages"]["page_embedding"]["status"] == "failed"
    assert record.maintenance["archive"]["affected_page_ids"] == [archived_page.id]
    assert record.maintenance["generated"]["affected_page_ids"] == [generated_page.id]

    calls = []

    def retry_cascade(knowledge_base, affected_page_ids, event, **kwargs):
        calls.append((list(affected_page_ids), event, kwargs))
        is_archive = event == "page_delete"
        return {
            "status": "success",
            "event": event,
            "affected_page_ids": list(affected_page_ids),
            "stages": {"page_embedding": {"status": "success", "count": 1}},
            "cleared_pages": 1 if is_archive else 0,
            "indexed_pages": 0 if is_archive else 1,
        }

    monkeypatch.setattr(wiki_page_view, "cascade", retry_cascade)

    response = api_client.post(
        f"/api/v1/opspilot/wiki_mgmt/build_record/{record.id}/retry_maintenance/",
        {"stages": ["page_embedding"]},
        format="json",
    )

    assert response.status_code == 200, response.content
    assert calls == [
        ([archived_page.id], "page_delete", {"stages": ["page_embedding"], "deleted_titles": ["ArchivedAI"]}),
        ([generated_page.id], "maintenance_retry", {"stages": ["page_embedding"]}),
    ]
    data = response.json()["data"]
    assert set(data["affected_pages"]) == {archived_page.id, generated_page.id}
    assert data["status"] == "success"
    assert data["maintenance"]["status"] == "success"
    assert data["maintenance"]["stages"]["page_embedding"]["status"] == "success"
    assert data["maintenance"]["archive"]["status"] == "success"
    assert data["maintenance"]["generated"]["status"] == "success"


@pytest.mark.django_db
def test_material_delete_retry_partitions_invalidated_and_shared_pages(
    api_client,
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    from apps.opspilot.models import Material, PageEvidence
    from apps.opspilot.services.wiki import update_service
    from apps.opspilot.viewsets import wiki_page_view

    kb = _kb()
    removed = Material.objects.create(
        knowledge_base=kb,
        name="removed",
        material_type="text",
        text_content="facts",
    )
    remaining = Material.objects.create(
        knowledge_base=kb,
        name="remaining",
        material_type="text",
        text_content="facts",
    )
    invalidated_page = _page(kb, title="Invalidated")
    shared_page = _page(kb, title="Shared")
    PageEvidence.objects.create(page=invalidated_page, material=removed)
    PageEvidence.objects.create(page=shared_page, material=removed)
    PageEvidence.objects.create(page=shared_page, material=remaining)
    initial_calls = []

    def initial_cascade(knowledge_base, affected_page_ids, event, **kwargs):
        initial_calls.append((list(affected_page_ids), event, kwargs))
        is_invalidated = event == "material_delete"
        return {
            "status": "partial" if is_invalidated else "success",
            "event": event,
            "affected_page_ids": list(affected_page_ids),
            "stages": {"page_embedding": ({"status": "failed", "error": "clear failed"} if is_invalidated else {"status": "success", "count": 1})},
            "cleared_pages": 0,
            "indexed_pages": 0 if is_invalidated else 1,
        }

    monkeypatch.setattr(update_service, "cascade", initial_cascade)

    with django_capture_on_commit_callbacks(execute=True):
        record = update_service.handle_material_deletion(removed, operator="admin")

    assert initial_calls == [
        ([invalidated_page.id], "material_delete", {}),
        ([shared_page.id], "build", {}),
    ]
    assert set(record.affected_pages) == {invalidated_page.id, shared_page.id}
    assert record.status == "partial"
    assert record.maintenance["status"] == "partial"
    assert record.maintenance["stages"]["page_embedding"]["status"] == "failed"
    assert record.maintenance["invalidated"]["affected_page_ids"] == [invalidated_page.id]
    assert record.maintenance["shared"]["affected_page_ids"] == [shared_page.id]

    retry_calls = []

    def retry_cascade(knowledge_base, affected_page_ids, event, **kwargs):
        retry_calls.append((list(affected_page_ids), event, kwargs))
        return {
            "status": "success",
            "event": event,
            "affected_page_ids": list(affected_page_ids),
            "stages": {"page_embedding": {"status": "success", "count": 1}},
            "cleared_pages": 1 if event == "material_delete" else 0,
            "indexed_pages": 0 if event == "material_delete" else 1,
        }

    monkeypatch.setattr(wiki_page_view, "cascade", retry_cascade)

    response = api_client.post(
        f"/api/v1/opspilot/wiki_mgmt/build_record/{record.id}/retry_maintenance/",
        {"stages": ["page_embedding"]},
        format="json",
    )

    assert response.status_code == 200, response.content
    assert retry_calls == [
        ([invalidated_page.id], "material_delete", {"stages": ["page_embedding"]}),
        ([shared_page.id], "maintenance_retry", {"stages": ["page_embedding"]}),
    ]
    data = response.json()["data"]
    assert set(data["affected_pages"]) == {invalidated_page.id, shared_page.id}
    assert data["status"] == "success"
    assert data["maintenance"]["status"] == "success"
    assert data["maintenance"]["invalidated"]["status"] == "success"
    assert data["maintenance"]["shared"]["status"] == "success"


@pytest.mark.django_db
def test_two_decisions_append_child_summaries_without_overwriting_source_maintenance(
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    from apps.opspilot.models import BuildRecord
    from apps.opspilot.services.wiki import check_service

    kb = _kb()
    first_page = _page(kb, title="first", body="old first")
    second_page = _page(kb, title="second", body="old second")
    original_maintenance = {
        "status": "partial",
        "event": "build",
        "affected_page_ids": [first_page.id, second_page.id],
        "stages": {
            "relations": {"status": "success", "count": 2},
            "page_embedding": {"status": "failed", "error": "provider down"},
        },
    }
    source_record = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="material_update",
        status="partial",
        stage="done",
        affected_pages=[first_page.id, second_page.id],
        maintenance=original_maintenance,
    )
    first_check = check_service.create_candidate(
        first_page,
        body="new first",
        reason="first decision",
        check_type="material_update",
        build_record=source_record,
    )
    second_check = check_service.create_candidate(
        second_page,
        body="new second",
        reason="second decision",
        check_type="material_update",
        build_record=source_record,
    )

    def fake_cascade(knowledge_base, affected_page_ids, event, **kwargs):
        page_id = affected_page_ids[0]
        return {
            "status": "success",
            "event": event,
            "affected_page_ids": [page_id],
            "stages": {"relations": {"status": "success", "count": page_id}},
        }

    monkeypatch.setattr(check_service, "cascade", fake_cascade)

    with django_capture_on_commit_callbacks(execute=True):
        check_service.accept_candidate(first_check, operator="alice")
        check_service.accept_candidate(second_check, operator="bob")

    source_record.refresh_from_db()
    assert source_record.maintenance["status"] == original_maintenance["status"]
    assert source_record.maintenance["event"] == original_maintenance["event"]
    assert source_record.maintenance["affected_page_ids"] == original_maintenance["affected_page_ids"]
    assert source_record.maintenance["stages"] == original_maintenance["stages"]
    children = source_record.maintenance["decision_children"]
    assert set(children) == {str(first_check.id), str(second_check.id)}
    for check, page in ((first_check, first_page), (second_check, second_page)):
        child = children[str(check.id)]
        child_record = BuildRecord.objects.get(pk=child["build_record_id"])
        assert child["check_id"] == check.id
        assert child["status"] == "success"
        assert child["event"] == "accept"
        assert child["affected_page_ids"] == [page.id]
        assert child_record.inputs["source_build_record_id"] == source_record.id
        assert child_record.inputs["decision_check_id"] == check.id
