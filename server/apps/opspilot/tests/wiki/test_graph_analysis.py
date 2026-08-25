import pytest


def _kb(name="kb-graph-analysis"):
    from apps.opspilot.models import WikiKnowledgeBase
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base

    kb = WikiKnowledgeBase.objects.create(name=name, team=[1], purpose_md="# Purpose", schema_md="# Schema")
    bootstrap_knowledge_base(kb, operator="tester")
    kb.refresh_from_db()
    return kb


def _page(kb, title, body="", page_type="concept", tags=None):
    from apps.opspilot.services.wiki.page_service import create_manual_page

    return create_manual_page(
        knowledge_base=kb,
        page_type=page_type,
        title=title,
        body=body,
        tags=tags or [],
        created_by="tester",
        contribution="ai",
        update_method="ai_create",
        change_type="ai_create",
    )


def _material(kb, name="m"):
    from apps.opspilot.models import Material

    return Material.objects.create(knowledge_base=kb, name=name, material_type="text")


def _evi(page, material):
    from apps.opspilot.models import PageEvidence

    PageEvidence.objects.create(page=page, material=material)


def _rel(kb, a, b, rtype="reference", weight=1.0):
    from apps.opspilot.models import PageRelation

    kb.refresh_from_db()
    from_page, to_page = (a, b)
    if rtype == "shared_source":
        from_page, to_page = sorted((a, b), key=lambda page: page.id)
    return PageRelation.objects.create(
        from_page=from_page,
        to_page=to_page,
        relation_type=rtype,
        weight=weight,
        generation_id=kb.active_generation_id,
    )


@pytest.mark.django_db
def test_weight_combines_multiple_signals():
    from apps.opspilot.services.wiki.graph_service import SIGNAL_WEIGHTS, analyze_graph

    kb = _kb("kb-weight-signals")
    mat = _material(kb)
    a = _page(kb, "A", page_type="howto", tags=["net", "ops"])
    b = _page(kb, "B", page_type="howto", tags=["net"])
    _evi(a, mat)
    _evi(b, mat)
    _rel(kb, a, b, "shared_source", weight=1.0)  # 代际关系表提供 shared_source

    g = analyze_graph(kb)
    assert len(g["edges"]) == 1
    e = g["edges"][0]
    expected = SIGNAL_WEIGHTS["shared_source"] * 1 + SIGNAL_WEIGHTS["shared_tags"] * 1 + SIGNAL_WEIGHTS["same_type"]
    assert e["weight"] == round(expected, 3)
    assert e["signals"] == {"shared_source": 1, "shared_tags": 1, "same_type": 1}


@pytest.mark.django_db
def test_pure_same_type_does_not_create_edge():
    from apps.opspilot.services.wiki.graph_service import analyze_graph

    kb = _kb("kb-pure-same-type")
    _page(kb, "A", page_type="howto")
    _page(kb, "B", page_type="howto")
    _page(kb, "C", page_type="howto")

    g = analyze_graph(kb)
    assert g["edges"] == []
    assert g["insights"]["analysis_edge_count"] == 0
    assert g["insights"]["edge_prune"]["drop_pure_same_type"] is True


def test_prune_display_edges_keeps_top_k_per_node():
    from apps.opspilot.services.wiki.graph_service import _prune_display_edges

    edges = [
        {"from": 1, "to": 2, "weight": 3.0, "signals": {}},
        {"from": 1, "to": 3, "weight": 2.0, "signals": {}},
        {"from": 1, "to": 4, "weight": 1.0, "signals": {}},
        {"from": 2, "to": 3, "weight": 0.5, "signals": {}},
    ]
    pruned = _prune_display_edges(edges, max_per_node=1, max_total=100)
    keys = {tuple(sorted((edge["from"], edge["to"]))) for edge in pruned}
    # 1 保留 1-2; 3 保留 1-3; 4 保留 1-4; 2-3 因两端都不优先而被丢弃
    assert keys == {(1, 2), (1, 3), (1, 4)}


def test_prune_display_edges_applies_global_cap():
    from apps.opspilot.services.wiki.graph_service import _prune_display_edges

    edges = [{"from": i, "to": i + 1, "weight": float(i), "signals": {}} for i in range(1, 6)]
    pruned = _prune_display_edges(edges, max_per_node=8, max_total=2)
    assert [edge["weight"] for edge in pruned] == [5.0, 4.0]


@pytest.mark.django_db
def test_reference_signal_and_communities():
    from apps.opspilot.services.wiki.graph_service import analyze_graph

    kb = _kb("kb-ref-communities")
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

    kb = _kb("kb-alias-ref")
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

    kb = _kb("kb-alias-collapse")
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

    kb = _kb("kb-cross-community")
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
    for left, right in ((a1, a2), (a1, a3), (a2, a3)):
        _rel(kb, left, right, "shared_source", weight=1.0)
    for left, right in ((b1, b2), (b1, b3), (b2, b3)):
        _rel(kb, left, right, "shared_source", weight=1.0)

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
        kb = _kb("kb-graph-analysis-view")
        _page(kb, "A", body="[[B]]", tags=["x"])
        _page(kb, "B", tags=["x"])
        r = api_client.get(f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{kb.id}/graph_analysis/")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["insights"]["edge_count"] >= 1
        assert "signal_weights" in data["insights"]
        assert data["insights"]["edge_prune"]["drop_pure_same_type"] is True
