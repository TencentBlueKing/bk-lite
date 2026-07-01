"""ops-tasks-engine 切片: tasks.py 知识训练 / QA 摄取编排真实测试。

聚焦真实编排与 DB 副作用，仅在 RAG / ES 存储边界打桩：
- general_embed_by_document_list: 创建 KnowledgeTask、逐文档训练、全成功删任务、
  有失败保留任务并置 FAILED；invoke_one_document is_show 预览分支
- invoke_document_to_es: 文档不存在短路；成功置 READY；失败置 ERROR
- create_qa_pairs_by_json: 创建 QAPairs + KnowledgeTask、逐条摄取、完成后删任务、计数累加
- _build_qa_item_params / _ingest_qa_once / _ingest_single_qa_item: 参数构建、成功/失败/异常/空 instruction

外部边界打桩：tasks.invoke_one_document / tasks.invoke_document_to_es /
tasks.PgvectorRag / KnowledgeSearchService.delete_es_content。DB 用真实 Postgres。
"""

import pydantic.root_model  # noqa  预热

import pytest

from apps.opspilot import tasks
from apps.opspilot.enum import DocumentStatus, KnowledgeTaskStatus
from apps.opspilot.models import KnowledgeBase, KnowledgeDocument, KnowledgeTask, QAPairs

pytestmark = pytest.mark.django_db


@pytest.fixture
def kb():
    return KnowledgeBase.objects.create(name="kb", team=[1])


def _make_doc(kb, name="doc", status=DocumentStatus.PENDING, source="manual"):
    return KnowledgeDocument.objects.create(
        knowledge_base=kb, name=name, train_status=status, knowledge_source_type=source, created_by="u", domain="d.com"
    )


# ===========================================================================
# general_embed_by_document_list
# ===========================================================================
class TestGeneralEmbedByDocumentList:
    def test_全部成功删除任务(self, mocker, kb):
        d1 = _make_doc(kb, "d1")
        d2 = _make_doc(kb, "d2")

        def _fake_invoke(document=None, delete_qa_pairs=False):
            document.train_status = DocumentStatus.READY
            document.save()

        mocker.patch.object(tasks, "invoke_document_to_es", side_effect=_fake_invoke)
        tasks.general_embed_by_document_list(
            KnowledgeDocument.objects.filter(id__in=[d1.id, d2.id]), username="u", domain="d.com"
        )
        # 全成功 -> 任务行被删除，不残留
        assert KnowledgeTask.objects.count() == 0

    def test_有失败保留任务并置FAILED(self, mocker, kb):
        d1 = _make_doc(kb, "d1")
        d2 = _make_doc(kb, "d2")

        def _fake_invoke(document=None, delete_qa_pairs=False):
            # d2 训练失败
            document.train_status = DocumentStatus.ERROR if document.name == "d2" else DocumentStatus.READY
            document.save()

        mocker.patch.object(tasks, "invoke_document_to_es", side_effect=_fake_invoke)
        tasks.general_embed_by_document_list(
            KnowledgeDocument.objects.filter(id__in=[d1.id, d2.id]), username="u", domain="d.com"
        )
        task = KnowledgeTask.objects.get()
        assert task.status == KnowledgeTaskStatus.FAILED
        # 一个成功
        assert task.completed_count == 1

    def test_异常被捕获标记文档ERROR并保留任务(self, mocker, kb):
        d1 = _make_doc(kb, "d1")
        mocker.patch.object(tasks, "invoke_document_to_es", side_effect=RuntimeError("boom"))
        tasks.general_embed_by_document_list(
            KnowledgeDocument.objects.filter(id__in=[d1.id]), username="u", domain="d.com"
        )
        d1.refresh_from_db()
        assert d1.train_status == DocumentStatus.ERROR
        assert d1.error_message == "训练过程中发生异常"
        assert KnowledgeTask.objects.get().status == KnowledgeTaskStatus.FAILED

    def test_is_show预览返回前若干page_content(self, mocker, kb):
        d1 = _make_doc(kb, "d1")
        remote_docs = [{"page_content": f"c{i}"} for i in range(15)]
        mocker.patch.object(tasks, "invoke_one_document", return_value=({}, remote_docs, None))
        docs = tasks.general_embed_by_document_list(
            KnowledgeDocument.objects.filter(id__in=[d1.id]), is_show=True
        )
        assert docs == [f"c{i}" for i in range(10)]


# ===========================================================================
# invoke_document_to_es
# ===========================================================================
class TestInvokeDocumentToEs:
    def test_文档不存在短路(self, mocker):
        # 不存在的 document_id，且未传 document
        spy = mocker.patch.object(tasks, "invoke_one_document")
        tasks.invoke_document_to_es(document_id=999999)
        spy.assert_not_called()

    def test_成功置READY(self, mocker, kb):
        d = _make_doc(kb, "d")
        mocker.patch.object(tasks.KnowledgeSearchService, "delete_es_content", return_value=None)
        mocker.patch.object(tasks, "invoke_one_document", return_value=(True, [], None))
        tasks.invoke_document_to_es(document=d)
        d.refresh_from_db()
        assert d.train_status == DocumentStatus.READY
        assert d.error_message is None

    def test_失败置ERROR并记录错误(self, mocker, kb):
        d = _make_doc(kb, "d")
        mocker.patch.object(tasks.KnowledgeSearchService, "delete_es_content", return_value=None)
        mocker.patch.object(tasks, "invoke_one_document", return_value=(False, [], "摄取失败"))
        tasks.invoke_document_to_es(document=d)
        d.refresh_from_db()
        assert d.train_status == DocumentStatus.ERROR
        assert d.error_message == "摄取失败"


# ===========================================================================
# invoke_one_document —— 类型分派 + 结果判定
# ===========================================================================
class TestInvokeOneDocument:
    def test_不支持类型返回失败(self, mocker, kb):
        d = _make_doc(kb, "d", source="unknown_type")
        mocker.patch.object(tasks, "PgvectorRag")
        ok, docs, err = tasks.invoke_one_document(d)
        assert ok is False
        assert "不支持的文档类型" in err

    def test_manual摄取成功(self, mocker, kb):
        d = _make_doc(kb, "d", source="manual")
        mocker.patch.object(tasks, "PgvectorRag")
        mocker.patch.object(tasks, "_handle_manual_ingest", return_value={"status": "success", "chunks_size": 5})
        ok, docs, err = tasks.invoke_one_document(d)
        assert ok is True
        assert err is None
        # invoke_one_document 只在内存对象上设置 chunk_size（落库由调用方负责）
        assert d.chunk_size == 5

    def test_chunk_size为0记录错误(self, mocker, kb):
        d = _make_doc(kb, "d", source="manual")
        mocker.patch.object(tasks, "PgvectorRag")
        mocker.patch.object(tasks, "_handle_manual_ingest", return_value={"status": "success", "chunks_size": 0})
        ok, docs, err = tasks.invoke_one_document(d)
        assert ok is True  # status success
        assert "获取不到文档" in err

    def test_摄取抛异常返回error(self, mocker, kb):
        d = _make_doc(kb, "d", source="manual")
        mocker.patch.object(tasks, "PgvectorRag")
        mocker.patch.object(tasks, "_handle_manual_ingest", side_effect=ValueError("找不到记录"))
        ok, docs, err = tasks.invoke_one_document(d)
        assert ok is False
        assert err == "找不到记录"


# ===========================================================================
# create_qa_pairs_by_json
# ===========================================================================
class TestCreateQaPairsByJson:
    def test_知识库不存在直接返回(self, mocker):
        spy = mocker.patch.object(tasks, "_initialize_qa_task")
        tasks.create_qa_pairs_by_json({"a": []}, knowledge_base_id=999999, username="u", domain="d")
        spy.assert_not_called()

    def test_批量创建并删除任务(self, mocker, kb):
        # _prepare_qa_ingest_params 访问 kb.embed_model（可能为空），打桩基础参数构建
        mocker.patch.object(tasks, "_prepare_qa_ingest_params", return_value={"knowledge_id": "0"})
        mocker.patch.object(tasks, "PgvectorRag")
        # _process_single_qa_pairs 真实编排成本高（含 sleep/RAG），桩其返回成功条数
        mocker.patch.object(tasks, "_process_single_qa_pairs", return_value=2)
        file_data = {"QA组1": [{"instruction": "q1", "output": "a1"}, {"instruction": "q2", "output": "a2"}]}
        tasks.create_qa_pairs_by_json(file_data, knowledge_base_id=kb.id, username="u", domain="d")
        # QAPairs 真实落库且完成、计数累加
        qa = QAPairs.objects.get(name="QA组1", knowledge_base=kb)
        assert qa.status == "completed"
        assert qa.qa_count == 2
        assert qa.generate_count == 2
        # 任务行执行完被删除
        assert KnowledgeTask.objects.count() == 0


# ===========================================================================
# QA 单项摄取辅助函数
# ===========================================================================
class TestQaItemHelpers:
    def test_build_params_空instruction返回None(self):
        assert tasks._build_qa_item_params({"instruction": "", "output": "a"}, {}, {}) is None

    def test_build_params_注入metadata(self):
        params = tasks._build_qa_item_params(
            {"instruction": "q", "output": "a"}, {"knowledge_id": "k"}, {"enabled": "true"}
        )
        assert params["knowledge_id"] == "k"
        assert params["metadata"]["qa_question"] == "q"
        assert params["metadata"]["qa_answer"] == "a"
        assert params["metadata"]["enabled"] == "true"

    def test_ingest_once_成功(self, mocker):
        rag = mocker.Mock()
        rag.custom_content_ingest.return_value = {"status": "success"}
        assert tasks._ingest_qa_once("content", {}, rag, 0) is True

    def test_ingest_once_非success返回False(self, mocker):
        rag = mocker.Mock()
        rag.custom_content_ingest.return_value = {"status": "fail", "message": "x"}
        assert tasks._ingest_qa_once("content", {}, rag, 0) is False

    def test_ingest_once_异常返回False(self, mocker):
        rag = mocker.Mock()
        rag.custom_content_ingest.side_effect = RuntimeError("boom")
        assert tasks._ingest_qa_once("content", {}, rag, 0) is False

    def test_ingest_single_空instruction返回None(self, mocker):
        rag = mocker.Mock()
        assert tasks._ingest_single_qa_item({"instruction": "", "output": "a"}, 0, {}, {}, rag) is None
        rag.custom_content_ingest.assert_not_called()

    def test_ingest_single_正常委托ingest_once(self, mocker):
        rag = mocker.Mock()
        rag.custom_content_ingest.return_value = {"status": "success"}
        assert tasks._ingest_single_qa_item({"instruction": "q", "output": "a"}, 0, {}, {}, rag) is True
