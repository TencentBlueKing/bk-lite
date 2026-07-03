"""opspilot-ops 切片: viewsets/qa_pairs_view.QAPairsViewSet 自定义 action 真实 DRF + DB 测试。

补齐既有 test_slice_opbiz_qa_pairs_views.py 未覆盖的 @action 端点：
preview / generate_question / generate_answer / create_qa_pairs /
generate_answer_to_es / import_qa_json / set_file_data / get_details /
get_chunk_qa_pairs / update_qa_pairs / create_one_qa_pairs / delete_one_qa_pairs /
create_qa_pairs_by_custom / create_qa_pairs_by_chunk / get_qa_pairs_task_status /
export_qa_pairs / download_import_template / retrieve / update。

通过 APIRequestFactory 真实驱动 DRF、真实 ORM 落库。仅 mock 真实外部边界：
- ChunkHelper 的 ES / LLM 出站调用（generate_question/generate_answer/
  get_qa_content/get_document_es_chunk/update_qa_pairs/create_one_qa_pairs/
  delete_es_content）；
- celery 任务 .delay（分布式任务边界）；
- log_operation（system_mgmt 操作日志写出）。
断言真实 HTTP 状态 / JSON body / DB 副作用 / 传入 celery 的入参契约。
跳过纯 LLM 流式 chat 端点（本视图不含）。
"""

import json

import pydantic.root_model  # noqa  预热避免 cov 竞态
import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.opspilot.models import KnowledgeBase, KnowledgeTask, LLMModel, QAPairs
from apps.opspilot.viewsets.qa_pairs_view import QAPairsViewSet

pytestmark = pytest.mark.django_db

QA_MOD = "apps.opspilot.viewsets.qa_pairs_view"


def _body(resp):
    if hasattr(resp, "data"):
        return resp.data
    return json.loads(resp.content.decode("utf-8"))


def _su():
    from apps.base.models import User

    u = User.objects.create_user(
        username=f"qa_su_{User.objects.count()}",
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


def _llm(name="m"):
    return LLMModel.objects.create(name=name, team=[1], model="gpt-x")


def _dispatch(action_name, method, *, data=None, query="", user=None, pk=None, fmt="json"):
    factory = APIRequestFactory()
    path = f"/{query}"
    if method == "post":
        request = factory.post(path, data=data or {}, format=fmt)
    elif method == "delete":
        request = factory.delete(path, data=data or {}, format=fmt)
    else:
        request = factory.get(path)
    force_authenticate(request, user=user or _su())
    request.COOKIES["current_team"] = "1"
    view = QAPairsViewSet.as_view({method: action_name})
    if pk is not None:
        return view(request, pk=pk)
    return view(request)


class TestPreview:
    def test_超管预览生成问答对(self, mocker):
        kb = _kb()
        q_llm = _llm("q")
        a_llm = _llm("a")
        ch = mocker.patch(f"{QA_MOD}.ChunkHelper")
        inst = ch.return_value
        inst.generate_question.return_value = {"result": True, "data": [{"question": "Q1"}]}
        inst.generate_answer.return_value = {"result": True, "data": {"question": "Q1", "answer": "A1"}}
        data = {
            "knowledge_base_id": kb.id,
            "llm_model_id": q_llm.id,
            "answer_llm_model_id": a_llm.id,
            "qa_count": 1,
            "chunk_list": [{"content": "原始内容"}],
        }
        resp = _dispatch("preview", "post", data=data)
        body = _body(resp)
        assert body["result"] is True
        assert body["data"] == [{"question": "Q1", "answer": "A1"}]
        # 校验 generate_question 入参契约: 内容/模型/api_base 由 DB 真实派生
        _, kwargs = inst.generate_question.call_args
        passed = inst.generate_question.call_args.args[0]
        assert passed["content"] == "原始内容"
        assert passed["model"] == "gpt-x"

    def test_生成问题失败返回result_false(self, mocker):
        kb = _kb()
        llm = _llm()
        ch = mocker.patch(f"{QA_MOD}.ChunkHelper")
        ch.return_value.generate_question.return_value = {"result": False}
        data = {
            "knowledge_base_id": kb.id,
            "llm_model_id": llm.id,
            "answer_llm_model_id": llm.id,
            "chunk_list": [{"content": "c"}],
        }
        resp = _dispatch("preview", "post", data=data)
        assert _body(resp)["result"] is False

    def test_生成答案失败返回result_false(self, mocker):
        kb = _kb()
        llm = _llm()
        ch = mocker.patch(f"{QA_MOD}.ChunkHelper")
        inst = ch.return_value
        inst.generate_question.return_value = {"result": True, "data": [{"question": "Q"}]}
        inst.generate_answer.return_value = {"result": False}
        data = {
            "knowledge_base_id": kb.id,
            "llm_model_id": llm.id,
            "answer_llm_model_id": llm.id,
            "chunk_list": [{"content": "c"}],
        }
        resp = _dispatch("preview", "post", data=data)
        assert _body(resp)["result"] is False


class TestGenerateQuestion:
    def test_按文档生成问题(self, mocker):
        kb = _kb()
        llm = _llm()
        ch = mocker.patch(f"{QA_MOD}.ChunkHelper")
        inst = ch.return_value
        inst.get_qa_content.return_value = [{"content": "chunk-a"}]
        inst.generate_question.return_value = {"result": True, "data": [{"question": "Q?"}]}
        data = {
            "knowledge_base_id": kb.id,
            "llm_model_id": llm.id,
            "document_list": [{"document_id": 7}],
        }
        resp = _dispatch("generate_question", "post", data=data)
        body = _body(resp)
        assert body["result"] is True
        # 返回数据合并了 content 字段
        assert body["data"][0]["question"] == "Q?"
        assert body["data"][0]["content"] == "chunk-a"


class TestGenerateAnswer:
    def test_按问题生成答案(self, mocker):
        llm = _llm()
        mocker.patch(
            f"{QA_MOD}.ChunkHelper.generate_answer",
            return_value={"result": True, "data": {"answer": "A"}},
        )
        data = {
            "answer_llm_model_id": llm.id,
            "question_data": [{"content": "ctx", "question": "Q"}],
        }
        resp = _dispatch("generate_answer", "post", data=data)
        body = _body(resp)
        assert body["result"] is True
        assert body["data"] == [{"answer": "A"}]

    def test_生成答案失败(self, mocker):
        llm = _llm()
        mocker.patch(f"{QA_MOD}.ChunkHelper.generate_answer", return_value={"result": False})
        data = {"answer_llm_model_id": llm.id, "question_data": [{"content": "c", "question": "q"}]}
        resp = _dispatch("generate_answer", "post", data=data)
        assert _body(resp)["result"] is False


class TestCreateQaPairs:
    def test_批量创建并触发celery_跳过已存在文档(self, mocker):
        kb = _kb()
        q_llm = _llm("q")
        a_llm = _llm("a")
        # 已有 document_id=1 的 QAPairs，应被跳过
        QAPairs.objects.create(name="exist", knowledge_base=kb, document_id=1)
        delay = mocker.patch(f"{QA_MOD}.create_qa_pairs.delay")
        mocker.patch(f"{QA_MOD}.log_operation")
        data = {
            "knowledge_base_id": kb.id,
            "llm_model_id": q_llm.id,
            "answer_llm_model_id": a_llm.id,
            "qa_count": 2,
            "question_prompt": "qp",
            "answer_prompt": "ap",
            "only_question": True,
            "document_list": [
                {"document_id": 1, "name": "skip-me"},
                {"document_id": 2, "name": "new-one"},
            ],
        }
        resp = _dispatch("create_qa_pairs", "post", data=data)
        assert _body(resp)["result"] is True
        created = QAPairs.objects.filter(knowledge_base=kb, document_id=2)
        assert created.count() == 1
        assert created.first().status == "pending"
        # 仅新建的那一条 id 传入 celery，only_question=True
        new_id = created.first().id
        delay.assert_called_once_with([new_id], True)


class TestGenerateAnswerToEs:
    def test_缺少id返回false(self):
        resp = _dispatch("generate_answer_to_es", "post", data={})
        assert _body(resp)["result"] is False

    def test_有id触发celery(self, mocker):
        kb = _kb()
        qa = QAPairs.objects.create(name="qa", knowledge_base=kb)
        delay = mocker.patch(f"{QA_MOD}.generate_answer.delay")
        resp = _dispatch("generate_answer_to_es", "post", data={"qa_pairs_id": qa.id})
        assert _body(resp)["result"] is True
        delay.assert_called_once_with(qa.id)


class TestImportQaJson:
    def test_无文件返回false(self):
        resp = _dispatch("import_qa_json", "post", data={}, fmt="multipart")
        assert _body(resp)["result"] is False

    def test_导入json文件触发celery(self, mocker):
        import io

        from django.core.files.uploadedfile import SimpleUploadedFile

        kb = _kb()
        delay = mocker.patch(f"{QA_MOD}.create_qa_pairs_by_json.delay")
        mocker.patch(f"{QA_MOD}.log_operation")
        content = json.dumps([{"instruction": "Q", "output": "A"}]).encode("utf-8")
        upload = SimpleUploadedFile("qa.json", content, content_type="application/json")
        factory = APIRequestFactory()
        request = factory.post(
            "/",
            data={"file": upload, "knowledge_base_id": str(kb.id)},
            format="multipart",
        )
        force_authenticate(request, user=_su())
        request.COOKIES["current_team"] = "1"
        resp = QAPairsViewSet.as_view({"post": "import_qa_json"})(request)
        assert _body(resp)["result"] is True
        # 校验解析后的 file_data 真实进入 celery
        args = delay.call_args.args
        assert args[0] == {"qa.json": [{"instruction": "Q", "output": "A"}]}
        assert args[1] == kb.id
        _ = io  # noqa


class TestSetFileData:
    def test_解析csv去掉表头(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        vs = QAPairsViewSet()
        vs.loader = None
        csv_bytes = "问题,答案\n你好,世界\n无逗号行\n甲,乙\n".encode("utf-8")
        f = SimpleUploadedFile("d.csv", csv_bytes, content_type="text/csv")
        result = vs.set_file_data([f])
        assert result["d.csv"] == [
            {"instruction": "你好", "output": "世界"},
            {"instruction": "甲", "output": "乙"},
        ]

    def test_非法扩展名抛异常(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        vs = QAPairsViewSet()
        vs.loader = None
        f = SimpleUploadedFile("bad.txt", b"x", content_type="text/plain")
        with pytest.raises(Exception):
            vs.set_file_data([f])

    def test_非法json抛异常(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        vs = QAPairsViewSet()
        vs.loader = None
        f = SimpleUploadedFile("x.json", b"{not json", content_type="application/json")
        with pytest.raises(Exception):
            vs.set_file_data([f])


class TestGetDetails:
    def test_返回es分页问答对(self, mocker):
        kb = _kb()
        qa = QAPairs.objects.create(name="qa", knowledge_base=kb)
        ch = mocker.patch(f"{QA_MOD}.ChunkHelper")
        ch.return_value.get_document_es_chunk.return_value = {
            "count": 1,
            "documents": [
                {
                    "metadata": {
                        "qa_question": "Q",
                        "qa_answer": "A",
                        "chunk_id": "c1",
                        "base_chunk_id": "b1",
                    }
                }
            ],
        }
        resp = _dispatch("get_details", "get", pk=qa.id)
        body = _body(resp)
        assert body["result"] is True
        assert body["data"]["count"] == 1
        assert body["data"]["items"][0] == {"question": "Q", "answer": "A", "id": "c1", "base_chunk_id": "b1"}


class TestGetChunkQaPairs:
    def test_成功返回(self, mocker):
        mocker.patch(
            f"{QA_MOD}.ChunkHelper.get_document_es_chunk",
            return_value={
                "status": "success",
                "documents": [
                    {"page_content": "Q", "metadata": {"qa_answer": "A", "chunk_id": "c1"}},
                ],
            },
        )
        resp = _dispatch("get_chunk_qa_pairs", "get", query="?index_name=idx&chunk_id=10")
        body = _body(resp)
        assert body["result"] is True
        assert body["data"][0]["question"] == "Q"

    def test_es失败返回false(self, mocker):
        mocker.patch(
            f"{QA_MOD}.ChunkHelper.get_document_es_chunk",
            return_value={"status": "fail", "message": "boom"},
        )
        resp = _dispatch("get_chunk_qa_pairs", "get", query="?chunk_id=1")
        body = _body(resp)
        assert body["result"] is False
        assert body["message"] == "boom"


class TestUpdateQaPairs:
    def test_更新成功记录操作(self, mocker):
        kb = _kb()
        qa = QAPairs.objects.create(name="qa", knowledge_base=kb)
        mocker.patch(f"{QA_MOD}.ChunkHelper.update_qa_pairs", return_value=True)
        log = mocker.patch(f"{QA_MOD}.log_operation")
        data = {"id": "c1", "question": "newQ", "answer": "newA", "qa_pairs_id": qa.id}
        resp = _dispatch("update_qa_pairs", "post", data=data)
        assert _body(resp)["result"] is True
        log.assert_called_once()

    def test_更新失败返回false(self, mocker):
        kb = _kb()
        qa = QAPairs.objects.create(name="qa", knowledge_base=kb)
        mocker.patch(f"{QA_MOD}.ChunkHelper.update_qa_pairs", return_value=False)
        data = {"id": "c1", "question": "q", "answer": "a", "qa_pairs_id": qa.id}
        resp = _dispatch("update_qa_pairs", "post", data=data)
        assert _body(resp)["result"] is False


class TestCreateOneQaPairs:
    def test_创建成功累加generate_count(self, mocker):
        from apps.opspilot.models import EmbedProvider

        embed = EmbedProvider.objects.create(name="e", team=[1], model="emb")
        kb = KnowledgeBase.objects.create(name="kb", team=[1], embed_model=embed)
        qa = QAPairs.objects.create(name="qa", knowledge_base=kb, generate_count=0)
        mocker.patch(f"{QA_MOD}.ChunkHelper.create_one_qa_pairs", return_value={"result": True})
        mocker.patch(f"{QA_MOD}.log_operation")
        data = {"qa_pairs_id": qa.id, "question": "Q", "answer": "A"}
        resp = _dispatch("create_one_qa_pairs", "post", data=data)
        assert _body(resp)["result"] is True
        qa.refresh_from_db()
        assert qa.generate_count == 1


class TestDeleteOneQaPairs:
    def test_删除成功(self, mocker):
        kb = _kb()
        qa = QAPairs.objects.create(name="qa", knowledge_base=kb)
        mocker.patch(f"{QA_MOD}.ChunkHelper.delete_es_content", return_value=True)
        mocker.patch(f"{QA_MOD}.log_operation")
        data = {"id": "c1", "qa_pairs_id": qa.id, "question": "Q"}
        resp = _dispatch("delete_one_qa_pairs", "post", data=data)
        assert _body(resp)["result"] is True

    def test_删除失败(self, mocker):
        kb = _kb()
        qa = QAPairs.objects.create(name="qa", knowledge_base=kb)
        mocker.patch(f"{QA_MOD}.ChunkHelper.delete_es_content", return_value=False)
        data = {"id": "c1", "qa_pairs_id": qa.id}
        resp = _dispatch("delete_one_qa_pairs", "post", data=data)
        assert _body(resp)["result"] is False


class TestCreateByCustom:
    def test_自定义创建落库并触发celery(self, mocker):
        kb = _kb()
        delay = mocker.patch(f"{QA_MOD}.create_qa_pairs_by_custom.delay")
        mocker.patch(f"{QA_MOD}.log_operation")
        data = {
            "name": "custom-qa",
            "knowledge_base_id": kb.id,
            "qa_pairs": [{"instruction": "Q", "output": "A"}, {"instruction": "Q2", "output": "A2"}],
        }
        resp = _dispatch("create_qa_pairs_by_custom", "post", data=data)
        assert _body(resp)["result"] is True
        obj = QAPairs.objects.get(name="custom-qa")
        assert obj.create_type == "custom"
        assert obj.qa_count == 2
        delay.assert_called_once_with(obj.id, data["qa_pairs"])


class TestCreateByChunk:
    def test_按chunk创建返回id并触发celery(self, mocker):
        kb = _kb()
        q_llm = _llm("q")
        a_llm = _llm("a")
        delay = mocker.patch(f"{QA_MOD}.create_qa_pairs_by_chunk.delay")
        mocker.patch(f"{QA_MOD}.log_operation")
        data = {
            "name": "chunk-qa",
            "knowledge_base_id": kb.id,
            "document_id": 5,
            "document_source": "file",
            "qa_count": 3,
            "llm_model_id": q_llm.id,
            "answer_llm_model_id": a_llm.id,
            "question_prompt": "qp",
            "answer_prompt": "ap",
            "chunk_list": [{"content": "c"}],
        }
        resp = _dispatch("create_qa_pairs_by_chunk", "post", data=data)
        body = _body(resp)
        assert body["result"] is True
        obj = QAPairs.objects.get(name="chunk-qa")
        assert body["data"]["qa_pairs_id"] == obj.id
        called_id, called_kwargs = delay.call_args.args
        assert called_id == obj.id
        assert called_kwargs["qa_count"] == 3


class TestGetTaskStatus:
    def test_无qa对象返回空(self):
        resp = _dispatch("get_qa_pairs_task_status", "get", query="?document_id=999")
        body = _body(resp)
        assert body["result"] is True
        assert body["data"] == []

    def test_running映射为generating(self):
        kb = _kb()
        qa = QAPairs.objects.create(name="qa-task", knowledge_base=kb, document_id=11)
        KnowledgeTask.objects.create(
            task_name="qa-task",
            is_qa_task=True,
            knowledge_ids=[qa.id],
            knowledge_base_id=kb.id,
            status="running",
            completed_count=2,
            total_count=5,
        )
        resp = _dispatch("get_qa_pairs_task_status", "get", query="?document_id=11")
        body = _body(resp)
        assert body["data"][0]["status"] == "generating"
        assert body["data"][0]["process"] == "2/5"

    def test_success状态透传(self):
        kb = _kb()
        qa = QAPairs.objects.create(name="qa-ok", knowledge_base=kb, document_id=12)
        KnowledgeTask.objects.create(
            task_name="qa-ok",
            is_qa_task=True,
            knowledge_ids=[qa.id],
            knowledge_base_id=kb.id,
            status="success",
            completed_count=5,
            total_count=5,
        )
        resp = _dispatch("get_qa_pairs_task_status", "get", query="?document_id=12")
        assert _body(resp)["data"][0]["status"] == "success"


class TestExportQaPairs:
    def test_导出json附件(self, mocker):
        kb = _kb()
        qa = QAPairs.objects.create(name="export-me", knowledge_base=kb)
        mocker.patch(
            f"{QA_MOD}.ChunkHelper.get_document_es_chunk",
            return_value={"documents": [{"page_content": "Q", "metadata": {"qa_answer": "A"}}]},
        )
        resp = _dispatch("export_qa_pairs", "post", data={"qa_pairs_id": qa.id})
        assert resp["Content-Disposition"] == 'attachment; filename="export-me.json"'
        payload = json.loads(resp.content.decode("utf-8"))
        assert payload == [{"instruction": "Q", "output": "A"}]


class TestDownloadTemplate:
    def test_json模板(self):
        resp = _dispatch("download_import_template", "get", query="?file_type=json")
        assert resp["Content-Disposition"] == 'attachment; filename="template.json"'
        assert json.loads(resp.content.decode("utf-8")) == [{"instruction": "问题1", "output": "答案1"}]

    def test_csv模板带bom(self):
        resp = _dispatch("download_import_template", "get", query="?file_type=csv")
        assert resp["Content-Disposition"] == 'attachment; filename="template.csv"'
        text = resp.content.decode("utf-8")
        assert text.startswith("﻿")
        assert "问题1,答案1" in text


class TestRetrieveUpdate:
    def test_retrieve返回单条(self):
        kb = _kb()
        qa = QAPairs.objects.create(name="single", knowledge_base=kb)
        resp = _dispatch("retrieve", "get", pk=qa.id)
        assert resp.status_code == 200
        assert _body(resp)["name"] == "single"

    def test_update记录操作(self, mocker):
        kb = _kb()
        qa = QAPairs.objects.create(name="old", knowledge_base=kb, status="completed")
        log = mocker.patch(f"{QA_MOD}.log_operation")
        mocker.patch("apps.opspilot.serializers.qa_pairs_serializers.create_qa_pairs.delay")
        data = {"name": "new-name", "knowledge_base": kb.id}
        # PUT 走 update：用 factory.put
        factory = APIRequestFactory()
        request = factory.put("/", data=data, format="json")
        force_authenticate(request, user=_su())
        request.COOKIES["current_team"] = "1"
        resp = QAPairsViewSet.as_view({"put": "update"})(request, pk=qa.id)
        assert resp.status_code == 200
        qa.refresh_from_db()
        assert qa.name == "new-name"
        log.assert_called_once()
