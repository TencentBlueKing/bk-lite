"""Knowledge retrieval tool builders extracted from node.py."""
from __future__ import annotations

from apps.core.logger import opspilot_logger as logger


class KnowledgeToolsMixin:
    """Mixin for ToolsNodes; extracted without behavior change."""

    def _build_knowledge_retrieve_tool(self, graph_request):
        """构建 agent 可调用的 knowledge_retrieve 工具（双模式中的“工具模式”）。

        基于 request.naive_rag_request（DocumentRetrieverRequest 列表）按需检索：
        每次调用用 agent 的 query 覆盖各请求的 search_query 再走 PgvectorRag。
        best-effort：无知识库配置或构建失败时返回 None，不影响主引擎。
        """
        naive_rag_request = list(getattr(graph_request, "naive_rag_request", None) or [])
        if not naive_rag_request:
            return None
        try:
            from types import SimpleNamespace

            from apps.opspilot.metis.llm.rag.naive_rag.pgvector.pgvector_rag import PgvectorRag
            from apps.opspilot.metis.llm.tools.knowledge_tool import build_knowledge_retrieve_tool

            # 用 DocumentRetrieverRequest 作为“知识库”载体；kwargs_map 不参与（search_fn 自带逻辑）
            knowledge_bases = []
            kwargs_map = {}
            for idx, req in enumerate(naive_rag_request):
                kb_id = str(getattr(req, "index_name", None) or f"kb_{idx}")
                knowledge_bases.append(SimpleNamespace(id=kb_id, name=kb_id, req=req))
                kwargs_map[kb_id] = {}

            def _search_fn(kb, query, kwargs, score_threshold=0, is_qa=False):
                req = kb.req
                try:
                    cloned = req.model_copy(update={"search_query": query})
                except Exception:
                    cloned = req
                    try:
                        cloned.search_query = query
                    except Exception:
                        pass
                if PgvectorRag is None:
                    return []
                results = PgvectorRag().search(cloned)
                return self._normalize_kb_results(results)

            return build_knowledge_retrieve_tool(knowledge_bases, kwargs_map, search_fn=_search_fn)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("knowledge_retrieve 工具构建失败，跳过: %r", e)
            return None

    @staticmethod
    def _normalize_kb_results(results) -> list:
        """把 PgvectorRag 返回结果规整成 knowledge_tool 期望的 dict 列表。"""
        normalized = []
        for item in results or []:
            meta = getattr(item, "metadata", None)
            if meta is None and isinstance(item, dict):
                meta = item.get("metadata", {})
            page = getattr(item, "page_content", None)
            if page is None and isinstance(item, dict):
                page = item.get("page_content") or item.get("content", "")
            normalized.append(
                {
                    "content": page or "",
                    "title": (meta or {}).get("title") or (meta or {}).get("source", ""),
                    "score": (meta or {}).get("score") or getattr(item, "score", 0),
                }
            )
        return normalized


# Backward-compat module-level aliases (tests patch chain.node.*)
_build_knowledge_retrieve_tool = KnowledgeToolsMixin._build_knowledge_retrieve_tool
_normalize_kb_results = KnowledgeToolsMixin._normalize_kb_results
