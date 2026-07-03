"""关系图谱(P5):由 PageRelation 装配图,做社区发现 + 基础洞察。

build_graph 以"连通分量"作为粗粒度聚类;analyze_graph 用 **4 信号加权 + 纯 Python Louvain
社区发现**(模块度贪心 + 多层聚合,无外部依赖、跨 DB 可用)。洞察含孤立节点、枢纽页等。
"""

import re
from collections import defaultdict
from itertools import combinations

from apps.opspilot.models import KnowledgePage, PageEvidence, PageRelation
from apps.opspilot.services.wiki.relation_service import LINK_RE, normalize_wikilink_key
from apps.opspilot.services.wiki.title_service import canonical_title

# 4 信号关联度权重(共享资料 / 共享标签 / 正文引用 / 同类型)。Louvain 用无外部依赖的标签传播替代。
SIGNAL_WEIGHTS = {"shared_source": 1.0, "shared_tags": 0.6, "reference": 0.8, "same_type": 0.3}


def build_graph(knowledge_base):
    """返回 {nodes, edges, clusters, insights}。节点附带 cluster/degree。"""
    pages = list(KnowledgePage.objects.filter(knowledge_base=knowledge_base, status="active").order_by("id"))
    graph_nodes = _canonical_graph_nodes(knowledge_base, pages, include_contribution=True)
    node_ids = {node["id"] for node in graph_nodes["nodes"]}
    nodes = graph_nodes["nodes"]
    raw_to_node = graph_nodes["raw_to_node"]

    rels = PageRelation.objects.filter(from_page__knowledge_base=knowledge_base)
    edge_map, adj, degree = {}, defaultdict(set), defaultdict(int)
    for r in rels.values("from_page_id", "to_page_id", "relation_type", "weight"):
        a = raw_to_node.get(r["from_page_id"])
        b = raw_to_node.get(r["to_page_id"])
        if not a or not b or a == b:
            continue
        key = (a, b, r["relation_type"])
        if key not in edge_map:
            edge_map[key] = {"from": a, "to": b, "relation_type": r["relation_type"], "weight": 0.0}
        edge_map[key]["weight"] += float(r["weight"] or 0)

    edges = list(edge_map.values())
    for edge in edges:
        edge["weight"] = round(edge["weight"], 3)
        a, b = edge["from"], edge["to"]
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


def _canonical_graph_nodes(knowledge_base, pages, include_contribution=False):
    groups = defaultdict(list)
    canonical_titles = {}
    for page in sorted(pages, key=lambda item: item.id):
        canonical = (canonical_title(knowledge_base, page.title) or page.title or "").strip()
        key = canonical.lower() or f"__page_{page.id}"
        groups[key].append(page)
        canonical_titles.setdefault(key, canonical or page.title or "")

    nodes = []
    raw_to_node = {}
    for key, group in groups.items():
        display_title = canonical_titles[key]
        representative = _canonical_representative(group, display_title)
        page_ids = sorted(page.id for page in group)
        for page_id in page_ids:
            raw_to_node[page_id] = representative.id
        node = {
            "id": representative.id,
            "title": display_title,
            "page_type": representative.page_type,
            "page_ids": page_ids,
            "aliases": _canonical_alias_titles(group, display_title),
        }
        if include_contribution:
            node["contribution"] = representative.contribution
        nodes.append(node)

    return {
        "nodes": sorted(nodes, key=lambda item: item["id"]),
        "raw_to_node": raw_to_node,
    }


def _canonical_representative(pages, display_title):
    exact = [page for page in pages if (page.title or "").strip() == display_title]
    return sorted(exact or pages, key=lambda item: item.id)[0]


def _canonical_alias_titles(pages, display_title):
    aliases = []
    seen = set()
    for page in sorted(pages, key=lambda item: item.id):
        title = (page.title or "").strip()
        if not title or title == display_title or title in seen:
            continue
        aliases.append(title)
        seen.add(title)
    return aliases


def _connected_components(node_ids, adj):
    node_ids = set(node_ids)
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
            stack.extend((adj[n] & node_ids) - seen)
        comps.append(comp)
    return comps


def _bridge_nodes(node_ids, wadj, by_id, limit=10):
    """Return articulation-like nodes that connect otherwise separate graph areas."""
    node_ids = set(node_ids)
    if len(node_ids) < 3:
        return []
    adj = _weighted_adjacency_sets(wadj)
    base_components = len(_connected_components(node_ids, adj))
    bridges = []
    for node_id in sorted(node_ids):
        degree = len(adj[node_id])
        if degree < 2:
            continue
        components_after_removal = len(_connected_components(node_ids - {node_id}, adj))
        if components_after_removal <= base_components:
            continue
        page = by_id.get(node_id)
        bridges.append(
            {
                "id": node_id,
                "title": page.title if page else "",
                "degree": degree,
                "component_count_after_removal": components_after_removal,
            }
        )
    return sorted(bridges, key=lambda item: (-item["degree"], item["title"], item["id"]))[:limit]


def _weighted_adjacency_sets(wadj):
    adj = defaultdict(set)
    for source, targets in wadj.items():
        for target, weight in targets.items():
            if weight <= 0:
                continue
            adj[source].add(target)
            adj[target].add(source)
    return adj


def _sparse_communities(node_ids, wadj, by_id, min_size=4, max_density=0.5, limit=10):
    """Return connected graph areas that are large enough but weakly linked."""
    node_ids = set(node_ids)
    if len(node_ids) < min_size:
        return []
    adj = _weighted_adjacency_sets(wadj)
    sparse = []
    for component in _connected_components(node_ids, adj):
        size = len(component)
        if size < min_size:
            continue
        possible_edges = size * (size - 1) // 2
        edge_count = sum(1 for source in component for target in adj[source] if target in component and source < target)
        density = round(edge_count / possible_edges, 3) if possible_edges else 0
        if density > max_density:
            continue
        page_ids = sorted(component)
        sparse.append(
            {
                "page_ids": page_ids,
                "titles": [by_id[page_id].title for page_id in page_ids if page_id in by_id],
                "size": size,
                "edge_count": edge_count,
                "possible_edges": possible_edges,
                "density": density,
            }
        )
    return sorted(sparse, key=lambda item: (item["density"], -item["size"], item["page_ids"]))[:limit]


def _cross_community_edges(edges, community_of, by_id, min_weight=1.0, limit=10):
    strong_edges = []
    for edge in edges:
        source = edge["from"]
        target = edge["to"]
        source_community = community_of.get(source, -1)
        target_community = community_of.get(target, -1)
        if source_community < 0 or target_community < 0 or source_community == target_community:
            continue
        weight = float(edge.get("weight") or 0)
        if weight < min_weight:
            continue
        source_page = by_id.get(source)
        target_page = by_id.get(target)
        strong_edges.append(
            {
                "from": source,
                "to": target,
                "from_title": source_page.title if source_page else "",
                "to_title": target_page.title if target_page else "",
                "weight": round(weight, 3),
                "signals": dict(edge.get("signals") or {}),
                "from_community": source_community,
                "to_community": target_community,
            }
        )
    return sorted(strong_edges, key=lambda item: (-item["weight"], item["from_title"], item["to_title"]))[:limit]


def _surprise_links(edges, community_of, by_id, min_weight=2.0, limit=10):
    """惊奇连接:跨社区 + 强边 + 标题不共享显著词(暗示语义远但被某种信号强关联)。

    与 _cross_community_edges 的差异:cross_community 是"任何跨社区强边";surprise_link
    进一步要求两侧标题没有共享显著名词(共用词少于 1),强调"出乎意料"的跨主题关联,
    通常对应值得人工复核的"惊奇发现"。
    """
    surprise = []
    for edge in edges:
        source = edge["from"]
        target = edge["to"]
        source_community = community_of.get(source, -1)
        target_community = community_of.get(target, -1)
        if source_community < 0 or target_community < 0 or source_community == target_community:
            continue
        weight = float(edge.get("weight") or 0)
        if weight < min_weight:
            continue
        source_page = by_id.get(source)
        target_page = by_id.get(target)
        if not source_page or not target_page:
            continue
        from_title = source_page.title
        to_title = target_page.title
        # 计算两侧标题的共有"显著词"(去常见停用词)
        if not from_title.strip() or not to_title.strip():
            continue
        if _shared_significant_words(from_title, to_title) > 0:
            continue
        surprise.append(
            {
                "from": source,
                "to": target,
                "from_title": from_title,
                "to_title": to_title,
                "weight": round(weight, 3),
                "signals": dict(edge.get("signals") or {}),
                "from_community": source_community,
                "to_community": target_community,
            }
        )
    return sorted(surprise, key=lambda item: (-item["weight"], item["from_title"], item["to_title"]))[:limit]


_STOPWORDS = {
    # 中文常见虚词/连接词
    "的",
    "是",
    "在",
    "和",
    "与",
    "或",
    "及",
    "了",
    "也",
    "都",
    "就",
    "但",
    "而",
    "为",
    "对",
    "以",
    "从",
    "到",
    "由",
    "之",
    "其",
    "各",
    "本",
    "此",
    # 英文常见停用词
    "the",
    "a",
    "an",
    "of",
    "for",
    "in",
    "on",
    "to",
    "and",
    "or",
    "is",
    "are",
    "with",
    "by",
    "as",
    "at",
    "be",
    "this",
    "that",
    "it",
    "from",
    "into",
}


def _significant_words(title):
    """从标题提取显著词(中文按 2-gram 切,英文按空格切;去停用词)。"""
    if not title:
        return set()
    words = set()
    text = title.strip()
    # 英文/数字部分:按非字母数字字符切
    for token in re.findall(r"[A-Za-z0-9]+", text):
        if token.lower() not in _STOPWORDS and len(token) > 1:
            words.add(token.lower())
    # 中文部分:剔除非中文字符后 2-gram 切(避免单字噪音)
    chinese = re.sub(r"[^一-鿿]+", "", text)
    for i in range(len(chinese) - 1):
        gram = chinese[i : i + 2]
        if gram not in _STOPWORDS:
            words.add(gram)
    return words


def _shared_significant_words(title_a, title_b):
    """两个标题的共有显著词数量(0 表示语义上明显不同)。"""
    return len(_significant_words(title_a) & _significant_words(title_b))


def analyze_graph(knowledge_base):
    """4 信号关联度加权 + Louvain 社区发现(P5 增强,纯 Python 无外部依赖)。

    对每对页面综合 4 个确定性信号计算关联权重:共享资料数、共享标签数、正文 [[引用]]、同页面类型;
    再以加权图做 Louvain 模块度优化得到社区。返回 {nodes, edges, communities, insights}。
    """
    pages = list(KnowledgePage.objects.filter(knowledge_base=knowledge_base, status="active").order_by("id"))
    by_id = {p.id: p for p in pages}
    raw_node_ids = set(by_id)
    graph_nodes = _canonical_graph_nodes(knowledge_base, pages)
    raw_to_node = graph_nodes["raw_to_node"]
    node_ids = {node["id"] for node in graph_nodes["nodes"]}
    nodes = graph_nodes["nodes"]

    mats = {pid: set(PageEvidence.objects.filter(page_id=pid).values_list("material_id", flat=True)) for pid in raw_node_ids}
    tags = {pid: set(by_id[pid].tags or []) for pid in raw_node_ids}
    refs = _reference_pairs(pages)

    raw_edges = []
    for a, b in combinations(sorted(raw_node_ids), 2):
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
            raw_edges.append({"from": a, "to": b, "weight": weight, "signals": signals})

    edges = _collapse_analysis_edges(raw_edges, raw_to_node)
    wadj = _weighted_adjacency(edges)

    communities = _louvain(node_ids, wadj)
    community_of = {nid: idx for idx, c in enumerate(communities) for nid in c}
    for n in nodes:
        n["community"] = community_of.get(n["id"], -1)

    insights = {
        "node_count": len(node_ids),
        "edge_count": len(edges),
        "community_count": len(communities),
        "largest_community": max((len(c) for c in communities), default=0),
        "strongest_edges": sorted(edges, key=lambda e: e["weight"], reverse=True)[:5],
        "bridge_nodes": _bridge_nodes(node_ids, wadj, by_id),
        "sparse_communities": _sparse_communities(node_ids, wadj, by_id),
        "cross_community_edges": _cross_community_edges(edges, community_of, by_id),
        "surprise_links": _surprise_links(edges, community_of, by_id),
        "signal_weights": SIGNAL_WEIGHTS,
    }
    return {"nodes": nodes, "edges": edges, "communities": [sorted(c) for c in communities], "insights": insights}


def _collapse_analysis_edges(edges, raw_to_node):
    collapsed = {}
    for edge in edges:
        a = raw_to_node.get(edge["from"])
        b = raw_to_node.get(edge["to"])
        if not a or not b or a == b:
            continue
        source, target = sorted((a, b))
        key = (source, target)
        if key not in collapsed:
            collapsed[key] = {"from": source, "to": target, "weight": 0.0, "signals": defaultdict(int)}
        collapsed[key]["weight"] += float(edge["weight"] or 0)
        for signal, value in (edge.get("signals") or {}).items():
            collapsed[key]["signals"][signal] += value
    result = []
    for edge in collapsed.values():
        result.append(
            {
                "from": edge["from"],
                "to": edge["to"],
                "weight": round(edge["weight"], 3),
                "signals": dict(edge["signals"]),
            }
        )
    return result


def _weighted_adjacency(edges):
    wadj = defaultdict(dict)
    for edge in edges:
        source, target, weight = edge["from"], edge["to"], edge["weight"]
        wadj[source][target] = weight
        wadj[target][source] = weight
    return wadj


def _page_match_keys(page):
    keys = {normalize_wikilink_key(page.title)}
    canonical = canonical_title(page.knowledge_base, page.title)
    if canonical:
        keys.add(normalize_wikilink_key(canonical))
    return {key for key in keys if key}


def _target_match_keys(knowledge_base, title):
    keys = {normalize_wikilink_key(title)}
    canonical = canonical_title(knowledge_base, title)
    if canonical:
        keys.add(normalize_wikilink_key(canonical))
    return {key for key in keys if key}


def _reference_lookups(pages):
    by_title = defaultdict(list)
    by_key = defaultdict(list)
    for page in pages:
        by_title[(page.title or "").strip()].append(page)
        for key in _page_match_keys(page):
            by_key[key].append(page)
    return by_title, by_key


def _reference_target_id(by_title, by_key, knowledge_base, title, source_id):
    exact = by_title.get((title or "").strip()) or []
    candidates = exact[:]
    if not candidates:
        seen = set()
        for key in _target_match_keys(knowledge_base, title):
            for page in by_key.get(key, []):
                if page.id in seen:
                    continue
                candidates.append(page)
                seen.add(page.id)
    candidates = [page for page in candidates if page.id != source_id]
    if len(candidates) != 1:
        return None
    return candidates[0].id


def _reference_pairs(pages):
    """从各页面当前正文解析 [[标题]],返回有向引用对集合 {(from_id, to_id)}。"""
    by_title, by_key = _reference_lookups(pages)
    pairs = set()
    for p in pages:
        body = p.current_version.body if p.current_version_id else ""
        for match in LINK_RE.finditer(body or ""):
            title = match.group(1).strip()
            tid = _reference_target_id(by_title, by_key, p.knowledge_base, title, p.id)
            if tid and tid != p.id:
                pairs.add((p.id, tid))
    return pairs


def _louvain(node_ids, wadj, max_passes=20):
    """纯 Python Louvain 社区发现(模块度贪心 + 多层聚合),无外部依赖。确定性遍历。

    返回原始节点 id 的社区划分 list[set]。孤立节点(无边)自成一社区。
    """
    nodes = sorted(node_ids)
    adj = {n: dict(wadj[n]) for n in nodes}
    node_to_super = {n: n for n in nodes}
    super_nodes = list(nodes)

    for _ in range(max_passes):
        comm, improved = _louvain_one_level(super_nodes, adj)
        if not improved or len(set(comm.values())) == len(super_nodes):
            break
        for orig, sup in node_to_super.items():
            node_to_super[orig] = comm[sup]
        agg = defaultdict(lambda: defaultdict(float))
        for u in super_nodes:
            cu = comm[u]
            for v, w in adj[u].items():
                agg[cu][comm[v]] += w
        adj = {k: dict(v) for k, v in agg.items()}
        super_nodes = sorted(adj.keys())

    groups = defaultdict(set)
    for orig, sup in node_to_super.items():
        groups[sup].add(orig)
    return [g for g in groups.values()]


def _louvain_one_level(nodes, adj):
    """单层模块度优化:返回 ({node: 社区代表}, 是否有提升)。"""
    k = {u: sum(adj[u].values()) for u in nodes}
    m2 = sum(k.values())  # = 2m
    if m2 == 0:
        return {u: u for u in nodes}, False
    comm = {u: u for u in nodes}
    sigma_tot = {u: k[u] for u in nodes}
    improved = changed = True
    while changed:
        changed = False
        for u in nodes:
            cu = comm[u]
            sigma_tot[cu] -= k[u]
            nbr = defaultdict(float)
            for v, w in adj[u].items():
                if v != u:
                    nbr[comm[v]] += w
            # ΔQ(移入社区 c) ∝ w_in(u,c) - sigma_tot[c]*k[u]/2m;留在原社区为基线
            stay = nbr.get(cu, 0.0) - sigma_tot[cu] * k[u] / m2
            best_c, best_gain = cu, stay
            for c, w_in in sorted(nbr.items()):
                gain = w_in - sigma_tot[c] * k[u] / m2
                if gain > best_gain:
                    best_gain, best_c = gain, c
            comm[u] = best_c
            sigma_tot[best_c] += k[u]
            if best_c != cu:
                changed = True
                improved = True
    members = defaultdict(list)
    for u in nodes:
        members[comm[u]].append(u)
    relabel = {c: min(ms) for c, ms in members.items()}
    return {u: relabel[comm[u]] for u in nodes}, improved
