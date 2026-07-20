import pytest


def _page_with_current(kb, title="T", body="v1", page_type="concept"):
    from apps.opspilot.services.wiki.page_service import create_manual_page

    return create_manual_page(kb, page_type=page_type, title=title, body=body, created_by="u")


@pytest.mark.django_db
def test_candidate_does_not_pollute_current_then_accept():
    from apps.opspilot.models import WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import accept_candidate, create_candidate

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    page = _page_with_current(kb, body="current")
    check = create_candidate(page, body="candidate", reason="conflict", check_type="cannot_merge", created_by="ai")

    page.refresh_from_db()
    assert page.current_version.body == "current"  # 当前有效版本未被污染
    assert check.candidate_version.is_current is False
    assert check.status == "open"

    accept_candidate(check, operator="u")
    page.refresh_from_db()
    check.refresh_from_db()
    assert page.current_version.body == "candidate"
    assert check.status == "resolved"


@pytest.mark.django_db
def test_reject_candidate_keeps_current():
    from apps.opspilot.models import PageVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import create_candidate, reject_candidate

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    page = _page_with_current(kb, body="current")
    check = create_candidate(page, body="candidate", reason="conflict", check_type="cannot_merge")
    cand_id = check.candidate_version_id

    reject_candidate(check, operator="u")
    page.refresh_from_db()
    check.refresh_from_db()
    assert page.current_version.body == "current"
    assert check.status == "dismissed"
    assert not PageVersion.objects.filter(id=cand_id).exists()


@pytest.mark.django_db
def test_create_candidate_rejects_non_decision_type_without_side_effects():
    from apps.opspilot.models import CheckItem, PageVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import create_candidate

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    page = _page_with_current(kb, body="current")
    version_ids = set(PageVersion.objects.filter(page=page).values_list("id", flat=True))

    with pytest.raises(ValueError, match="knowledge conflict or page identity"):
        create_candidate(
            page,
            body="candidate",
            reason="legacy admission",
            check_type="qa_answer_candidate",
        )

    page.refresh_from_db()
    assert page.current_version.body == "current"
    assert set(PageVersion.objects.filter(page=page).values_list("id", flat=True)) == version_ids
    assert not CheckItem.objects.filter(knowledge_base=kb).exists()


@pytest.mark.django_db
def test_database_rejects_open_non_decision_checks():
    from django.db import IntegrityError, transaction

    from apps.opspilot.models import CheckItem, WikiKnowledgeBase

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            CheckItem.objects.create(
                knowledge_base=kb,
                check_type="orphan",
                status="open",
            )

    diagnostic = CheckItem.objects.create(
        knowledge_base=kb,
        check_type="orphan",
        status="auto_resolved",
    )
    assert diagnostic.status == "auto_resolved"


@pytest.mark.django_db
def test_scan_health_flags_orphan_and_is_idempotent():
    from apps.opspilot.models import CheckItem, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import scan_health

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    _page_with_current(kb)  # 人工页面,无关系无证据 -> orphan
    created = scan_health(kb)
    assert len(created) == 1
    assert created[0].check_type == "orphan"
    assert created[0].status == "auto_resolved"
    assert created[0].suggested_actions == []
    assert created[0].related["resolution"]["action"] == "automatic_maintenance"
    assert created[0].related["resolution"]["processed_at"]
    # 幂等:再次扫描不重复创建
    again = scan_health(kb)
    assert again == []
    assert CheckItem.objects.filter(knowledge_base=kb, check_type="orphan").count() == 1


@pytest.mark.django_db
def test_scan_health_flags_alias_title_duplicates():
    from apps.opspilot.models import CheckItem, Material, PageEvidence, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import scan_health

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    material = Material.objects.create(knowledge_base=kb, name="source", material_type="text", status="done")
    cmdb = _page_with_current(kb, title="CMDB", body="CMDB platform content that is long enough")
    config = _page_with_current(kb, title="配置平台", body="配置平台内容足够长,用于避免低置信度")
    PageEvidence.objects.create(page=cmdb, material=material)
    PageEvidence.objects.create(page=config, material=material)

    created = scan_health(kb)

    assert len(created) == 1
    check = created[0]
    assert check.check_type == "duplicate"
    assert check.related["canonical_title"] == "配置平台"
    assert set(check.related["pages"]) == {cmdb.id, config.id}
    assert scan_health(kb) == []
    assert CheckItem.objects.filter(knowledge_base=kb, check_type="duplicate").count() == 1


@pytest.mark.django_db
def test_scan_health_flags_alias_title_conflicts_when_types_differ():
    from apps.opspilot.models import CheckItem, Material, PageEvidence, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import scan_health

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    material = Material.objects.create(knowledge_base=kb, name="source", material_type="text", status="done")
    cmdb = _page_with_current(kb, title="CMDB", body="CMDB content enough", page_type="entity")
    config = _page_with_current(kb, title="配置平台", body="配置平台内容足够长", page_type="concept")
    PageEvidence.objects.create(page=cmdb, material=material)
    PageEvidence.objects.create(page=config, material=material)

    created = scan_health(kb)

    assert len(created) == 1
    assert created[0].check_type == "conflict"
    assert created[0].related["canonical_title"] == "配置平台"
    assert set(created[0].related["pages"]) == {cmdb.id, config.id}
    assert CheckItem.objects.filter(knowledge_base=kb, check_type="conflict").count() == 1


@pytest.mark.django_db
def test_merge_duplicate_check_archives_source_and_moves_evidence_relations_chunks(django_capture_on_commit_callbacks):
    from apps.opspilot.models import Material, PageChunk, PageEvidence, PageRelation, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import ensure_check, merge_duplicate_check
    from apps.opspilot.services.wiki.relation_service import rebuild_relations

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    material = Material.objects.create(knowledge_base=kb, name="source", material_type="text", status="done")
    duplicate = _page_with_current(kb, title="CMDB", body="CMDB stores configuration data.", page_type="entity")
    canonical = _page_with_current(kb, title="配置平台", body="配置平台负责配置数据管理。", page_type="entity")
    consumer = _page_with_current(kb, title="业务系统", body="依赖 [[CMDB]] 提供配置数据。", page_type="entity")
    PageEvidence.objects.create(page=duplicate, material=material)
    PageChunk.objects.create(page=duplicate, version=duplicate.current_version, idx=0, text="old chunk", embedding=[0.5])
    rebuild_relations(kb)
    assert PageRelation.objects.filter(from_page=consumer, to_page=duplicate, relation_type="reference").exists()
    check = ensure_check(
        kb,
        "duplicate",
        duplicate,
        related={"pages": [duplicate.id, canonical.id], "canonical_title": "配置平台"},
    )[0]

    with django_capture_on_commit_callbacks(execute=True):
        result = merge_duplicate_check(check, operator="reviewer")

    duplicate.refresh_from_db()
    canonical.refresh_from_db()
    check.refresh_from_db()
    assert result["target_page_id"] == canonical.id
    assert result["archived_page_ids"] == [duplicate.id]
    assert duplicate.status == "archived"
    assert canonical.status == "active"
    assert canonical.current_version.change_type == "merge_duplicate"
    assert "CMDB stores configuration data." in canonical.current_version.body
    assert PageEvidence.objects.filter(page=canonical, material=material).exists()
    assert not PageEvidence.objects.filter(page=duplicate).exists()
    assert PageRelation.objects.filter(from_page=consumer, to_page=canonical, relation_type="reference").exists()
    assert not PageRelation.objects.filter(to_page=duplicate).exists()
    assert list(PageChunk.objects.filter(page=duplicate).values_list("embedding", flat=True)) == [[]]
    assert check.status == "resolved"


@pytest.mark.django_db
def test_merge_duplicate_check_rejects_conflict_checks():
    from apps.opspilot.models import CheckItem, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import merge_duplicate_check

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    left = _page_with_current(kb, title="CMDB", body="CMDB content", page_type="entity")
    right = _page_with_current(kb, title="配置平台", body="配置平台内容", page_type="concept")
    check = CheckItem.objects.create(
        knowledge_base=kb,
        check_type="conflict",
        status="open",
        related={"pages": [left.id, right.id], "canonical_title": "配置平台"},
    )

    with pytest.raises(ValueError, match="duplicate"):
        merge_duplicate_check(check, operator="reviewer")


@pytest.mark.django_db
def test_merge_duplicate_check_handles_messy_related_and_existing_evidence():
    from apps.opspilot.models import Material, PageEvidence, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import ensure_check, merge_duplicate_check

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    material = Material.objects.create(knowledge_base=kb, name="source", material_type="text", status="done")
    target = _page_with_current(kb, title="CMDB", body="same body", page_type="entity")
    source = _page_with_current(kb, title="配置平台", body="same body", page_type="entity")
    PageEvidence.objects.create(page=target, material=material)
    PageEvidence.objects.create(page=source, material=material)
    check = ensure_check(
        kb,
        "duplicate",
        target,
        related={"pages": ["bad", target.id, target.id, source.id], "canonical_title": "规范配置平台"},
    )[0]
    assert check.related["pages"] == [target.id, source.id]

    result = merge_duplicate_check(check, operator="reviewer")

    target.refresh_from_db()
    source.refresh_from_db()
    assert result["target_page_id"] == target.id
    assert target.title == "规范配置平台"
    assert source.status == "archived"
    assert PageEvidence.objects.filter(page=target, material=material).count() == 1
    assert not PageEvidence.objects.filter(page=source).exists()


@pytest.mark.django_db
def test_merge_duplicate_check_rejects_non_open_or_inactive_related_pages():
    from apps.opspilot.models import CheckItem, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import ensure_check, merge_duplicate_check

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    target = _page_with_current(kb, title="CMDB", body="CMDB content", page_type="entity")
    source = _page_with_current(kb, title="配置平台", body="配置平台内容", page_type="entity")
    resolved = CheckItem.objects.create(
        knowledge_base=kb,
        check_type="duplicate",
        status="resolved",
        related={"pages": [target.id, source.id]},
    )
    inactive = ensure_check(
        kb,
        "duplicate",
        target,
        related={"pages": [target.id, source.id]},
    )[0]
    source.status = "archived"
    source.save(update_fields=["status"])

    with pytest.raises(ValueError, match="open"):
        merge_duplicate_check(resolved, operator="reviewer")
    assert merge_duplicate_check(inactive, operator="reviewer") is None
    inactive.refresh_from_db()
    assert inactive.status == "auto_resolved"


@pytest.mark.django_db
def test_scan_health_flags_source_stale_confidence_same_title_and_broken_relation():
    from apps.opspilot.models import CheckItem, Material, PageEvidence, PageRelation, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import scan_health

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    done = Material.objects.create(knowledge_base=kb, name="done", material_type="text", status="done")
    failed = Material.objects.create(knowledge_base=kb, name="failed", material_type="text", status="failed")
    updated = Material.objects.create(knowledge_base=kb, name="updated", material_type="text", status="updated")
    anchor = _page_with_current(kb, title="Anchor", body="anchor body long enough")
    no_source = _page_with_current(kb, title="No Source", body="body long enough to avoid low confidence")
    invalid_source = _page_with_current(kb, title="Invalid Source", body="body long enough")
    stale = _page_with_current(kb, title="Stale", body="body long enough")
    low_confidence = _page_with_current(kb, title="Low", body="short")
    duplicate_a = _page_with_current(kb, title="Same", body="same a")
    duplicate_b = _page_with_current(kb, title="Same", body="same b")
    archived_target = _page_with_current(kb, title="Archived", body="archived")
    for page in [no_source, low_confidence, duplicate_a, duplicate_b]:
        page.contribution = "ai"
        page.save(update_fields=["contribution"])
    archived_target.status = "archived"
    archived_target.save(update_fields=["status"])
    PageRelation.objects.create(from_page=no_source, to_page=anchor, relation_type="reference")
    PageEvidence.objects.create(page=invalid_source, material=failed)
    PageEvidence.objects.create(page=stale, material=updated)
    PageEvidence.objects.create(page=low_confidence, material=done)
    PageRelation.objects.create(from_page=anchor, to_page=archived_target, relation_type="reference")

    created = scan_health(kb)

    created_types = [check.check_type for check in created]
    assert "no_source" in created_types
    assert "all_sources_invalid" in created_types
    assert "stale" in created_types
    assert "low_confidence" in created_types
    assert "duplicate" in created_types
    assert "broken_relation" in created_types
    assert CheckItem.objects.filter(knowledge_base=kb, check_type="duplicate", related__pages__contains=[duplicate_a.id]).exists()


@pytest.mark.django_db
def test_scan_health_converts_graph_bridge_nodes_to_checks():
    from apps.opspilot.models import CheckItem, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import scan_health
    from apps.opspilot.services.wiki.relation_service import rebuild_relations

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    _page_with_current(kb, title="入口A", body="依赖 [[桥接页]] 进入后续体系。", page_type="entry")
    _page_with_current(kb, title="入口B", body="依赖 [[桥接页]] 进入后续体系。", page_type="channel")
    bridge = _page_with_current(kb, title="桥接页", body="桥接 [[核心C]] 与入口侧知识。", page_type="bridge")
    _page_with_current(kb, title="核心C", body="连接 [[核心D]] 并承接桥接页。", page_type="core")
    _page_with_current(kb, title="核心D", body="核心D提供稳定能力说明。", page_type="leaf")
    rebuild_relations(kb)

    created = scan_health(kb)

    bridge_check = CheckItem.objects.get(knowledge_base=kb, check_type="bridge_node", related__pages__contains=[bridge.id])
    assert bridge_check in created
    assert bridge_check.related["graph_insight"] == "bridge_node"
    assert bridge_check.related["degree"] >= 2
    assert bridge_check.status == "auto_resolved"
    assert bridge_check.suggested_actions == []
    assert bridge_check.related["resolution"]["action"] == "automatic_maintenance"
    assert scan_health(kb) == []
    assert CheckItem.objects.filter(knowledge_base=kb, check_type="bridge_node", related__pages__contains=[bridge.id]).count() == 1


@pytest.mark.django_db
def test_scan_health_converts_sparse_graph_communities_to_checks():
    from apps.opspilot.models import CheckItem, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import scan_health
    from apps.opspilot.services.wiki.relation_service import rebuild_relations

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    page_a = _page_with_current(kb, title="社区A", body="关联 [[社区B]]。", page_type="type-a")
    page_b = _page_with_current(kb, title="社区B", body="关联 [[社区C]]。", page_type="type-b")
    page_c = _page_with_current(kb, title="社区C", body="关联 [[社区D]]。", page_type="type-c")
    page_d = _page_with_current(kb, title="社区D", body="社区D是链路末端。", page_type="type-d")
    rebuild_relations(kb)

    created = scan_health(kb)

    page_ids = {page_a.id, page_b.id, page_c.id, page_d.id}
    sparse_check = CheckItem.objects.get(
        knowledge_base=kb,
        check_type="sparse_community",
        related__pages__contains=[page_a.id],
    )
    assert sparse_check in created
    assert set(sparse_check.related["pages"]) == page_ids
    assert sparse_check.related["graph_insight"] == "sparse_community"
    assert sparse_check.related["density"] <= 0.5
    assert sparse_check.status == "auto_resolved"
    assert sparse_check.suggested_actions == []
    assert sparse_check.related["resolution"]["action"] == "automatic_maintenance"
    assert scan_health(kb) == []
    assert CheckItem.objects.filter(knowledge_base=kb, check_type="sparse_community").count() == 1


@pytest.mark.django_db
def test_scan_health_converts_cross_community_edges_to_checks():
    from apps.opspilot.models import CheckItem, Material, PageEvidence, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import scan_health

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    material_a = Material.objects.create(knowledge_base=kb, name="source-a", material_type="text", status="done")
    material_b = Material.objects.create(knowledge_base=kb, name="source-b", material_type="text", status="done")
    a1 = _page_with_current(kb, title="A1", body="A1 内容足够长。", page_type="group-a")
    a2 = _page_with_current(kb, title="A2", body="A2 内容足够长。", page_type="group-a")
    a3 = _page_with_current(kb, title="A3", body="A3 跨域依赖 [[B1]]。", page_type="group-a")
    b1 = _page_with_current(kb, title="B1", body="B1 内容足够长。", page_type="group-b")
    b2 = _page_with_current(kb, title="B2", body="B2 内容足够长。", page_type="group-b")
    b3 = _page_with_current(kb, title="B3", body="B3 内容足够长。", page_type="group-b")
    a3.tags = ["group-a", "handoff"]
    b1.tags = ["group-b", "handoff"]
    a3.save(update_fields=["tags"])
    b1.save(update_fields=["tags"])
    for page in [a1, a2, a3]:
        page.tags = list(dict.fromkeys([*(page.tags or []), "group-a"]))
        page.save(update_fields=["tags"])
        PageEvidence.objects.create(page=page, material=material_a)
    for page in [b1, b2, b3]:
        page.tags = list(dict.fromkeys([*(page.tags or []), "group-b"]))
        page.save(update_fields=["tags"])
        PageEvidence.objects.create(page=page, material=material_b)

    created = scan_health(kb)

    check = CheckItem.objects.get(knowledge_base=kb, check_type="cross_community_edge")
    assert check in created
    assert set(check.related["pages"]) == {a3.id, b1.id}
    assert check.related["graph_insight"] == "cross_community_edge"
    assert check.related["from_community"] != check.related["to_community"]
    assert check.related["signals"] == {"shared_tags": 1, "reference": 1}
    assert check.status == "auto_resolved"
    assert check.suggested_actions == []
    assert check.related["resolution"]["action"] == "automatic_maintenance"
    assert scan_health(kb) == []
    assert CheckItem.objects.filter(knowledge_base=kb, check_type="cross_community_edge").count() == 1


@pytest.mark.django_db
def test_resolve_check_cannot_reopen_automatic_diagnostic():
    from apps.opspilot.models import CheckItem, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import resolve_check

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    page = _page_with_current(kb, title="桥接节点", body="已补充来源和关系说明。")
    check = CheckItem.objects.create(
        knowledge_base=kb,
        check_type="bridge_node",
        status="auto_resolved",
        related={"pages": [page.id], "graph_insight": "bridge_node", "resolution": {"action": "automatic_maintenance"}},
        suggested_actions=[],
    )

    with pytest.raises(ValueError, match="only open"):
        resolve_check(check, operator="admin", note="已补充资料并确认关系合理")

    check.refresh_from_db()
    assert check.status == "auto_resolved"
    assert check.related["graph_insight"] == "bridge_node"
    assert check.related["resolution"]["action"] == "automatic_maintenance"


@pytest.mark.django_db
def test_scan_health_converts_missing_wikilinks_to_knowledge_gap_checks():
    from apps.opspilot.models import CheckItem, Material, PageEvidence, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import scan_health

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    material = Material.objects.create(knowledge_base=kb, name="source", material_type="text", status="done")
    source = _page_with_current(kb, title="业务接入", body="业务接入依赖 [[未知系统]] 提供账号同步。")
    PageEvidence.objects.create(page=source, material=material)

    created = scan_health(kb)

    check = CheckItem.objects.get(knowledge_base=kb, check_type="missing")
    assert check in created
    assert check.related["graph_insight"] == "knowledge_gap"
    assert check.related["target"] == "未知系统"
    assert check.related["target_key"]
    assert check.related["pages"] == [source.id]
    assert check.related["suggested_queries"] == ["未知系统", "业务接入 未知系统"]
    assert check.status == "auto_resolved"
    assert check.suggested_actions == []
    assert check.related["resolution"]["action"] == "automatic_maintenance"
    assert scan_health(kb) == []
    assert CheckItem.objects.filter(knowledge_base=kb, check_type="missing").count() == 1


@pytest.mark.django_db
class TestCheckViews:
    def test_list_accept_and_scan_endpoints(self, api_client):
        from apps.opspilot.models import WikiKnowledgeBase
        from apps.opspilot.services.wiki.check_service import create_candidate

        kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
        page = _page_with_current(kb, body="current")
        check = create_candidate(page, body="cand", reason="conflict", check_type="cannot_merge")

        lst = api_client.get(f"/api/v1/opspilot/wiki_mgmt/check_item/?knowledge_base={kb.id}")
        assert lst.status_code == 200
        assert any(c["id"] == check.id for c in lst.json()["data"]["items"])

        acc = api_client.post(f"/api/v1/opspilot/wiki_mgmt/check_item/{check.id}/accept/", {}, format="json")
        assert acc.status_code == 410
        page.refresh_from_db()
        assert page.current_version.body == "current"

        scan = api_client.post(f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{kb.id}/scan/", {}, format="json")
        assert scan.status_code == 200

    def test_pending_list_auto_closes_incomplete_knowledge_conflict(self, api_client):
        from apps.opspilot.models import CheckItem, WikiKnowledgeBase

        kb = WikiKnowledgeBase.objects.create(name="kb-incomplete", team=[1])
        check = CheckItem.objects.create(
            knowledge_base=kb,
            check_type="conflict",
            status="open",
            decision_key="",
            decision_context={},
            suggested_actions=["keep_current", "use_new"],
        )

        response = api_client.get(f"/api/v1/opspilot/wiki_mgmt/check_item/?knowledge_base={kb.id}&view=pending")

        assert response.status_code == 200, response.content
        assert response.json()["data"]["items"] == []
        check.refresh_from_db()
        assert check.status == "auto_resolved"
        assert check.related["resolution"]["reason"] == "decision_context_incomplete"

    def test_filters_retrieve_reject_and_accept_without_candidate(self, api_client):
        from apps.opspilot.models import CheckItem, Material, WikiKnowledgeBase
        from apps.opspilot.services.wiki.check_service import create_candidate

        kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
        page = _page_with_current(kb, body="current")
        material = Material.objects.create(
            knowledge_base=kb,
            name="incoming",
            material_type="text",
            content_hash="incoming-v1",
        )
        candidate_check = create_candidate(
            page,
            body="cand",
            reason="conflict",
            check_type="cannot_merge",
            incoming_material=material,
        )
        plain_check = CheckItem.objects.create(knowledge_base=kb, check_type="orphan", status="auto_resolved", related={"pages": [page.id]})

        listed = api_client.get(
            f"/api/v1/opspilot/wiki_mgmt/check_item/?knowledge_base={kb.id}&status=open&check_type=cannot_merge&page=x&page_size=y"
        )
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()["data"]["items"]] == [candidate_check.id]

        dismissed = api_client.get(f"/api/v1/opspilot/wiki_mgmt/check_item/?knowledge_base={kb.id}&status=dismissed")
        assert dismissed.status_code == 200
        assert dismissed.json()["data"]["items"] == []

        retrieved = api_client.get(f"/api/v1/opspilot/wiki_mgmt/check_item/{plain_check.id}/")
        assert retrieved.status_code == 404

        accepted_scan = api_client.post(f"/api/v1/opspilot/wiki_mgmt/check_item/{plain_check.id}/accept/", {}, format="json")
        assert accepted_scan.status_code == 410
        plain_check.refresh_from_db()
        assert plain_check.status == "auto_resolved"

        rejected = api_client.post(f"/api/v1/opspilot/wiki_mgmt/check_item/{candidate_check.id}/reject/", {}, format="json")
        assert rejected.status_code == 410
        candidate_check.refresh_from_db()
        assert candidate_check.status == "open"

    def test_batch_accept_accepts_candidate_and_scan_checks(self, api_client):
        from apps.opspilot.models import CheckItem, WikiKnowledgeBase
        from apps.opspilot.services.wiki.check_service import create_candidate

        kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
        page_a = _page_with_current(kb, title="A", body="current-a")
        page_b = _page_with_current(kb, title="B", body="current-b")
        candidate_a = create_candidate(page_a, body="candidate-a", reason="conflict", check_type="cannot_merge")
        candidate_b = create_candidate(page_b, body="candidate-b", reason="conflict", check_type="cannot_merge")
        scan_check = CheckItem.objects.create(knowledge_base=kb, check_type="source_invalid", status="auto_resolved", related={"pages": [page_a.id]})

        response = api_client.post(
            "/api/v1/opspilot/wiki_mgmt/check_item/batch_accept/",
            {"ids": [candidate_a.id, candidate_b.id, scan_check.id]},
            format="json",
        )

        assert response.status_code == 410
        page_a.refresh_from_db()
        page_b.refresh_from_db()
        candidate_a.refresh_from_db()
        candidate_b.refresh_from_db()
        scan_check.refresh_from_db()
        assert page_a.current_version.body == "current-a"
        assert page_b.current_version.body == "current-b"
        assert candidate_a.status == "open"
        assert candidate_b.status == "open"
        assert scan_check.status == "auto_resolved"

    def test_accept_endpoint_rejects_semantic_duplicate(self, api_client):
        from apps.opspilot.models import CheckItem, WikiKnowledgeBase

        kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
        duplicate = _page_with_current(kb, title="CMDB", body="CMDB content", page_type="entity")
        canonical = _page_with_current(kb, title="配置平台", body="配置平台内容", page_type="entity")
        check = CheckItem.objects.create(
            knowledge_base=kb,
            check_type="duplicate",
            status="open",
            related={"pages": [duplicate.id, canonical.id], "canonical_title": "配置平台"},
            suggested_actions=["merge", "dismiss"],
        )

        response = api_client.post(f"/api/v1/opspilot/wiki_mgmt/check_item/{check.id}/accept/", {}, format="json")

        assert response.status_code == 410, response.content
        duplicate.refresh_from_db()
        check.refresh_from_db()
        assert duplicate.status == "active"
        assert check.status == "open"
        assert "decide" in response.json()["message"]

    def test_batch_reject_dismisses_selected_open_checks(self, api_client):
        from apps.opspilot.models import CheckItem, PageVersion, WikiKnowledgeBase
        from apps.opspilot.services.wiki.check_service import create_candidate

        kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
        page = _page_with_current(kb, body="current")
        candidate_check = create_candidate(page, body="candidate", reason="conflict", check_type="cannot_merge")
        candidate_id = candidate_check.candidate_version_id
        scan_check = CheckItem.objects.create(knowledge_base=kb, check_type="orphan", status="auto_resolved", related={"pages": [page.id]})

        response = api_client.post(
            "/api/v1/opspilot/wiki_mgmt/check_item/batch_reject/",
            {"ids": [candidate_check.id, scan_check.id]},
            format="json",
        )

        assert response.status_code == 410
        candidate_check.refresh_from_db()
        scan_check.refresh_from_db()
        page.refresh_from_db()
        assert candidate_check.status == "open"
        assert scan_check.status == "auto_resolved"
        assert page.current_version.body == "current"
        assert PageVersion.objects.filter(id=candidate_id).exists()

    def test_batch_resolve_marks_scan_checks_processed_and_skips_candidates(self, api_client):
        from apps.opspilot.models import CheckItem, WikiKnowledgeBase
        from apps.opspilot.services.wiki.check_service import create_candidate

        kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
        page = _page_with_current(kb, body="current")
        scan_check = CheckItem.objects.create(
            knowledge_base=kb,
            check_type="missing",
            status="auto_resolved",
            related={"pages": [page.id], "resolution": {"note": "已确认无需继续处理"}},
        )
        graph_check = CheckItem.objects.create(
            knowledge_base=kb,
            check_type="bridge_node",
            status="auto_resolved",
            related={"pages": [page.id], "resolution": {"action": "manual_resolve"}},
        )
        candidate_check = create_candidate(page, body="candidate", reason="conflict", check_type="cannot_merge")
        resolved_check = CheckItem.objects.create(
            knowledge_base=kb,
            check_type="source_invalid",
            status="resolved",
            related={"pages": [page.id]},
        )

        response = api_client.post(
            "/api/v1/opspilot/wiki_mgmt/check_item/batch_resolve/",
            {
                "ids": [scan_check.id, graph_check.id, candidate_check.id, resolved_check.id, 999999],
                "note": "已确认无需继续处理",
            },
            format="json",
        )

        assert response.status_code == 410
        scan_check.refresh_from_db()
        graph_check.refresh_from_db()
        candidate_check.refresh_from_db()
        resolved_check.refresh_from_db()
        assert scan_check.status == "auto_resolved"
        assert graph_check.status == "auto_resolved"
        assert candidate_check.status == "open"
        assert resolved_check.status == "resolved"
        assert scan_check.related["resolution"]["note"] == "已确认无需继续处理"
        assert graph_check.related["resolution"]["action"] == "manual_resolve"

    def test_batch_endpoints_validate_ids_and_skip_non_open_checks(self, api_client):
        from apps.opspilot.models import CheckItem, WikiKnowledgeBase

        kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
        page = _page_with_current(kb, body="current")
        open_check = CheckItem.objects.create(knowledge_base=kb, check_type="orphan", status="auto_resolved", related={"pages": [page.id]})
        resolved_check = CheckItem.objects.create(
            knowledge_base=kb,
            check_type="source_invalid",
            status="resolved",
            related={"pages": [page.id]},
        )

        empty_ids = api_client.post(
            "/api/v1/opspilot/wiki_mgmt/check_item/batch_accept/",
            {},
            format="json",
        )
        assert empty_ids.status_code == 410

        bad_ids = api_client.post(
            "/api/v1/opspilot/wiki_mgmt/check_item/batch_reject/",
            {"ids": ["bad"]},
            format="json",
        )
        assert bad_ids.status_code == 410

        response = api_client.post(
            "/api/v1/opspilot/wiki_mgmt/check_item/batch_reject/",
            {"ids": [open_check.id, resolved_check.id, 999999]},
            format="json",
        )

        assert response.status_code == 410
        open_check.refresh_from_db()
        resolved_check.refresh_from_db()
        assert open_check.status == "auto_resolved"
        assert resolved_check.status == "resolved"

    def test_merge_duplicate_endpoint_resolves_scan_duplicate(self, api_client):
        from apps.opspilot.models import CheckItem, WikiKnowledgeBase

        kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
        duplicate = _page_with_current(kb, title="CMDB", body="CMDB content", page_type="entity")
        canonical = _page_with_current(kb, title="配置平台", body="配置平台内容", page_type="entity")
        check = CheckItem.objects.create(
            knowledge_base=kb,
            check_type="duplicate",
            status="open",
            related={"pages": [duplicate.id, canonical.id], "canonical_title": "配置平台"},
            suggested_actions=["merge", "dismiss"],
        )

        response = api_client.post(f"/api/v1/opspilot/wiki_mgmt/check_item/{check.id}/merge/", {}, format="json")

        assert response.status_code == 410, response.content
        duplicate.refresh_from_db()
        check.refresh_from_db()
        assert duplicate.status == "active"
        assert check.status == "open"

    def test_resolve_endpoint_marks_scan_check_processed(self, api_client):
        from apps.opspilot.models import CheckItem, WikiKnowledgeBase

        kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
        page = _page_with_current(kb, title="跨社区强边", body="已确认是合理依赖。")
        check = CheckItem.objects.create(
            knowledge_base=kb,
            check_type="cross_community_edge",
            status="auto_resolved",
            related={"pages": [page.id], "graph_insight": "cross_community_edge", "resolution": {"action": "automatic_maintenance"}},
            suggested_actions=[],
        )

        response = api_client.post(
            f"/api/v1/opspilot/wiki_mgmt/check_item/{check.id}/resolve/",
            {"note": "已确认该跨社区关系合理"},
            format="json",
        )

        assert response.status_code == 410
        check.refresh_from_db()
        assert check.status == "auto_resolved"
        assert check.related["resolution"]["action"] == "automatic_maintenance"


@pytest.mark.django_db
def test_page_identity_keep_separate_preserves_pages_and_writes_rule():
    from apps.opspilot.models import WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import decide_check, ensure_check

    kb = WikiKnowledgeBase.objects.create(name="kb-keep-separate", team=[1])
    left = _page_with_current(kb, title="CMDB", body="left body", page_type="entity")
    right = _page_with_current(kb, title="配置平台", body="right body", page_type="entity")
    created = ensure_check(
        kb,
        "duplicate",
        left,
        related={
            "pages": [left.id, right.id],
            "canonical_title": "配置平台",
        },
    )
    check = created[0]

    rule = decide_check(check, action="keep_separate", operator="reviewer")

    left.refresh_from_db()
    right.refresh_from_db()
    check.refresh_from_db()
    assert left.status == right.status == "active"
    assert left.current_version.body == "left body"
    assert right.current_version.body == "right body"
    assert check.status == "resolved"
    assert len(check.decision_key) == 64
    assert rule.action == "keep_separate"
    assert rule.created_by == "reviewer"
    assert len(rule.match_snapshot["page_identities"]) == 2


@pytest.mark.django_db
@pytest.mark.parametrize("reverse_related", [False, True])
def test_page_identity_merge_uses_frozen_target_identity(reverse_related):
    from apps.opspilot.models import WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import decide_check, ensure_check

    kb = WikiKnowledgeBase.objects.create(name=f"kb-identity-merge-{reverse_related}", team=[1])
    source = _page_with_current(kb, title="CMDB", body="source body", page_type="entity")
    target = _page_with_current(kb, title="配置平台", body="target body", page_type="entity")
    page_ids = [target.id, source.id] if reverse_related else [source.id, target.id]
    check = ensure_check(
        kb,
        "duplicate",
        source,
        related={
            "pages": page_ids,
            "canonical_title": "配置平台",
        },
    )[0]
    frozen_target = check.decision_context["target_identity"]

    rule = decide_check(check, action="merge", operator="reviewer")

    source.refresh_from_db()
    target.refresh_from_db()
    check.refresh_from_db()
    assert frozen_target["page_id"] == target.id
    assert target.status == "active"
    assert source.status == "archived"
    assert rule.action == "merge"
    assert rule.result_page_id == target.id
    assert rule.result_snapshot["target_identity"]["canonical_title_key"] == "配置平台"
    assert [item["page_id"] for item in rule.result_snapshot["source_identities"]] == [source.id]
    assert check.related["merged_into"] == target.id


@pytest.mark.django_db
def test_merge_duplicate_check_wrapper_with_frozen_context_writes_semantic_rule():
    from apps.opspilot.models import WikiDecisionRule, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import ensure_check, merge_duplicate_check

    kb = WikiKnowledgeBase.objects.create(name="kb-wrapper-rule", team=[1])
    source = _page_with_current(kb, title="CMDB", body="source body", page_type="entity")
    target = _page_with_current(kb, title="配置平台", body="target body", page_type="entity")
    check = ensure_check(
        kb,
        "duplicate",
        source,
        related={
            "pages": [source.id, target.id],
            "canonical_title": "配置平台",
        },
    )[0]

    result = merge_duplicate_check(check, operator="reviewer")

    rule = WikiDecisionRule.objects.get(source_check=check)
    assert result["target_page_id"] == target.id
    assert rule.decision_type == "page_identity"
    assert rule.action == "merge"
    assert rule.result_snapshot["operator"] == "reviewer"
    assert rule.result_snapshot["target_identity"]["page_id"] == target.id
    assert rule.result_snapshot["source_identities"][0]["page_id"] == source.id


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("action", "changed_field", "changed_value"),
    [
        ("merge", "title", "CMDB renamed"),
        ("keep_separate", "title", "CMDB renamed"),
        ("merge", "page_type", "service"),
        ("keep_separate", "page_type", "service"),
    ],
)
def test_page_identity_decision_auto_resolves_stable_identity_drift(
    action,
    changed_field,
    changed_value,
):
    from apps.opspilot.models import WikiDecisionRule, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import decide_check, ensure_check

    kb = WikiKnowledgeBase.objects.create(
        name=f"kb-identity-drift-{action}-{changed_field}",
        team=[1],
    )
    source = _page_with_current(kb, title="CMDB", body="source body", page_type="entity")
    target = _page_with_current(kb, title="配置平台", body="target body", page_type="entity")
    check = ensure_check(
        kb,
        "duplicate",
        source,
        related={
            "pages": [source.id, target.id],
            "canonical_title": "配置平台",
        },
    )[0]
    setattr(source, changed_field, changed_value)
    source.save(update_fields=[changed_field, "updated_at"])

    assert decide_check(check, action=action, operator="reviewer") is None

    check.refresh_from_db()
    source.refresh_from_db()
    target.refresh_from_db()
    assert check.status == "auto_resolved"
    assert check.suggested_actions == []
    assert check.related["resolution"]["action"] == "automatic_maintenance"
    assert check.related["resolution"]["reason"] == "decision_context_stale"
    assert source.status == "active"
    assert target.status == "active"
    assert source.current_version.body == "source body"
    assert target.current_version.body == "target body"
    assert getattr(source, changed_field) == changed_value
    assert not WikiDecisionRule.objects.filter(source_check=check).exists()


def _make_page_without_page_service(kb, title, *, page_type="concept", body="body"):
    from apps.opspilot.models import KnowledgePage, PageVersion

    page = KnowledgePage.objects.create(
        knowledge_base=kb,
        title=title,
        page_type=page_type,
    )
    page.current_version = PageVersion.objects.create(
        page=page,
        no=1,
        body=body,
        is_current=True,
        change_type="ai_create",
    )
    page.save(update_fields=["current_version"])
    return page


@pytest.mark.django_db
def test_page_identity_canonical_alias_fallback_target_is_order_independent():
    from apps.opspilot.models import WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import ensure_check

    generation_rules = {
        "title_aliases": [
            {
                "canonical": "配置平台",
                "aliases": ["CMDB", "配置管理数据库"],
            }
        ]
    }
    targets = []
    for reverse in (False, True):
        kb = WikiKnowledgeBase.objects.create(
            name=f"kb-{reverse}",
            team=[1],
            generation_rules=generation_rules,
        )
        cmdb = _page_with_current(kb, "CMDB")
        config_db = _page_with_current(kb, "配置管理数据库")
        pages = [cmdb, config_db]
        if reverse:
            pages.reverse()
        check = ensure_check(
            kb,
            "duplicate",
            pages[0],
            related={
                "pages": [page.id for page in pages],
                "canonical_title": "配置平台",
            },
        )[0]
        targets.append(check.decision_context["target_identity"]["compact_title_key"])

    assert targets[0] == targets[1]


@pytest.mark.django_db
def test_page_identity_decision_auto_resolves_legacy_check_with_more_than_two_pages():
    from apps.opspilot.models import CheckItem, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import decide_check

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    pages = [_page_with_current(kb, title) for title in ("one", "two", "three")]
    check = CheckItem.objects.create(
        knowledge_base=kb,
        check_type="duplicate",
        status="open",
        related={"pages": [page.id for page in pages]},
    )

    assert decide_check(check, "merge", operator="alice") is None

    check.refresh_from_db()
    assert check.status == "auto_resolved"
    assert check.suggested_actions == []
    assert check.related["resolution"]["action"] == "automatic_maintenance"
    assert check.related["resolution"]["reason"] == "decision_context_stale"
    assert all(page.status == "active" for page in pages)


@pytest.mark.django_db
def test_diagnostic_identity_distinguishes_targets_and_reuses_exact_repeat():
    from apps.opspilot.models import CheckItem, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import ensure_check

    kb = WikiKnowledgeBase.objects.create(name="kb-diagnostic-identity", team=[1])
    page = _page_with_current(kb, title="source")

    first = ensure_check(
        kb,
        "broken_relation",
        page,
        related={"pages": [page.id], "target": "目标 A"},
    )
    second = ensure_check(
        kb,
        "broken_relation",
        page,
        related={"pages": [page.id], "target": "目标 B"},
    )
    repeated = ensure_check(
        kb,
        "broken_relation",
        page,
        related={"pages": [page.id], "target": "目标 A"},
    )

    assert len(first) == 1
    assert len(second) == 1
    assert first[0].id != second[0].id
    assert repeated == []
    diagnostics = list(
        CheckItem.objects.filter(
            knowledge_base=kb,
            check_type="broken_relation",
        ).order_by("id")
    )
    assert len(diagnostics) == 2
    assert all(item.status == "auto_resolved" for item in diagnostics)
    assert {item.related["target"] for item in diagnostics} == {"目标 A", "目标 B"}
