"""检索与问答(P3 核心)。

MVP 检索:对知识页面(标题+正文)与资料摘要做关键词匹配 + 简单打分,跨 DB 可用;
pgvector 语义检索为后期可选增强(P6),不在此处。
问答:检索 Top-N 页面 → metis chain 带页面上下文作答 → 返回引用页面,可追溯到资料。
"""

import hashlib
import json
import re

from django.core.cache import cache

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest
from apps.opspilot.metis.llm.common.llm_client_factory import LLMClientFactory
from apps.opspilot.models import LLMModel, Material, PageVersion, WikiGenerationIndexEntry
from apps.opspilot.services.llm_context_budget import working_budget_for_model
from apps.opspilot.services.wiki.active_generation_query_service import (
    assert_read_scope_current,
    bind_read_scope,
    directory_scope_ids,
    page_queryset,
    page_snapshot,
)
from apps.opspilot.services.wiki.embed_cache import embed_texts_cached
from apps.opspilot.services.wiki.embedding_service import cosine, rrf_fuse
from apps.opspilot.services.wiki.title_service import title_identity_key
from apps.opspilot.services.wiki.wiki_budget_service import estimate_tokens


def _has_cjk(text):
    return any("一" <= ch <= "鿿" for ch in text)


def _tokenize(query):
    """分词:空白/标点切分;CJK 长词补充二元组(bigram),以适配中文无空格查询。"""
    terms = set()
    for tok in re.split(r"[\s,，。;；、:：!！?？]+", (query or "").strip().lower()):
        tok = tok.strip()
        if not tok:
            continue
        terms.add(tok)
        if _has_cjk(tok) and len(tok) > 2:
            for i in range(len(tok) - 1):
                terms.add(tok[i : i + 2])
    return [t for t in terms if t]


def _score(text, terms):
    text = (text or "").lower()
    return sum(text.count(t) for t in terms if t)


def _matched_terms(terms, *texts):
    text = "\n".join(texts or "").lower()
    return [term for term in terms if term and term in text]


def _keyword_explanation(score, terms, *texts):
    return {
        "matched_by": ["keyword"],
        "keyword_score": score,
        "matched_terms": _matched_terms(terms, *texts),
    }


def _dynamic_snippet(body, terms, *, radius=1000):
    """Extract a retrieval excerpt centered on the earliest matched term.

    Default window is ~2000 chars so QA fallback / context is usable without a model.
    """
    text = body or ""
    lowered = text.casefold()
    positions = [lowered.find(term.casefold()) for term in terms if term]
    positions = [position for position in positions if position >= 0]
    if not positions:
        return text[: radius * 2].strip()
    position = min(positions)
    start = max(0, position - radius)
    end = min(len(text), position + radius)
    prefix = "..." if start else ""
    suffix = "..." if end < len(text) else ""
    return f"{prefix}{text[start:end].strip()}{suffix}"


_FALLBACK_PREFIX = "未使用模型生成回答（知识库未配置模型或模型调用失败）。" "以下为相关页面摘录，用于验证检索是否正常：\n\n"


def _fallback_answer(contexts):
    top = contexts[0]
    return f"{_FALLBACK_PREFIX}根据《{top['title']}》：\n{top['snippet']}"


def _index_score(entry, terms, query):
    title = entry.title or ""
    aliases = " ".join(entry.aliases or [])
    tags = " ".join(entry.tags or [])
    headings = " ".join(entry.headings or [])
    keywords = " ".join(entry.keywords or [])
    entities = " ".join(entry.entities or [])
    summary = entry.summary or ""
    normalized_query = title_identity_key(query)
    exact = bool(normalized_query) and normalized_query in {
        entry.normalized_title,
        *(title_identity_key(alias) for alias in (entry.aliases or [])),
    }
    score = (
        _score(title, terms) * 12
        + _score(aliases, terms) * 10
        + _score(tags, terms) * 5
        + _score(keywords, terms) * 5
        + _score(entities, terms) * 4
        + _score(headings, terms) * 3
        + _score(summary, terms) * 2
        + _score(entry.page_type, terms)
    )
    if exact:
        score += 100
    return score, exact


def _generation_search_cache_key(scope, query, directory_ids, top_k):
    payload = json.dumps(
        {
            "query": str(query or ""),
            "directory_ids": sorted(directory_ids) if directory_ids is not None else None,
            "top_k": int(top_k),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    return f"wiki:generation-index-search:v1:{scope.generation_id}:{digest}"


def _generation_index_search(scope, terms, *, query, directory_ids, top_k):
    cache_key = _generation_search_cache_key(
        scope,
        query,
        directory_ids,
        top_k,
    )
    cached = cache.get(cache_key)
    if isinstance(cached, list):
        return cached
    queryset = WikiGenerationIndexEntry.objects.filter(
        generation_id=scope.generation_id,
    )
    if directory_ids is not None:
        queryset = queryset.filter(directory_id__in=directory_ids)
    ranked = []
    for entry in queryset.order_by("page_id"):
        score, exact = _index_score(entry, terms, query)
        if score <= 0:
            continue
        ranked.append((score, exact, entry))
    ranked.sort(key=lambda item: (-item[0], not item[1], item[2].normalized_title, item[2].page_id))
    selected = ranked[:top_k]
    top_score = selected[0][0] if selected else 0
    second_score = selected[1][0] if len(selected) > 1 else 0
    high_confidence = bool(selected) and (
        selected[0][1] or top_score >= 20 or (top_score >= 8 and top_score >= max(second_score * 1.8, second_score + 4))
    )
    versions = PageVersion.objects.in_bulk([entry.page_version_id for _score_value, _exact, entry in selected])
    results = []
    for score, exact, entry in selected:
        page_version = versions.get(entry.page_version_id)
        if page_version is None:
            logger.warning(
                "wiki generation index references a missing page version generation=%s entry=%s version=%s",
                scope.generation_id,
                entry.pk,
                entry.page_version_id,
            )
            continue
        heading_path = next(
            (heading for heading in (entry.headings or []) if any(term.casefold() in str(heading).casefold() for term in terms)),
            "",
        )
        results.append(
            {
                "kind": "page",
                "id": entry.page_id,
                "page_version_id": entry.page_version_id,
                "title": entry.title,
                "snippet": _dynamic_snippet(page_version.body, terms),
                "score": score,
                "generation_id": scope.generation_id,
                "directory_id": entry.directory_id,
                "directory_key": entry.directory_key,
                "directory_breadcrumb": list(entry.directory_breadcrumb or []),
                "heading_path": heading_path,
                "route_confidence": "high" if high_confidence else "low",
                "explanation": {
                    **_keyword_explanation(score, terms, entry.search_text),
                    "matched_by": ["generation_index"],
                    "exact_title_or_alias": exact,
                    "index_fingerprint": entry.content_fingerprint,
                },
            }
        )
    cache.set(cache_key, results, timeout=300)
    return results


def search(
    knowledge_base,
    query,
    top_k=5,
    *,
    directory_id=None,
    include_descendants=False,
    read_scope=None,
):
    """Search compact generation Index first, loading bodies only for candidates."""

    scope = read_scope or bind_read_scope(knowledge_base)
    directory_ids = directory_scope_ids(
        knowledge_base,
        directory_id=directory_id,
        include_descendants=include_descendants,
        read_scope=scope,
    )
    terms = _tokenize(query)
    if scope.generation_id is not None:
        results = _generation_index_search(
            scope,
            terms,
            query=query,
            directory_ids=directory_ids,
            top_k=top_k,
        )
        assert_read_scope_current(scope)
        return results

    results = []
    pages = page_queryset(
        knowledge_base,
        statuses=("active",),
        directory_ids=directory_ids,
        read_scope=scope,
    ).order_by("id")
    for page in pages:
        snapshot = page_snapshot(page, knowledge_base=knowledge_base)
        body = snapshot.body
        title = snapshot.title
        score = _score(title, terms) * 5 + _score(body, terms)
        if score > 0:
            results.append(
                {
                    "kind": "page",
                    "id": page.id,
                    "page_version_id": snapshot.page_version_id,
                    "title": title,
                    "snippet": _dynamic_snippet(body, terms),
                    "score": score,
                    "generation_id": snapshot.generation_id,
                    "directory_id": snapshot.directory_id,
                    "directory_key": snapshot.directory_key,
                    "directory_breadcrumb": list(snapshot.directory_breadcrumb),
                    "heading_path": "",
                    "route_confidence": "direct_fallback",
                    "explanation": _keyword_explanation(score, terms, title, body),
                }
            )

    if directory_ids is None:
        for material in Material.objects.filter(knowledge_base=knowledge_base).exclude(ai_summary=""):
            score = _score(material.ai_summary, terms) + _score(material.name, terms) * 2
            if score > 0:
                results.append(
                    {
                        "kind": "material_summary",
                        "id": material.id,
                        "title": material.name,
                        "snippet": _dynamic_snippet(material.ai_summary, terms),
                        "score": score,
                        "generation_id": scope.generation_id,
                        "directory_id": None,
                        "directory_key": "",
                        "directory_breadcrumb": [],
                        "heading_path": "",
                        "route_confidence": "direct_fallback",
                        "explanation": _keyword_explanation(score, terms, material.name, material.ai_summary),
                    }
                )

    results.sort(key=lambda result: result["score"], reverse=True)
    results = results[:top_k]
    assert_read_scope_current(scope)
    return results


def hybrid_search(
    knowledge_base,
    query,
    top_k=5,
    candidate_k=20,
    embed_fn=None,
    *,
    directory_id=None,
    include_descendants=False,
    read_scope=None,
):
    """混合检索:关键词召回候选 → 语义重排 → RRF 融合。无嵌入/失败时回退关键词。

    embed_fn(texts)->List[vector] 可注入以便测试;默认走知识库的 EmbedProvider。
    """
    candidates = search(
        knowledge_base,
        query,
        top_k=candidate_k,
        directory_id=directory_id,
        include_descendants=include_descendants,
        read_scope=read_scope,
    )
    if not candidates:
        return []

    def _key(c):
        return f"{c['kind']}:{c['id']}"

    by_key = {_key(c): c for c in candidates}
    kw_rank = [_key(c) for c in candidates]

    embed = embed_fn or (lambda texts: embed_texts_cached(texts, knowledge_base.embed_provider))
    qvecs = embed([query])
    cvecs = embed([f"{c['title']} {c['snippet']}" for c in candidates])
    if not qvecs or not cvecs or len(cvecs) != len(candidates):
        return candidates[:top_k]  # 无嵌入 → 回退关键词

    qv = qvecs[0]
    vector_scores = {i: cosine(qv, cvecs[i]) for i in range(len(candidates))}
    order = sorted(range(len(candidates)), key=lambda i: vector_scores[i], reverse=True)
    sem_rank = [_key(candidates[i]) for i in order]
    fused = rrf_fuse([kw_rank, sem_rank], top_k=top_k)
    keyword_ranks = {key: rank for rank, key in enumerate(kw_rank, start=1)}
    semantic_ranks = {key: rank for rank, key in enumerate(sem_rank, start=1)}
    vector_score_by_key = {_key(candidates[i]): vector_scores[i] for i in range(len(candidates))}

    results = []
    for key in fused:
        item = dict(by_key[key])
        explanation = dict(item.get("explanation") or {})
        matched_by = list(explanation.get("matched_by") or [])
        if "keyword" not in matched_by:
            matched_by.append("keyword")
        if "vector" not in matched_by:
            matched_by.append("vector")
        explanation.update(
            {
                "matched_by": matched_by,
                "keyword_rank": keyword_ranks.get(key),
                "semantic_rank": semantic_ranks.get(key),
                "vector_score": vector_score_by_key.get(key, 0),
                "fusion": "rrf",
            }
        )
        item["explanation"] = explanation
        results.append(item)
    return results


def _qa_basic_llm_request(llm, prompt, *, max_output_tokens):
    """Build a BasicLLMRequest with the same protocol/vendor wiring as wiki build."""
    derived = working_budget_for_model(llm, scene_output_default=max_output_tokens)
    vendor_type = ""
    if getattr(llm, "vendor_id", None):
        vendor_type = str(getattr(llm.vendor, "vendor_type", "") or "")
    protocol_type = getattr(llm, "protocol_type", None) or "openai"
    return BasicLLMRequest(
        openai_api_base=llm.openai_api_base,
        openai_api_key=llm.openai_api_key,
        model=llm.model_name,
        temperature=0.2,
        max_output_tokens=derived.output_reserve_tokens,
        user_message=prompt,
        protocol_type=protocol_type,
        vendor_type=vendor_type,
        extra_config={
            "input_working_tokens": derived.input_working_tokens,
            "context_window_tokens": derived.window_tokens,
        },
    )


def _answer_with_llm(query, contexts, llm_model_id, *, max_output_tokens):
    if not llm_model_id:
        return None
    try:
        llm = LLMModel.objects.select_related("vendor").get(id=llm_model_id)
        # 上下文用 [n] 编号,与智能体对话路径 wiki_citations 的 [n] 引用一致,
        # 让前端 WikiCitations.referenced 过滤逻辑(c.n != null ? [n] : title)直接命中。
        # 否则 LLM 用 [引用: 标题] 时,前端按 title 模糊匹配容易因简化/缩写导致空列表。
        prompt = _build_qa_prompt(query, contexts)
        request = _qa_basic_llm_request(llm, prompt, max_output_tokens=max_output_tokens)
        input_working = int((request.extra_config or {}).get("input_working_tokens") or 0)
        if input_working and estimate_tokens(prompt) > input_working:
            return None
        answer = (
            LLMClientFactory.invoke_isolated(
                request,
                [{"role": "user", "content": prompt}],
            )
            or ""
        ).strip()
        return {
            "answer": answer,
            "finish_reason": (request.extra_config or {}).get("_isolated_finish_reason") or "",
            "output_truncated": bool((request.extra_config or {}).get("_isolated_output_truncated")),
        }
    except Exception:
        logger.exception("wiki 问答 LLM 调用失败")
        return None


def _build_qa_prompt(query, contexts):
    ctx_text = "\n\n".join(f"[{i + 1}]\n# {c['title']}\n{c['snippet']}" for i, c in enumerate(contexts))
    return (
        "基于下面的知识页面与资料摘要回答问题。优先使用知识页面;"
        "在回答末尾用 [n] 标注所引用的编号(n 与上文 [n] 一致),"
        "例如引用第 1 个上下文则写 [1]。"
        "若资料不足,请明确说明。\n\n"
        f"# 上下文\n{ctx_text}\n\n# 问题\n{query}\n"
    )


def _prepare_answer_context(
    knowledge_base,
    query,
    llm_model_id=None,
    top_k=5,
    *,
    directory_id=None,
    include_descendants=False,
):
    from apps.opspilot.services.wiki.wiki_budget_service import WikiBudgetExceeded, load_wiki_budget_config
    from apps.opspilot.services.wiki.wiki_context_service import build_context

    config = load_wiki_budget_config()
    context_result = build_context(
        [knowledge_base.pk],
        query,
        top_k=top_k,
        per_kb=top_k,
        directory_id=directory_id,
        include_descendants=include_descendants,
        llm_model_id=llm_model_id,
    )
    contexts = context_result["hits"]
    citations = context_result["citations"]
    if not contexts:
        return {
            "empty": True,
            "config": config,
            "contexts": [],
            "citations": [],
            "context_result": context_result,
        }
    used_calls = int((context_result["budget"].get("llm_budget") or {}).get("used_calls") or 0)
    if llm_model_id and used_calls >= config.qa_max_llm_calls:
        raise WikiBudgetExceeded(
            "wiki_llm_call_budget_exceeded",
            "知识库问答 LLM 调用次数已达到上限",
            details=context_result["budget"],
        )
    return {
        "empty": False,
        "config": config,
        "contexts": contexts,
        "citations": citations,
        "context_result": context_result,
    }


def stream_answer(
    knowledge_base,
    query,
    llm_model_id=None,
    top_k=5,
    *,
    directory_id=None,
    include_descendants=False,
):
    """Yield SSE-oriented events: meta / delta / done / error."""
    prepared = _prepare_answer_context(
        knowledge_base,
        query,
        llm_model_id=llm_model_id,
        top_k=top_k,
        directory_id=directory_id,
        include_descendants=include_descendants,
    )
    if prepared["empty"]:
        empty_answer = "知识库中暂无相关资料,无法回答该问题。"
        yield {
            "event": "meta",
            "mode": "empty",
            "citations": [],
            "contexts": [],
        }
        yield {"event": "delta", "text": empty_answer}
        yield {
            "event": "done",
            "answer": empty_answer,
            "finish_reason": "",
            "output_truncated": False,
            "mode": "empty",
        }
        return

    contexts = prepared["contexts"]
    citations = prepared["citations"]
    config = prepared["config"]

    if not llm_model_id:
        answer_text = _fallback_answer(contexts)
        yield {
            "event": "meta",
            "mode": "fallback",
            "citations": citations,
            "contexts": contexts,
            "warning_code": "wiki_answer_fallback",
            "warning": "未使用模型生成回答，以下为检索到的页面摘录",
        }
        yield {"event": "delta", "text": answer_text}
        yield {
            "event": "done",
            "answer": answer_text,
            "finish_reason": "",
            "output_truncated": False,
            "mode": "fallback",
            "warning_code": "wiki_answer_fallback",
            "warning": "未使用模型生成回答，以下为检索到的页面摘录",
        }
        return

    try:
        llm = LLMModel.objects.select_related("vendor").get(id=llm_model_id)
    except LLMModel.DoesNotExist:
        answer_text = _fallback_answer(contexts)
        yield {
            "event": "meta",
            "mode": "fallback",
            "citations": citations,
            "contexts": contexts,
            "warning_code": "wiki_answer_fallback",
            "warning": "未使用模型生成回答，以下为检索到的页面摘录",
        }
        yield {"event": "delta", "text": answer_text}
        yield {
            "event": "done",
            "answer": answer_text,
            "finish_reason": "",
            "output_truncated": False,
            "mode": "fallback",
            "warning_code": "wiki_answer_fallback",
            "warning": "未使用模型生成回答，以下为检索到的页面摘录",
        }
        return

    prompt = _build_qa_prompt(query, contexts)
    request = _qa_basic_llm_request(
        llm,
        prompt,
        max_output_tokens=config.qa_max_output_tokens,
    )
    yield {
        "event": "meta",
        "mode": "llm",
        "citations": citations,
        "contexts": contexts,
    }
    parts = []
    try:
        for chunk in LLMClientFactory.stream_isolated(
            request,
            [{"role": "user", "content": prompt}],
        ):
            if not chunk:
                continue
            parts.append(chunk)
            yield {"event": "delta", "text": chunk}
    except Exception as exc:
        logger.exception("wiki 问答 LLM 流式调用失败")
        if parts:
            yield {
                "event": "error",
                "message": str(exc) or "wiki 问答 LLM 流式调用失败",
            }
            answer_text = "".join(parts).strip()
            finish_reason = (request.extra_config or {}).get("_isolated_finish_reason") or ""
            output_truncated = bool((request.extra_config or {}).get("_isolated_output_truncated"))
            done = {
                "event": "done",
                "answer": answer_text,
                "finish_reason": finish_reason,
                "output_truncated": output_truncated,
                "mode": "llm",
            }
            if output_truncated:
                done["warning_code"] = "wiki_answer_output_truncated"
                done["warning"] = "回答达到输出 token 上限，内容可能不完整"
            yield done
            return
        answer_text = _fallback_answer(contexts)
        yield {
            "event": "error",
            "message": str(exc) or "wiki 问答 LLM 流式调用失败",
            "fallback": True,
        }
        yield {"event": "delta", "text": answer_text}
        yield {
            "event": "done",
            "answer": answer_text,
            "finish_reason": "",
            "output_truncated": False,
            "mode": "fallback",
            "warning_code": "wiki_answer_fallback",
            "warning": "未使用模型生成回答，以下为检索到的页面摘录",
        }
        return

    answer_text = "".join(parts).strip()
    finish_reason = (request.extra_config or {}).get("_isolated_finish_reason") or ""
    output_truncated = bool((request.extra_config or {}).get("_isolated_output_truncated"))
    done = {
        "event": "done",
        "answer": answer_text,
        "finish_reason": finish_reason,
        "output_truncated": output_truncated,
        "mode": "llm",
    }
    if output_truncated:
        done["warning_code"] = "wiki_answer_output_truncated"
        done["warning"] = "回答达到输出 token 上限，内容可能不完整"
    yield done


def answer(
    knowledge_base,
    query,
    llm_model_id=None,
    top_k=5,
    *,
    directory_id=None,
    include_descendants=False,
):
    """问答试用:复用 generation 查询预算后执行一次有界回答。"""
    prepared = _prepare_answer_context(
        knowledge_base,
        query,
        llm_model_id=llm_model_id,
        top_k=top_k,
        directory_id=directory_id,
        include_descendants=include_descendants,
    )
    if prepared["empty"]:
        return {"answer": "知识库中暂无相关资料,无法回答该问题。", "citations": [], "contexts": [], "mode": "empty"}

    contexts = prepared["contexts"]
    citations = prepared["citations"]
    config = prepared["config"]
    llm_result = _answer_with_llm(
        query,
        contexts,
        llm_model_id,
        max_output_tokens=config.qa_max_output_tokens,
    )
    mode = "llm"
    if llm_result is None:
        # 无模型/失败时的兜底:回显最相关页面摘要,保证可追溯
        mode = "fallback"
        llm_result = {
            "answer": _fallback_answer(contexts),
            "finish_reason": "",
            "output_truncated": False,
        }
    result = {
        "answer": llm_result["answer"],
        "citations": citations,
        "contexts": contexts,
        "mode": mode,
        "finish_reason": llm_result["finish_reason"],
        "output_truncated": llm_result["output_truncated"],
    }
    if mode == "fallback":
        result["warning_code"] = "wiki_answer_fallback"
        result["warning"] = "未使用模型生成回答，以下为检索到的页面摘录"
    elif llm_result["output_truncated"]:
        result["warning_code"] = "wiki_answer_output_truncated"
        result["warning"] = "回答达到输出 token 上限，内容可能不完整"
    return result
