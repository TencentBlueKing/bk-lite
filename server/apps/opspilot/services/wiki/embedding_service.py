"""嵌入与混合检索基础(P6,无需 pgvector)。

策略:**检索后重排(retrieve-then-rerank)**——关键词召回候选 → 对候选做向量相似度重排 →
RRF 融合关键词序与语义序。只需对小候选集调用嵌入服务,无需存储向量或 pgvector 扩展;
后续可用 pgvector 索引替换 in-Python 余弦以扩展规模。

嵌入调用走 EmbedProvider(OpenAI 兼容);cosine / rrf_fuse 为纯函数,便于测试。
"""

import logging
import math
import re

logger = logging.getLogger("opspilot")

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def chunk_markdown(body, max_chars=800):
    """按 markdown 标题切分正文为块,过长段落再按 max_chars 二次切。

    返回 [{idx, text, heading_path}];heading_path 为该块所属最近标题。
    """
    sections, heading, buf = [], "", []

    def _flush():
        text = "\n".join(buf).strip()
        if text:
            sections.append({"heading_path": heading, "text": text})

    for line in (body or "").splitlines():
        m = _HEADING_RE.match(line)
        if m:
            _flush()
            heading = m.group(2).strip()
            buf = [line]
        else:
            buf.append(line)
    _flush()

    out = []
    for sec in sections:
        text = sec["text"]
        if len(text) <= max_chars:
            out.append(sec)
        else:
            for i in range(0, len(text), max_chars):
                out.append({"heading_path": sec["heading_path"], "text": text[i : i + max_chars]})
    return [{"idx": i, **sec} for i, sec in enumerate(out)]


def cosine(a, b):
    """两个等长向量的余弦相似度;任一为空或零向量返回 0。"""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def rrf_fuse(rank_lists, k=60, top_k=None):
    """Reciprocal Rank Fusion:输入多个有序 id 列表,返回融合后按分数降序的 id 列表。

    score(id) = Σ 1/(k + rank),rank 从 1 起。多路都靠前的条目得分最高。
    """
    scores = {}
    for ranking in rank_lists:
        for rank, item_id in enumerate(ranking, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
    fused = sorted(scores, key=lambda i: scores[i], reverse=True)
    return fused[:top_k] if top_k else fused


def index_version(version, embed_provider, embed_fn=None):
    """为页面版本生成并存储正文嵌入(语义索引)。返回是否成功写入。

    无 provider/正文为空/嵌入失败时静默跳过(置空),不影响主流程。embed_fn 可注入测试。
    """
    body = (getattr(version, "body", "") or "").strip()
    if not body:
        return False
    embed = embed_fn or (lambda texts: embed_texts(texts, embed_provider))
    vecs = embed([body[:8000]])
    if not vecs or not vecs[0]:
        return False
    version.embedding = vecs[0]
    version.save(update_fields=["embedding"])
    return True


def reindex_knowledge_base(knowledge_base, embed_fn=None):
    """为知识库所有有效页面的当前版本(重新)生成语义索引,返回成功建索引的页面数。"""
    from apps.opspilot.models import KnowledgePage

    count = 0
    pages = KnowledgePage.objects.filter(knowledge_base=knowledge_base, status="active").select_related("current_version")
    for page in pages:
        cv = page.current_version
        if cv and index_version(cv, knowledge_base.embed_provider, embed_fn=embed_fn):
            count += 1
    return count


def semantic_search(knowledge_base, query, top_k=5, embed_fn=None):
    """基于已存储的页面嵌入做语义检索(余弦),返回 [{id,title,snippet,score}]。

    仅覆盖已建索引(current_version.embedding 非空)的页面;无嵌入则返回 []。
    """
    from apps.opspilot.models import KnowledgePage

    embed = embed_fn or (lambda texts: embed_texts(texts, knowledge_base.embed_provider))
    qvecs = embed([query])
    if not qvecs or not qvecs[0]:
        return []
    qv = qvecs[0]
    results = []
    pages = KnowledgePage.objects.filter(knowledge_base=knowledge_base, status="active").select_related("current_version")
    for page in pages:
        cv = page.current_version
        vec = getattr(cv, "embedding", None) if cv else None
        if not vec:
            continue
        score = cosine(qv, vec)
        if score > 0:
            body = cv.body or ""
            results.append({"kind": "page", "id": page.id, "title": page.title, "snippet": body[:300], "score": score})
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:top_k]


def reindex_page_chunks(page, embed_provider, embed_fn=None):
    """重建某页面当前版本的分块索引:删旧块 → 切块 → 批量嵌入 → 落库。返回建索引的块数。"""
    from django.db import transaction

    from apps.opspilot.models import PageChunk

    cv = page.current_version
    if not cv:
        return 0
    chunks = chunk_markdown(cv.body or "")
    if not chunks:
        with transaction.atomic():
            PageChunk.objects.filter(page=page).delete()
        return 0
    embed = embed_fn or (lambda texts: embed_texts(texts, embed_provider))
    vecs = embed([c["text"] for c in chunks])
    if not vecs or len(vecs) != len(chunks):
        return 0
    with transaction.atomic():
        PageChunk.objects.filter(page=page).delete()
        PageChunk.objects.bulk_create(
            [
                PageChunk(
                    page=page,
                    version=cv,
                    idx=c["idx"],
                    text=c["text"],
                    heading_path=c["heading_path"][:512],
                    embedding=vecs[i],
                )
                for i, c in enumerate(chunks)
            ]
        )
    return len(chunks)


def reindex_chunks(knowledge_base, embed_fn=None):
    """为知识库所有有效页面重建分块索引,返回 (页面数, 块数)。"""
    from apps.opspilot.models import KnowledgePage

    pages = KnowledgePage.objects.filter(knowledge_base=knowledge_base, status="active").select_related("current_version")
    n_pages = n_chunks = 0
    for page in pages:
        c = reindex_page_chunks(page, knowledge_base.embed_provider, embed_fn=embed_fn)
        if c:
            n_pages += 1
            n_chunks += c
    return n_pages, n_chunks


def chunk_semantic_search(knowledge_base, query, top_k=5, embed_fn=None):
    """块级语义检索:query 嵌入 vs 已存块嵌入余弦,返回 [{page_id,title,heading_path,snippet,score}]。"""
    from apps.opspilot.models import PageChunk

    embed = embed_fn or (lambda texts: embed_texts(texts, knowledge_base.embed_provider))
    qvecs = embed([query])
    if not qvecs or not qvecs[0]:
        return []
    qv = qvecs[0]
    results = []
    chunks = PageChunk.objects.filter(page__knowledge_base=knowledge_base, page__status="active").select_related("page")
    for ch in chunks:
        if not ch.embedding:
            continue
        score = cosine(qv, ch.embedding)
        if score > 0:
            results.append(
                {
                    "page_id": ch.page_id,
                    "title": ch.page.title,
                    "heading_path": ch.heading_path,
                    "snippet": (ch.text or "")[:300],
                    "score": score,
                }
            )
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:top_k]


def embed_texts(texts, embed_provider):
    """用 EmbedProvider(OpenAI 兼容)批量生成嵌入向量;失败返回 []。"""
    if not texts or embed_provider is None:
        return []
    try:
        from openai import OpenAI

        client = OpenAI(base_url=embed_provider.base_url, api_key=embed_provider.api_key)
        resp = client.embeddings.create(model=embed_provider.model_name, input=list(texts))
        return [item.embedding for item in resp.data]
    except Exception:
        logger.exception("wiki 嵌入生成失败 provider=%s", getattr(embed_provider, "id", None))
        return []
