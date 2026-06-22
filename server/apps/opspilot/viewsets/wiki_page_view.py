from django.http import JsonResponse

from apps.core.utils.viewset_utils import AuthViewSet
from apps.opspilot.models import BuildRecord, KnowledgePage
from apps.opspilot.serializers.wiki_serializers import BuildRecordSerializer, KnowledgePageSerializer


class WikiPageViewSet(AuthViewSet):
    """知识页面浏览(本增量只读;手工创建/编辑/版本在后续增量接入)。"""

    queryset = KnowledgePage.objects.all().order_by("-id")
    serializer_class = KnowledgePageSerializer
    ordering = ("-id",)
    http_method_names = ["get", "head", "options"]

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
