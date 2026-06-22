"""检索与问答(P3 核心)。

MVP 检索:对知识页面(标题+正文)与资料摘要做关键词匹配 + 简单打分,跨 DB 可用;
pgvector 语义检索为后期可选增强(P6),不在此处。
问答:检索 Top-N 页面 → metis chain 带页面上下文作答 → 返回引用页面,可追溯到资料。
"""

import logging
import re

from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest
from apps.opspilot.metis.llm.common.llm_client_factory import LLMClientFactory
from apps.opspilot.models import KnowledgePage, LLMModel, Material

logger = logging.getLogger("opspilot")


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


def search(knowledge_base, query, top_k=5):
    """返回 [{kind, id, title, snippet, score}],kind ∈ {page, material_summary}。"""
    terms = _tokenize(query)
    results = []

    for page in KnowledgePage.objects.filter(knowledge_base=knowledge_base, status="active").select_related("current_version"):
        body = page.current_version.body if page.current_version_id else ""
        score = _score(page.title, terms) * 5 + _score(body, terms)
        if score > 0:
            results.append({"kind": "page", "id": page.id, "title": page.title, "snippet": (body or "")[:300], "score": score})

    for material in Material.objects.filter(knowledge_base=knowledge_base).exclude(ai_summary=""):
        score = _score(material.ai_summary, terms) + _score(material.name, terms) * 2
        if score > 0:
            results.append(
                {
                    "kind": "material_summary",
                    "id": material.id,
                    "title": f"资料摘要: {material.name}",
                    "snippet": (material.ai_summary or "")[:300],
                    "score": score,
                }
            )

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:top_k]


def hybrid_search(knowledge_base, query, top_k=5, candidate_k=20, embed_fn=None):
    """混合检索:关键词召回候选 → 语义重排 → RRF 融合。无嵌入/失败时回退关键词。

    embed_fn(texts)->List[vector] 可注入以便测试;默认走知识库的 EmbedProvider。
    """
    from apps.opspilot.services.wiki.embedding_service import cosine, embed_texts, rrf_fuse

    candidates = search(knowledge_base, query, top_k=candidate_k)
    if not candidates:
        return []

    def _key(c):
        return f"{c['kind']}:{c['id']}"

    by_key = {_key(c): c for c in candidates}
    kw_rank = [_key(c) for c in candidates]

    embed = embed_fn or (lambda texts: embed_texts(texts, knowledge_base.embed_provider))
    qvecs = embed([query])
    cvecs = embed([f"{c['title']} {c['snippet']}" for c in candidates])
    if not qvecs or not cvecs or len(cvecs) != len(candidates):
        return candidates[:top_k]  # 无嵌入 → 回退关键词

    qv = qvecs[0]
    order = sorted(range(len(candidates)), key=lambda i: cosine(qv, cvecs[i]), reverse=True)
    sem_rank = [_key(candidates[i]) for i in order]
    fused = rrf_fuse([kw_rank, sem_rank], top_k=top_k)
    return [by_key[k] for k in fused]


def _answer_with_llm(query, contexts, llm_model_id):
    if not llm_model_id:
        return None
    try:
        llm = LLMModel.objects.get(id=llm_model_id)
        ctx_text = "\n\n".join(f"[{c['title']}]\n{c['snippet']}" for c in contexts)
        prompt = (
            "基于下面的知识页面与资料摘要回答问题。优先使用知识页面;在回答末尾用 [引用: 标题] 标注所依据的页面。"
            "若资料不足,请明确说明。\n\n"
            f"# 上下文\n{ctx_text}\n\n# 问题\n{query}\n"
        )
        request = BasicLLMRequest(
            openai_api_base=llm.openai_api_base,
            openai_api_key=llm.openai_api_key,
            model=llm.model_name,
            temperature=0.2,
            user_message=prompt,
        )
        return (LLMClientFactory.invoke_isolated(request, [{"role": "user", "content": prompt}]) or "").strip()
    except Exception:
        logger.exception("wiki 问答 LLM 调用失败")
        return None


def answer(knowledge_base, query, llm_model_id=None, top_k=5):
    """问答试用:检索 + 作答 + 引用。返回 {answer, citations, contexts}。"""
    contexts = search(knowledge_base, query, top_k=top_k)
    citations = [{"kind": c["kind"], "id": c["id"], "title": c["title"]} for c in contexts]
    if not contexts:
        return {"answer": "知识库中暂无相关资料,无法回答该问题。", "citations": [], "contexts": []}
    llm_answer = _answer_with_llm(query, contexts, llm_model_id)
    if llm_answer is None:
        # 无模型/失败时的兜底:回显最相关页面摘要,保证可追溯
        top = contexts[0]
        llm_answer = f"根据《{top['title']}》:{top['snippet']}"
    return {"answer": llm_answer, "citations": citations, "contexts": contexts}
