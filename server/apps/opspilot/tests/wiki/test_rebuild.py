import json

import pytest


def _kb(schema="# schema"):
    from apps.opspilot.models import WikiKnowledgeBase

    return WikiKnowledgeBase.objects.create(name="kb", team=[1], schema_md=schema)


def _material(kb, name="m"):
    from apps.opspilot.models import Material

    return Material.objects.create(knowledge_base=kb, name=name, material_type="text", text_content="facts")


def _page(kb, title, contribution):
    from apps.opspilot.models import KnowledgePage, PageVersion

    page = KnowledgePage.objects.create(knowledge_base=kb, page_type="concept", title=title, contribution=contribution)
    v = PageVersion.objects.create(page=page, no=1, body="old", change_type="ai_create", is_current=True)
    page.current_version = v
    page.save(update_fields=["current_version"])
    return page


@pytest.mark.django_db
def test_rebuild_archives_ai_keeps_human_and_regenerates():
    from apps.opspilot.models import CheckItem, KnowledgePage
    from apps.opspilot.services.wiki.rebuild_service import rebuild_knowledge_base

    kb = _kb()
    mat = _material(kb)
    ai_page = _page(kb, "OldAI", "ai")
    human_page = _page(kb, "Human", "mixed")

    build = rebuild_knowledge_base(kb, generator=lambda m: [{"page_type": "concept", "title": f"New-{m.name}", "tags": [], "body": "fresh"}])

    ai_page.refresh_from_db()
    human_page.refresh_from_db()
    assert ai_page.status == "archived"  # 旧 AI 页归档
    assert human_page.status == "active"  # 人工页保留
    assert not CheckItem.objects.filter(knowledge_base=kb, check_type="schema_changed").exists()

    new_pages = KnowledgePage.objects.filter(knowledge_base=kb, update_method="rebuild", status="active")
    assert new_pages.count() == 1 and new_pages.first().title == f"New-{mat.name}"
    assert build.counts == {"new": 1, "archived": 1, "unchanged": 0, "pending_review": 0}


@pytest.mark.django_db
def test_rebuild_with_no_generated_pages():
    from apps.opspilot.services.wiki.rebuild_service import rebuild_knowledge_base

    kb = _kb()
    _material(kb)
    _page(kb, "AI", "ai")

    build = rebuild_knowledge_base(kb, generator=lambda m: [])
    assert build.counts["new"] == 0 and build.counts["archived"] == 1
    assert build.status == "success"


@pytest.mark.django_db
def test_rebuild_default_generator_extracts_facts_before_generating_pages(monkeypatch):
    from apps.opspilot.services.wiki import rebuild_service

    kb = _kb()
    _material(kb)
    seen = {}

    def fake_extract(text, llm_model_id):
        seen["extract_text"] = text
        seen["extract_model"] = llm_model_id
        return "EXTRACTED_FACTS"

    def fake_generate(kb_arg, source_text, llm_model_id):
        seen["generate_text"] = source_text
        seen["generate_model"] = llm_model_id
        return [{"page_type": "concept", "title": "FromFacts", "tags": [], "body": "body"}]

    monkeypatch.setattr(rebuild_service, "load_parsed_markdown", lambda material: "FULL_MARKDOWN")
    monkeypatch.setattr(rebuild_service, "_llm_extract_facts", fake_extract, raising=False)
    monkeypatch.setattr(rebuild_service, "_llm_generate_pages", fake_generate)

    build = rebuild_service.rebuild_knowledge_base(kb, llm_model_id=123)

    assert build.counts["new"] == 1
    assert seen == {
        "extract_text": "FULL_MARKDOWN",
        "extract_model": 123,
        "generate_text": "EXTRACTED_FACTS",
        "generate_model": 123,
    }


@pytest.mark.django_db
def test_rebuild_merges_same_title_generated_from_multiple_materials():
    from apps.opspilot.models import KnowledgePage, PageEvidence
    from apps.opspilot.services.wiki.rebuild_service import rebuild_knowledge_base

    kb = _kb()
    first = _material(kb, "first")
    second = _material(kb, "second")

    build = rebuild_knowledge_base(
        kb,
        generator=lambda material: [
            {
                "page_type": "entity",
                "title": "蓝鲸平台",
                "tags": [material.name],
                "body": f"{material.name} body",
            }
        ],
    )

    page = KnowledgePage.objects.get(knowledge_base=kb, title="蓝鲸平台", status="active")
    assert build.counts["new"] == 1
    assert KnowledgePage.objects.filter(knowledge_base=kb, title="蓝鲸平台", status="active").count() == 1
    assert "first body" in page.current_version.body
    assert "second body" in page.current_version.body
    assert PageEvidence.objects.filter(page=page, material__in=[first, second]).count() == 2


@pytest.mark.django_db
def test_rebuild_merges_abbreviation_and_full_name_generated_from_multiple_materials():
    from apps.opspilot.models import KnowledgePage, PageEvidence
    from apps.opspilot.services.wiki.rebuild_service import rebuild_knowledge_base

    kb = _kb()
    first = _material(kb, "first")
    second = _material(kb, "second")

    def generator(material):
        title = "CMDB" if material == first else "配置平台"
        return [
            {
                "page_type": "entity",
                "title": title,
                "tags": [material.name],
                "body": f"{title} {material.name} body",
            }
        ]

    build = rebuild_knowledge_base(kb, generator=generator)

    page = KnowledgePage.objects.get(knowledge_base=kb, title="配置平台", status="active")
    assert build.counts["new"] == 1
    assert KnowledgePage.objects.filter(knowledge_base=kb, status="active").count() == 1
    assert not KnowledgePage.objects.filter(knowledge_base=kb, title="CMDB", status="active").exists()
    assert "CMDB first body" in page.current_version.body
    assert "配置平台 second body" in page.current_version.body
    assert PageEvidence.objects.filter(page=page, material__in=[first, second]).count() == 2


@pytest.mark.django_db
def test_rebuild_records_source_chunk_locator_for_generated_page():
    from apps.opspilot.models import PageEvidence
    from apps.opspilot.services.wiki.rebuild_service import rebuild_knowledge_base

    kb = _kb()
    marker = "REBUILD_TAIL_COMPONENT"
    material = _material(kb)
    material.text_content = ("head content\n" * 1200) + f"\n{marker} 是全量重建尾部事实。"
    material.save(update_fields=["text_content"])

    rebuild_knowledge_base(
        kb,
        generator=lambda m: [
            {
                "page_type": "entity",
                "title": "尾部组件",
                "tags": [],
                "body": f"{marker} 需要保留片段级来源。",
            }
        ],
    )

    evidence = PageEvidence.objects.get(material=material)
    locator = json.loads(evidence.locator)
    assert locator["kind"] == "material_chunk"
    assert locator["chunk_index"] > 0
    assert locator["chunk_count"] > 1
    assert marker in locator["snippet"]


@pytest.mark.django_db
def test_rebuild_traces_pending_review_and_skips_titleless_page_data():
    from apps.opspilot.models import CheckItem, KnowledgePage
    from apps.opspilot.services.wiki.rebuild_service import rebuild_knowledge_base

    kb = _kb()
    _page(kb, "人工页面", "mixed")
    _material(kb, "first")
    _material(kb, "second")

    build = rebuild_knowledge_base(
        kb,
        generator=lambda m: [
            {"page_type": "concept", "title": "", "tags": [], "body": "missing title"},
            {"page_type": "concept", "title": "人工页面", "tags": [], "body": f"{m.name} candidate"},
        ],
    )

    actions = [action["action"] for material_trace in build.inputs["source_trace"]["materials"] for action in material_trace["page_actions"]]
    assert actions == ["pending_review", "pending_review"]
    assert KnowledgePage.objects.filter(knowledge_base=kb, title="", status="active").count() == 0
    checks = CheckItem.objects.filter(
        knowledge_base=kb,
        check_type="cannot_merge",
        status="open",
    )
    assert checks.count() == 2
    assert all(check.candidate_version_id for check in checks)
    assert build.counts["pending_review"] == 2


@pytest.mark.django_db
class TestRebuildView:
    def test_rebuild_endpoint_enqueues_task_and_returns_running_record(self, api_client, monkeypatch):
        from apps.opspilot import tasks
        from apps.opspilot.models import BuildRecord

        kb = _kb()
        calls = []

        class Task:
            @staticmethod
            def delay(kb_id, llm_model_id, operator, build_record_id):
                calls.append((kb_id, llm_model_id, operator, build_record_id))

        monkeypatch.setattr(tasks, "wiki_rebuild_kb_task", Task)

        r = api_client.post(f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{kb.id}/rebuild/", {}, format="json")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["trigger"] == "rebuild"
        assert data["status"] == "running"
        assert data["stage"] == "queued"
        assert BuildRecord.objects.filter(id=data["id"], knowledge_base=kb, status="running").exists()
        assert calls == [(kb.id, kb.llm_model_id, data["operator"], data["id"])]

    def test_rebuild_endpoint_rejects_when_build_running(self, api_client, monkeypatch):
        from apps.opspilot import tasks
        from apps.opspilot.models import BuildRecord

        kb = _kb()
        BuildRecord.objects.create(knowledge_base=kb, trigger="rebuild", status="running", stage="generating")

        class Task:
            @staticmethod
            def delay(*args, **kwargs):
                pytest.fail("running rebuild should not enqueue another task")

        monkeypatch.setattr(tasks, "wiki_rebuild_kb_task", Task)

        r = api_client.post(f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{kb.id}/rebuild/", {}, format="json")
        assert r.status_code == 400
        assert "运行中" in r.json()["message"]
        assert BuildRecord.objects.filter(knowledge_base=kb, status="running").count() == 1

    def test_delete_endpoint_rejects_when_build_running(self, api_client):
        from apps.opspilot.models import BuildRecord, WikiKnowledgeBase

        kb = _kb()
        BuildRecord.objects.create(knowledge_base=kb, trigger="rebuild", status="running", stage="generating")

        r = api_client.delete(f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{kb.id}/")
        assert r.status_code == 400
        assert "运行中" in r.json()["message"]
        assert WikiKnowledgeBase.objects.filter(id=kb.id).exists()

    def test_build_record_list_can_filter_running_status(self, api_client):
        from apps.opspilot.models import BuildRecord

        kb = _kb()
        BuildRecord.objects.create(knowledge_base=kb, trigger="rebuild", status="running", stage="generating")
        BuildRecord.objects.create(knowledge_base=kb, trigger="rebuild", status="success", stage="done")

        r = api_client.get(f"/api/v1/opspilot/wiki_mgmt/build_record/?knowledge_base={kb.id}&status=running&page_size=1")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["count"] == 1
        assert data["items"][0]["status"] == "running"


def _versioned_rebuild_material(kb, name, content_hash):
    from apps.opspilot.models import MaterialVersion

    material = _material(kb, name)
    material.text_content = f"source-{name}"
    material.content_hash = content_hash
    version = MaterialVersion.objects.create(material=material, content_hash=content_hash)
    material.current_version = version
    material.save(update_fields=["text_content", "content_hash", "current_version", "updated_at"])
    return material, version


@pytest.mark.django_db
def test_rebuild_conflict_has_real_candidate_and_full_context_without_schema_check():
    from apps.opspilot.models import CheckItem, PageEvidence
    from apps.opspilot.services.wiki.rebuild_service import rebuild_knowledge_base

    kb = _kb()
    material_a, version_a = _versioned_rebuild_material(kb, "A", "hash-a")
    material_b, version_b = _versioned_rebuild_material(kb, "B", "hash-b")
    page = _page(kb, "共享知识", "mixed")
    PageEvidence.objects.create(
        page=page,
        material=material_a,
        material_version=version_a,
    )

    build = rebuild_knowledge_base(
        kb,
        generator=lambda material: (
            []
            if material.id == material_a.id
            else [
                {
                    "page_type": "concept",
                    "title": "共享知识",
                    "tags": [],
                    "body": "candidate from B",
                }
            ]
        ),
    )

    assert not CheckItem.objects.filter(
        knowledge_base=kb,
        check_type="schema_changed",
    ).exists()
    check = CheckItem.objects.get(
        knowledge_base=kb,
        check_type="cannot_merge",
        status="open",
    )
    assert check.candidate_version is not None
    assert check.candidate_version.body == "candidate from B"
    assert {(item["material_id"], item["content_hash"]) for item in check.decision_context["participants"]} == {
        (material_a.id, version_a.content_hash),
        (material_b.id, version_b.content_hash),
    }
    assert check.decision_context["incoming"]["material_version_id"] == version_b.id
    assert build.counts["pending_review"] == 1


@pytest.mark.django_db
def test_rebuild_replays_prior_conflict_and_preserves_decision_trace(monkeypatch):
    from apps.opspilot.models import CheckItem, PageEvidence, PageVersion
    from apps.opspilot.services.wiki import build_service
    from apps.opspilot.services.wiki.check_service import decide_check
    from apps.opspilot.services.wiki.rebuild_service import rebuild_knowledge_base

    kb = _kb()
    material_a, version_a = _versioned_rebuild_material(kb, "A", "hash-a")
    material_b, _version_b = _versioned_rebuild_material(kb, "B", "hash-b")
    page = _page(kb, "共享知识", "human")
    page.current_version.body = "knowledge-a"
    page.current_version.save(update_fields=["body", "updated_at"])
    PageEvidence.objects.create(
        page=page,
        material=material_a,
        material_version=version_a,
    )

    monkeypatch.setattr(
        build_service,
        "_llm_extract_facts",
        lambda text, llm_model_id: text,
    )
    monkeypatch.setattr(
        build_service,
        "_llm_generate_pages",
        lambda kb, source_text, llm_model_id: [
            {
                "page_type": "concept",
                "title": "共享知识",
                "tags": [],
                "body": "knowledge-b",
            }
        ],
    )
    build_service.build_from_material(material_b, llm_model_id=1)
    check = CheckItem.objects.get(
        knowledge_base=kb,
        check_type="cannot_merge",
        status="open",
    )
    rule = decide_check(check, "use_new", operator="admin")
    version_count = PageVersion.objects.filter(page=page).count()

    rebuild = rebuild_knowledge_base(
        kb,
        generator=lambda material: [
            {
                "page_type": "concept",
                "title": "共享知识",
                "tags": [],
                "body": "knowledge-a" if material.id == material_a.id else "knowledge-b",
            }
        ],
    )

    assert not CheckItem.objects.filter(knowledge_base=kb, status="open").exists()
    assert not CheckItem.objects.filter(
        knowledge_base=kb,
        check_type="schema_changed",
    ).exists()
    assert PageVersion.objects.filter(page=page).count() == version_count
    assert rebuild.counts["pending_review"] == 0
    assert rebuild.counts["unchanged"] == 2
    actions = [action for material_trace in rebuild.inputs["source_trace"]["materials"] for action in material_trace["page_actions"]]
    reused = [action for action in actions if action.get("decision_reused")]
    assert len(reused) == 1
    assert reused[0]["rule_id"] == rule.id
    assert reused[0]["action"] == "use_new"


@pytest.mark.django_db
def test_rebuild_archived_pages_clear_relations_and_vectors():
    from django.db.models import Q

    from apps.opspilot.models import PageChunk, PageRelation
    from apps.opspilot.services.wiki.rebuild_service import rebuild_knowledge_base

    kb = _kb()
    _material(kb, "source")
    archived_page = _page(kb, "OldAI", "ai")
    active_page = _page(kb, "Human", "human")
    archived_version = archived_page.current_version
    archived_version.embedding = [0.1, 0.2]
    archived_version.save(update_fields=["embedding", "updated_at"])
    chunk = PageChunk.objects.create(
        page=archived_page,
        version=archived_version,
        idx=0,
        text="old chunk",
        embedding=[0.3, 0.4],
    )
    PageRelation.objects.create(
        from_page=archived_page,
        to_page=active_page,
        relation_type="reference",
    )

    build = rebuild_knowledge_base(
        kb,
        generator=lambda current_material: [
            {
                "page_type": "concept",
                "title": f"New-{current_material.name}",
                "tags": [],
                "body": "fresh",
            }
        ],
    )

    archived_page.refresh_from_db()
    archived_version.refresh_from_db()
    chunk.refresh_from_db()
    assert archived_page.status == "archived"
    assert not PageRelation.objects.filter(Q(from_page=archived_page) | Q(to_page=archived_page)).exists()
    assert archived_version.embedding == []
    assert chunk.embedding == []
    assert build.maintenance["archive"]["event"] == "page_delete"
    assert build.maintenance["archive"]["affected_page_ids"] == [archived_page.id]


@pytest.mark.django_db
def test_rebuild_keeps_page_identity_rule_for_new_page_ids_and_future_scan(monkeypatch):
    from apps.opspilot.models import CheckItem, WikiDecisionRule
    from apps.opspilot.services.wiki import rebuild_service
    from apps.opspilot.services.wiki.check_service import decide_check, ensure_check, scan_health

    kb = _kb()
    kb.generation_rules = {
        "title_aliases": [
            {
                "canonical": "配置平台",
                "aliases": ["CMDB"],
            }
        ]
    }
    kb.save(update_fields=["generation_rules", "updated_at"])
    _material(kb, "source")
    original_target = _page(kb, "配置平台", "ai")
    original_source = _page(kb, "CMDB", "ai")
    original_check = ensure_check(
        kb,
        "duplicate",
        original_source,
        related={
            "pages": [original_source.id, original_target.id],
            "canonical_title": "配置平台",
        },
    )[0]
    rule = decide_check(original_check, "keep_separate", operator="admin")
    monkeypatch.setattr(
        rebuild_service,
        "cascade",
        lambda knowledge_base, page_ids, event, **kwargs: {
            "status": "success",
            "event": event,
            "affected_page_ids": list(page_ids),
            "stages": {},
        },
    )

    build = rebuild_service.rebuild_knowledge_base(
        kb,
        operator="admin",
        generator=lambda material: [],
    )

    original_target.refresh_from_db()
    original_source.refresh_from_db()
    rule.refresh_from_db()
    assert original_target.status == "archived"
    assert original_source.status == "archived"
    assert rule.status == WikiDecisionRule.STATUS_ACTIVE
    assert "rules_revoked" not in build.inputs

    fresh_target = _page(kb, "配置平台", "ai")
    fresh_source = _page(kb, "CMDB", "ai")
    assert {fresh_target.id, fresh_source.id}.isdisjoint({original_target.id, original_source.id})

    scan_health(kb)

    rule.refresh_from_db()
    assert rule.status == WikiDecisionRule.STATUS_ACTIVE
    assert rule.replay_count == 1
    open_identity_checks = CheckItem.objects.filter(
        knowledge_base=kb,
        check_type__in=["duplicate", "conflict"],
        status="open",
    )
    assert not any(fresh_target.id in (check.related or {}).get("pages", []) for check in open_identity_checks)


@pytest.mark.django_db
def test_rebuild_unchanged_adds_frozen_evidence_with_locator_idempotently():
    import json

    from apps.opspilot.models import CheckItem, PageEvidence
    from apps.opspilot.services.wiki.rebuild_service import rebuild_knowledge_base

    kb = _kb()
    material_a, version_a = _versioned_rebuild_material(kb, "A", "hash-a")
    material_b, version_b = _versioned_rebuild_material(kb, "B", "hash-b")
    page = _page(kb, "SharedSame", "mixed")
    page.current_version.body = "same body"
    page.current_version.save(update_fields=["body", "updated_at"])
    PageEvidence.objects.create(
        page=page,
        material=material_a,
        material_version=version_a,
    )

    def generator(material):
        if material.id == material_a.id:
            return []
        return [
            {
                "page_type": "concept",
                "title": "SharedSame",
                "tags": [],
                "body": "same body",
            }
        ]

    first = rebuild_knowledge_base(kb, generator=generator)

    evidence = PageEvidence.objects.get(page=page, material=material_b)
    locator = json.loads(evidence.locator)
    assert first.counts["unchanged"] == 1
    assert first.counts["pending_review"] == 0
    assert evidence.material_version_id == version_b.id
    assert locator["material_version_id"] == version_b.id
    assert locator["kind"] == "material_chunk"
    assert not CheckItem.objects.filter(knowledge_base=kb).exists()

    second = rebuild_knowledge_base(kb, generator=generator)

    evidence.refresh_from_db()
    assert second.counts["unchanged"] == 1
    assert PageEvidence.objects.filter(page=page, material=material_b).count() == 1
    assert evidence.material_version_id == version_b.id
    assert json.loads(evidence.locator) == locator


@pytest.mark.django_db
def test_rebuild_generator_failure_keeps_old_pages_and_persists_failed_record():
    from apps.opspilot.models import BuildRecord, KnowledgePage
    from apps.opspilot.services.wiki.rebuild_service import rebuild_knowledge_base

    kb = _kb()
    _material(kb, "first")
    _material(kb, "second")
    old_page = _page(kb, "OldAI", "ai")
    generated_for = []

    def generator(material):
        generated_for.append(material.name)
        if material.name == "second":
            raise RuntimeError("generation exploded")
        return [
            {
                "page_type": "concept",
                "title": "MustNotApply",
                "tags": [],
                "body": "candidate",
            }
        ]

    with pytest.raises(RuntimeError, match="generation exploded"):
        rebuild_knowledge_base(kb, generator=generator)

    old_page.refresh_from_db()
    build = BuildRecord.objects.get(knowledge_base=kb, trigger="rebuild")
    assert generated_for == ["first", "second"]
    assert old_page.status == "active"
    assert not KnowledgePage.objects.filter(
        knowledge_base=kb,
        title="MustNotApply",
    ).exists()
    assert build.status == "failed"
    assert build.stage == "failed"
    assert build.errors == ["generation exploded"]


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [
        pytest.param("delete", "资料已被删除", id="deleted"),
        pytest.param("add", "资料集合已变化", id="added"),
        pytest.param("change", "资料内容已变化", id="content-changed"),
        pytest.param("version", "资料版本已变化", id="version-changed"),
        pytest.param("schema", "Schema 已变化", id="schema-changed"),
    ],
)
@pytest.mark.django_db
def test_rebuild_aborts_safely_when_context_changes_after_prepare(
    monkeypatch,
    mutation,
    expected_error,
):
    from apps.opspilot.models import BuildRecord, KnowledgePage, Material, MaterialVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki import rebuild_service

    kb = _kb()
    material = _material(kb, "source")
    if mutation == "version":
        current_version = MaterialVersion.objects.create(
            material=material,
            content_hash="same-hash",
        )
        material.content_hash = "same-hash"
        material.current_version = current_version
        material.save(
            update_fields=[
                "content_hash",
                "current_version",
                "updated_at",
            ]
        )
    old_page = _page(kb, "OldAI", "ai")
    apply_prepared = rebuild_service._apply_prepared_rebuild

    def mutate_material_then_apply(*args, **kwargs):
        live_material = Material.objects.get(pk=material.pk)
        if mutation == "delete":
            live_material.delete()
        elif mutation == "add":
            _material(kb, "added-after-prepare")
        elif mutation == "version":
            replacement = MaterialVersion.objects.create(
                material=live_material,
                content_hash="same-hash",
            )
            live_material.current_version = replacement
            live_material.save(update_fields=["current_version", "updated_at"])
        elif mutation == "schema":
            WikiKnowledgeBase.objects.filter(pk=kb.pk).update(schema_md="# changed schema")
        else:
            live_material.text_content = "changed after prepare"
            live_material.save(update_fields=["text_content", "updated_at"])
        return apply_prepared(*args, **kwargs)

    monkeypatch.setattr(
        rebuild_service,
        "_apply_prepared_rebuild",
        mutate_material_then_apply,
    )

    with pytest.raises(RuntimeError, match=expected_error):
        rebuild_service.rebuild_knowledge_base(
            kb,
            generator=lambda current_material: [
                {
                    "page_type": "concept",
                    "title": "MustNotApply",
                    "tags": [],
                    "body": "candidate",
                }
            ],
        )

    old_page.refresh_from_db()
    build = BuildRecord.objects.get(knowledge_base=kb, trigger="rebuild")
    assert old_page.status == "active"
    assert not KnowledgePage.objects.filter(
        knowledge_base=kb,
        title="MustNotApply",
    ).exists()
    assert build.status == "failed"
    assert build.stage == "failed"
    assert expected_error in build.errors[0]


@pytest.mark.django_db
def test_rebuild_core_apply_failure_rolls_back_all_page_changes_but_keeps_failed_record(
    monkeypatch,
):
    from apps.opspilot.models import BuildRecord, KnowledgePage
    from apps.opspilot.services.wiki import rebuild_service

    kb = _kb()
    _material(kb, "source")
    old_page = _page(kb, "OldAI", "ai")
    create_page = rebuild_service._create_ai_page

    def fail_after_create(*args, **kwargs):
        create_page(*args, **kwargs)
        raise RuntimeError("core apply exploded")

    monkeypatch.setattr(rebuild_service, "_create_ai_page", fail_after_create)
    monkeypatch.setattr(
        rebuild_service,
        "cascade",
        lambda *args, **kwargs: pytest.fail("core apply failure must not cascade"),
    )

    with pytest.raises(RuntimeError, match="core apply exploded"):
        rebuild_service.rebuild_knowledge_base(
            kb,
            generator=lambda material: [
                {
                    "page_type": "concept",
                    "title": "RolledBack",
                    "tags": [],
                    "body": "candidate",
                }
            ],
        )

    old_page.refresh_from_db()
    build = BuildRecord.objects.get(knowledge_base=kb, trigger="rebuild")
    assert old_page.status == "active"
    assert not KnowledgePage.objects.filter(
        knowledge_base=kb,
        title="RolledBack",
    ).exists()
    assert build.status == "failed"
    assert build.stage == "failed"
    assert build.errors == ["core apply exploded"]


@pytest.mark.django_db
def test_rebuild_cascade_exception_keeps_core_commit_and_records_retryable_partial(
    monkeypatch,
):
    from apps.opspilot.models import KnowledgePage
    from apps.opspilot.services.wiki import rebuild_service

    kb = _kb()
    _material(kb, "source")
    old_page = _page(kb, "OldAI", "ai")
    monkeypatch.setattr(rebuild_service, "enrich_pages_wikilinks", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        rebuild_service,
        "cascade",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("cascade exploded")),
    )

    build = rebuild_service.rebuild_knowledge_base(
        kb,
        generator=lambda material: [
            {
                "page_type": "concept",
                "title": "Committed",
                "tags": [],
                "body": "fresh",
            }
        ],
    )

    old_page.refresh_from_db()
    generated = KnowledgePage.objects.get(knowledge_base=kb, title="Committed")
    build.refresh_from_db()
    assert old_page.status == "archived"
    assert generated.status == "active"
    assert build.status == "partial"
    assert build.stage == "done"
    assert set(build.affected_pages) == {old_page.id, generated.id}
    assert build.maintenance["archive"]["affected_page_ids"] == [old_page.id]
    assert build.maintenance["generated"]["affected_page_ids"] == [generated.id]
    assert build.maintenance["archive"]["stages"]["cascade"]["status"] == "failed"
    assert build.maintenance["generated"]["stages"]["cascade"]["status"] == "failed"
    assert build.errors == ["cascade exploded"]


@pytest.mark.django_db
def test_rebuild_enrichment_exception_is_partial_after_core_commit(monkeypatch):
    from apps.opspilot.models import KnowledgePage
    from apps.opspilot.services.wiki import rebuild_service

    kb = _kb()
    _material(kb, "source")
    monkeypatch.setattr(
        rebuild_service,
        "enrich_pages_wikilinks",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("enrichment exploded")),
    )
    monkeypatch.setattr(
        rebuild_service,
        "cascade",
        lambda knowledge_base, page_ids, event, **kwargs: {
            "status": "success",
            "event": event,
            "affected_page_ids": list(page_ids),
            "stages": {},
        },
    )

    build = rebuild_service.rebuild_knowledge_base(
        kb,
        generator=lambda material: [
            {
                "page_type": "concept",
                "title": "Committed",
                "tags": [],
                "body": "fresh",
            }
        ],
    )

    generated = KnowledgePage.objects.get(knowledge_base=kb, title="Committed")
    build.refresh_from_db()
    assert generated.status == "active"
    assert build.status == "partial"
    assert build.stage == "done"
    assert build.maintenance["affected_page_ids"] == [generated.id]
    assert build.maintenance["stages"]["wikilink_enrichment"] == {
        "status": "failed",
        "error": "enrichment exploded",
    }
    assert build.errors == ["enrichment exploded"]
