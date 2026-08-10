import pytest


def _kb():
    from apps.opspilot.models import WikiKnowledgeBase

    return WikiKnowledgeBase.objects.create(name="kb", team=[1])


def _material(kb, name="m"):
    from apps.opspilot.models import Material

    return Material.objects.create(knowledge_base=kb, name=name, material_type="text", text_content="x")


def _page(kb, title="A"):
    from apps.opspilot.models import KnowledgePage, PageVersion

    page = KnowledgePage.objects.create(knowledge_base=kb, page_type="concept", title=title, contribution="ai")
    v = PageVersion.objects.create(page=page, no=1, body="b", change_type="ai_create", is_current=True)
    page.current_version = v
    page.save(update_fields=["current_version"])
    return page


@pytest.mark.django_db(transaction=True)
def test_deleting_only_source_invalidates_without_user_review_and_clears_index():
    from apps.opspilot.models import CheckItem, Material, PageChunk, PageEvidence
    from apps.opspilot.services.wiki.update_service import handle_material_deletion

    kb = _kb()
    mat = _material(kb)
    page = _page(kb)
    page.current_version.embedding = [0.1, 0.2]
    page.current_version.save(update_fields=["embedding", "updated_at"])
    chunk = PageChunk.objects.create(
        page=page,
        version=page.current_version,
        idx=0,
        text="indexed",
        embedding=[0.3, 0.4],
    )
    PageEvidence.objects.create(page=page, material=mat)
    stale_source_check = CheckItem.objects.create(
        knowledge_base=kb,
        check_type="source_invalid",
        status="auto_resolved",
        related={
            "pages": [page.id],
            "resolution": {"action": "automatic_maintenance", "operator": "system"},
        },
    )
    obsolete_conflict = CheckItem.objects.create(
        knowledge_base=kb,
        check_type="cannot_merge",
        status="open",
        related={"pages": [page.id], "materials": [mat.id]},
    )
    initial_check_count = CheckItem.objects.filter(knowledge_base=kb).count()

    build = handle_material_deletion(mat, operator="sys")

    page.refresh_from_db()
    page.current_version.refresh_from_db()
    chunk.refresh_from_db()
    stale_source_check.refresh_from_db()
    obsolete_conflict.refresh_from_db()
    assert not Material.objects.filter(id=mat.id).exists()
    assert page.status == "source_invalid"
    assert page.current_version.embedding == []
    assert chunk.embedding == []
    assert build.counts == {"new": 0, "updated": 1, "unchanged": 0, "pending_review": 0}
    assert build.affected_pages == [page.id]
    assert build.maintenance["invalidated"]["event"] == "material_delete"
    assert stale_source_check.status == "auto_resolved"
    assert obsolete_conflict.status == "auto_resolved"
    assert CheckItem.objects.filter(knowledge_base=kb).count() == initial_check_count


@pytest.mark.django_db(transaction=True)
def test_page_with_remaining_source_stays_active_and_keeps_index():
    from apps.opspilot.models import CheckItem, PageChunk, PageEvidence
    from apps.opspilot.services.wiki.update_service import handle_material_deletion

    kb = _kb()
    m1, m2 = _material(kb, "m1"), _material(kb, "m2")
    page = _page(kb)
    page.current_version.embedding = [0.1, 0.2]
    page.current_version.save(update_fields=["embedding", "updated_at"])
    chunk = PageChunk.objects.create(
        page=page,
        version=page.current_version,
        idx=0,
        text="indexed",
        embedding=[0.3, 0.4],
    )
    PageEvidence.objects.create(page=page, material=m1)
    PageEvidence.objects.create(page=page, material=m2)

    build = handle_material_deletion(m1, operator="sys")

    page.refresh_from_db()
    page.current_version.refresh_from_db()
    chunk.refresh_from_db()
    assert page.status == "active"
    assert page.current_version.embedding == [0.1, 0.2]
    assert chunk.embedding == [0.3, 0.4]
    assert PageEvidence.objects.filter(page=page, material=m2).exists()
    assert build.counts == {"new": 0, "updated": 0, "unchanged": 1, "pending_review": 0}
    assert build.maintenance["shared"]["event"] == "build"
    assert not CheckItem.objects.filter(knowledge_base=kb, check_type="source_invalid").exists()


@pytest.mark.django_db
def test_material_deletion_recounts_source_build_pending_review():
    from apps.opspilot.models import BuildRecord, CheckItem, PageEvidence, PageVersion
    from apps.opspilot.services.wiki.update_service import handle_material_deletion

    kb = _kb()
    material = _material(kb)
    page = _page(kb)
    PageEvidence.objects.create(page=page, material=material)
    source_build = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="material",
        status="success",
        stage="done",
        counts={"new": 0, "updated": 0, "unchanged": 0, "pending_review": 1},
    )
    candidate = PageVersion.objects.create(
        page=page,
        no=2,
        body="candidate",
        change_type="candidate",
        is_current=False,
        build_record=source_build,
    )
    check = CheckItem.objects.create(
        knowledge_base=kb,
        check_type="cannot_merge",
        status="open",
        candidate_version=candidate,
        related={"pages": [page.id], "materials": [material.id]},
    )

    handle_material_deletion(material, operator="sys")

    check.refresh_from_db()
    source_build.refresh_from_db()
    assert check.status == "auto_resolved"
    assert source_build.counts["pending_review"] == 0


@pytest.mark.django_db
def test_material_deletion_closes_shared_page_decision_from_frozen_material_context():
    from apps.opspilot.models import BuildRecord, CheckItem, PageEvidence, PageVersion
    from apps.opspilot.services.wiki.update_service import handle_material_deletion

    kb = _kb()
    removed = _material(kb, "removed-context")
    remaining = _material(kb, "remaining-context")
    removed_id = removed.id
    page = _page(kb, "shared-context")
    PageEvidence.objects.create(page=page, material=removed)
    PageEvidence.objects.create(page=page, material=remaining)
    source_build = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="material",
        status="success",
        stage="done",
        counts={"new": 0, "updated": 0, "unchanged": 0, "pending_review": 1},
    )
    candidate = PageVersion.objects.create(
        page=page,
        no=2,
        body="candidate",
        change_type="candidate",
        is_current=False,
        build_record=source_build,
    )
    check = CheckItem.objects.create(
        knowledge_base=kb,
        check_type="cannot_merge",
        status="open",
        candidate_version=candidate,
        related={"pages": [page.id]},
        decision_context={
            "participants": [
                {"material_id": removed_id, "content_hash": "removed-hash"},
                {"material_id": remaining.id, "content_hash": "remaining-hash"},
            ],
            "incoming": {"material_id": removed_id, "content_hash": "removed-hash"},
        },
    )

    handle_material_deletion(removed, operator="sys")

    check.refresh_from_db()
    source_build.refresh_from_db()
    page.refresh_from_db()
    assert page.status == "active"
    assert check.status == "auto_resolved"
    assert source_build.counts["pending_review"] == 0


@pytest.mark.django_db
def test_material_deletion_closes_checks_for_invalidated_pages_but_keeps_shared_page_checks_open():
    from apps.opspilot.models import CheckItem, PageEvidence
    from apps.opspilot.services.wiki.update_service import handle_material_deletion

    kb = _kb()
    removed = _material(kb, "removed")
    remaining = _material(kb, "remaining")
    invalidated = _page(kb, "invalidated")
    shared = _page(kb, "shared")
    invalidated_peer = _page(kb, "invalidated peer")
    shared_peer = _page(kb, "shared peer")
    PageEvidence.objects.create(page=invalidated, material=removed)
    PageEvidence.objects.create(page=shared, material=removed)
    PageEvidence.objects.create(page=shared, material=remaining)
    invalidated_check = CheckItem.objects.create(
        knowledge_base=kb,
        check_type="duplicate",
        status="open",
        related={"pages": [invalidated.id, invalidated_peer.id]},
    )
    shared_check = CheckItem.objects.create(
        knowledge_base=kb,
        check_type="duplicate",
        status="open",
        related={"pages": [shared.id, shared_peer.id]},
    )

    build = handle_material_deletion(removed, operator="sys")

    invalidated_check.refresh_from_db()
    shared_check.refresh_from_db()
    assert invalidated_check.status == "auto_resolved"
    assert shared_check.status == "open"
    assert build.counts["pending_review"] == 0
    assert not CheckItem.objects.filter(status="open", related__pages__contains=[invalidated.id]).exists()


@pytest.mark.django_db(transaction=True)
def test_material_deletion_previews_and_audits_archived_recoverable_page_source_loss():
    from apps.opspilot.models import PageEvidence
    from apps.opspilot.services.wiki.update_service import handle_material_deletion, preview_material_deletion

    kb = _kb()
    material = _material(kb)
    active = _page(kb, "active")
    archived = _page(kb, "archived")
    archived.status = "archived"
    archived.save(update_fields=["status", "updated_at"])
    PageEvidence.objects.create(page=active, material=material)
    PageEvidence.objects.create(page=archived, material=material)

    preview = preview_material_deletion(material)

    assert preview["affected_count"] == 2
    assert [item["id"] for item in preview["affected_pages"]] == [active.id, archived.id]
    assert preview["archived_recoverable_count"] == 1
    assert [item["id"] for item in preview["archived_recoverable"]] == [archived.id]
    assert "永久失去" in preview["archived_recoverable"][0]["reason"]

    build = handle_material_deletion(material, operator="sys")

    active.refresh_from_db()
    archived.refresh_from_db()
    build.refresh_from_db()
    assert active.status == "source_invalid"
    assert archived.status == "archived"
    assert build.inputs["all_evidence_page_ids"] == [active.id, archived.id]
    assert build.inputs["archived_recoverable_page_ids"] == [archived.id]
    assert build.inputs["archived_source_loss"] == "页面可恢复，但被删除的资料来源不可恢复"
    assert build.counts["archived_recoverable"] == 1
    assert build.affected_pages == [active.id, archived.id]
    assert build.maintenance["invalidated"]["affected_page_ids"] == [active.id, archived.id]


@pytest.mark.django_db(transaction=True)
def test_deleting_shared_material_recomputes_remaining_shared_source_relation():
    from apps.opspilot.models import PageEvidence, PageRelation
    from apps.opspilot.services.wiki.relation_service import rebuild_relations
    from apps.opspilot.services.wiki.update_service import handle_material_deletion

    kb = _kb()
    removed = _material(kb, "removed")
    remaining = _material(kb, "remaining")
    left = _page(kb, "left")
    right = _page(kb, "right")
    PageEvidence.objects.create(page=left, material=removed)
    PageEvidence.objects.create(page=right, material=removed)
    PageEvidence.objects.create(page=left, material=remaining)
    PageEvidence.objects.create(page=right, material=remaining)
    rebuild_relations(kb)
    rel = PageRelation.objects.get(from_page=left, to_page=right, relation_type="shared_source")
    assert rel.weight == 2
    assert rel.via_material_id == removed.id

    build = handle_material_deletion(removed, operator="sys")

    assert build.counts["pending_review"] == 0
    rel = PageRelation.objects.get(from_page=left, to_page=right, relation_type="shared_source")
    assert rel.weight == 1
    assert rel.via_material_id == remaining.id


@pytest.mark.django_db(transaction=True)
class TestDeleteView:
    def test_delete_impact_endpoint_reports_source_loss_without_mutation(self, api_client):
        from apps.opspilot.models import BuildRecord, CheckItem, Material, PageEvidence

        kb = _kb()
        removed = _material(kb, "removed")
        remaining = _material(kb, "remaining")
        only_source = _page(kb, "only source")
        shared_source = _page(kb, "shared source")
        untouched = _page(kb, "untouched")
        PageEvidence.objects.create(page=only_source, material=removed)
        PageEvidence.objects.create(page=shared_source, material=removed)
        PageEvidence.objects.create(page=shared_source, material=remaining)
        PageEvidence.objects.create(page=untouched, material=remaining)
        existing_check = CheckItem.objects.create(
            knowledge_base=kb,
            check_type="source_invalid",
            status="auto_resolved",
            related={
                "pages": [only_source.id],
                "resolution": {"action": "automatic_maintenance", "operator": "system"},
            },
        )
        initial_build_count = BuildRecord.objects.filter(knowledge_base=kb).count()
        initial_check_count = CheckItem.objects.filter(knowledge_base=kb).count()

        r = api_client.get(f"/api/v1/opspilot/wiki_mgmt/material/{removed.id}/delete_impact/")

        assert r.status_code == 200
        data = r.json()["data"]
        assert data["material_id"] == removed.id
        assert data["affected_count"] == 2
        assert [p["id"] for p in data["affected_pages"]] == [only_source.id, shared_source.id]
        assert [p["id"] for p in data["will_be_source_invalid"]] == [only_source.id]
        assert [p["id"] for p in data["shared_source_protected"]] == [shared_source.id]
        assert Material.objects.filter(id=removed.id).exists()
        assert PageEvidence.objects.filter(material=removed).count() == 2
        assert BuildRecord.objects.filter(knowledge_base=kb).count() == initial_build_count
        assert CheckItem.objects.filter(knowledge_base=kb).count() == initial_check_count
        existing_check.refresh_from_db()
        only_source.refresh_from_db()
        shared_source.refresh_from_db()
        assert existing_check.status == "auto_resolved"
        assert only_source.status == "active"
        assert shared_source.status == "active"

    def test_destroy_endpoint_reports_automatic_physical_delete(self, api_client):
        from apps.opspilot.models import CheckItem, Material, PageEvidence

        kb = _kb()
        mat = _material(kb)
        material_id = mat.id
        page = _page(kb)
        PageEvidence.objects.create(page=page, material=mat)

        r = api_client.delete(f"/api/v1/opspilot/wiki_mgmt/material/{material_id}/")

        assert r.status_code == 200
        data = r.json()["data"]
        page.refresh_from_db()
        assert data["deleted"] is True
        assert data["material_id"] == material_id
        assert data["pending_review"] == 0
        assert data["status"] in {"success", "partial"}
        assert data["counts"]["updated"] == 1
        assert data["build_record_id"]
        assert data["maintenance"]["event"] == "material_delete"
        assert page.status == "source_invalid"
        assert not CheckItem.objects.filter(knowledge_base=kb, status="open").exists()
        assert not Material.objects.filter(id=material_id).exists()


@pytest.mark.django_db
def test_deleting_file_material_removes_minio_file(monkeypatch, django_capture_on_commit_callbacks):
    """删除 file 资料应删除其 MinIO 文件对象(post_delete 信号)。"""
    from apps.opspilot.models import Material
    from apps.opspilot.services.wiki.update_service import handle_material_deletion

    deleted = []
    kb = _kb()
    mat = Material.objects.create(knowledge_base=kb, name="f", material_type="file")
    monkeypatch.setattr(type(mat.file.storage), "delete", lambda self, name: deleted.append(name))
    mat.file = "fake/material.txt"  # 模拟已上传文件(字符串赋值不触发真实上传)
    mat.save(update_fields=["file", "updated_at"])

    with django_capture_on_commit_callbacks(execute=True):
        handle_material_deletion(mat, operator="sys")
        assert deleted == []

    assert deleted == ["fake/material.txt"]


@pytest.mark.django_db
def test_deleting_material_removes_parsed_markdown_versions(monkeypatch, django_capture_on_commit_callbacks):
    """删除资料应删除该资料所有 wiki/parsed 解析产物。"""
    from apps.opspilot.models import MaterialVersion
    from apps.opspilot.services.wiki import material_service
    from apps.opspilot.services.wiki.update_service import handle_material_deletion

    deleted = []

    class Storage:
        def delete(self, name):
            deleted.append(name)

    kb = _kb()
    mat = _material(kb)
    first_locator = f"wiki/parsed/{kb.id}/{mat.id}/h1.md"
    second_locator = f"wiki/parsed/{kb.id}/{mat.id}/h2.md"
    MaterialVersion.objects.create(material=mat, content_hash="h1", content_locator=first_locator)
    MaterialVersion.objects.create(material=mat, content_hash="h2", content_locator=second_locator)
    monkeypatch.setattr(material_service, "_PARSED_STORAGE", Storage())

    with django_capture_on_commit_callbacks(execute=True):
        handle_material_deletion(mat, operator="sys")
        assert deleted == []

    assert sorted(deleted) == sorted([first_locator, second_locator])


@pytest.mark.django_db
def test_material_external_cleanup_is_discarded_on_transaction_rollback(monkeypatch):
    from django.db import transaction

    from apps.opspilot.models import Material, MaterialVersion
    from apps.opspilot.services.wiki import material_service

    file_deletes = []
    parsed_deletes = []

    class Storage:
        def delete(self, name):
            parsed_deletes.append(name)

    kb = _kb()
    material = Material.objects.create(
        knowledge_base=kb,
        name="rollback",
        material_type="file",
        file="fake/rollback.txt",
    )
    material_id = material.id
    locator = f"wiki/parsed/{kb.id}/{material.id}/rollback.md"
    MaterialVersion.objects.create(material=material, content_hash="rollback", content_locator=locator)
    monkeypatch.setattr(type(material.file.storage), "delete", lambda self, name: file_deletes.append(name))
    monkeypatch.setattr(material_service, "_PARSED_STORAGE", Storage())

    with pytest.raises(RuntimeError, match="rollback"):
        with transaction.atomic():
            material.delete()
            assert file_deletes == []
            assert parsed_deletes == []
            raise RuntimeError("rollback")

    assert Material.objects.filter(pk=material_id).exists()
    assert file_deletes == []
    assert parsed_deletes == []


@pytest.mark.django_db
def test_external_cleanup_failure_does_not_break_committed_delete(monkeypatch, django_capture_on_commit_callbacks):
    from apps.opspilot.models import Material

    kb = _kb()
    material = Material.objects.create(
        knowledge_base=kb,
        name="broken cleanup",
        material_type="file",
        file="fake/broken.txt",
    )
    material_id = material.id

    def fail_delete(self, name):
        raise RuntimeError("storage unavailable")

    monkeypatch.setattr(type(material.file.storage), "delete", fail_delete)

    with django_capture_on_commit_callbacks(execute=True):
        material.delete()

    assert not Material.objects.filter(pk=material_id).exists()


@pytest.mark.django_db
def test_parsed_cleanup_callback_failure_does_not_break_committed_delete(
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    from apps.opspilot.models import Material, MaterialVersion
    from apps.opspilot.signals import wiki_material_signal

    kb = _kb()
    material = _material(kb)
    material_id = material.id
    locator = f"wiki/parsed/{kb.id}/{material.id}/broken.md"
    version = MaterialVersion.objects.create(
        material=material,
        content_hash="broken",
        content_locator=locator,
    )
    version_id = version.id

    def fail_delete(parsed_locator):
        assert parsed_locator == locator
        raise RuntimeError("parsed storage unavailable")

    monkeypatch.setattr(wiki_material_signal, "delete_parsed_markdown", fail_delete)

    with django_capture_on_commit_callbacks(execute=True):
        material.delete()

    assert not MaterialVersion.objects.filter(pk=version_id).exists()
    assert not Material.objects.filter(pk=material_id).exists()


@pytest.mark.django_db
def test_deleting_material_skips_parsed_markdown_locator_for_other_material(monkeypatch, django_capture_on_commit_callbacks):
    """防止异常版本 locator 指向其它资料时误删其它资料的解析产物。"""
    from apps.opspilot.models import MaterialVersion
    from apps.opspilot.services.wiki import material_service
    from apps.opspilot.services.wiki.update_service import handle_material_deletion

    deleted = []

    class Storage:
        def delete(self, name):
            deleted.append(name)

    kb = _kb()
    removed = _material(kb, "removed")
    other = _material(kb, "other")
    other_locator = f"wiki/parsed/{kb.id}/{other.id}/other.md"
    MaterialVersion.objects.create(material=removed, content_hash="bad", content_locator=other_locator)
    monkeypatch.setattr(material_service, "_PARSED_STORAGE", Storage())

    with django_capture_on_commit_callbacks(execute=True):
        handle_material_deletion(removed, operator="sys")

    assert deleted == []


def test_delete_parsed_markdown_rejects_prefix_locators(monkeypatch):
    """防止异常 locator 把目录/前缀当成可删除对象。"""
    from apps.opspilot.services.wiki import material_service

    deleted = []

    class Storage:
        def delete(self, name):
            deleted.append(name)

    monkeypatch.setattr(material_service, "_PARSED_STORAGE", Storage())

    for locator in ["wiki", "wiki/", "wiki/parsed", "wiki/parsed/", "wiki/parsed/1/", "wiki/parsed/1/2/"]:
        assert material_service.delete_parsed_markdown(locator) is False

    assert deleted == []


@pytest.mark.django_db
def test_deleting_kb_cascade_removes_material_minio_files(monkeypatch, django_capture_on_commit_callbacks):
    """删除知识库 → 级联删资料 → 同样触发 post_delete,删除 MinIO 文件。"""
    from apps.opspilot.models import Material, WikiKnowledgeBase

    deleted = []
    kb = WikiKnowledgeBase.objects.create(name="kb-cascade", team=[1])
    mat = Material.objects.create(knowledge_base=kb, name="f", material_type="file", file="fake/cascade.txt")
    monkeypatch.setattr(type(mat.file.storage), "delete", lambda self, name: deleted.append(name))

    with django_capture_on_commit_callbacks(execute=True):
        kb.delete()
        assert deleted == []

    assert not Material.objects.filter(id=mat.id).exists()
    assert "fake/cascade.txt" in deleted


@pytest.mark.django_db
def test_deleting_kb_cascade_removes_parsed_markdown_versions(monkeypatch, django_capture_on_commit_callbacks):
    """删除知识库级联删除资料时,也应删除 wiki/parsed 解析产物。"""
    from apps.opspilot.models import Material, MaterialVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki import material_service

    deleted = []

    class Storage:
        def delete(self, name):
            deleted.append(name)

    kb = WikiKnowledgeBase.objects.create(name="kb-parsed-cascade", team=[1])
    mat = Material.objects.create(knowledge_base=kb, name="m", material_type="text", text_content="x")
    locator = f"wiki/parsed/{kb.id}/{mat.id}/h1.md"
    MaterialVersion.objects.create(material=mat, content_hash="h1", content_locator=locator)
    monkeypatch.setattr(material_service, "_PARSED_STORAGE", Storage())

    with django_capture_on_commit_callbacks(execute=True):
        kb.delete()
        assert deleted == []

    assert not Material.objects.filter(id=mat.id).exists()
    assert deleted == [locator]


@pytest.mark.django_db
def test_deleting_one_kb_keeps_other_kb_parsed_markdown(monkeypatch, django_capture_on_commit_callbacks):
    """删除一个知识库时,只删除该库资料版本的解析产物,不碰其它知识库。"""
    from apps.opspilot.models import Material, MaterialVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki import material_service

    deleted = []

    class Storage:
        def delete(self, name):
            deleted.append(name)

    removed_kb = WikiKnowledgeBase.objects.create(name="removed", team=[1])
    kept_kb = WikiKnowledgeBase.objects.create(name="kept", team=[1])
    removed_material = Material.objects.create(knowledge_base=removed_kb, name="removed", material_type="text", text_content="x")
    kept_material = Material.objects.create(knowledge_base=kept_kb, name="kept", material_type="text", text_content="x")
    removed_locator = f"wiki/parsed/{removed_kb.id}/{removed_material.id}/removed.md"
    kept_locator = f"wiki/parsed/{kept_kb.id}/{kept_material.id}/kept.md"
    MaterialVersion.objects.create(material=removed_material, content_hash="h1", content_locator=removed_locator)
    MaterialVersion.objects.create(material=kept_material, content_hash="h2", content_locator=kept_locator)
    monkeypatch.setattr(material_service, "_PARSED_STORAGE", Storage())

    with django_capture_on_commit_callbacks(execute=True):
        removed_kb.delete()
        assert deleted == []

    assert deleted == [removed_locator]
    assert Material.objects.filter(id=kept_material.id).exists()
    assert MaterialVersion.objects.filter(content_locator=kept_locator).exists()


@pytest.mark.django_db
def test_delete_kb_endpoint_removes_only_its_parsed_prefix_orphans(monkeypatch, api_client):
    """知识库删除应清理自身 parsed 残留,但不能清理其它知识库或更宽 wiki 目录。"""
    from apps.opspilot.models import WikiKnowledgeBase
    from apps.opspilot.services.wiki import material_service

    deleted = []
    removed_kb = WikiKnowledgeBase.objects.create(name="removed-prefix", team=[1])
    kept_kb = WikiKnowledgeBase.objects.create(name="kept-prefix", team=[1])
    removed_orphan = f"wiki/parsed/{removed_kb.id}/999/orphan.md"
    removed_nested = f"wiki/parsed/{removed_kb.id}/888/nested.md"
    kept_orphan = f"wiki/parsed/{kept_kb.id}/999/orphan.md"
    similar_prefix = f"wiki/parsed/{removed_kb.id}0/999/not-this-kb.md"
    unrelated = "wiki/materials/loose-file.md"

    class Storage:
        bucket = "munchkin-private"

        def __init__(self):
            self.objects = {removed_orphan, removed_nested, kept_orphan, similar_prefix, unrelated}

        def listdir(self, bucket_name):
            assert bucket_name == self.bucket
            return [(name, object()) for name in sorted(self.objects)]

        def delete(self, name):
            deleted.append(name)
            self.objects.discard(name)

    storage = Storage()
    monkeypatch.setattr(material_service, "_PARSED_STORAGE", storage)

    response = api_client.delete(f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{removed_kb.id}/")

    assert response.status_code == 200, response.content
    assert set(deleted) == {removed_orphan, removed_nested}
    assert kept_orphan in storage.objects
    assert similar_prefix in storage.objects
    assert unrelated in storage.objects


def test_delete_knowledge_base_parsed_markdown_filters_prefix_and_locator_shape(monkeypatch):
    from apps.opspilot.services.wiki import material_service
    from apps.opspilot.services.wiki.parsed_storage_service import delete_knowledge_base_parsed_markdown

    deleted = []

    class Storage:
        bucket = "munchkin-private"

        def listdir(self, bucket_name):
            assert bucket_name == self.bucket
            return [
                ("wiki/parsed/42/1/a.md", object()),
                ("wiki/parsed/42/1/not-markdown.txt", object()),
                ("wiki/parsed/42/orphan.md", object()),
                ("wiki/parsed/420/1/other.md", object()),
                ("wiki/parsed/4/2/wrong.md", object()),
            ]

        def delete(self, name):
            deleted.append(name)

    monkeypatch.setattr(material_service, "_PARSED_STORAGE", Storage())

    invalid = delete_knowledge_base_parsed_markdown("bad")
    result = delete_knowledge_base_parsed_markdown(42)

    assert invalid == {"prefix": "", "deleted": 0, "skipped": 0}
    assert result == {"prefix": "wiki/parsed/42/", "deleted": 1, "skipped": 4}
    assert deleted == ["wiki/parsed/42/1/a.md"]


def test_delete_knowledge_base_parsed_markdown_handles_object_items_delete_failures_and_scan_errors(monkeypatch):
    from types import SimpleNamespace

    from apps.opspilot.services.wiki import material_service
    from apps.opspilot.services.wiki.parsed_storage_service import delete_knowledge_base_parsed_markdown

    class ObjectStorage:
        bucket = "munchkin-private"

        def listdir(self, bucket_name):
            assert bucket_name == self.bucket
            return [SimpleNamespace(object_name="wiki/parsed/7/1/a.md")]

    class BrokenStorage:
        bucket = "munchkin-private"

        def listdir(self, bucket_name):
            raise RuntimeError("minio down")

    monkeypatch.setattr(material_service, "_PARSED_STORAGE", ObjectStorage())
    monkeypatch.setattr(material_service, "delete_parsed_markdown", lambda name: False)

    negative = delete_knowledge_base_parsed_markdown(-1)
    failed_delete = delete_knowledge_base_parsed_markdown(7)

    monkeypatch.setattr(material_service, "_PARSED_STORAGE", BrokenStorage())
    scan_failed = delete_knowledge_base_parsed_markdown(8)

    assert negative == {"prefix": "", "deleted": 0, "skipped": 0}
    assert failed_delete == {"prefix": "wiki/parsed/7/", "deleted": 0, "skipped": 1}
    assert scan_failed == {"prefix": "wiki/parsed/8/", "deleted": 0, "skipped": 0}


@pytest.mark.django_db(transaction=True)
def test_material_delete_defers_cascade_until_outer_transaction_commits(monkeypatch):
    from django.db import transaction

    from apps.opspilot.models import BuildRecord, PageEvidence
    from apps.opspilot.services.wiki import update_service

    kb = _kb()
    material = _material(kb)
    page = _page(kb)
    PageEvidence.objects.create(page=page, material=material)
    calls = []

    def fake_cascade(cascade_kb, page_ids, event):
        calls.append((cascade_kb.id, list(page_ids), event))
        return {
            "status": "success",
            "event": event,
            "affected_page_ids": list(page_ids),
            "stages": {},
        }

    monkeypatch.setattr(update_service, "cascade", fake_cascade)

    with transaction.atomic():
        build = update_service.handle_material_deletion(material, operator="admin")
        assert calls == []
        assert build.status == "partial"
        assert build.stage == "done"
        assert build.progress == 100
        assert build.maintenance["status"] == "partial"

    build.refresh_from_db()
    assert calls == [(kb.id, [page.id], "material_delete")]
    assert build.status == "success"
    assert BuildRecord.objects.filter(pk=build.pk).exists()


@pytest.mark.django_db(transaction=True)
def test_material_delete_partial_cascade_persists_stage_errors(monkeypatch):
    from apps.opspilot.models import PageEvidence
    from apps.opspilot.services.wiki import update_service

    kb = _kb()
    material = _material(kb, "partial-cascade")
    page = _page(kb, "partial-cascade-page")
    PageEvidence.objects.create(page=page, material=material)

    monkeypatch.setattr(
        update_service,
        "cascade",
        lambda cascade_kb, page_ids, event: {
            "status": "partial",
            "event": event,
            "affected_page_ids": list(page_ids),
            "stages": {
                "relations": {
                    "status": "failed",
                    "error": "relations unavailable",
                }
            },
        },
    )

    build = update_service.handle_material_deletion(material, operator="admin")

    build.refresh_from_db()
    assert build.status == "partial"
    assert build.stage == "done"
    assert build.progress == 100
    assert build.errors == ["relations unavailable"]


@pytest.mark.django_db(transaction=True)
def test_material_delete_outer_rollback_does_not_run_cascade(monkeypatch):
    from django.db import transaction

    from apps.opspilot.models import BuildRecord, Material, PageEvidence
    from apps.opspilot.services.wiki import update_service

    kb = _kb()
    material = _material(kb)
    material_id = material.id
    page = _page(kb)
    PageEvidence.objects.create(page=page, material=material)
    calls = []

    monkeypatch.setattr(
        update_service,
        "cascade",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    with pytest.raises(RuntimeError, match="rollback material delete"):
        with transaction.atomic():
            build = update_service.handle_material_deletion(material, operator="admin")
            assert calls == []
            raise RuntimeError("rollback material delete")

    assert calls == []
    assert Material.objects.filter(pk=material_id).exists()
    assert not BuildRecord.objects.filter(pk=build.pk).exists()
    assert PageEvidence.objects.filter(page=page, material_id=material_id).exists()
