import pytest


def _kb():
    from apps.opspilot.models import WikiKnowledgeBase

    return WikiKnowledgeBase.objects.create(name="kb", team=[1])


def _page(kb, title, body="", page_type="concept", tags=None):
    from apps.opspilot.models import KnowledgePage, PageVersion

    page = KnowledgePage.objects.create(knowledge_base=kb, page_type=page_type, title=title, contribution="ai", tags=tags or [])
    v = PageVersion.objects.create(page=page, no=1, body=body, change_type="ai_create", is_current=True)
    page.current_version = v
    page.save(update_fields=["current_version"])
    return page


def _evi(page, material):
    from apps.opspilot.models import PageEvidence

    PageEvidence.objects.create(page=page, material=material)


def _material(kb, name="m"):
    from apps.opspilot.models import Material

    return Material.objects.create(knowledge_base=kb, name=name, material_type="text")


@pytest.mark.django_db
def test_weight_combines_multiple_signals():
    from apps.opspilot.services.wiki.graph_service import SIGNAL_WEIGHTS, analyze_graph

    kb = _kb()
    mat = _material(kb)
    a = _page(kb, "A", page_type="howto", tags=["net", "ops"])
    b = _page(kb, "B", page_type="howto", tags=["net"])
    _evi(a, mat)
    _evi(b, mat)  # 共享 1 资料 + 共享 1 标签(net)+ 同类型 howto

    g = analyze_graph(kb)
    assert len(g["edges"]) == 1
    e = g["edges"][0]
    expected = SIGNAL_WEIGHTS["shared_source"] * 1 + SIGNAL_WEIGHTS["shared_tags"] * 1 + SIGNAL_WEIGHTS["same_type"]
    assert e["weight"] == round(expected, 3)
    assert e["signals"] == {"shared_source": 1, "shared_tags": 1, "same_type": 1}


@pytest.mark.django_db
def test_reference_signal_and_communities():
    from apps.opspilot.services.wiki.graph_service import analyze_graph

    kb = _kb()
    # 两个强关联对,彼此无关 -> 两个社区
    a = _page(kb, "A", body="see [[B]]", page_type="t1", tags=["x"])
    b = _page(kb, "B", page_type="t1", tags=["x"])
    c = _page(kb, "C", page_type="t2", tags=["y"])
    d = _page(kb, "D", body="see [[C]]", page_type="t2", tags=["y"])

    g = analyze_graph(kb)
    # A-B 有引用 + 共享标签 + 同类型;C-D 同理
    ab = next(e for e in g["edges"] if {e["from"], e["to"]} == {a.id, b.id})
    assert "reference" in ab["signals"]
    assert g["insights"]["community_count"] == 2
    comm = {n["id"]: n["community"] for n in g["nodes"]}
    assert comm[a.id] == comm[b.id] and comm[c.id] == comm[d.id]
    assert comm[a.id] != comm[c.id]


@pytest.mark.django_db
class TestGraphAnalysisView:
    def test_endpoint(self, api_client):
        kb = _kb()
        _page(kb, "A", body="[[B]]", tags=["x"])
        _page(kb, "B", tags=["x"])
        r = api_client.get(f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{kb.id}/graph_analysis/")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["insights"]["edge_count"] >= 1
        assert "signal_weights" in data["insights"]
