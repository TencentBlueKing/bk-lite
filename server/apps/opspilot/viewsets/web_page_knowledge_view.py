from django.http import JsonResponse
from rest_framework.decorators import action

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import LanguageViewSet
from apps.opspilot.models import KnowledgeDocument, WebPageKnowledge
from apps.opspilot.serializers import WebPageKnowledgeSerializer
from apps.opspilot.utils.team_permission_mixin import TeamPermissionMixin
from apps.system_mgmt.utils.operation_log_utils import log_operation


class WebPageKnowledgeViewSet(TeamPermissionMixin, LanguageViewSet):
    """网页知识 ViewSet - 仅暴露 create_web_page_knowledge action，禁用 list/retrieve/update/destroy"""

    queryset = WebPageKnowledge.objects.all()
    serializer_class = WebPageKnowledgeSerializer
    ordering = ("-id",)
    search_fields = ("name",)
    # 禁用未使用的 HTTP 方法，减少攻击面
    http_method_names = ["post", "options"]

    @action(methods=["POST"], detail=False)
    @HasPermission("knowledge_document-Add")
    def create_web_page_knowledge(self, request):
        kwargs = request.data
        if not kwargs.get("url", "").strip():
            msg = self.loader.get("error.url_required") if self.loader else "url is required"
            return JsonResponse({"result": False, "message": msg})

        knowledge_base_id = kwargs.get("knowledge_base_id")
        if not knowledge_base_id:
            msg = self.loader.get("error.knowledge_base_required") if self.loader else "缺少 knowledge_base_id"
            return JsonResponse({"result": False, "message": msg})

        # 验证知识库权限
        self._validate_knowledge_base_permission(request, knowledge_base_id)

        kwargs["knowledge_source_type"] = "web_page"
        new_doc = KnowledgeDocument.create_new_document(kwargs, request.user.username, request.user.domain)
        knowledge_obj = WebPageKnowledge.objects.create(
            knowledge_document_id=new_doc.id,
            url=kwargs.get("url", "").strip(),
            max_depth=kwargs.get("max_depth", 1),
            sync_enabled=kwargs.get("sync_enabled", False),
            sync_time=kwargs.get("sync_time", "00:00"),
        )
        if knowledge_obj.sync_enabled:
            knowledge_obj.create_sync_periodic_task()
        log_operation(request, "create", "opspilot", f"创建网页知识文档: {kwargs.get('url', '').strip()}")
        return JsonResponse({"result": True, "data": knowledge_obj.knowledge_document_id})
