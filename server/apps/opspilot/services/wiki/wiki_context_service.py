"""多智能体复用(P4):把 Wiki 检索结果整理成可注入聊天/技能提示词的上下文。

技能/智能体在配置中选择若干 Wiki 知识库;回答时调用 build_context(kb_ids, query) 取回
带编号引用的上下文块,供 chat chain 拼接进系统提示。检索复用 retrieval_service,
因此跨 DB 可用、无需向量;后续接入聊天链时只需在技能执行处调用本服务。
"""

import re

from django.db.models import Q

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.models import WikiKnowledgeBase
from apps.opspilot.services.llm_context_budget import working_budget_for_model_id
from apps.opspilot.services.wiki.active_generation_query_service import (
    ActiveGenerationReadError,
    assert_read_scope_current,
    bind_read_scope,
    directory_scope_ids,
    page_queryset,
    page_snapshot,
    relation_queryset,
)
from apps.opspilot.services.wiki.generation_query_routing_service import OverviewRouteResult, route_overview_scopes
from apps.opspilot.services.wiki.retrieval_service import hybrid_search as wiki_hybrid_search
from apps.opspilot.services.wiki.retrieval_service import search as wiki_search
from apps.opspilot.services.wiki.wiki_budget_service import WikiBudgetExceeded, estimate_tokens, load_wiki_budget_config, new_query_call_budget

_RETRIEVAL_MODES = {"keyword", "hybrid", "chunk"}

# 寒暄/致谢/短确认：不走 Wiki 检索与 overview 路由，避免问候也烧 LLM/知识库。
_WIKI_SKIP_QUERY_RE = re.compile(
    r"^(?:"
    r"你[好呀啊吗嘛]*|您好|大家好|"
    r"早上好|中午好|下午好|晚上好|早安|晚安|"
    r"hi+|hello|hey|yo+|good\s*(?:morning|afternoon|evening|night)|"
    r"在吗|在不在|有人吗|嗨+|哈喽|嘿+|"
    r"谢谢(?:你|您)?|感谢|多谢|thanks|thank\s*you|"
    r"好的|嗯+|哦+|噢+|哈哈+|呵呵+|嘿嘿+|"
    r"没事|没关系|不用了|ok|okay|bye|再见|拜拜|"
    r"测试一下|test"
    r")[\s!！。.?？~～…]*$",
    re.IGNORECASE,
)


def should_skip_wiki_retrieval(query: str) -> bool:
    """判断是否应跳过 Wiki 检索（问好/闲聊/短确认）。

    仅覆盖无需知识库即可回复的短句；稍长或含业务意图的问题仍走检索。
    """
    text = " ".join(str(query or "").strip().split())
    if not text:
        return True
    # 过长几乎不可能是纯寒暄，避免误伤正常业务问句。
    if len(text) > 32:
        return False
    return bool(_WIKI_SKIP_QUERY_RE.match(text))


def _estimate_tokens(text):
    return estimate_tokens(text)


def _context_prefix(n, hit):
    metadata = []
    breadcrumb = hit.get("directory_breadcrumb") or []
    if breadcrumb:
        metadata.append("知识目录: " + " / ".join(item.get("name", "") for item in breadcrumb))
    heading_path = (hit.get("heading_path") or "").strip()
    if heading_path:
        metadata.append(f"Markdown 标题: {heading_path}")
    location = f"; {'; '.join(metadata)}" if metadata else ""
    return f"[{n}] 《{hit['title']}》(知识库: {hit['kb_name']}{location})\n"


def _context_line(n, hit):
    return f"{_context_prefix(n, hit)}{hit['snippet']}"


def _truncate_context_line(n, hit, token_budget):
    prefix = _context_prefix(n, hit)
    if _estimate_tokens(prefix) > token_budget:
        return ""
    snippet = hit.get("snippet") or ""
    line = f"{prefix}{snippet}"
    if _estimate_tokens(line) <= token_budget:
        return line

    marker = "..."
    low, high = 0, len(snippet)
    best = ""
    while low <= high:
        midpoint = (low + high) // 2
        candidate_text = snippet[:midpoint].rstrip()
        candidate = f"{prefix}{candidate_text}{marker}" if candidate_text else f"{prefix}{marker}"
        if _estimate_tokens(candidate) <= token_budget:
            best = candidate
            low = midpoint + 1
        else:
            high = midpoint - 1
    return best


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


def _search_kb(
    kb,
    query,
    per_kb,
    retrieval_mode="keyword",
    embed_fn=None,
    *,
    read_scope=None,
    directory_id=None,
    include_descendants=False,
):
    if retrieval_mode == "chunk":
        raise ActiveGenerationReadError(
            "chunk_retrieval_not_generation_safe",
            "当前知识库代际模式暂不支持 Chunk 检索，请使用 keyword 或 hybrid",
            details={"knowledge_base_id": kb.pk},
        )
    if retrieval_mode == "hybrid":
        return wiki_hybrid_search(
            kb,
            query,
            top_k=per_kb,
            embed_fn=embed_fn,
            directory_id=directory_id,
            include_descendants=include_descendants,
            read_scope=read_scope,
        )
    return wiki_search(
        kb,
        query,
        top_k=per_kb,
        directory_id=directory_id,
        include_descendants=include_descendants,
        read_scope=read_scope,
    )


def _normalize_retrieval_mode(retrieval_mode):
    mode = (retrieval_mode or "keyword").strip().lower()
    return mode if mode in _RETRIEVAL_MODES else "keyword"


def _graph_hit(kb, snapshot, source_hit, relation, hop):
    source_score = source_hit.get("score", 0) or 0
    score = max(source_score * (0.75**hop), 0.01)
    return {
        "kind": "page",
        "id": snapshot.page_id,
        "title": snapshot.title,
        "snippet": (snapshot.body or "")[:2000],
        "score": score,
        "kb_id": kb.id,
        "kb_name": kb.name,
        "generation_id": snapshot.generation_id,
        "directory_id": snapshot.directory_id,
        "directory_key": snapshot.directory_key,
        "directory_breadcrumb": list(snapshot.directory_breadcrumb),
        "heading_path": "",
        "explanation": {
            "matched_by": ["graph"],
            "graph_hop": hop,
            "graph_source_id": source_hit["id"],
            "graph_source_title": source_hit["title"],
            "relation_type": relation.relation_type,
            "relation_weight": relation.weight,
        },
    }


def _expand_graph_hits(
    kb,
    hits,
    graph_hops=1,
    limit_per_seed=2,
    *,
    read_scope,
    directory_id=None,
    include_descendants=False,
):
    if not graph_hops:
        return hits
    page_hits = {hit["id"]: hit for hit in hits if hit.get("kind") == "page"}
    if not page_hits:
        return hits

    scoped_directory_ids = directory_scope_ids(
        kb,
        directory_id=directory_id,
        include_descendants=include_descendants,
        read_scope=read_scope,
    )
    expanded = list(hits)
    seen_page_ids = set(page_hits)
    frontier_ids = set(page_hits)
    for hop in range(1, graph_hops + 1):
        rels = (
            relation_queryset(kb, read_scope=read_scope)
            .filter(Q(from_page_id__in=frontier_ids) | Q(to_page_id__in=frontier_ids))
            .order_by("-weight", "id")
        )
        relations = list(rels)
        neighbor_ids = {
            neighbor_id
            for relation in relations
            for source_id, neighbor_id in (
                (relation.from_page_id, relation.to_page_id),
                (relation.to_page_id, relation.from_page_id),
            )
            if source_id in frontier_ids and neighbor_id not in seen_page_ids
        }
        snapshots = {}
        if neighbor_ids:
            neighbors = page_queryset(
                kb,
                statuses=("active",),
                directory_ids=scoped_directory_ids,
                read_scope=read_scope,
            ).filter(pk__in=neighbor_ids)
            for page in neighbors:
                snapshot = page_snapshot(page, knowledge_base=kb)
                snapshots[snapshot.page_id] = snapshot
        additions, per_seed_count = [], {}
        for relation in relations:
            pairs = (
                (relation.from_page_id, relation.to_page_id),
                (relation.to_page_id, relation.from_page_id),
            )
            for source_id, neighbor_id in pairs:
                snapshot = snapshots.get(neighbor_id)
                if source_id not in frontier_ids or snapshot is None or neighbor_id in seen_page_ids:
                    continue
                count = per_seed_count.get(source_id, 0)
                if count >= limit_per_seed:
                    continue
                source_hit = page_hits[source_id]
                hit = _graph_hit(kb, snapshot, source_hit, relation, hop)
                additions.append(hit)
                seen_page_ids.add(neighbor_id)
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
                "generation_id": hit.get("generation_id"),
                "directory_id": hit.get("directory_id"),
                "directory_key": hit.get("directory_key", ""),
                "directory_breadcrumb": list(hit.get("directory_breadcrumb") or []),
                "heading_path": hit.get("heading_path", ""),
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
    directory_id=None,
    include_descendants=False,
    llm_model_id=None,
):
    """Search compact Index first and spend at most one call on Overview routing."""

    if should_skip_wiki_retrieval(query):
        return {
            "context": "",
            "citations": [],
            "hits": [],
            "budget": {
                "overview_status": "skipped_chitchat",
                "overview_scopes": [],
                "overview_tokens": 0,
                "llm_budget": {"used_calls": 0},
            },
            "retrieval_mode": _normalize_retrieval_mode(retrieval_mode),
        }

    retrieval_mode = _normalize_retrieval_mode(retrieval_mode)
    config = load_wiki_budget_config()
    derived = working_budget_for_model_id(llm_model_id, scene_output_default=config.qa_max_output_tokens)
    knowledge_cap = derived.knowledge_inject_tokens
    requested_budget = int(token_budget) if token_budget is not None and int(token_budget) > 0 else knowledge_cap
    effective_budget = min(requested_budget, knowledge_cap)
    call_budget = new_query_call_budget()
    hits = []
    scopes = []
    initial_hits_by_kb = {}
    for kb in WikiKnowledgeBase.objects.filter(id__in=list(kb_ids or [])):
        read_scope = bind_read_scope(kb)
        scopes.append((kb, read_scope))
        kb_hits = [
            {**result, "kb_id": kb.id, "kb_name": kb.name}
            for result in _search_kb(
                kb,
                query,
                per_kb,
                retrieval_mode,
                embed_fn,
                read_scope=read_scope,
                directory_id=directory_id,
                include_descendants=include_descendants,
            )
        ]
        initial_hits_by_kb[kb.pk] = kb_hits
        hits.extend(
            _expand_graph_hits(
                kb,
                kb_hits,
                graph_hops=graph_hops,
                limit_per_seed=graph_limit_per_seed,
                read_scope=read_scope,
                directory_id=directory_id,
                include_descendants=include_descendants,
            )
        )

    route = OverviewRouteResult((), 0, False, "not_needed")
    needs_overview_route = (
        retrieval_mode == "keyword"
        and directory_id is None
        and any(not kb_hits or kb_hits[0].get("route_confidence") != "high" for kb_hits in initial_hits_by_kb.values())
    )
    if needs_overview_route:
        from apps.opspilot.services.wiki.build_service import _invoke_llm

        route = route_overview_scopes(
            scopes,
            query,
            llm_model_id=llm_model_id,
            call_budget=call_budget,
            knowledge_token_limit=effective_budget,
            invoke_llm=_invoke_llm,
        )
        scope_map = {kb.pk: (kb, read_scope) for kb, read_scope in scopes}
        for kb_id, routed_directory_id in route.scopes:
            item = scope_map.get(kb_id)
            if item is None:
                continue
            kb, read_scope = item
            routed_hits = [
                {**result, "kb_id": kb.id, "kb_name": kb.name}
                for result in _search_kb(
                    kb,
                    query,
                    per_kb,
                    retrieval_mode,
                    embed_fn,
                    read_scope=read_scope,
                    directory_id=routed_directory_id,
                    include_descendants=True,
                )
            ]
            hits.extend(
                _expand_graph_hits(
                    kb,
                    routed_hits,
                    graph_hops=graph_hops,
                    limit_per_seed=graph_limit_per_seed,
                    read_scope=read_scope,
                    directory_id=routed_directory_id,
                    include_descendants=True,
                )
            )

    hits = _dedupe_hits(hits)
    hits.sort(key=lambda item: item["score"], reverse=True)
    hits = hits[:top_k]
    remaining_budget = max(effective_budget - route.knowledge_tokens, 0)
    lines, citations, budget = _render_context(hits, token_budget=remaining_budget)
    budget.update(
        {
            "configured_token_budget": knowledge_cap,
            "effective_token_budget": effective_budget,
            "overview_tokens": route.knowledge_tokens,
            "overview_status": route.status,
            "overview_scopes": [{"kb_id": kb_id, "directory_id": routed_directory_id} for kb_id, routed_directory_id in route.scopes],
            "llm_budget": call_budget.trace(),
        }
    )
    for _knowledge_base, read_scope in scopes:
        assert_read_scope_current(read_scope)
    if budget["truncated"]:
        raise WikiBudgetExceeded(
            "wiki_query_token_budget_exceeded",
            "知识库查询结果超过单次 token 上限",
            details=budget,
        )
    return {
        "context": "\n\n".join(lines),
        "citations": citations,
        "hits": hits[: len(citations)],
        "budget": budget,
        "retrieval_mode": retrieval_mode,
    }


def augment_prompt_with_trace(
    system_prompt,
    kb_ids,
    query,
    top_k=5,
    retrieval_mode="keyword",
    graph_hops=1,
    token_budget=None,
    embed_fn=None,
    llm_model_id=None,
):
    if not kb_ids or not (query or "").strip():
        return system_prompt, [], {}
    if should_skip_wiki_retrieval(query):
        logger.info("Wiki 检索跳过(寒暄/闲聊): query=%r", str(query)[:32])
        return (
            system_prompt,
            [],
            {
                "overview_status": "skipped_chitchat",
                "overview_scopes": [],
                "overview_tokens": 0,
                "llm_budget": {"used_calls": 0},
            },
        )
    result = build_context(
        kb_ids,
        query,
        top_k=top_k,
        retrieval_mode=retrieval_mode,
        graph_hops=graph_hops,
        token_budget=token_budget,
        embed_fn=embed_fn,
        llm_model_id=llm_model_id,
    )
    if not result["context"]:
        return system_prompt, [], result["budget"]
    augmented = (
        f"{system_prompt or ''}\n\n"
        "【相关知识库信息】请严格依据以下知识库内容回答用户问题,并在末尾用 [n] 标注所引用的条目;"
        "若以下内容未覆盖用户的问题,请明确回复「知识库中暂无相关内容」,"
        "不得使用知识库以外的信息,也不得自行推测或编造。\n"
        f"{result['context']}"
    )
    return augmented, result["citations"], result["budget"]


def augment_prompt(
    system_prompt,
    kb_ids,
    query,
    top_k=5,
    retrieval_mode="keyword",
    graph_hops=1,
    token_budget=None,
    embed_fn=None,
    llm_model_id=None,
):
    """Backward-compatible two-value wrapper around the budget-aware query path."""

    augmented, citations, _trace = augment_prompt_with_trace(
        system_prompt,
        kb_ids,
        query,
        top_k=top_k,
        retrieval_mode=retrieval_mode,
        graph_hops=graph_hops,
        token_budget=token_budget,
        embed_fn=embed_fn,
        llm_model_id=llm_model_id,
    )
    return augmented, citations
