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
def test_reference_signal_uses_canonical_title_aliases():
    from apps.opspilot.services.wiki.graph_service import analyze_graph

    kb = _kb()
    kb.generation_rules = {"title_aliases": [{"canonical": "配置平台", "aliases": ["CMDB"]}]}
    kb.save(update_fields=["generation_rules"])
    source = _page(kb, "业务系统", body="依赖 [[CMDB]] 提供配置数据。", page_type="system")
    target = _page(kb, "配置平台", page_type="platform")

    graph = analyze_graph(kb)

    edge = next(edge for edge in graph["edges"] if {edge["from"], edge["to"]} == {source.id, target.id})
    assert edge["signals"]["reference"] == 1


@pytest.mark.django_db
def test_graph_analysis_collapses_alias_nodes_to_canonical_title():
    from apps.opspilot.services.wiki.graph_service import analyze_graph

    kb = _kb()
    kb.generation_rules = {"title_aliases": [{"canonical": "配置平台", "aliases": ["CMDB"]}]}
    kb.save(update_fields=["generation_rules"])
    alias = _page(kb, "CMDB", page_type="platform")
    canonical = _page(kb, "配置平台", page_type="platform")
    source = _page(kb, "业务系统", body="依赖 [[CMDB]] 提供配置数据。", page_type="system")

    graph = analyze_graph(kb)

    titles = {node["title"] for node in graph["nodes"]}
    assert "CMDB" not in titles
    assert "配置平台" in titles
    canonical_node = next(node for node in graph["nodes"] if node["title"] == "配置平台")
    assert canonical_node["id"] == canonical.id
    assert canonical_node["page_ids"] == [alias.id, canonical.id]
    assert canonical_node["aliases"] == ["CMDB"]
    assert graph["insights"]["node_count"] == 2
    edge = next(edge for edge in graph["edges"] if {edge["from"], edge["to"]} == {source.id, canonical.id})
    assert edge["signals"]["reference"] == 1


@pytest.mark.django_db
def test_graph_analysis_reports_strong_edges_between_communities():
    from apps.opspilot.services.wiki.graph_service import SIGNAL_WEIGHTS, analyze_graph

    kb = _kb()
    material_a = _material(kb, "source-a")
    material_b = _material(kb, "source-b")
    a1 = _page(kb, "A1", page_type="group-a", tags=["group-a"])
    a2 = _page(kb, "A2", page_type="group-a", tags=["group-a"])
    a3 = _page(kb, "A3", body="跨域依赖 [[B1]]。", page_type="group-a", tags=["group-a", "handoff"])
    b1 = _page(kb, "B1", page_type="group-b", tags=["group-b", "handoff"])
    b2 = _page(kb, "B2", page_type="group-b", tags=["group-b"])
    b3 = _page(kb, "B3", page_type="group-b", tags=["group-b"])
    for page in [a1, a2, a3]:
        _evi(page, material_a)
    for page in [b1, b2, b3]:
        _evi(page, material_b)

    graph = analyze_graph(kb)

    cross_edges = graph["insights"]["cross_community_edges"]
    assert len(cross_edges) == 1
    cross = cross_edges[0]
    assert {cross["from"], cross["to"]} == {a3.id, b1.id}
    assert cross["from_community"] != cross["to_community"]
    assert cross["signals"] == {"shared_tags": 1, "reference": 1}
    expected_weight = SIGNAL_WEIGHTS["shared_tags"] + SIGNAL_WEIGHTS["reference"]
    assert cross["weight"] == round(expected_weight, 3)


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
