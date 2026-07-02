"""opspilot-biz 切片: knowledge_search_service 补充覆盖。

补齐既有用例未覆盖的分支：
- set_graph_rag_request 启用且有/无 KnowledgeGraph 的两条路径；
- _get_embed_provider / _get_rerank_provider 未命中缓存时回退 DB .get；
- delete_es_index 正常与异常；
- delete_es_content 带 doc_name 的成功日志与异常降级日志。
只 mock PgvectorRag（向量检索后端）与 ORM .get/.filter（真实 DB 边界）。
"""

from types import SimpleNamespace

import pydantic.root_model  # noqa
import pytest

from apps.opspilot.services import knowledge_search_service as kss
from apps.opspilot.services.knowledge_search_service import KnowledgeSearchService

pytestmark = pytest.mark.unit


class TestSetGraphRagRequest:
    def test_未启用返回空字典(self):
        kb = SimpleNamespace(id=1, graph_size=10)
        out = KnowledgeSearchService.set_graph_rag_request(kb, {"enable_graph_rag": False}, "q")
        assert out == {}

    def test_启用但无graph对象返回空(self, mocker):
        kb = SimpleNamespace(id=1, graph_size=10)
        mocker.patch.object(kss.KnowledgeGraph.objects, "filter").return_value.first.return_value = None
        out = KnowledgeSearchService.set_graph_rag_request(kb, {"enable_graph_rag": True}, "q")
        assert out == {}

    def test_启用且有graph对象构建完整请求(self, mocker):
        kb = SimpleNamespace(id=7, graph_size=20)
        graph_obj = SimpleNamespace(
            id=3,
            embed_model=SimpleNamespace(base_url="http://e", api_key="ek", model_name="em"),
            rerank_model=SimpleNamespace(base_url="http://r", api_key="", model_name="rm"),
        )
        mocker.patch.object(kss.KnowledgeGraph.objects, "filter").return_value.first.return_value = graph_obj
        out = KnowledgeSearchService.set_graph_rag_request(kb, {"enable_graph_rag": True}, "查询词")
        assert out["embed_model_base_url"] == "http://e"
        assert out["embed_model_api_key"] == "ek"
        assert out["embed_model_name"] == "em"
        assert out["rerank_model_base_url"] == "http://r"
        # 空 api_key 回退为单空格
        assert out["rerank_model_api_key"] == " "
        assert out["size"] == 20
        assert out["group_ids"] == ["graph-3"]
        assert out["search_query"] == "查询词"


class TestGetProvidersFallback:
    def test_embed_provider_未命中缓存走DB_get(self, mocker):
        # 知识库的 embed_model_id 与请求不一致 => 不复用 => .get
        kb = SimpleNamespace(embed_model_id=99, _state=SimpleNamespace(fields_cache={}))
        sentinel = SimpleNamespace(base_url="x")
        mocker.patch.object(kss.EmbedProvider.objects, "get", return_value=sentinel)
        assert KnowledgeSearchService._get_embed_provider(kb, 1) is sentinel
        kss.EmbedProvider.objects.get.assert_called_once_with(id=1)

    def test_embed_provider_缓存为None回退DB(self, mocker):
        kb = SimpleNamespace(embed_model_id=1, _state=SimpleNamespace(fields_cache={"embed_model": None}))
        sentinel = SimpleNamespace(base_url="y")
        mocker.patch.object(kss.EmbedProvider.objects, "get", return_value=sentinel)
        assert KnowledgeSearchService._get_embed_provider(kb, 1) is sentinel

    def test_embed_provider_命中缓存复用不查询DB(self, mocker):
        cached = SimpleNamespace(base_url="cached")
        kb = SimpleNamespace(embed_model_id=1, _state=SimpleNamespace(fields_cache={"embed_model": cached}))
        get = mocker.patch.object(kss.EmbedProvider.objects, "get")
        assert KnowledgeSearchService._get_embed_provider(kb, 1) is cached
        get.assert_not_called()

    def test_rerank_provider_未命中缓存走DB_get(self, mocker):
        kb = SimpleNamespace(rerank_model_id=99, _state=SimpleNamespace(fields_cache={}))
        sentinel = SimpleNamespace(base_url="z")
        mocker.patch.object(kss.RerankProvider.objects, "get", return_value=sentinel)
        assert KnowledgeSearchService._get_rerank_provider(kb, 2) is sentinel
        kss.RerankProvider.objects.get.assert_called_once_with(id=2)

    def test_rerank_provider_命中缓存复用(self, mocker):
        cached = SimpleNamespace(base_url="rc")
        kb = SimpleNamespace(rerank_model_id=2, _state=SimpleNamespace(fields_cache={"rerank_model": cached}))
        get = mocker.patch.object(kss.RerankProvider.objects, "get")
        assert KnowledgeSearchService._get_rerank_provider(kb, 2) is cached
        get.assert_not_called()


class TestDeleteEsIndex:
    def test_成功删除索引(self, mocker):
        fake_rag = mocker.MagicMock()
        mocker.patch.object(kss, "PgvectorRag", return_value=fake_rag)
        KnowledgeSearchService.delete_es_index("idx-1")
        fake_rag.delete_index.assert_called_once()
        req = fake_rag.delete_index.call_args[0][0]
        assert req.index_name == "idx-1"

    def test_删除异常被吞掉不抛(self, mocker):
        fake_rag = mocker.MagicMock()
        fake_rag.delete_index.side_effect = RuntimeError("boom")
        mocker.patch.object(kss, "PgvectorRag", return_value=fake_rag)
        # 不抛异常即视为通过
        KnowledgeSearchService.delete_es_index("idx-2")


class TestDeleteEsContentDocName:
    def test_成功删除带doc_name记录info(self, mocker):
        fake_rag = mocker.MagicMock()
        mocker.patch.object(kss, "PgvectorRag", return_value=fake_rag)
        log = mocker.patch.object(kss, "logger")
        KnowledgeSearchService.delete_es_content("idx", 5, doc_name="文档A")
        fake_rag.delete_document.assert_called_once()
        # knowledge 模式: knowledge_ids 含 "5"
        req = fake_rag.delete_document.call_args[0][0]
        assert req.knowledge_ids == ["5"]
        assert req.chunk_ids == []
        log.info.assert_called()

    def test_删除异常且带doc_name降级日志(self, mocker):
        fake_rag = mocker.MagicMock()
        fake_rag.delete_document.side_effect = ValueError("x")
        mocker.patch.object(kss, "PgvectorRag", return_value=fake_rag)
        log = mocker.patch.object(kss, "logger")
        KnowledgeSearchService.delete_es_content("idx", 5, doc_name="文档B")
        log.exception.assert_called()
        log.info.assert_called()  # "not found, skipping deletion"

    def test_chunk模式list_doc_id(self, mocker):
        fake_rag = mocker.MagicMock()
        mocker.patch.object(kss, "PgvectorRag", return_value=fake_rag)
        KnowledgeSearchService.delete_es_content("idx", [1, 2], is_chunk=True, keep_qa=True)
        req = fake_rag.delete_document.call_args[0][0]
        assert req.chunk_ids == ["1", "2"]
        assert req.knowledge_ids == []
        assert req.keep_qa is True
