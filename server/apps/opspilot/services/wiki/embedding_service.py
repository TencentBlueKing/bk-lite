"""嵌入与混合检索基础(P6,无需 pgvector)。

策略:**检索后重排(retrieve-then-rerank)**——关键词召回候选 → 对候选做向量相似度重排 →
RRF 融合关键词序与语义序。只需对小候选集调用嵌入服务,无需存储向量或 pgvector 扩展;
后续可用 pgvector 索引替换 in-Python 余弦以扩展规模。

嵌入调用走 EmbedProvider(OpenAI 兼容);cosine / rrf_fuse 为纯函数,便于测试。
"""

import logging
import math

logger = logging.getLogger("opspilot")


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
