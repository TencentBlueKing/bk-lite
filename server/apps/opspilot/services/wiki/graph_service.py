"""关系图谱(P5):由 PageRelation 装配图,做连通分量聚类 + 基础洞察。

MVP 以"连通分量"作为社区(无外部依赖、跨 DB 可用);Louvain 社区发现 + 4 信号
关联度加权留待增强(需 networkx/python-louvain)。洞察包含孤立节点、枢纽页(高度数)等。
"""

from collections import defaultdict
from itertools import combinations

from apps.opspilot.models import KnowledgePage, PageEvidence, PageRelation
from apps.opspilot.services.wiki.relation_service import LINK_RE

# 4 信号关联度权重(共享资料 / 共享标签 / 正文引用 / 同类型)。Louvain 用无外部依赖的标签传播替代。
SIGNAL_WEIGHTS = {"shared_source": 1.0, "shared_tags": 0.6, "reference": 0.8, "same_type": 0.3}


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


def analyze_graph(knowledge_base):
    """4 信号关联度加权 + 标签传播社区发现(P5 增强,无外部依赖)。

    对每对页面综合 4 个确定性信号计算关联权重:共享资料数、共享标签数、正文 [[引用]]、同页面类型;
    再以加权图做标签传播(Louvain 的轻量替代)得到社区。返回 {nodes, edges, communities, insights}。
    """
    pages = list(KnowledgePage.objects.filter(knowledge_base=knowledge_base, status="active"))
    by_id = {p.id: p for p in pages}
    node_ids = set(by_id)
    nodes = [{"id": p.id, "title": p.title, "page_type": p.page_type} for p in pages]

    mats = {pid: set(PageEvidence.objects.filter(page_id=pid).values_list("material_id", flat=True)) for pid in node_ids}
    tags = {pid: set(by_id[pid].tags or []) for pid in node_ids}
    refs = _reference_pairs(pages)

    edges, wadj = [], defaultdict(dict)
    for a, b in combinations(sorted(node_ids), 2):
        signals, weight = {}, 0.0
        sc = len(mats[a] & mats[b])
        if sc:
            signals["shared_source"] = sc
            weight += SIGNAL_WEIGHTS["shared_source"] * sc
        tc = len(tags[a] & tags[b])
        if tc:
            signals["shared_tags"] = tc
            weight += SIGNAL_WEIGHTS["shared_tags"] * tc
        if (a, b) in refs or (b, a) in refs:
            signals["reference"] = 1
            weight += SIGNAL_WEIGHTS["reference"]
        if by_id[a].page_type == by_id[b].page_type:
            signals["same_type"] = 1
            weight += SIGNAL_WEIGHTS["same_type"]
        if weight > 0:
            weight = round(weight, 3)
            edges.append({"from": a, "to": b, "weight": weight, "signals": signals})
            wadj[a][b] = weight
            wadj[b][a] = weight

    communities = _label_propagation(node_ids, wadj)
    community_of = {nid: idx for idx, c in enumerate(communities) for nid in c}
    for n in nodes:
        n["community"] = community_of.get(n["id"], -1)

    insights = {
        "node_count": len(node_ids),
        "edge_count": len(edges),
        "community_count": len(communities),
        "largest_community": max((len(c) for c in communities), default=0),
        "strongest_edges": sorted(edges, key=lambda e: e["weight"], reverse=True)[:5],
        "signal_weights": SIGNAL_WEIGHTS,
    }
    return {"nodes": nodes, "edges": edges, "communities": [sorted(c) for c in communities], "insights": insights}


def _reference_pairs(pages):
    """从各页面当前正文解析 [[标题]],返回有向引用对集合 {(from_id, to_id)}。"""
    by_title = {p.title: p.id for p in pages}
    pairs = set()
    for p in pages:
        body = p.current_version.body if p.current_version_id else ""
        for title in LINK_RE.findall(body or ""):
            tid = by_title.get(title.strip())
            if tid and tid != p.id:
                pairs.add((p.id, tid))
    return pairs


def _label_propagation(node_ids, wadj, max_iter=30):
    """确定性标签传播:节点采用邻居中加权得分最高的标签(平票取最小标签)。"""
    label = {n: n for n in node_ids}
    ordered = sorted(node_ids)
    for _ in range(max_iter):
        changed = False
        for n in ordered:
            if not wadj[n]:
                continue
            scores = defaultdict(float)
            for m, w in wadj[n].items():
                scores[label[m]] += w
            best = min(scores.items(), key=lambda kv: (-kv[1], kv[0]))[0]
            if best != label[n]:
                label[n] = best
                changed = True
        if not changed:
            break
    groups = defaultdict(set)
    for n, lab in label.items():
        groups[lab].add(n)
    return [g for g in groups.values()]
