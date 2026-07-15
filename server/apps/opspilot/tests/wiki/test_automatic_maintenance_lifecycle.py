import pytest


def _kb(name):
    from apps.opspilot.models import WikiKnowledgeBase

    return WikiKnowledgeBase.objects.create(name=name, team=[1])


def _material(kb, name="source"):
    from apps.opspilot.models import Material

    return Material.objects.create(
        knowledge_base=kb,
        name=name,
        material_type="text",
        text_content="source body",
        status="done",
    )


def _page_with_evidence(kb, material, *, title="Page", body="current", status="active"):
    from apps.opspilot.models import KnowledgePage, PageEvidence, PageVersion

    page = KnowledgePage.objects.create(
        knowledge_base=kb,
        title=title,
        page_type="concept",
        contribution="mixed",
        status=status,
    )
    version = PageVersion.objects.create(
        page=page,
        no=1,
        body=body,
        change_type="human_edit",
        is_current=True,
    )
    page.current_version = version
    page.save(update_fields=["current_version", "updated_at"])
    PageEvidence.objects.create(page=page, material=material)
    return page


def _stub_new_page_build(monkeypatch, build_service):
    monkeypatch.setattr(build_service, "load_parsed_markdown", lambda material: "source body")
    monkeypatch.setattr(build_service, "_llm_extract_facts", lambda text, llm_model_id: text)
    monkeypatch.setattr(
        build_service,
        "_llm_generate_pages",
        lambda kb, source_text, llm_model_id: [
            {
                "page_type": "concept",
                "title": "Generated",
                "tags": [],
                "body": "generated body",
            }
        ],
    )
    monkeypatch.setattr(build_service, "enrich_pages_wikilinks", lambda *args, **kwargs: [])


def test_maintenance_errors_collects_nested_stage_failures_once():
    from apps.opspilot.services.wiki.update_service import _maintenance_errors

    maintenance = {
        "status": "partial",
        "error": "top-level failure",
        "stages": {
            "relations": {
                "status": "failed",
                "components": {
                    "invalidated": {"status": "failed", "error": "relations unavailable"},
                    "shared": {"status": "failed", "error": "top-level failure"},
                },
            },
            "page_embedding": {"status": "failed", "error": "embedding unavailable"},
        },
    }

    assert _maintenance_errors(maintenance) == [
        "top-level failure",
        "relations unavailable",
        "embedding unavailable",
    ]


@pytest.mark.django_db
def test_build_from_material_promotes_partial_cascade_to_retryable_build(monkeypatch):
    from apps.opspilot.services.wiki import build_service

    kb = _kb("build-partial")
    material = _material(kb)
    _stub_new_page_build(monkeypatch, build_service)

    def partial_cascade(knowledge_base, affected_page_ids, event):
        return {
            "status": "partial",
            "event": event,
            "affected_page_ids": list(affected_page_ids),
            "stages": {"relations": {"status": "failed", "error": "relations unavailable"}},
        }

    monkeypatch.setattr(build_service, "cascade", partial_cascade)

    build = build_service.build_from_material(material, llm_model_id=1)

    assert build.status == "partial"
    assert build.stage == "done"
    assert build.affected_pages == build.maintenance["affected_page_ids"]
    assert build.maintenance["event"] == "build"
    assert build.errors == ["relations unavailable"]


@pytest.mark.django_db
def test_build_from_material_contains_cascade_exception_as_partial(monkeypatch):
    from apps.opspilot.services.wiki import build_service

    kb = _kb("build-cascade-exception")
    material = _material(kb)
    _stub_new_page_build(monkeypatch, build_service)
    monkeypatch.setattr(
        build_service,
        "cascade",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("cascade crashed")),
    )

    build = build_service.build_from_material(material, llm_model_id=1)

    assert build.status == "partial"
    assert build.maintenance == {
        "status": "partial",
        "event": "build",
        "affected_page_ids": build.affected_pages,
        "stages": {"cascade": {"status": "failed", "error": "cascade crashed"}},
        "error": "cascade crashed",
    }
    assert build.errors == ["cascade crashed"]


@pytest.mark.django_db
def test_propose_update_runs_and_persists_automatic_cascade(monkeypatch):
    from apps.opspilot.services.wiki import update_service

    kb = _kb("update-cascade")
    material = _material(kb)
    page = _page_with_evidence(kb, material, body="same body")
    calls = []

    def partial_cascade(knowledge_base, affected_page_ids, event):
        calls.append((knowledge_base.id, list(affected_page_ids), event))
        return {
            "status": "partial",
            "event": event,
            "affected_page_ids": list(affected_page_ids),
            "stages": {"page_embedding": {"status": "failed", "error": "embedding unavailable"}},
        }

    monkeypatch.setattr(update_service, "cascade", partial_cascade)

    build = update_service.propose_update(
        material,
        generator=lambda current_page, source: "same body",
    )

    assert calls == [(kb.id, [page.id], "material_update")]
    assert build.status == "partial"
    assert build.affected_pages == [page.id]
    assert build.maintenance["affected_page_ids"] == [page.id]
    assert build.errors == ["embedding unavailable"]


@pytest.mark.parametrize("check_type", ["material_update", "cannot_merge"])
@pytest.mark.django_db
def test_sweep_open_knowledge_conflicts_recounts_source_build_pending_review(check_type):
    from apps.opspilot.models import BuildRecord, CheckItem, PageVersion
    from apps.opspilot.services.wiki.sweep_service import sweep_open_checks

    kb = _kb("sweep-recount")
    material = _material(kb)
    page = _page_with_evidence(kb, material, status="source_invalid")
    build = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="material_update",
        counts={"pending_review": 1},
    )
    candidate = PageVersion.objects.create(
        page=page,
        no=2,
        body="candidate",
        change_type="candidate",
        is_current=False,
        build_record=build,
    )
    check = CheckItem.objects.create(
        knowledge_base=kb,
        check_type=check_type,
        status="open",
        related={"pages": [page.id]},
        candidate_version=candidate,
    )

    assert sweep_open_checks(kb) == 1

    check.refresh_from_db()
    build.refresh_from_db()
    assert check.status == "auto_resolved"
    assert build.counts["pending_review"] == 0


@pytest.mark.parametrize("drift", ["schema", "participant"])
@pytest.mark.django_db
def test_sweep_auto_resolves_frozen_conflict_when_context_drifts(drift):
    from apps.opspilot.models import MaterialVersion, PageEvidence, WikiDecisionRule
    from apps.opspilot.services.wiki.check_service import create_candidate
    from apps.opspilot.services.wiki.sweep_service import sweep_open_checks

    kb = _kb(f"sweep-context-{drift}")
    source = _material(kb, "source")
    source_version = MaterialVersion.objects.create(material=source, content_hash="source-v1")
    source.current_version = source_version
    source.content_hash = "source-v1"
    source.save(update_fields=["current_version", "content_hash", "updated_at"])
    page = _page_with_evidence(kb, source)
    PageEvidence.objects.filter(page=page, material=source).update(material_version=source_version)
    incoming = _material(kb, "incoming")
    incoming_version = MaterialVersion.objects.create(material=incoming, content_hash="incoming-v1")
    incoming.current_version = incoming_version
    incoming.content_hash = "incoming-v1"
    incoming.save(update_fields=["current_version", "content_hash", "updated_at"])
    check = create_candidate(
        page,
        body="candidate",
        reason="conflict",
        check_type="cannot_merge",
        incoming_material=incoming,
        incoming_material_version=incoming_version,
    )
    current_version_id = page.current_version_id

    if drift == "schema":
        kb.schema_md = "# changed schema"
        kb.save(update_fields=["schema_md", "updated_at"])
    else:
        extra = _material(kb, "late-source")
        extra_version = MaterialVersion.objects.create(material=extra, content_hash="late-v1")
        extra.current_version = extra_version
        extra.content_hash = "late-v1"
        extra.save(update_fields=["current_version", "content_hash", "updated_at"])
        PageEvidence.objects.create(page=page, material=extra, material_version=extra_version)

    assert sweep_open_checks(kb) == 1

    check.refresh_from_db()
    page.refresh_from_db()
    assert check.status == "auto_resolved"
    assert check.suggested_actions == []
    assert check.related["resolution"]["action"] == "automatic_maintenance"
    assert check.related["resolution"]["reason"] == "premise_invalid"
    assert page.current_version_id == current_version_id
    assert not WikiDecisionRule.objects.filter(source_check=check).exists()


@pytest.mark.django_db
def test_sweep_auto_resolves_page_identity_when_schema_changes():
    from apps.opspilot.models import WikiDecisionRule
    from apps.opspilot.services.wiki.check_service import ensure_check
    from apps.opspilot.services.wiki.sweep_service import sweep_open_checks

    kb = _kb("sweep-page-identity-schema")
    material = _material(kb)
    left = _page_with_evidence(kb, material, title="CMDB")
    right = _page_with_evidence(kb, material, title="配置平台")
    check = ensure_check(
        kb,
        "duplicate",
        left,
        related={
            "pages": [left.id, right.id],
            "canonical_title": "配置平台",
        },
    )[0]
    kb.schema_md = "# changed schema"
    kb.save(update_fields=["schema_md", "updated_at"])

    assert sweep_open_checks(kb) == 1

    check.refresh_from_db()
    left.refresh_from_db()
    right.refresh_from_db()
    assert check.status == "auto_resolved"
    assert check.suggested_actions == []
    assert check.related["resolution"]["reason"] == "premise_invalid"
    assert left.status == "active"
    assert right.status == "active"
    assert not WikiDecisionRule.objects.filter(source_check=check).exists()


@pytest.mark.django_db
def test_sweep_keeps_unchanged_page_identity_context_open():
    from apps.opspilot.services.wiki.check_service import ensure_check
    from apps.opspilot.services.wiki.sweep_service import sweep_open_checks

    kb = _kb("sweep-page-identity-current")
    material = _material(kb)
    source = _page_with_evidence(kb, material, title="CMDB", body="source body")
    target = _page_with_evidence(kb, material, title="配置平台", body="target body")
    check = ensure_check(
        kb,
        "duplicate",
        source,
        related={"pages": [source.id, target.id], "canonical_title": "配置平台"},
    )[0]

    assert sweep_open_checks(kb) == 0
    check.refresh_from_db()
    assert check.status == "open"


@pytest.mark.parametrize(
    "drift",
    [
        "title",
        "page_type",
        "current_version",
        "body",
        "page_set",
        "evidence_set",
        "target_identity",
    ],
)
@pytest.mark.django_db
def test_sweep_auto_resolves_page_identity_when_frozen_context_drifts(drift):
    from apps.opspilot.models import PageVersion, WikiDecisionRule
    from apps.opspilot.services.wiki.check_service import ensure_check
    from apps.opspilot.services.wiki.sweep_service import sweep_open_checks

    kb = _kb(f"sweep-page-identity-{drift}")
    material = _material(kb)
    source = _page_with_evidence(kb, material, title="CMDB", body="source body")
    target = _page_with_evidence(kb, material, title="配置平台", body="target body")
    check = ensure_check(
        kb,
        "duplicate",
        source,
        related={
            "pages": [source.id, target.id],
            "canonical_title": "配置平台",
        },
    )[0]
    frozen_source_version_id = source.current_version_id
    frozen_target_version_id = target.current_version_id

    if drift == "title":
        source.title = "CMDB renamed"
        source.save(update_fields=["title", "updated_at"])
    elif drift == "page_type":
        source.page_type = "service"
        source.save(update_fields=["page_type", "updated_at"])
    elif drift == "current_version":
        source.current_version.is_current = False
        source.current_version.save(update_fields=["is_current", "updated_at"])
        replacement = PageVersion.objects.create(
            page=source,
            no=2,
            body="source body",
            change_type="human_edit",
            is_current=True,
        )
        source.current_version = replacement
        source.save(update_fields=["current_version", "updated_at"])
    elif drift == "body":
        source.current_version.body = "source body changed after freeze"
        source.current_version.save(update_fields=["body", "updated_at"])
    elif drift == "page_set":
        replacement = _page_with_evidence(kb, material, title="CMDB", body="source body")
        check.related = {**check.related, "pages": [replacement.id, target.id]}
        check.save(update_fields=["related", "updated_at"])
    elif drift == "evidence_set":
        from apps.opspilot.models import MaterialVersion, PageEvidence

        extra = _material(kb, "late-source")
        extra_version = MaterialVersion.objects.create(material=extra, content_hash="late-v1")
        extra.current_version = extra_version
        extra.content_hash = "late-v1"
        extra.save(update_fields=["current_version", "content_hash", "updated_at"])
        PageEvidence.objects.create(page=source, material=extra, material_version=extra_version)
    else:
        context = dict(check.decision_context)
        target_identity = dict(context["target_identity"])
        target_identity["page_id"] = source.id
        context["target_identity"] = target_identity
        check.decision_context = context
        check.save(update_fields=["decision_context", "updated_at"])

    assert sweep_open_checks(kb) == 1

    check.refresh_from_db()
    source.refresh_from_db()
    target.refresh_from_db()
    assert check.status == "auto_resolved"
    assert check.suggested_actions == []
    assert check.related["resolution"]["reason"] == "premise_invalid"
    assert source.status == "active"
    assert target.status == "active"
    if drift != "current_version":
        assert source.current_version_id == frozen_source_version_id
    assert target.current_version_id == frozen_target_version_id
    assert not WikiDecisionRule.objects.filter(source_check=check).exists()


@pytest.mark.django_db
def test_sweep_does_not_overwrite_a_check_processed_during_evaluation(monkeypatch):
    from apps.opspilot.models import CheckItem, PageVersion
    from apps.opspilot.services.wiki import sweep_service

    kb = _kb("sweep-concurrent-decision")
    material = _material(kb)
    page = _page_with_evidence(kb, material, status="source_invalid")
    candidate = PageVersion.objects.create(
        page=page,
        no=2,
        body="candidate",
        change_type="candidate",
        is_current=False,
    )
    check = CheckItem.objects.create(
        knowledge_base=kb,
        check_type="cannot_merge",
        status="open",
        related={"pages": [page.id]},
        candidate_version=candidate,
    )

    def resolve_while_evaluating(current_check):
        CheckItem.objects.filter(pk=current_check.pk).update(status="resolved")
        return True

    monkeypatch.setattr(sweep_service, "_should_auto_resolve", resolve_while_evaluating)

    assert sweep_service.sweep_open_checks(kb) == 0
    check.refresh_from_db()
    assert check.status == "resolved"


@pytest.mark.django_db
def test_drop_page_references_recounts_source_build_pending_review():
    from apps.opspilot.models import BuildRecord, CheckItem, PageVersion
    from apps.opspilot.services.wiki.sweep_service import drop_page_references

    kb = _kb("drop-recount")
    material = _material(kb)
    page = _page_with_evidence(kb, material)
    build = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="material_update",
        counts={"pending_review": 1},
        affected_pages=[page.id],
    )
    candidate = PageVersion.objects.create(
        page=page,
        no=2,
        body="candidate",
        change_type="candidate",
        is_current=False,
        build_record=build,
    )
    check = CheckItem.objects.create(
        knowledge_base=kb,
        check_type="material_update",
        status="open",
        related={"pages": [page.id]},
        candidate_version=candidate,
    )

    result = drop_page_references(kb, [page.id])

    check.refresh_from_db()
    build.refresh_from_db()
    assert result == {"checks": 1, "build_records": 1}
    assert check.status == "auto_resolved"
    assert build.counts["pending_review"] == 0
