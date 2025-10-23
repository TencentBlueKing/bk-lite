import json
import os

from django.http import HttpResponse, JsonResponse
from django_filters import filters
from django_filters.rest_framework import FilterSet
from rest_framework.decorators import action

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import MaintainerViewSet
from apps.opspilot.models import KnowledgeBase, KnowledgeTask, LLMModel, QAPairs
from apps.opspilot.serializers.qa_pairs_serializers import QAPairsSerializer
from apps.opspilot.tasks import create_qa_pairs, create_qa_pairs_by_chunk, create_qa_pairs_by_custom, create_qa_pairs_by_json, generate_answer
from apps.opspilot.utils.chunk_helper import ChunkHelper
from apps.opspilot.utils.permission_check import CheckKnowledgePermission


class QAPairsFilter(FilterSet):
    name = filters.CharFilter(field_name="name", lookup_expr="icontains")
    knowledge_base_id = filters.NumberFilter(field_name="knowledge_base_id", lookup_expr="exact")


class QAPairsViewSet(MaintainerViewSet):
    queryset = QAPairs.objects.all()
    serializer_class = QAPairsSerializer
    filterset_class = QAPairsFilter
    ordering = ("-id",)

    @HasPermission("knowledge_document-View")
    @CheckKnowledgePermission(QAPairs)
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("knowledge_document-Delete")
    @CheckKnowledgePermission(QAPairs)
    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj.status == "generating" or obj.status == "pending":
            message = self.loader.get("qa_pairs_generating") if self.loader else "QA pairs is generating, cannot delete"
            return JsonResponse({"result": False, "message": message})
        return super().destroy(request, *args, **kwargs)

    @action(methods=["POST"], detail=False)
    @HasPermission("knowledge_document-Add")
    @CheckKnowledgePermission(QAPairs)
    def generate_question(self, request):
        params = request.data
        client = ChunkHelper()
        data_count = 0
        chunk_data = []
        if not request.user.is_superuser:
            knowledge_base = KnowledgeBase.objects.get(id=params["knowledge_base_id"])
            current_team = request.COOKIES.get("current_team", "0")
            has_permission = self.get_has_permission(request.user, knowledge_base, current_team)
            if not has_permission:
                message = self.loader.get("no_update_permission") if self.loader else "You do not have permission to update this instance"
                return JsonResponse(
                    {
                        "result": False,
                        "message": message,
                    }
                )
        for i in params.get("document_list", []):
            chunk_data.extend(
                client.get_qa_content(
                    i.get("document_id", 0),
                    f"knowledge_base_{params['knowledge_base_id']}",
                    page_size=10,
                )
            )
            data_count += len(chunk_data)
            if data_count >= 10:
                chunk_data = chunk_data[:10]  # 限制最多10条数据
                break
        llm_model = LLMModel.objects.get(id=params["llm_model_id"])
        openai_api_base = llm_model.decrypted_llm_config["openai_base_url"]
        openai_api_key = llm_model.decrypted_llm_config["openai_api_key"]
        model = llm_model.decrypted_llm_config["model"] or llm_model.name
        return_data = []
        for i in chunk_data:
            kwargs = {
                "content": i["content"],
                "size": 1,
                "openai_api_base": openai_api_base,
                "openai_api_key": openai_api_key,
                "model": model,
                "extra_prompt": params.get("question_prompt", ""),
            }
            res = client.generate_question(kwargs)
            if not res["result"]:
                message = self.loader.get("generate_question_failed") if self.loader else "generate question failed"
                return JsonResponse({"result": False, "message": message})
            return_data.extend([dict(x, **{"content": i["content"]}) for x in res["data"]])
        return JsonResponse({"result": True, "data": return_data})

    @action(methods=["POST"], detail=False)
    @HasPermission("knowledge_document-Add")
    @CheckKnowledgePermission(QAPairs)
    def generate_answer(self, request):
        params = request.data
        llm_model = LLMModel.objects.get(id=params["answer_llm_model_id"])
        openai_api_base = llm_model.decrypted_llm_config["openai_base_url"]
        openai_api_key = llm_model.decrypted_llm_config["openai_api_key"]
        model = llm_model.decrypted_llm_config["model"] or llm_model.name
        return_data = []
        for i in params["question_data"]:
            kwargs = {
                "context": i["content"],
                "content": i["question"],
                "openai_api_base": openai_api_base,
                "openai_api_key": openai_api_key,
                "model": model,
                "extra_prompt": params.get("answer_prompt", ""),
            }
            res = ChunkHelper.generate_answer(kwargs)
            if not res["result"]:
                message = self.loader.get("generate_answer_failed") if self.loader else "generate answer failed"
                return JsonResponse({"result": False, "message": message})
            return_data.append(res["data"])
        return JsonResponse({"result": True, "data": return_data})

    @action(methods=["POST"], detail=False)
    @HasPermission("knowledge_document-Add")
    @CheckKnowledgePermission(QAPairs)
    def create_qa_pairs(self, request):
        params = request.data
        document_list = params.get("document_list", [])
        qa_list = []
        exist_qa_pairs = list(QAPairs.objects.all().values_list("document_id", flat=True).distinct())
        for i in document_list:
            if i["document_id"] in exist_qa_pairs:
                continue
            qa_list.append(
                QAPairs(
                    name=i.get("name", ""),
                    knowledge_base_id=params["knowledge_base_id"],
                    llm_model_id=params["llm_model_id"],
                    answer_llm_model_id=params["answer_llm_model_id"],
                    qa_count=params.get("qa_count", 0),
                    document_id=i.get("document_id", 0),
                    document_source=i.get("document_source", "file"),
                    created_by=request.user.username,
                    domain=request.user.domain,
                    status="pending",
                    question_prompt=params["question_prompt"],
                    answer_prompt=params["answer_prompt"],
                )
            )
        add_list = QAPairs.objects.bulk_create(qa_list, batch_size=100)
        create_qa_pairs.delay([instance.id for instance in add_list], params.get("only_question", False))
        return JsonResponse({"result": True})

    @HasPermission("knowledge_document-Set")
    @CheckKnowledgePermission(QAPairs)
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @action(methods=["POST"], detail=False)
    @HasPermission("knowledge_document-Add")
    @CheckKnowledgePermission(QAPairs, "qa_pairs_id")
    def generate_answer_to_es(self, request):
        qa_paris_id = request.data.get("qa_pairs_id")
        if not qa_paris_id:
            message = self.loader.get("qa_pairs_id_required") if self.loader else "QA pairs ID is required."
            return JsonResponse({"result": False, "message": message})
        generate_answer.delay(qa_paris_id)
        return JsonResponse(
            {
                "result": True,
            }
        )

    @action(methods=["POST"], detail=False)
    @HasPermission("knowledge_document-Add")
    @CheckKnowledgePermission(QAPairs)
    def import_qa_json(self, request):
        files = request.FILES.getlist("file")
        if not files:
            return JsonResponse({"result": False, "message": "No file provided."})
        try:
            file_data = self.set_file_data(files)
        except Exception as e:
            return JsonResponse({"result": False, "message": str(e)})
        params = request.data
        create_qa_pairs_by_json.delay(
            file_data,
            int(params["knowledge_base_id"]),
            request.user.username,
            request.user.domain,
        )
        return JsonResponse({"result": True, "message": "QA pairs import started."})

    def set_file_data(self, files):
        file_data = {}
        # 验证文件格式
        allowed_extensions = [".json", ".csv"]
        for i in files:
            file_ext = os.path.splitext(i.name)[1].lower()
            if file_ext not in allowed_extensions:
                message = (
                    self.loader.get("error.invalid_file_format") if self.loader else "Invalid file format. Only .json and .csv files are allowed."
                )
                raise Exception(message)
            try:
                if file_ext == ".json":
                    file_data.setdefault(i.name, []).extend(json.loads(i.read().decode("utf-8")))
                else:
                    csv_content = i.read().decode("utf-8").split("\n")[1:]
                    content = []
                    for line in csv_content:
                        if "," not in line:
                            continue
                        q, a = line.strip().split(",", 1)
                        content.append({"instruction": q.strip(), "output": a.strip()})
                    file_data.setdefault(i.name, []).extend(content)
            except json.JSONDecodeError:
                message = self.loader.get("error.invalid_json_file") if self.loader else "Invalid JSON file"
                raise Exception(message)
        return file_data

    @action(methods=["GET"], detail=True)
    @HasPermission("knowledge_document-View")
    @CheckKnowledgePermission(QAPairs)
    def get_details(self, request, *args, **kwargs):
        instance: QAPairs = self.get_object()
        client = ChunkHelper()
        page = request.query_params.get("page", 1)
        page_size = request.query_params.get("page_size", 10)
        search_text = request.query_params.get("search_text", "")
        metadata_filter = {"qa_pairs_id": str(instance.id)}
        index_name = instance.knowledge_base.knowledge_index_name()

        res = client.get_document_es_chunk(index_name, page, page_size, search_text, metadata_filter)
        return_data = [
            {
                "question": i["metadata"]["qa_question"],
                "answer": i["metadata"]["qa_answer"],
                "id": i["metadata"]["chunk_id"],
                "base_chunk_id": i["metadata"].get("base_chunk_id", ""),
            }
            for i in res.get("documents", [])
        ]
        return JsonResponse({"result": True, "data": {"items": return_data, "count": res["count"]}})

    # TODO 前端配合添加参数knowledge_base_id
    @action(methods=["GET"], detail=False)
    @HasPermission("knowledge_document-View")
    @CheckKnowledgePermission(QAPairs)
    def get_chunk_qa_pairs(self, request):
        """
        Get chunk QA pairs
        """
        index_name = request.GET.get("index_name", "")
        chunk_id = request.GET.get("chunk_id")
        res = ChunkHelper.get_document_es_chunk(
            index_name,
            1,
            0,
            metadata_filter={"base_chunk_id": str(chunk_id)},
        )
        if res.get("status", "fail") != "success":
            return JsonResponse(
                {
                    "result": False,
                    "message": res.get("message", "Failed to retrieve data."),
                }
            )
        return_data = [
            {
                "question": i["page_content"],
                "answer": i["metadata"]["qa_answer"],
                "id": i["metadata"]["chunk_id"],
                "base_chunk_id": i["metadata"].get("base_chunk_id", ""),
            }
            for i in res.get("documents", [])
        ]
        return JsonResponse({"result": True, "data": return_data})

    @action(methods=["POST"], detail=False)
    @HasPermission("knowledge_document-Set")
    @CheckKnowledgePermission(QAPairs, "qa_pairs_id")
    def update_qa_pairs(self, request):
        params = request.data
        chunk_id = params["id"]
        question = params["question"]
        answer = params["answer"]
        result = ChunkHelper.update_qa_pairs(chunk_id, question, answer)
        if not result:
            message = self.loader.get("qa_pair_update_failed") if self.loader else "Failed to update QA pair."
            return JsonResponse({"result": False, "message": message})
        return JsonResponse({"result": True})

    @action(methods=["POST"], detail=False)
    @HasPermission("knowledge_document-Add")
    @CheckKnowledgePermission(QAPairs, "qa_pairs_id")
    def create_one_qa_pairs(self, request):
        params = request.data
        qa_paris = QAPairs.objects.get(id=params["qa_pairs_id"])
        index_name = qa_paris.knowledge_base.knowledge_index_name()
        question = params["question"]
        answer = params["answer"]
        embed_config = qa_paris.knowledge_base.embed_model.decrypted_embed_config
        embed_config["model"] = embed_config.get("model", qa_paris.knowledge_base.embed_model.name)
        result = ChunkHelper.create_one_qa_pairs(embed_config, index_name, params["qa_pairs_id"], question, answer)
        if result["result"]:
            qa_paris.generate_count += 1
            qa_paris.save()
        return JsonResponse(result)

    @action(methods=["POST"], detail=False)
    @HasPermission("knowledge_document-Delete")
    @CheckKnowledgePermission(QAPairs, "qa_pairs_id")
    def delete_one_qa_pairs(self, request):
        params = request.data
        chunk_id = params["id"]
        result = ChunkHelper.delete_es_content(chunk_id, True)
        if not result:
            message = self.loader.get("qa_pair_delete_failed") if self.loader else "Failed to delete QA pair."
            return JsonResponse({"result": False, "message": message})
        # if params["base_chunk_id"]:
        #     ChunkHelper.update_document_qa_pairs_count(index_name, -1, params["base_chunk_id"])
        return JsonResponse({"result": True})

    @action(methods=["POST"], detail=False)
    @HasPermission("knowledge_document-Add")
    @CheckKnowledgePermission(QAPairs)
    def create_qa_pairs_by_custom(self, request):
        params = request.data
        qa_pairs = QAPairs.objects.create(
            name=params["name"],
            description=params.get("description", ""),
            knowledge_base_id=params["knowledge_base_id"],
            qa_count=len(params["qa_pairs"]),
            document_id=0,
            create_type="custom",
            status="pending",
            created_by=request.user.username,
            domain=request.user.domain,
        )
        create_qa_pairs_by_custom.delay(qa_pairs.id, params["qa_pairs"])
        return JsonResponse({"result": True})

    @action(methods=["POST"], detail=False)
    @HasPermission("knowledge_document-Add")
    @CheckKnowledgePermission(QAPairs)
    def create_qa_pairs_by_chunk(self, request):
        params = request.data
        qa_pairs, _ = QAPairs.objects.get_or_create(
            name=params["name"],
            knowledge_base_id=params["knowledge_base_id"],
            document_id=params["document_id"],
            document_source=params["document_source"],
            defaults={
                "created_by": request.user.username,
                "domain": request.user.domain,
                "description": params.get("description", ""),
                "qa_count": params["qa_count"],
                "llm_model_id": params["llm_model_id"],
                "answer_llm_model_id": params["answer_llm_model_id"],
                "status": "pending",
                "question_prompt": params["question_prompt"],
                "answer_prompt": params["answer_prompt"],
            },
        )
        kwargs = {
            "chunk_list": params["chunk_list"],
            "llm_model_id": params["llm_model_id"],
            "answer_llm_model_id": params["answer_llm_model_id"],
            "qa_count": params["qa_count"],
            "question_prompt": params["question_prompt"],
            "answer_prompt": params["answer_prompt"],
            "only_question": params.get("only_question", False),
        }
        create_qa_pairs_by_chunk.delay(qa_pairs.id, kwargs)
        return JsonResponse({"result": True, "data": {"qa_pairs_id": qa_pairs.id}})

    @action(methods=["GET"], detail=False)
    @HasPermission("knowledge_document-View")
    @CheckKnowledgePermission(QAPairs, "document_id", id_field="document_id")
    def get_qa_pairs_task_status(self, request):
        document_id = request.GET.get("document_id")
        qa_pairs_obj = QAPairs.objects.filter(
            document_id=document_id,
        ).first()
        if not qa_pairs_obj:
            return JsonResponse({"result": True, "data": []})
        task_list = KnowledgeTask.objects.filter(
            is_qa_task=True,
            task_name=qa_pairs_obj.name,
            knowledge_ids__contains=int(qa_pairs_obj.id),
        )
        if not task_list:
            return JsonResponse({"result": True, "data": []})
        return JsonResponse(
            {
                "result": True,
                "data": [
                    {
                        "status": "generating",
                        "process": f"{task_obj.completed_count}/{task_obj.total_count}",
                    }
                    for task_obj in task_list
                ],
            }
        )

    @action(methods=["POST"], detail=False)
    @HasPermission("knowledge_document-Add")
    @CheckKnowledgePermission(QAPairs, "qa_pairs_id")
    def export_qa_pairs(self, request):
        instance_id = request.data.get("qa_pairs_id")
        instance = QAPairs.objects.get(id=instance_id)
        if not request.user.is_superuser:
            current_team = request.COOKIES.get("current_team", "0")
            has_permission = self.get_has_permission(request.user, instance.knowledge_base, current_team)
            if not has_permission:
                message = self.loader.get("no_update_permission") if self.loader else "You do not have permission to update this instance"
                return JsonResponse(
                    {
                        "result": False,
                        "message": message,
                    }
                )
        res = ChunkHelper.get_document_es_chunk(
            instance.knowledge_base.knowledge_index_name(),
            1,
            0,
            metadata_filter={"qa_pairs_id": str(instance_id)},
            get_count=False,
        )
        export_data = [{"instruction": i["page_content"], "output": i["metadata"]["qa_answer"]} for i in res.get("documents", [])]
        export_file_name = instance.name
        if not export_file_name.endswith(".json"):
            export_file_name = f"{export_file_name}.json"

        # 创建 JSON 文件响应
        response = HttpResponse(
            json.dumps(export_data, ensure_ascii=False, indent=2),
            content_type="application/json",
        )
        response["Content-Disposition"] = f'attachment; filename="{export_file_name}"'
        return response

    @action(methods=["GET"], detail=False)
    def download_import_template(self, request):
        file_type = request.GET.get("file_type", "json")
        if file_type == "json":
            tmp_data = [{"instruction": "问题1", "output": "答案1"}]
            response = HttpResponse(
                json.dumps(tmp_data, ensure_ascii=False, indent=2),
                content_type="application/json",
            )
            response["Content-Disposition"] = 'attachment; filename="template.json"'
            return response
        tmp_data = "问题(不要动),答案(不要动)\n"
        tmp_data += "问题1,答案1\n"
        # 添加 UTF-8 BOM 头解决中文乱码问题
        response = HttpResponse("\ufeff" + tmp_data, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="template.csv"'
        return response
