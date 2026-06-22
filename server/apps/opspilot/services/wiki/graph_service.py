"""关系图谱(P5):由 PageRelation 装配图,做连通分量聚类 + 基础洞察。

MVP 以"连通分量"作为社区(无外部依赖、跨 DB 可用);Louvain 社区发现 + 4 信号
关联度加权留待增强(需 networkx/python-louvain)。洞察包含孤立节点、枢纽页(高度数)等。
"""

from collections import defaultdict

from apps.opspilot.models import KnowledgePage, PageRelation


def build_graph(knowledge_base):
    """返回 {nodes, edges, clusters, insights}。节点附带 cluster/degree。"""
    pages = list(KnowledgePage.objects.filter(knowledge_base=knowledge_base, status="active"))
    node_ids = {p.id for p in pages}
    nodes = [{"id": p.id, "title": p.title, "page_type": p.page_type, "contribution": p.contribution} for p in pages]

    rels = PageRelation.objects.filter(from_page__knowledge_base=knowledge_base)
    edges, adj, degree = [], defaultdict(set), defaultdict(int)
    for r in rels.values("from_page_id", "to_page_id", "relation_type", "weight"):
        a, b = r["from_page_id"], r["to_page_id"]
        edges.append({"from": a, "to": b, "relation_type": r["relation_type"], "weight": r["weight"]})
        if a in node_ids and b in node_ids and a != b:
            adj[a].add(b)
            adj[b].add(a)
            degree[a] += 1
            degree[b] += 1

    clusters = _connected_components(node_ids, adj)
    cluster_of = {nid: idx for idx, comp in enumerate(clusters) for nid in comp}
    for n in nodes:
        n["cluster"] = cluster_of.get(n["id"], -1)
        n["degree"] = degree[n["id"]]

    isolated = sorted(nid for nid in node_ids if degree[nid] == 0)
    hubs = sorted(
        ({"id": nid, "degree": degree[nid]} for nid in node_ids if degree[nid] > 0),
        key=lambda x: x["degree"],
        reverse=True,
    )[:5]
    insights = {
        "node_count": len(node_ids),
        "edge_count": len(edges),
        "cluster_count": len(clusters),
        "isolated": isolated,
        "largest_cluster": max((len(c) for c in clusters), default=0),
        "hubs": hubs,
    }
    return {"nodes": nodes, "edges": edges, "clusters": [sorted(c) for c in clusters], "insights": insights}


def _connected_components(node_ids, adj):
    seen, comps = set(), []
    for start in sorted(node_ids):
        if start in seen:
            continue
        stack, comp = [start], set()
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            comp.add(n)
            stack.extend(adj[n] - seen)
        comps.append(comp)
    return comps
