from django.http import JsonResponse
from rest_framework.decorators import action

from apps.core.utils.viewset_utils import AuthViewSet
from apps.opspilot.models import CheckItem
from apps.opspilot.serializers.wiki_serializers import CheckItemSerializer
from apps.opspilot.services.wiki.check_service import accept_candidate, reject_candidate
from apps.system_mgmt.utils.operation_log_utils import log_operation


class WikiCheckItemViewSet(AuthViewSet):
    """检查与审核:列出风险/检查事项,接受/拒绝候选版本。"""

    queryset = CheckItem.objects.all().order_by("-id")
    serializer_class = CheckItemSerializer
    ordering = ("-id",)
    http_method_names = ["get", "post", "head", "options"]

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        kb_id = request.GET.get("knowledge_base")
        if kb_id:
            queryset = queryset.filter(knowledge_base_id=kb_id)
        status_filter = request.GET.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        check_type = request.GET.get("check_type")
        if check_type:
            queryset = queryset.filter(check_type=check_type)
        return JsonResponse({"result": True, "data": self.get_serializer(queryset, many=True).data})

    def retrieve(self, request, *args, **kwargs):
        return JsonResponse({"result": True, "data": self.get_serializer(self.get_object()).data})

    @action(methods=["POST"], detail=True)
    def accept(self, request, pk=None):
        """接受候选版本:置为当前有效版本并关闭检查。"""
        check = self.get_object()
        if not check.candidate_version_id:
            return JsonResponse({"result": False, "message": "该检查无候选版本"}, status=400)
        accept_candidate(check, operator=getattr(request.user, "username", ""))
        log_operation(request, "execute", "opspilot", f"接受候选版本(检查#{check.id})")
        return JsonResponse({"result": True, "data": self.get_serializer(check).data})

    @action(methods=["POST"], detail=True)
    def reject(self, request, pk=None):
        """拒绝候选版本:丢弃候选,当前有效版本不变。"""
        check = self.get_object()
        reject_candidate(check, operator=getattr(request.user, "username", ""))
        log_operation(request, "execute", "opspilot", f"拒绝候选版本(检查#{check.id})")
        return JsonResponse({"result": True, "data": self.get_serializer(check).data})
