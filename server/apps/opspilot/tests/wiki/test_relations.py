import pytest


def _kb():
    from apps.opspilot.models import WikiKnowledgeBase

    return WikiKnowledgeBase.objects.create(name="kb", team=[1])


def _page(kb, title, body=""):
    from apps.opspilot.services.wiki.page_service import create_manual_page

    return create_manual_page(kb, page_type="concept", title=title, body=body, created_by="u")


def _material(kb, name="m"):
    from apps.opspilot.models import Material

    return Material.objects.create(knowledge_base=kb, name=name, material_type="text", text_content="x")


@pytest.mark.django_db
def test_shared_source_links_pages_built_from_same_material():
    from apps.opspilot.models import PageEvidence
    from apps.opspilot.services.wiki.relation_service import rebuild_relations

    kb = _kb()
    a, b = _page(kb, "A"), _page(kb, "B")
    mat = _material(kb)
    PageEvidence.objects.create(page=a, material=mat)
    PageEvidence.objects.create(page=b, material=mat)

    created = rebuild_relations(kb)
    assert len(created) == 1
    rel = created[0]
    assert rel.relation_type == "shared_source"
    assert {rel.from_page_id, rel.to_page_id} == {a.id, b.id}
    assert rel.from_page_id < rel.to_page_id  # 无向只存一条(小 id 在前)
    assert rel.via_material_id == mat.id


@pytest.mark.django_db
def test_reference_link_in_body_creates_directed_relation():
    from apps.opspilot.services.wiki.relation_service import rebuild_relations

    kb = _kb()
    target = _page(kb, "重启服务")
    src = _page(kb, "故障处理", body="详见 [[重启服务]] 一节。")

    created = rebuild_relations(kb)
    refs = [r for r in created if r.relation_type == "reference"]
    assert len(refs) == 1
    assert refs[0].from_page_id == src.id and refs[0].to_page_id == target.id


@pytest.mark.django_db
def test_reference_link_matches_normalized_title_and_alias():
    from apps.opspilot.services.wiki.relation_service import rebuild_relations

    kb = _kb()
    target = _page(kb, "KV Cache")
    src = _page(kb, "推理优化", body="详见 [[kv-cache|KV 缓存]]。")

    rebuild_relations(kb)

    refs = list(src.relations_out.filter(relation_type="reference"))
    assert len(refs) == 1
    assert refs[0].to_page_id == target.id


@pytest.mark.django_db
def test_reference_link_resolves_title_alias_to_canonical_page():
    from apps.opspilot.models import CheckItem, PageRelation
    from apps.opspilot.services.wiki.relation_service import rebuild_relations

    kb = _kb()
    target = _page(kb, "配置平台", body="配置平台负责配置数据管理。")
    source = _page(kb, "业务系统", body="依赖 [[CMDB]] 提供配置数据。")

    rebuild_relations(kb)

    assert PageRelation.objects.filter(from_page=source, to_page=target, relation_type="reference").exists()
    assert not CheckItem.objects.filter(knowledge_base=kb, check_type="broken_relation").exists()


@pytest.mark.django_db
def test_ambiguous_wikilink_creates_check_without_relation():
    from apps.opspilot.models import CheckItem, PageRelation
    from apps.opspilot.services.wiki.relation_service import rebuild_relations

    kb = _kb()
    _page(kb, "AI")
    _page(kb, "A-I")
    src = _page(kb, "overview", body="See [[ai]].")

    rebuild_relations(kb)

    assert not PageRelation.objects.filter(from_page=src, relation_type="reference").exists()
    assert CheckItem.objects.filter(knowledge_base=kb, check_type="ambiguous_link", related__pages__contains=[src.id]).exists()


@pytest.mark.django_db
def test_broken_wikilink_creates_check_without_relation():
    from apps.opspilot.models import CheckItem, PageRelation
    from apps.opspilot.services.wiki.relation_service import rebuild_relations

    kb = _kb()
    src = _page(kb, "overview", body="See [[missing-page]].")

    rebuild_relations(kb)

    assert not PageRelation.objects.filter(from_page=src, relation_type="reference").exists()
    assert CheckItem.objects.filter(knowledge_base=kb, check_type="broken_relation", related__pages__contains=[src.id]).exists()


@pytest.mark.django_db
def test_rebuild_is_idempotent():
    from apps.opspilot.models import PageEvidence, PageRelation
    from apps.opspilot.services.wiki.relation_service import rebuild_relations

    kb = _kb()
    a, b = _page(kb, "A"), _page(kb, "B")
    mat = _material(kb)
    PageEvidence.objects.create(page=a, material=mat)
    PageEvidence.objects.create(page=b, material=mat)

    rebuild_relations(kb)
    rebuild_relations(kb)
    assert PageRelation.objects.filter(from_page__knowledge_base=kb).count() == 1


@pytest.mark.django_db
def test_related_page_not_flagged_orphan_by_scan():
    from apps.opspilot.models import CheckItem, PageEvidence
    from apps.opspilot.services.wiki.check_service import scan_health
    from apps.opspilot.services.wiki.relation_service import rebuild_relations

    kb = _kb()
    a, b = _page(kb, "A"), _page(kb, "B")
    mat = _material(kb)
    PageEvidence.objects.create(page=a, material=mat)
    PageEvidence.objects.create(page=b, material=mat)
    rebuild_relations(kb)

    scan_health(kb)
    # 两页面均有证据(非孤立),不应产生 orphan
    assert not CheckItem.objects.filter(knowledge_base=kb, check_type="orphan").exists()


@pytest.mark.django_db
class TestRelationViews:
    def test_rebuild_and_list_endpoints(self, api_client):
        from apps.opspilot.models import PageEvidence

        kb = _kb()
        a, b = _page(kb, "A"), _page(kb, "B")
        mat = _material(kb)
        PageEvidence.objects.create(page=a, material=mat)
        PageEvidence.objects.create(page=b, material=mat)

        r = api_client.post(f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{kb.id}/rebuild_relations/", {}, format="json")
        assert r.status_code == 200
        assert r.json()["data"]["relations"] == 1

        lst = api_client.get(f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{kb.id}/relations/")
        assert lst.status_code == 200
        edges = lst.json()["data"]
        assert len(edges) == 1 and edges[0]["relation_type"] == "shared_source"
