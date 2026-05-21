from django.http import JsonResponse
from rest_framework.decorators import action

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import LanguageViewSet
from apps.opspilot.models import KnowledgeDocument, ManualKnowledge
from apps.opspilot.serializers import ManualKnowledgeSerializer
from apps.opspilot.utils.team_permission_mixin import TeamPermissionMixin
from apps.system_mgmt.utils.operation_log_utils import log_operation


class ManualKnowledgeViewSet(TeamPermissionMixin, LanguageViewSet):
    """手动知识 ViewSet - 仅暴露 create_manual_knowledge action，禁用 list/retrieve/update/destroy"""

    queryset = ManualKnowledge.objects.all()
    serializer_class = ManualKnowledgeSerializer
    ordering = ("-id",)
    search_fields = ("name",)
    # 禁用未使用的 HTTP 方法，减少攻击面
    http_method_names = ["post", "options"]

    @action(methods=["POST"], detail=False)
    @HasPermission("knowledge_document-Add")
    def create_manual_knowledge(self, request):
        kwargs = request.data
        knowledge_base_id = kwargs.get("knowledge_base_id")
        if not knowledge_base_id:
            msg = self.loader.get("error.knowledge_base_required") if self.loader else "缺少 knowledge_base_id"
            return JsonResponse({"result": False, "message": msg})

        # 验证知识库权限
        self._validate_knowledge_base_permission(request, knowledge_base_id)

        kwargs["knowledge_source_type"] = "manual"
        new_doc = KnowledgeDocument.create_new_document(kwargs, request.user.username, request.user.domain)
        knowledge_obj = ManualKnowledge.objects.create(
            knowledge_document_id=new_doc.id,
            content=kwargs.get("content", ""),
        )
        log_operation(request, "create", "opspilot", f"创建手动知识文档: {kwargs.get('name', '')}")
        return JsonResponse({"result": True, "data": knowledge_obj.knowledge_document_id})
