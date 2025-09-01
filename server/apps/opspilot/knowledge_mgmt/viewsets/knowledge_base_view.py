from django.db.transaction import atomic
from django.http import JsonResponse
from django.utils.translation import gettext as _
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import AuthViewSet
from apps.opspilot.knowledge_mgmt.models import (
    FileKnowledge,
    KnowledgeGraph,
    ManualKnowledge,
    QAPairs,
    WebPageKnowledge,
)
from apps.opspilot.knowledge_mgmt.models.knowledge_document import DocumentStatus
from apps.opspilot.knowledge_mgmt.serializers import KnowledgeBaseSerializer
from apps.opspilot.models import EmbedProvider, KnowledgeBase, KnowledgeDocument
from apps.opspilot.tasks import retrain_all


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
        count_data["document_count"] = sum(
            value for key, value in count_data.items() if key not in ["qa_count", "graph_count"]
        )
        return_data.update(count_data)
        return JsonResponse({"result": True, "data": return_data})

    @HasPermission("knowledge_list-Add")
    def create(self, request, *args, **kwargs):
        params = request.data
        if not params.get("team"):
            return JsonResponse({"result": False, "message": _("The team field is required.")})
        if "embed_model" not in params:
            params["embed_model"] = EmbedProvider.objects.get(name="FastEmbed(BAAI/bge-small-zh-v1.5)").id
        if KnowledgeBase.objects.filter(name=params["name"]).exists():
            return JsonResponse({"result": False, "message": _("The knowledge base name already exists.")})
        params["created_by"] = request.user.username
        if params.get("enable_rerank") is None:
            params["enable_rerank"] = False
        if not params.get("team"):
            params["team"] = [int(request.COOKIES.get("current_team"))]
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
                return JsonResponse(
                    {"result": False, "message": _("The knowledge base is training and cannot be modified.")}
                )
            delete_qa_pairs = params.pop("delete_qa_pairs", False)
            retrain_all.delay(instance.id, request.user.username, request.user.domain, delete_qa_pairs)
        return super().update(request, *args, **kwargs)

    @action(methods=["POST"], detail=True)
    @HasPermission("knowledge_setting-Edit")
    def update_settings(self, request, *args, **kwargs):
        instance: KnowledgeBase = self.get_object()
        if not request.user.is_superuser:
            current_team = request.COOKIES.get("current_team", "0")
            has_permission = self.get_has_permission(request.user, instance, current_team)
            if not has_permission:
                return JsonResponse(
                    {"result": False, "message": _("You do not have permission to update this instance")}
                )

        kwargs = request.data
        if kwargs.get("name"):
            if KnowledgeBase.objects.filter(name=kwargs["name"]).exclude(id=instance.id).exists():
                return JsonResponse({"result": False, "message": _("The knowledge base name already exists.")})
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
        instance.save()
        return JsonResponse({"result": True})

    @HasPermission("knowledge_list-Delete")
    def destroy(self, request, *args, **kwargs):
        if KnowledgeDocument.objects.filter(knowledge_base_id=kwargs["pk"]).exists():
            return JsonResponse(
                {"result": False, "message": _("This knowledge base contains documents and cannot be deleted.")}
            )
        elif QAPairs.objects.filter(knowledge_base_id=kwargs["pk"]).exists():
            return JsonResponse(
                {"result": False, "message": _("This knowledge base contains Q&A pairs and cannot be deleted.")}
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=["GET"])
    def get_teams(self, request):
        groups = request.user.group_list
        return JsonResponse({"result": True, "data": groups})
