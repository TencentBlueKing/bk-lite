from django.http import JsonResponse
from rest_framework import viewsets
from rest_framework.decorators import action

from apps.core.decorators.api_permission import HasPermission
from apps.opspilot.models import ManualKnowledge
from apps.opspilot.serializers import ManualKnowledgeSerializer
from apps.opspilot.utils.knowledge_utils import KnowledgeDocumentUtils


class ManualKnowledgeViewSet(viewsets.ModelViewSet):
    queryset = ManualKnowledge.objects.all()
    serializer_class = ManualKnowledgeSerializer
    ordering = ("-id",)
    search_fields = ("name",)

    @action(methods=["POST"], detail=False)
    @HasPermission("knowledge_document-Add")
    def create_manual_knowledge(self, request):
        kwargs = request.data
        kwargs["knowledge_source_type"] = "manual"
        new_doc = KnowledgeDocumentUtils.get_new_document(kwargs, request.user.username, request.user.domain)
        knowledge_obj = ManualKnowledge.objects.create(
            knowledge_document_id=new_doc.id,
            content=kwargs.get("content", ""),
        )
        return JsonResponse({"result": True, "data": knowledge_obj.knowledge_document_id})
