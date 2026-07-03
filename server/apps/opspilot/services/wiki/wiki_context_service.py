"""多智能体复用(P4):把 Wiki 检索结果整理成可注入聊天/技能提示词的上下文。

技能/智能体在配置中选择若干 Wiki 知识库;回答时调用 build_context(kb_ids, query) 取回
带编号引用的上下文块,供 chat chain 拼接进系统提示。检索复用 retrieval_service,
因此跨 DB 可用、无需向量;后续接入聊天链时只需在技能执行处调用本服务。
"""

import logging

from django.db.models import Q

from apps.opspilot.models import PageRelation, WikiKnowledgeBase
from apps.opspilot.services.wiki.embedding_service import chunk_semantic_search as wiki_chunk_search
from apps.opspilot.services.wiki.retrieval_service import hybrid_search as wiki_hybrid_search
from apps.opspilot.services.wiki.retrieval_service import search as wiki_search

logger = logging.getLogger("opspilot")

_TOKEN_CHAR_RATIO = 4
_RETRIEVAL_MODES = {"keyword", "hybrid", "chunk"}


def _estimate_tokens(text):
    text = text or ""
    if not text:
        return 0
    return max(1, (len(text) + _TOKEN_CHAR_RATIO - 1) // _TOKEN_CHAR_RATIO)


def _context_prefix(n, hit):
    return f"[{n}] 《{hit['title']}》(知识库: {hit['kb_name']})\n"


def _context_line(n, hit):
    return f"{_context_prefix(n, hit)}{hit['snippet']}"


def _truncate_context_line(n, hit, token_budget):
    prefix = _context_prefix(n, hit)
    if _estimate_tokens(prefix) > token_budget:
        return ""
    max_chars = max(token_budget * _TOKEN_CHAR_RATIO - len(prefix), 0)
    snippet = hit.get("snippet") or ""
    if len(snippet) > max_chars:
        marker = "..."
        snippet = snippet[: max(max_chars - len(marker), 0)].rstrip()
        snippet = f"{snippet}{marker}" if snippet else marker[:max_chars]
    line = f"{prefix}{snippet}"
    return line if _estimate_tokens(line) <= token_budget else ""


def _hit_key(hit):
    return hit["kb_id"], hit["kind"], hit["id"]


def _dedupe_hits(hits):
    by_key = {}
    for hit in hits:
        key = _hit_key(hit)
        current = by_key.get(key)
        if not current or hit.get("score", 0) > current.get("score", 0):
            by_key[key] = hit
    return list(by_key.values())


def _chunk_hit(result):
    explanation = result.get("explanation") or {}
    chunk_index = explanation.get("chunk_index")
    heading = (result.get("heading_path") or "").strip()
    title = f"{result['title']} / {heading}" if heading else result["title"]
    return {
        "kind": "page_chunk",
        "id": f"{result['page_id']}:{chunk_index}",
        "page_id": result["page_id"],
        "title": title,
        "heading_path": heading,
        "snippet": result.get("snippet", ""),
        "score": result.get("score", 0),
        "explanation": explanation,
    }


def _search_kb(kb, query, per_kb, retrieval_mode="keyword", embed_fn=None):
    if retrieval_mode == "chunk":
        return [_chunk_hit(result) for result in wiki_chunk_search(kb, query, top_k=per_kb, embed_fn=embed_fn)]
    if retrieval_mode == "hybrid":
        return wiki_hybrid_search(kb, query, top_k=per_kb, embed_fn=embed_fn)
    return wiki_search(kb, query, top_k=per_kb)


def _normalize_retrieval_mode(retrieval_mode):
    mode = (retrieval_mode or "keyword").strip().lower()
    return mode if mode in _RETRIEVAL_MODES else "keyword"


def _page_snippet(page):
    body = page.current_version.body if page.current_version_id else ""
    return (body or "")[:300]


def _graph_hit(kb, page, source_hit, relation, hop):
    source_score = source_hit.get("score", 0) or 0
    score = max(source_score * (0.75**hop), 0.01)
    return {
        "kind": "page",
        "id": page.id,
        "title": page.title,
        "snippet": _page_snippet(page),
        "score": score,
        "kb_id": kb.id,
        "kb_name": kb.name,
        "explanation": {
            "matched_by": ["graph"],
            "graph_hop": hop,
            "graph_source_id": source_hit["id"],
            "graph_source_title": source_hit["title"],
            "relation_type": relation.relation_type,
            "relation_weight": relation.weight,
        },
    }


def _expand_graph_hits(kb, hits, graph_hops=1, limit_per_seed=2):
    if not graph_hops:
        return hits
    page_hits = {hit["id"]: hit for hit in hits if hit.get("kind") == "page"}
    if not page_hits:
        return hits

    expanded = list(hits)
    seen_page_ids = set(page_hits)
    frontier_ids = set(page_hits)
    for hop in range(1, graph_hops + 1):
        rels = (
            PageRelation.objects.filter(
                Q(from_page_id__in=frontier_ids) | Q(to_page_id__in=frontier_ids),
                from_page__knowledge_base=kb,
                to_page__knowledge_base=kb,
            )
            .select_related("from_page", "from_page__current_version", "to_page", "to_page__current_version")
            .order_by("-weight", "id")
        )
        additions, per_seed_count = [], {}
        for relation in rels:
            pairs = (
                (relation.from_page_id, relation.to_page),
                (relation.to_page_id, relation.from_page),
            )
            for source_id, neighbor in pairs:
                if source_id not in frontier_ids or neighbor.id in seen_page_ids or neighbor.status != "active":
                    continue
                count = per_seed_count.get(source_id, 0)
                if count >= limit_per_seed:
                    continue
                source_hit = page_hits[source_id]
                hit = _graph_hit(kb, neighbor, source_hit, relation, hop)
                additions.append(hit)
                seen_page_ids.add(neighbor.id)
                per_seed_count[source_id] = count + 1
        if not additions:
            break
        additions.sort(key=lambda item: (-item["score"], item["title"], item["id"]))
        expanded.extend(additions)
        page_hits.update({hit["id"]: hit for hit in additions})
        frontier_ids = {hit["id"] for hit in additions}
    return expanded


def _render_context(hits, token_budget=None):
    lines, citations = [], []
    used_tokens = 0
    truncated = False
    for hit in hits:
        n = len(lines) + 1
        line = _context_line(n, hit)
        line_tokens = _estimate_tokens(line)
        if token_budget is not None:
            remaining = token_budget - used_tokens
            if remaining <= 0:
                truncated = True
                break
            if line_tokens > remaining:
                truncated = True
                if lines:
                    continue
                line = _truncate_context_line(n, hit, remaining)
                if not line:
                    break
                line_tokens = _estimate_tokens(line)
        used_tokens += line_tokens
        lines.append(line)
        citations.append(
            {
                "n": n,
                "kb_id": hit["kb_id"],
                "kind": hit["kind"],
                "id": hit["id"],
                "title": hit["title"],
                "explanation": hit.get("explanation", {}),
            }
        )
    return lines, citations, {"token_budget": token_budget, "used_tokens": used_tokens, "truncated": truncated}


def build_context(
    kb_ids,
    query,
    top_k=5,
    per_kb=5,
    token_budget=None,
    graph_hops=1,
    graph_limit_per_seed=2,
    retrieval_mode="keyword",
    embed_fn=None,
):
    """跨多个 Wiki 知识库检索,返回 {context, citations, hits}。

    - context:编号 markdown 文本,可直接拼进系统提示词;
    - citations:[{n, kb_id, kind, id, title}],供前端/回答标注来源;
    - hits:原始检索命中(含 score),供调用方进一步处理。
    """
    retrieval_mode = _normalize_retrieval_mode(retrieval_mode)
    hits = []
    for kb in WikiKnowledgeBase.objects.filter(id__in=list(kb_ids or [])):
        kb_hits = [{**r, "kb_id": kb.id, "kb_name": kb.name} for r in _search_kb(kb, query, per_kb, retrieval_mode, embed_fn)]
        hits.extend(_expand_graph_hits(kb, kb_hits, graph_hops=graph_hops, limit_per_seed=graph_limit_per_seed))
    hits = _dedupe_hits(hits)
    hits.sort(key=lambda h: h["score"], reverse=True)
    hits = hits[:top_k]

    lines, citations, budget = _render_context(hits, token_budget=token_budget)
    return {
        "context": "\n\n".join(lines),
        "citations": citations,
        "hits": hits[: len(citations)],
        "budget": budget,
        "retrieval_mode": retrieval_mode,
    }


def augment_prompt(
    system_prompt,
    kb_ids,
    query,
    top_k=5,
    retrieval_mode="keyword",
    graph_hops=1,
    token_budget=None,
    embed_fn=None,
):
    """把 Wiki 检索上下文拼接进系统提示词,返回 (新提示词, citations)。

    无所选知识库 / 无查询 / 无命中时,原样返回提示词与空引用,确保对聊天链零副作用。
    """
    if not kb_ids or not (query or "").strip():
        return system_prompt, []
    result = build_context(
        kb_ids,
        query,
        top_k=top_k,
        retrieval_mode=retrieval_mode,
        graph_hops=graph_hops,
        token_budget=token_budget,
        embed_fn=embed_fn,
    )
    if not result["context"]:
        return system_prompt, []
    augmented = (
        f"{system_prompt or ''}\n\n"
        "【相关知识库信息】请严格依据以下知识库内容回答用户问题,并在末尾用 [n] 标注所引用的条目;"
        "若以下内容未覆盖用户的问题,请明确回复「知识库中暂无相关内容」,"
        "不得使用知识库以外的信息,也不得自行推测或编造。\n"
        f"{result['context']}"
    )
    return augmented, result["citations"]
