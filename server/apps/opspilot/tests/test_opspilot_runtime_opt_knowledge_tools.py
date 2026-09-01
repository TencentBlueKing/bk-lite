"""OpsPilot runtime optimization: knowledge_tools unit tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


class TestNormalizeKbResults:
    def test_normalizes_object_and_dict_items(self):
        from apps.opspilot.metis.llm.chain.knowledge_tools import _normalize_kb_results

        doc = SimpleNamespace(
            page_content="hello",
            metadata={"title": "T", "score": 0.9},
        )
        row = {"content": "world", "metadata": {"source": "S"}, "score": 0.5}
        out = _normalize_kb_results([doc, row, None])
        assert out[0]["content"] == "hello"
        assert out[0]["title"] == "T"
        assert out[1]["content"] == "world"
        assert out[1]["title"] == "S"
        assert out[2]["content"] == ""


class TestBuildKnowledgeRetrieveTool:
    def test_returns_none_when_no_naive_rag_request(self):
        from apps.opspilot.metis.llm.chain.knowledge_tools import KnowledgeToolsMixin

        mixin = KnowledgeToolsMixin()
        request = SimpleNamespace(naive_rag_request=[])
        assert mixin._build_knowledge_retrieve_tool(request) is None

    def test_builds_tool_and_search_fn(self):
        import sys
        from types import ModuleType

        from apps.opspilot.metis.llm.chain.knowledge_tools import KnowledgeToolsMixin

        mixin = KnowledgeToolsMixin()
        req = SimpleNamespace(index_name="kb1", search_query="seed")
        req.model_copy = MagicMock(return_value=req)
        graph_request = SimpleNamespace(naive_rag_request=[req])

        fake_tool = object()
        rag_mod = ModuleType("apps.opspilot.metis.llm.rag.naive_rag.pgvector.pgvector_rag")
        rag_cls = MagicMock()
        rag_cls.return_value.search.return_value = [
            SimpleNamespace(page_content="hit", metadata={"title": "doc"})
        ]
        rag_mod.PgvectorRag = rag_cls
        with patch.dict(
            sys.modules,
            {"apps.opspilot.metis.llm.rag.naive_rag.pgvector.pgvector_rag": rag_mod},
        ):
            with patch(
                "apps.opspilot.metis.llm.tools.knowledge_tool.build_knowledge_retrieve_tool",
                return_value=fake_tool,
            ) as build_tool:
                tool = mixin._build_knowledge_retrieve_tool(graph_request)

        assert tool is fake_tool
        search_fn = build_tool.call_args.kwargs["search_fn"]
        results = search_fn(SimpleNamespace(req=req), "query", {})
        assert results[0]["content"] == "hit"

    def test_returns_none_on_build_failure(self):
        from apps.opspilot.metis.llm.chain.knowledge_tools import KnowledgeToolsMixin

        mixin = KnowledgeToolsMixin()
        graph_request = SimpleNamespace(naive_rag_request=[SimpleNamespace(index_name="kb1")])
        with patch(
            "apps.opspilot.metis.llm.tools.knowledge_tool.build_knowledge_retrieve_tool",
            side_effect=RuntimeError("boom"),
        ):
            assert mixin._build_knowledge_retrieve_tool(graph_request) is None
