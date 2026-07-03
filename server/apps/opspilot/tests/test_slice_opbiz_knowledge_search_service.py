"""opspilot-biz 切片: services/knowledge_search_service.KnowledgeSearchService。

只 mock 真实外部边界 PgvectorRag（向量检索后端）；断言：
- search 对返回 doc 的结果整形（qa / 普通 / rerank 字段）与按分数降序排序；
- 检索异常时返回 [] 且在 kwargs 写入 _search_exception 标记；
- delete_es_content 对 doc_id（str/int/list）的归一化与请求字段。
"""

from types import SimpleNamespace

import pytest

from apps.opspilot.services.knowledge_search_service import KnowledgeSearchService

pytestmark = pytest.mark.unit


def _doc(page_content="", **meta):
    return SimpleNamespace(page_content=page_content, metadata=meta)


def _kb():
    """最小知识库替身：提供 search 所需方法 / 预取关系。"""
    folder = SimpleNamespace()
    folder.embed_model_id = 1
    folder.rerank_model_id = 2
    # _state.fields_cache 命中预取的 embed/rerank（避免 DB 查询）
    folder._state = SimpleNamespace(
        fields_cache={
            "embed_model": SimpleNamespace(base_url="http://e", api_key="ek", model_name="em"),
            "rerank_model": SimpleNamespace(base_url="http://r", api_key="rk", model_name="rm"),
        }
    )
    folder.knowledge_index_name = lambda: "idx-1"
    return folder


def _base_kwargs(**over):
    kw = {
        "embed_model": 1,
        "rerank_model": 2,
        "enable_rerank": False,
        "search_type": "similarity_score_threshold",
        "rerank_top_k": 5,
        "enable_naive_rag": True,
        "enable_qa_rag": True,
    }
    kw.update(over)
    return kw


class TestSearch:
    def test_普通模式整形并排序(self, mocker):
        rag = mocker.Mock()
        rag.search.return_value = [
            _doc("low", similarity_score=0.2, knowledge_id="k1", knowledge_title="t1"),
            _doc("high", similarity_score=0.9, knowledge_id="k2", knowledge_title="t2"),
        ]
        mocker.patch(
            "apps.opspilot.services.knowledge_search_service.PgvectorRag", return_value=rag
        )
        out = KnowledgeSearchService.search(_kb(), "q", _base_kwargs())
        # 按 score 降序
        assert [d["score"] for d in out] == [0.9, 0.2]
        assert out[0]["content"] == "high"
        assert out[0]["knowledge_id"] == "k2"
        # 非 qa 模式不含 question 字段
        assert "question" not in out[0]

    def test_qa模式整形(self, mocker):
        rag = mocker.Mock()
        rag.search.return_value = [
            _doc(similarity_score=0.5, qa_question="问?", qa_answer="答", knowledge_id="k", knowledge_title="t"),
        ]
        mocker.patch(
            "apps.opspilot.services.knowledge_search_service.PgvectorRag", return_value=rag
        )
        out = KnowledgeSearchService.search(_kb(), "q", _base_kwargs(), is_qa=True)
        assert out[0]["question"] == "问?"
        assert out[0]["answer"] == "答"
        assert "content" not in out[0]

    def test_rerank附加relevance_score(self, mocker):
        rag = mocker.Mock()
        rag.search.return_value = [
            _doc("c", similarity_score=0.7, relevance_score=0.95, knowledge_id="k", knowledge_title="t"),
        ]
        mocker.patch(
            "apps.opspilot.services.knowledge_search_service.PgvectorRag", return_value=rag
        )
        out = KnowledgeSearchService.search(_kb(), "q", _base_kwargs(enable_rerank=True))
        assert out[0]["rerank_score"] == 0.95

    def test_检索异常返回空且写标记(self, mocker):
        rag = mocker.Mock()
        boom = RuntimeError("backend down")
        rag.search.side_effect = boom
        mocker.patch(
            "apps.opspilot.services.knowledge_search_service.PgvectorRag", return_value=rag
        )
        kwargs = _base_kwargs()
        out = KnowledgeSearchService.search(_kb(), "q", kwargs)
        assert out == []
        # 写入内部错误标记，区分故障与无结果
        assert kwargs["_search_exception"] is boom

    def test_无结果返回空且无异常标记(self, mocker):
        rag = mocker.Mock()
        rag.search.return_value = []
        mocker.patch(
            "apps.opspilot.services.knowledge_search_service.PgvectorRag", return_value=rag
        )
        kwargs = _base_kwargs()
        out = KnowledgeSearchService.search(_kb(), "q", kwargs)
        assert out == []
        assert "_search_exception" not in kwargs


class TestDeleteEsContent:
    def test_int_doc_id归一化为字符串列表_knowledge(self, mocker):
        rag = mocker.Mock()
        mocker.patch(
            "apps.opspilot.services.knowledge_search_service.PgvectorRag", return_value=rag
        )
        KnowledgeSearchService.delete_es_content("idx", 123, doc_name="d", is_chunk=False)
        req = rag.delete_document.call_args[0][0]
        assert req.knowledge_ids == ["123"]
        assert req.chunk_ids == []

    def test_list_doc_id_chunk模式(self, mocker):
        rag = mocker.Mock()
        mocker.patch(
            "apps.opspilot.services.knowledge_search_service.PgvectorRag", return_value=rag
        )
        KnowledgeSearchService.delete_es_content("idx", [1, 2], is_chunk=True, keep_qa=True)
        req = rag.delete_document.call_args[0][0]
        assert req.chunk_ids == ["1", "2"]
        assert req.knowledge_ids == []
        assert req.keep_qa is True

    def test_删除异常被吞掉不抛(self, mocker):
        rag = mocker.Mock()
        rag.delete_document.side_effect = RuntimeError("x")
        mocker.patch(
            "apps.opspilot.services.knowledge_search_service.PgvectorRag", return_value=rag
        )
        # 不应抛出
        KnowledgeSearchService.delete_es_content("idx", "5", doc_name="doc")


class TestChangeChunkEnable:
    def test_enabled_true写true(self, mocker):
        rag = mocker.Mock()
        mocker.patch(
            "apps.opspilot.services.knowledge_search_service.PgvectorRag", return_value=rag
        )
        KnowledgeSearchService.change_chunk_enable("idx", 7, True)
        req = rag.update_metadata.call_args[0][0]
        assert req.chunk_ids == ["7"]
        assert req.metadata == {"enabled": "true"}

    def test_enabled_false写false(self, mocker):
        rag = mocker.Mock()
        mocker.patch(
            "apps.opspilot.services.knowledge_search_service.PgvectorRag", return_value=rag
        )
        KnowledgeSearchService.change_chunk_enable("idx", 7, False)
        req = rag.update_metadata.call_args[0][0]
        assert req.metadata == {"enabled": "false"}


class TestGraphRagRequest:
    def test_未启用graph_rag返回空(self):
        out = KnowledgeSearchService.set_graph_rag_request(_kb(), {"enable_graph_rag": False}, "q")
        assert out == {}
