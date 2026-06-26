"""knowledge_retrieve 工具（agent 可调用的按需 RAG 检索）。

与预检索的 ``naive_rag_node`` 不同，本工具把知识库检索暴露为一个 langchain
``StructuredTool``，由 agent 自主决定检索时机、检索几轮、检索哪些知识库。

工厂函数 :func:`build_knowledge_retrieve_tool` 接收一组知识库对象与对应的
检索 kwargs，返回名为 ``knowledge_retrieve`` 的工具。底层检索复用
:meth:`KnowledgeSearchService.search`，但为便于单元测试可通过 ``search_fn``
注入替身（默认即为 ``KnowledgeSearchService.search``）。
"""

from typing import Any, Callable, Dict, List, Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from apps.core.logger import opspilot_logger as logger


class KnowledgeRetrieveInput(BaseModel):
    """knowledge_retrieve 工具入参 schema。"""

    query: str = Field(..., description="检索查询语句，应为完整、清晰的自然语言问题或关键词")
    kb_ids: Optional[List[Any]] = Field(
        default=None,
        description="可选，限定检索的知识库 id 列表；不传则检索全部已配置知识库",
    )


def _format_doc(kb_name: str, doc: Dict[str, Any], is_qa: bool) -> str:
    """把单条检索结果格式化为带来源标签的文本片段。"""
    score = doc.get("score", 0)
    title = doc.get("knowledge_title") or doc.get("knowledge_id") or "N/A"
    header = f"[来源: {kb_name} / {title}] (score: {score})"

    if is_qa:
        question = doc.get("question", "")
        answer = doc.get("answer", "")
        body = f"问题: {question}\n答案: {answer}"
    else:
        body = doc.get("content", "")

    return f"{header}\n{body}"


def build_knowledge_retrieve_tool(
    knowledge_bases: List[Any],
    kwargs_map: Dict[Any, Dict[str, Any]],
    score_threshold: float = 0,
    is_qa: bool = False,
    search_fn: Optional[Callable[..., List[Dict[str, Any]]]] = None,
    empty_hint: str = "未检索到与查询相关的知识内容。",
) -> StructuredTool:
    """构建 ``knowledge_retrieve`` 工具。

    Args:
        knowledge_bases: 知识库对象列表（需具备 ``id`` 与 ``name`` 属性）。
        kwargs_map: 以知识库 id 为键的检索参数字典（即每个 KB 的 naive_rag kwargs）。
        score_threshold: 分数阈值，透传给底层检索。
        is_qa: 是否为问答（QA）检索模式。
        search_fn: 检索实现，签名兼容
            ``search(knowledge_base, query, kwargs, score_threshold=, is_qa=)``。
            默认使用 :meth:`KnowledgeSearchService.search`，单测可注入替身。
        empty_hint: 全部知识库均无命中时返回的占位提示。

    Returns:
        名为 ``knowledge_retrieve`` 的 :class:`StructuredTool`。
    """
    # 延迟导入，避免在仅需工厂的场景下拉起重型依赖链。
    from apps.opspilot.services.knowledge_search_service import KnowledgeSearchService

    default_search_fn = KnowledgeSearchService.search
    resolved_search_fn = search_fn or default_search_fn

    def _retrieve(query: str, kb_ids: Optional[List[Any]] = None) -> str:
        # 把传入的 kb_ids 统一为字符串集合，兼容 int/str 混传。
        id_filter = None
        if kb_ids:
            id_filter = {str(i) for i in kb_ids}

        snippets: List[str] = []
        for kb in knowledge_bases:
            if id_filter is not None and str(kb.id) not in id_filter:
                continue

            kb_kwargs = kwargs_map.get(kb.id, {})
            try:
                results = resolved_search_fn(
                    kb,
                    query,
                    kb_kwargs,
                    score_threshold,
                    is_qa,
                )
            except Exception:
                # 单个知识库检索失败不应影响其它知识库。
                logger.exception(f"knowledge_retrieve 检索知识库[{getattr(kb, 'name', kb.id)}]失败")
                continue

            kb_name = getattr(kb, "name", str(kb.id))
            for doc in results or []:
                snippets.append(_format_doc(kb_name, doc, is_qa))

        if not snippets:
            return empty_hint

        return "\n\n".join(snippets)

    return StructuredTool.from_function(
        func=_retrieve,
        name="knowledge_retrieve",
        description=(
            "从配置的知识库中按需检索相关资料。当你需要产品/运维/业务领域知识来回答问题时调用本工具。"
            "传入清晰的自然语言查询 query；可选传入 kb_ids 限定检索范围。返回带来源标签的知识片段文本。"
        ),
        args_schema=KnowledgeRetrieveInput,
        metadata={"default_search_fn": default_search_fn},
    )
