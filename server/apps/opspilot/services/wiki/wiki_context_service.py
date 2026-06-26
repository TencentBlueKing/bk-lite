"""多智能体复用(P4):把 Wiki 检索结果整理成可注入聊天/技能提示词的上下文。

技能/智能体在配置中选择若干 Wiki 知识库;回答时调用 build_context(kb_ids, query) 取回
带编号引用的上下文块,供 chat chain 拼接进系统提示。检索复用 retrieval_service,
因此跨 DB 可用、无需向量;后续接入聊天链时只需在技能执行处调用本服务。
"""

import logging

from apps.opspilot.models import WikiKnowledgeBase
from apps.opspilot.services.wiki.retrieval_service import search as wiki_search

logger = logging.getLogger("opspilot")


def build_context(kb_ids, query, top_k=5, per_kb=5):
    """跨多个 Wiki 知识库检索,返回 {context, citations, hits}。

    - context:编号 markdown 文本,可直接拼进系统提示词;
    - citations:[{n, kb_id, kind, id, title}],供前端/回答标注来源;
    - hits:原始检索命中(含 score),供调用方进一步处理。
    """
    hits = []
    for kb in WikiKnowledgeBase.objects.filter(id__in=list(kb_ids or [])):
        for r in wiki_search(kb, query, top_k=per_kb):
            hits.append({**r, "kb_id": kb.id, "kb_name": kb.name})
    hits.sort(key=lambda h: h["score"], reverse=True)
    hits = hits[:top_k]

    lines, citations = [], []
    for i, h in enumerate(hits, 1):
        lines.append(f"[{i}] 《{h['title']}》(知识库: {h['kb_name']})\n{h['snippet']}")
        citations.append({"n": i, "kb_id": h["kb_id"], "kind": h["kind"], "id": h["id"], "title": h["title"]})
    return {"context": "\n\n".join(lines), "citations": citations, "hits": hits}


def augment_prompt(system_prompt, kb_ids, query, top_k=5):
    """把 Wiki 检索上下文拼接进系统提示词,返回 (新提示词, citations)。

    无所选知识库 / 无查询 / 无命中时,原样返回提示词与空引用,确保对聊天链零副作用。
    """
    if not kb_ids or not (query or "").strip():
        return system_prompt, []
    result = build_context(kb_ids, query, top_k=top_k)
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
