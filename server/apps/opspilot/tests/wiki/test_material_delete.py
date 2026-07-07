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


@pytest.mark.django_db
def test_deleting_only_source_flags_page_for_review():
    from apps.opspilot.models import CheckItem, Material, PageEvidence
    from apps.opspilot.services.wiki.update_service import handle_material_deletion

    kb = _kb()
    mat = _material(kb)
    page = _page(kb)
    PageEvidence.objects.create(page=page, material=mat)

    build = handle_material_deletion(mat, operator="sys")

    assert not Material.objects.filter(id=mat.id).exists()
    assert build.counts["pending_review"] == 1
    assert CheckItem.objects.filter(knowledge_base=kb, check_type="source_invalid", related__pages__contains=[page.id]).exists()


@pytest.mark.django_db
def test_page_with_remaining_source_not_flagged():
    from apps.opspilot.models import CheckItem, PageEvidence
    from apps.opspilot.services.wiki.update_service import handle_material_deletion

    kb = _kb()
    m1, m2 = _material(kb, "m1"), _material(kb, "m2")
    page = _page(kb)
    PageEvidence.objects.create(page=page, material=m1)
    PageEvidence.objects.create(page=page, material=m2)

    build = handle_material_deletion(m1, operator="sys")

    assert build.counts["pending_review"] == 0
    assert not CheckItem.objects.filter(knowledge_base=kb, check_type="source_invalid").exists()


@pytest.mark.django_db
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


@pytest.mark.django_db
class TestDeleteView:
    def test_delete_impact_endpoint_reports_source_loss_without_mutation(self, api_client):
        from apps.opspilot.models import Material, PageEvidence

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
        only_source.refresh_from_db()
        shared_source.refresh_from_db()
        assert only_source.status == "active"
        assert shared_source.status == "active"

    def test_destroy_endpoint_reports_impact(self, api_client):
        from apps.opspilot.models import Material, PageEvidence

        kb = _kb()
        mat = _material(kb)
        page = _page(kb)
        PageEvidence.objects.create(page=page, material=mat)

        r = api_client.delete(f"/api/v1/opspilot/wiki_mgmt/material/{mat.id}/")
        assert r.status_code == 200
        assert r.json()["data"]["pending_review"] == 1
        assert not Material.objects.filter(id=mat.id).exists()


@pytest.mark.django_db
def test_deleting_file_material_removes_minio_file(monkeypatch):
    """删除 file 资料应删除其 MinIO 文件对象(post_delete 信号)。"""
    from apps.opspilot.models import Material
    from apps.opspilot.services.wiki.update_service import handle_material_deletion

    deleted = []
    kb = _kb()
    mat = Material.objects.create(knowledge_base=kb, name="f", material_type="file")
    monkeypatch.setattr(type(mat.file.storage), "delete", lambda self, name: deleted.append(name))
    mat.file = "fake/material.txt"  # 模拟已上传文件(字符串赋值不触发真实上传)

    handle_material_deletion(mat, operator="sys")

    assert deleted == ["fake/material.txt"]


@pytest.mark.django_db
def test_deleting_material_removes_parsed_markdown_versions(monkeypatch):
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

    handle_material_deletion(mat, operator="sys")

    assert set(deleted) == {first_locator, second_locator}


@pytest.mark.django_db
def test_deleting_material_skips_parsed_markdown_locator_for_other_material(monkeypatch):
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
def test_deleting_kb_cascade_removes_material_minio_files(monkeypatch):
    """删除知识库 → 级联删资料 → 同样触发 post_delete,删除 MinIO 文件。"""
    from apps.opspilot.models import Material, WikiKnowledgeBase

    deleted = []
    kb = WikiKnowledgeBase.objects.create(name="kb-cascade", team=[1])
    mat = Material.objects.create(knowledge_base=kb, name="f", material_type="file", file="fake/cascade.txt")
    monkeypatch.setattr(type(mat.file.storage), "delete", lambda self, name: deleted.append(name))

    kb.delete()

    assert not Material.objects.filter(id=mat.id).exists()
    assert "fake/cascade.txt" in deleted


@pytest.mark.django_db
def test_deleting_kb_cascade_removes_parsed_markdown_versions(monkeypatch):
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

    kb.delete()

    assert not Material.objects.filter(id=mat.id).exists()
    assert deleted == [locator]


@pytest.mark.django_db
def test_deleting_one_kb_keeps_other_kb_parsed_markdown(monkeypatch):
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

    removed_kb.delete()

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
