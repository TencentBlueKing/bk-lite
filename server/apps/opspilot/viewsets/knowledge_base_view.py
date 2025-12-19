from django.db.transaction import atomic
from django.http import JsonResponse
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.logger import opspilot_logger as logger
from apps.core.utils.viewset_utils import AuthViewSet
from apps.opspilot.enum import DocumentStatus
from apps.opspilot.models import (
    EmbedProvider,
    FileKnowledge,
    KnowledgeBase,
    KnowledgeDocument,
    KnowledgeGraph,
    LLMSkill,
    ManualKnowledge,
    QAPairs,
    WebPageKnowledge,
)
from apps.opspilot.serializers import KnowledgeBaseSerializer
from apps.opspilot.services.knowledge_search_service import KnowledgeSearchService
from apps.opspilot.tasks import retrain_all
from apps.opspilot.utils.chunk_helper import ChunkHelper
from apps.opspilot.utils.graph_utils import GraphUtils


class KnowledgeBaseViewSet(AuthViewSet):
    queryset = KnowledgeBase.objects.all()
    serializer_class = KnowledgeBaseSerializer
    ordering = ("-id",)
    search_fields = ("name",)
    permission_key = "knowledge"

    @HasPermission("knowledge_list-View")
    def retrieve(self, request, *args, **kwargs):
        serializer = self.get_detail(request, *args, **kwargs)
        return_data = serializer.data
        query = {"knowledge_document__knowledge_base_id": kwargs["pk"]}
        count_data = {
            "file_count": FileKnowledge.objects.filter(**query).count(),
            "web_page_count": WebPageKnowledge.objects.filter(**query).count(),
            "manual_count": ManualKnowledge.objects.filter(**query).count(),
            "qa_count": QAPairs.objects.filter(knowledge_base_id=kwargs["pk"]).count(),
            "graph_count": KnowledgeGraph.objects.filter(knowledge_base_id=kwargs["pk"]).count(),
        }
        count_data["document_count"] = sum(value for key, value in count_data.items() if key not in ["qa_count", "graph_count"])
        return_data.update(count_data)
        return JsonResponse({"result": True, "data": return_data})

    @HasPermission("knowledge_list-Add")
    def create(self, request, *args, **kwargs):
        params = request.data
        if not params.get("team"):
            return JsonResponse({"result": False, "message": self.loader.get("error.team_required")})
        if "embed_model" not in params:
            params["embed_model"] = EmbedProvider.objects.get(name="FastEmbed(BAAI/bge-small-zh-v1.5)").id
        if KnowledgeBase.objects.filter(name=params["name"]).exists():
            return JsonResponse({"result": False, "message": self.loader.get("error.knowledge_base_name_exists")})
        params["created_by"] = request.user.username
        if params.get("enable_rerank") is None:
            params["enable_rerank"] = False
        if not params.get("team"):
            params["team"] = [int(request.COOKIES.get("current_team"))]
        params["score_threshold"] = 0.3
        params["search_type"] = "mmr"
        serializer = self.get_serializer(data=params)
        serializer.is_valid(raise_exception=True)
        with atomic():
            self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @HasPermission("knowledge_list-Edit")
    def update(self, request, *args, **kwargs):
        instance: KnowledgeBase = self.get_object()
        params = request.data
        if instance.embed_model_id != params["embed_model"]:
            if instance.knowledgedocument_set.filter(train_status=DocumentStatus.TRAINING).exists():
                return JsonResponse({"result": False, "message": self.loader.get("error.knowledge_base_training")})
            delete_qa_pairs = params.pop("delete_qa_pairs", False)
            retrain_all.delay(instance.id, request.user.username, request.user.domain, delete_qa_pairs)
        return super().update(request, *args, **kwargs)

    @action(methods=["POST"], detail=True)
    @HasPermission("knowledge_setting-Edit")
    def update_settings(self, request, *args, **kwargs):
        instance: KnowledgeBase = self.get_object()
        if not request.user.is_superuser:
            current_team = request.COOKIES.get("current_team", "0")
            include_children = request.COOKIES.get("include_children", "0") == "1"
            has_permission = self.get_has_permission(request.user, instance, current_team, include_children=include_children)
            if not has_permission:
                return JsonResponse({"result": False, "message": self.loader.get("error.permission_update_denied")})

        kwargs = request.data
        if kwargs.get("name"):
            if KnowledgeBase.objects.filter(name=kwargs["name"]).exclude(id=instance.id).exists():
                return JsonResponse({"result": False, "message": self.loader.get("error.knowledge_base_name_exists")})
            instance.name = kwargs["name"]
        if kwargs.get("introduction"):
            instance.introduction = kwargs["introduction"]
        if kwargs.get("team"):
            instance.team = kwargs["team"]
        instance.enable_rerank = kwargs["enable_rerank"]
        if kwargs.get("rerank_model") is None:
            instance.rerank_model = None
        else:
            instance.rerank_model_id = kwargs["rerank_model"]
            instance.rerank_top_k = kwargs["rerank_top_k"]
        instance.enable_naive_rag = kwargs["enable_naive_rag"]
        instance.enable_qa_rag = kwargs["enable_qa_rag"]
        instance.enable_graph_rag = kwargs["enable_graph_rag"]

        instance.rag_size = kwargs["rag_size"]
        instance.qa_size = kwargs["qa_size"]
        instance.graph_size = kwargs["graph_size"]
        instance.search_type = kwargs["search_type"]
        instance.score_threshold = kwargs.get("score_threshold", 0.7)
        instance.rag_recall_mode = kwargs.get("rag_recall_mode", "chunk")
        instance.save()
        return JsonResponse({"result": True})

    @HasPermission("knowledge_list-Delete")
    def destroy(self, request, *args, **kwargs):
        # 检查是否有LLMSkill使用该知识库
        llm_skills = LLMSkill.objects.filter(knowledge_base__id=kwargs["pk"])
        if llm_skills.exists():
            skill_names = ", ".join([skill.name for skill in llm_skills[:5]])
            if llm_skills.count() > 5:
                skill_names += f" 等{llm_skills.count()}个技能"
            message = self.loader.get("error.knowledge_base_used_by_skills").format(skill_names=skill_names)
            return JsonResponse({"result": False, "message": message})

        knowledge_base_id = kwargs["pk"]
        instance = self.get_object()
        index_name = instance.knowledge_index_name()
        try:
            # 1. 批量删除所有知识库文档
            knowledge_document_ids = list(KnowledgeDocument.objects.filter(knowledge_base_id=knowledge_base_id).values_list("id", flat=True))
            if knowledge_document_ids:
                KnowledgeSearchService.delete_es_content(index_name=index_name, doc_id=knowledge_document_ids, keep_qa=False)
            # 2. 删除问答对
            qa_pairs = list(QAPairs.objects.filter(knowledge_base_id=knowledge_base_id, document_id=0).values_list("id", flat=True))
            if qa_pairs:
                ChunkHelper.delete_es_content(qa_pairs)
            # 3. 批量删除知识图谱
            knowledge_graph = KnowledgeGraph.objects.filter(knowledge_base_id=knowledge_base_id).first()
            if knowledge_graph:
                GraphUtils.delete_graph(knowledge_graph)
                knowledge_graph.delete()
        except Exception as e:
            logger.exception(e)
            return JsonResponse({"result": False, "message": self.loader.get("error.knowledge_base_delete_related_data_failed")})
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=["GET"])
    def get_teams(self, request):
        groups = request.user.group_list
        return JsonResponse({"result": True, "data": groups})
