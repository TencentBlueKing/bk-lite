import pytest


def _kb():
    from apps.opspilot.models import WikiKnowledgeBase

    return WikiKnowledgeBase.objects.create(name="kb", team=[1])


def _page(kb, title):
    from apps.opspilot.services.wiki.page_service import create_manual_page

    return create_manual_page(kb, page_type="concept", title=title, body="", created_by="u")


def _rel(a, b, rtype="reference"):
    from apps.opspilot.models import PageRelation

    return PageRelation.objects.create(from_page=a, to_page=b, relation_type=rtype, weight=1.0)


@pytest.mark.django_db
def test_graph_clusters_and_isolated():
    from apps.opspilot.services.wiki.graph_service import build_graph

    kb = _kb()
    a, b, c = _page(kb, "A"), _page(kb, "B"), _page(kb, "C")
    _rel(a, b)  # A-B 一个社区;C 孤立

    g = build_graph(kb)
    assert g["insights"]["node_count"] == 3
    assert g["insights"]["edge_count"] == 1
    assert g["insights"]["cluster_count"] == 2
    assert g["insights"]["isolated"] == [c.id]
    assert g["insights"]["largest_cluster"] == 2
    # A、B 同社区,C 不同
    cluster = {n["id"]: n["cluster"] for n in g["nodes"]}
    assert cluster[a.id] == cluster[b.id] and cluster[c.id] != cluster[a.id]
    assert {n["id"]: n["degree"] for n in g["nodes"]}[c.id] == 0


@pytest.mark.django_db
def test_graph_hub_ranked_by_degree():
    from apps.opspilot.services.wiki.graph_service import build_graph

    kb = _kb()
    hub, x, y = _page(kb, "hub"), _page(kb, "X"), _page(kb, "Y")
    _rel(hub, x)
    _rel(hub, y)

    g = build_graph(kb)
    assert g["insights"]["hubs"][0]["id"] == hub.id
    assert g["insights"]["hubs"][0]["degree"] == 2


@pytest.mark.django_db
def test_graph_collapses_alias_nodes_to_canonical_title():
    from apps.opspilot.services.wiki.graph_service import build_graph

    kb = _kb()
    kb.generation_rules = {"title_aliases": [{"canonical": "配置平台", "aliases": ["CMDB"]}]}
    kb.save(update_fields=["generation_rules"])
    alias = _page(kb, "CMDB")
    canonical = _page(kb, "配置平台")
    source = _page(kb, "业务系统")
    _rel(source, alias)
    _rel(source, canonical)

    graph = build_graph(kb)

    titles = {node["title"] for node in graph["nodes"]}
    assert "CMDB" not in titles
    assert "配置平台" in titles
    canonical_node = next(node for node in graph["nodes"] if node["title"] == "配置平台")
    assert canonical_node["id"] == canonical.id
    assert canonical_node["page_ids"] == [alias.id, canonical.id]
    assert canonical_node["aliases"] == ["CMDB"]
    assert graph["insights"]["node_count"] == 2
    edges = [edge for edge in graph["edges"] if {edge["from"], edge["to"]} == {source.id, canonical.id}]
    assert len(edges) == 1
    assert edges[0]["weight"] == 2.0


@pytest.mark.django_db
class TestGraphView:
    def test_graph_endpoint(self, api_client):
        kb = _kb()
        a, b = _page(kb, "A"), _page(kb, "B")
        _rel(a, b)
        r = api_client.get(f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{kb.id}/graph/")
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data["nodes"]) == 2 and len(data["edges"]) == 1
