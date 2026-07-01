"""opspilot-ops 切片: viewsets/knowledge_document_view.KnowledgeDocumentViewSet 真实 DRF + DB 测试。

通过 APIRequestFactory 真实驱动 DRF、真实 ORM 落库（含 knowledge_base.team 作用域过滤），断言：
- create 内置接口禁用(405)；
- destroy（训练中拦截、正常删除联动清理 QAPairs/ConversationTag）；
- batch_train（无效参数 400、scoped 过滤 + celery .delay）；
- get_my_tasks（缺 kb_id、普通任务进度拼接）；
- testing（缺 query、naive/qa 检索装配文档元数据）；
- get_detail / get_chunk_detail（Document/QA/不支持类型/未命中）；
- delete_chunks（无效参数、成功）；enable_chunk（缺 chunk_id、成功、异常）；
- batch_delete（空、训练中拒绝、成功）；get_instance_detail / get_document_detail；
- update_document_base_info / update_parse_settings / update_chunk_settings /
  get_doc_list_config / preview_chunk / submit_settings。

仅 mock 真实外部边界：ChunkHelper(ES)、KnowledgeSearchService(ES)、GraphUtils(图库)、
celery .delay、general_embed_by_document_list、log_operation。断言 HTTP 状态 / JSON body /
DB 副作用 / 传给 celery 的 scoped id 契约。
"""

import json

import pydantic.root_model  # noqa  预热避免 cov 竞态
import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.opspilot.enum import DocumentStatus
from apps.opspilot.models import (
    ConversationTag,
    KnowledgeBase,
    KnowledgeDocument,
    KnowledgeTask,
    ManualKnowledge,
    QAPairs,
)
from apps.opspilot.viewsets.knowledge_document_view import KnowledgeDocumentViewSet

pytestmark = pytest.mark.django_db

KD_MOD = "apps.opspilot.viewsets.knowledge_document_view"


def _body(resp):
    if hasattr(resp, "data"):
        return resp.data
    return json.loads(resp.content.decode("utf-8"))


def _su():
    from apps.base.models import User

    u = User.objects.create_user(
        username=f"kd_su_{User.objects.count()}",
        password="x",
        domain="domain.com",
        locale="en",
        group_list=[{"id": 1, "name": "T1"}],
    )
    u.is_superuser = True
    u.save()
    return u


def _kb(name="kb"):
    return KnowledgeBase.objects.create(name=name, team=[1])


def _doc(kb, name="doc", source="manual", status=DocumentStatus.PENDING):
    return KnowledgeDocument.objects.create(
        knowledge_base=kb, name=name, knowledge_source_type=source, train_status=status
    )


def _dispatch(action_name, method, *, data=None, query="", user=None, pk=None):
    factory = APIRequestFactory()
    path = f"/{query}"
    if method in ("post",):
        request = factory.post(path, data=data or {}, format="json")
    elif method == "delete":
        request = factory.delete(path)
    else:
        request = factory.get(path)
    force_authenticate(request, user=user or _su())
    request.COOKIES["current_team"] = "1"
    view = KnowledgeDocumentViewSet.as_view({method: action_name})
    if pk is not None:
        return view(request, pk=pk)
    return view(request)


class TestCreateDisabled:
    def test_create返回405(self):
        resp = _dispatch("create", "post", data={"name": "x"})
        assert resp.status_code == 405
        assert _body(resp)["result"] is False


class TestDestroy:
    def test_训练中拦截(self):
        kb = _kb()
        doc = _doc(kb, status=DocumentStatus.TRAINING)
        resp = _dispatch("destroy", "delete", pk=doc.id)
        assert _body(resp)["result"] is False
        assert KnowledgeDocument.objects.filter(id=doc.id).exists()

    def test_正常删除联动清理(self, mocker):
        kb = _kb()
        doc = _doc(kb, status=DocumentStatus.PENDING)
        ConversationTag.objects.create(knowledge_document_id=doc.id, knowledge_base_id=kb.id)
        qa = QAPairs.objects.create(name="qa", knowledge_base=kb, document_id=doc.id)
        mocker.patch(f"{KD_MOD}.log_operation")
        # QAPairs.delete 触发 post_delete 清理 ES，mock 向量后端
        mocker.patch("apps.opspilot.services.knowledge_search_service.KnowledgeSearchService.delete_es_content")
        resp = _dispatch("destroy", "delete", pk=doc.id)
        assert _body(resp)["result"] is True
        assert not KnowledgeDocument.objects.filter(id=doc.id).exists()
        assert not ConversationTag.objects.filter(knowledge_document_id=doc.id).exists()
        assert not QAPairs.objects.filter(id=qa.id).exists()


class TestBatchTrain:
    def test_空参数走默认scoped为空(self):
        # 序列化器对 knowledge_document_ids 提供默认空列表，空请求合法，
        # scoped 为空时直接返回 result True（不触发训练）。
        resp = _dispatch("batch_train", "post", data={})
        assert resp.status_code == 200
        assert _body(resp)["result"] is True

    def test_scoped过滤并触发celery(self, mocker):
        kb = _kb()
        d1 = _doc(kb, name="d1")
        # 另一团队的文档，应被 scoped 过滤掉
        other_kb = KnowledgeBase.objects.create(name="okb", team=[9])
        d2 = _doc(other_kb, name="d2")
        delay = mocker.patch(f"{KD_MOD}.general_embed.delay")
        data = {"knowledge_document_ids": [d1.id, d2.id], "delete_qa_pairs": True}
        resp = _dispatch("batch_train", "post", data=data)
        assert _body(resp)["result"] is True
        d1.refresh_from_db()
        assert d1.train_status == DocumentStatus.TRAINING
        # 仅 scoped 内的 d1 被传入 celery
        called_ids = delay.call_args.args[0]
        assert called_ids == [d1.id]

    def test_scoped为空直接返回(self, mocker):
        other_kb = KnowledgeBase.objects.create(name="okb", team=[9])
        d2 = _doc(other_kb, name="d2")
        delay = mocker.patch(f"{KD_MOD}.general_embed.delay")
        resp = _dispatch("batch_train", "post", data={"knowledge_document_ids": [d2.id], "delete_qa_pairs": False})
        assert _body(resp)["result"] is True
        delay.assert_not_called()


class TestGetMyTasks:
    def test_缺kb_id(self):
        resp = _dispatch("get_my_tasks", "get")
        assert _body(resp)["result"] is False

    def test_普通任务进度拼接(self):
        kb = _kb()
        user = _su()
        KnowledgeTask.objects.create(
            task_name="t1",
            knowledge_base_id=kb.id,
            created_by=user.username,
            domain=user.domain,
            completed_count=3,
            total_count=10,
        )
        resp = _dispatch("get_my_tasks", "get", query=f"?knowledge_base_id={kb.id}", user=user)
        body = _body(resp)
        assert body["result"] is True
        assert body["data"][0]["train_progress"] == "3/10"


class TestTesting:
    def test_缺query(self):
        kb = _kb()
        resp = _dispatch("testing", "post", data={"knowledge_base_id": kb.id})
        assert _body(resp)["result"] is False

    def test_naive检索装配文档元数据(self, mocker):
        kb = _kb()
        doc = _doc(kb, name="命中文档")
        svc = mocker.patch(f"{KD_MOD}.KnowledgeSearchService").return_value
        svc.search.return_value = [{"knowledge_id": doc.id, "score": 0.9}]
        data = {
            "knowledge_base_id": kb.id,
            "query": "查询词",
            "enable_naive_rag": True,
            "enable_qa_rag": False,
            "enable_graph_rag": False,
        }
        resp = _dispatch("testing", "post", data=data)
        body = _body(resp)
        assert body["result"] is True
        assert body["data"]["docs"][0]["name"] == "命中文档"


class TestGetDetail:
    def test_返回es分页(self, mocker):
        kb = _kb()
        doc = _doc(kb)
        mocker.patch(
            f"{KD_MOD}.ChunkHelper.get_document_es_chunk",
            return_value={
                "count": 1,
                "documents": [{"metadata": {"chunk_id": "c1", "qa_count": 2}, "page_content": "正文"}],
            },
        )
        resp = _dispatch("get_detail", "get", pk=doc.id)
        body = _body(resp)
        assert body["result"] is True
        assert body["data"]["items"][0]["content"] == "正文"
        assert body["data"]["count"] == 1


class TestGetChunkDetail:
    def test_缺chunk_id(self):
        resp = _dispatch("get_chunk_detail", "get", query="?knowledge_id=1")
        assert _body(resp)["message"] is not None

    def test_document类型命中(self, mocker):
        kb = _kb()
        doc = _doc(kb, name="docA")
        mocker.patch(
            f"{KD_MOD}.ChunkHelper.get_document_es_chunk",
            return_value={"documents": [{"metadata": {"chunk_id": "c1"}, "page_content": "内容"}]},
        )
        resp = _dispatch("get_chunk_detail", "get", query=f"?knowledge_id={doc.id}&chunk_id=c1&type=Document")
        body = _body(resp)
        assert body["result"] is True
        assert body["data"]["doc_name"] == "docA"

    def test_qa类型命中(self, mocker):
        kb = _kb()
        qa = QAPairs.objects.create(name="qaX", knowledge_base=kb)
        mocker.patch(
            f"{KD_MOD}.ChunkHelper.get_document_es_chunk",
            return_value={
                "documents": [
                    {"metadata": {"chunk_id": "c1", "qa_question": "Q", "qa_answer": "A", "base_chunk_id": "b1"}}
                ]
            },
        )
        resp = _dispatch(
            "get_chunk_detail", "get", query=f"?knowledge_id=qa_pairs_id_{qa.id}&chunk_id=c1&type=QA"
        )
        body = _body(resp)
        assert body["result"] is True
        assert body["data"]["question"] == "Q"

    def test_不支持类型(self):
        resp = _dispatch("get_chunk_detail", "get", query="?knowledge_id=1&chunk_id=c1&type=Unknown")
        assert _body(resp)["result"] is True
        assert _body(resp)["message"] is not None

    def test_未命中(self, mocker):
        kb = _kb()
        doc = _doc(kb)
        mocker.patch(f"{KD_MOD}.ChunkHelper.get_document_es_chunk", return_value={"documents": []})
        resp = _dispatch("get_chunk_detail", "get", query=f"?knowledge_id={doc.id}&chunk_id=c1&type=Document")
        assert _body(resp)["result"] is False


class TestDeleteChunks:
    def test_无效参数400(self):
        resp = _dispatch("delete_chunks", "post", data={})
        assert resp.status_code == 400

    def test_成功(self, mocker):
        kb = _kb()
        mocker.patch(f"{KD_MOD}.ChunkHelper.delete_es_content", return_value=True)
        data = {"ids": ["c1", "c2"], "knowledge_base_id": kb.id, "delete_all": False}
        resp = _dispatch("delete_chunks", "post", data=data)
        assert _body(resp)["result"] is True

    def test_es失败(self, mocker):
        kb = _kb()
        mocker.patch(f"{KD_MOD}.ChunkHelper.delete_es_content", return_value=False)
        data = {"ids": ["c1"], "knowledge_base_id": kb.id, "delete_all": True}
        resp = _dispatch("delete_chunks", "post", data=data)
        assert _body(resp)["result"] is False


class TestEnableChunk:
    def test_缺chunk_id(self):
        kb = _kb()
        doc = _doc(kb)
        resp = _dispatch("enable_chunk", "post", data={"enabled": True}, pk=doc.id)
        assert _body(resp)["result"] is False

    def test_成功(self, mocker):
        kb = _kb()
        doc = _doc(kb)
        mocker.patch(f"{KD_MOD}.KnowledgeSearchService.change_chunk_enable", return_value=None)
        resp = _dispatch("enable_chunk", "post", data={"enabled": True, "chunk_id": "c1"}, pk=doc.id)
        assert _body(resp)["result"] is True

    def test_异常返回false(self, mocker):
        kb = _kb()
        doc = _doc(kb)
        mocker.patch(f"{KD_MOD}.KnowledgeSearchService.change_chunk_enable", side_effect=RuntimeError("x"))
        resp = _dispatch("enable_chunk", "post", data={"enabled": True, "chunk_id": "c1"}, pk=doc.id)
        assert _body(resp)["result"] is False


class TestBatchDelete:
    def test_空doc_ids(self):
        resp = _dispatch("batch_delete", "post", data={"doc_ids": [], "knowledge_base_id": 1})
        assert _body(resp)["result"] is True

    def test_训练中拒绝(self):
        kb = _kb()
        doc = _doc(kb, status=DocumentStatus.TRAINING)
        resp = _dispatch("batch_delete", "post", data={"doc_ids": [doc.id], "knowledge_base_id": kb.id})
        assert _body(resp)["result"] is False

    def test_成功(self, mocker):
        kb = _kb()
        doc = _doc(kb, status=DocumentStatus.PENDING)
        mocker.patch(f"{KD_MOD}.KnowledgeSearchService.delete_es_content", return_value=None)
        mocker.patch(f"{KD_MOD}.log_operation")
        resp = _dispatch("batch_delete", "post", data={"doc_ids": [doc.id], "knowledge_base_id": kb.id})
        assert _body(resp)["result"] is True
        assert not KnowledgeDocument.objects.filter(id=doc.id).exists()


class TestInstanceAndDocumentDetail:
    def test_get_instance_detail(self):
        kb = _kb()
        doc = _doc(kb, name="inst")
        resp = _dispatch("get_instance_detail", "get", pk=doc.id)
        body = _body(resp)
        assert body["result"] is True
        assert body["data"]["name"] == "inst"
        assert body["data"]["knowledge_base_id"] == kb.id

    def test_get_document_detail_manual(self):
        kb = _kb()
        doc = _doc(kb, name="man", source="manual")
        ManualKnowledge.objects.create(knowledge_document=doc, content="正文内容")
        resp = _dispatch("get_document_detail", "get", pk=doc.id)
        body = _body(resp)
        assert body["result"] is True
        assert body["data"]["content"] == "正文内容"


class TestUpdateSettings:
    def test_update_document_base_info_manual(self):
        kb = _kb()
        doc = _doc(kb, name="old", source="manual")
        ManualKnowledge.objects.create(knowledge_document=doc, content="旧")
        data = {"name": "新名", "content": "新内容"}
        resp = _dispatch("update_document_base_info", "post", data=data, pk=doc.id)
        assert _body(resp)["result"] is True
        doc.refresh_from_db()
        assert doc.name == "新名"
        assert ManualKnowledge.objects.get(knowledge_document=doc).content == "新内容"

    def test_update_parse_settings(self):
        kb = _kb()
        doc = _doc(kb)
        data = {"knowledge_document_list": [{"id": doc.id, "mode": "lite", "enable_ocr_parse": False}]}
        resp = _dispatch("update_parse_settings", "post", data=data)
        assert _body(resp)["result"] is True
        doc.refresh_from_db()
        assert doc.mode == "lite"

    def test_update_chunk_settings(self, mocker):
        kb = _kb()
        doc = _doc(kb)
        delay = mocker.patch(f"{KD_MOD}.general_embed.delay")
        data = {
            "knowledge_document_list": [doc.id],
            "general_parse_chunk_size": 200,
            "chunk_type": "semantic",
        }
        resp = _dispatch("update_chunk_settings", "post", data=data)
        assert _body(resp)["result"] is True
        doc.refresh_from_db()
        assert doc.general_parse_chunk_size == 200
        delay.assert_called_once()

    def test_get_doc_list_config(self):
        kb = _kb()
        doc = _doc(kb, name="cfg")
        resp = _dispatch("get_doc_list_config", "post", data={"doc_ids": [doc.id]})
        body = _body(resp)
        assert body["result"] is True
        assert body["data"][0]["name"] == "cfg"

    def test_preview_chunk(self, mocker):
        kb = _kb()
        doc = _doc(kb)
        mocker.patch(f"{KD_MOD}.general_embed_by_document_list", return_value=[{"chunk": "c"}])
        data = {"knowledge_document_id": doc.id, "general_parse_chunk_size": 128}
        resp = _dispatch("preview_chunk", "post", data=data)
        body = _body(resp)
        assert body["result"] is True
        assert body["data"] == [{"chunk": "c"}]

    def test_submit_settings(self):
        resp = _dispatch("submit_settings", "post", data={})
        assert _body(resp)["result"] is True
