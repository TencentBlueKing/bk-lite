from django.http import JsonResponse
from rest_framework.decorators import action

from apps.core.utils.viewset_utils import AuthViewSet
from apps.opspilot.models import BuildRecord, KnowledgePage, WikiKnowledgeBase
from apps.opspilot.serializers.wiki_serializers import BuildRecordSerializer, KnowledgePageSerializer, PageVersionSerializer
from apps.opspilot.services.wiki.page_service import create_manual_page, diff_versions, edit_page, restore_version
from apps.system_mgmt.utils.operation_log_utils import log_operation


class WikiPageViewSet(AuthViewSet):
    """知识页面:浏览 + 人工创建/编辑/删除 + 版本查看/恢复(spec §8/§9)。"""

    queryset = KnowledgePage.objects.all().order_by("-id")
    serializer_class = KnowledgePageSerializer
    ordering = ("-id",)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        kb_id = request.GET.get("knowledge_base")
        if kb_id:
            queryset = queryset.filter(knowledge_base_id=kb_id)
        page_type = request.GET.get("page_type")
        if page_type:
            queryset = queryset.filter(page_type=page_type)
        return JsonResponse({"result": True, "data": self.get_serializer(queryset, many=True).data})

    def retrieve(self, request, *args, **kwargs):
        return JsonResponse({"result": True, "data": self.get_serializer(self.get_object()).data})

    def create(self, request, *args, **kwargs):
        data = request.data
        kb = WikiKnowledgeBase.objects.get(id=data["knowledge_base"])
        page = create_manual_page(
            knowledge_base=kb,
            page_type=data.get("page_type", "concept"),
            title=data["title"],
            body=data.get("body", ""),
            tags=data.get("tags") or [],
            created_by=getattr(request.user, "username", ""),
        )
        log_operation(request, "create", "opspilot", f"新增知识页面: {page.title}")
        return JsonResponse({"result": True, "data": self.get_serializer(page).data}, status=201)

    def update(self, request, *args, **kwargs):
        page = self.get_object()
        edit_page(
            page,
            body=request.data.get("body"),
            title=request.data.get("title"),
            tags=request.data.get("tags"),
            updated_by=getattr(request.user, "username", ""),
        )
        page.refresh_from_db()
        log_operation(request, "update", "opspilot", f"编辑知识页面: {page.title}")
        return JsonResponse({"result": True, "data": self.get_serializer(page).data})

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        page = self.get_object()
        title = page.title
        page.delete()
        log_operation(request, "delete", "opspilot", f"删除知识页面: {title}")
        return JsonResponse({"result": True})

    @action(methods=["GET"], detail=True)
    def versions(self, request, pk=None):
        """列出该页面的全部版本(用于 diff/恢复)。"""
        page = self.get_object()
        qs = page.page_versions.order_by("-no")
        return JsonResponse({"result": True, "data": PageVersionSerializer(qs, many=True).data})

    @action(methods=["GET"], detail=True)
    def diff(self, request, pk=None):
        """对比两个版本正文,返回统一 diff 行(?from=<版本id>&to=<版本id>)。"""
        page = self.get_object()
        try:
            from_id = int(request.GET.get("from"))
            to_id = int(request.GET.get("to"))
        except (TypeError, ValueError):
            return JsonResponse({"result": False, "message": "from/to 版本 id 必填"}, status=400)
        try:
            lines = diff_versions(page, from_id, to_id)
        except ValueError:
            return JsonResponse({"result": False, "message": "版本不存在"}, status=404)
        return JsonResponse({"result": True, "data": {"diff": lines}})

    @action(methods=["POST"], detail=True)
    def restore(self, request, pk=None):
        """恢复到指定历史版本(创建新版本,不删除历史)。"""
        page = self.get_object()
        version_id = request.data.get("version_id")
        if not version_id:
            return JsonResponse({"result": False, "message": "version_id 必填"}, status=400)
        restore_version(page, version_id, operator=getattr(request.user, "username", ""))
        page.refresh_from_db()
        log_operation(request, "execute", "opspilot", f"恢复知识页面版本: {page.title}")
        return JsonResponse({"result": True, "data": self.get_serializer(page).data})


class WikiBuildRecordViewSet(AuthViewSet):
    """构建记录浏览(只读)。"""

    queryset = BuildRecord.objects.all().order_by("-id")
    serializer_class = BuildRecordSerializer
    ordering = ("-id",)
    http_method_names = ["get", "head", "options"]

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        kb_id = request.GET.get("knowledge_base")
        if kb_id:
            queryset = queryset.filter(knowledge_base_id=kb_id)
        return JsonResponse({"result": True, "data": self.get_serializer(queryset, many=True).data})

    def retrieve(self, request, *args, **kwargs):
        return JsonResponse({"result": True, "data": self.get_serializer(self.get_object()).data})
