from django.http import JsonResponse
from django_filters import filters
from django_filters.rest_framework import FilterSet
from rest_framework import viewsets
from rest_framework.decorators import action

from apps.core.decorators.api_permission import HasPermission
from apps.opspilot.models import QuotaRule
from apps.opspilot.serializers.quota_rule_serializers import QuotaRuleSerializer
from apps.opspilot.utils.quota_utils import get_quota_client
from apps.rpc.system_mgmt import SystemMgmt


class ObjFilter(FilterSet):
    name = filters.CharFilter(field_name="name", lookup_expr="icontains")


class QuotaRuleViewSet(viewsets.ModelViewSet):
    queryset = QuotaRule.objects.all()
    serializer_class = QuotaRuleSerializer
    ordering = ("-id",)
    filterset_class = ObjFilter

    # @HasRole("admin")
    @HasPermission("mange_quota-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("mange_quota-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("mange_quota-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @HasPermission("mange_quota-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=["GET"])
    @HasPermission("mange_quota-Add,mange_quota-Edit")
    def get_group_user(self, request, *args, **kwargs):
        teams = request.user.group_list
        current_team = request.COOKIES.get("current_team")
        if not current_team:
            current_team = teams[0]
        client = SystemMgmt()
        return_data = client.get_group_users(current_team)
        return JsonResponse(return_data)

    @action(detail=False, methods=["GET"])
    @HasPermission("my_quota-View")
    def my_quota(self, request):
        client = get_quota_client(request)
        all_file_size, used_file_size, is_file_uniform = client.get_file_quota()
        skill_count, used_skill_count, is_skill_uniform = client.get_skill_quota()
        bot_count, used_bot_count, is_bot_uniform = client.get_bot_quota()
        if all_file_size == -1:
            all_file_size = 0
        if skill_count == -1:
            skill_count = 0
        if bot_count == -1:
            bot_count = 0
        return_data = {
            "used_file_size": used_file_size,
            "is_file_uniform": is_file_uniform,
            "is_skill_uniform": is_skill_uniform,
            "is_bot_uniform": is_bot_uniform,
            "used_skill_count": used_skill_count,
            "used_bot_count": used_bot_count,
            "all_file_size": all_file_size,
            "all_skill_count": skill_count,
            "all_bot_count": bot_count,
        }
        return JsonResponse({"result": True, "data": return_data})
