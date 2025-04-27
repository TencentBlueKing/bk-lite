from django.http import JsonResponse
from django_filters import filters
from django_filters.rest_framework import FilterSet
from rest_framework import viewsets
from rest_framework.decorators import action

from apps.core.decorators.api_perminssion import HasRole
from apps.opspilot.models import QuotaRule
from apps.opspilot.quota_rule_mgmt.quota_utils import get_quota_client
from apps.opspilot.quota_rule_mgmt.serializers import QuotaRuleSerializer
from apps.rpc.system_mgmt import SystemMgmt


class ObjFilter(FilterSet):
    name = filters.CharFilter(field_name="name", lookup_expr="icontains")


class QuotaRuleViewSet(viewsets.ModelViewSet):
    queryset = QuotaRule.objects.all()
    serializer_class = QuotaRuleSerializer
    ordering = ("-id",)
    filterset_class = ObjFilter

    # @HasRole("admin")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasRole("admin")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasRole("admin")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @HasRole("admin")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasRole("admin")
    @action(detail=False, methods=["GET"])
    def get_group_user(self, request, *args, **kwargs):
        teams = request.user.group_list
        current_team = request.COOKIES.get("current_team")
        if not current_team:
            current_team = teams[0]
        client = SystemMgmt()
        return_data = client.get_group_users(current_team)
        return JsonResponse(return_data)

    @action(detail=False, methods=["GET"])
    def my_quota(self, request):
        client = get_quota_client(request)
        all_file_size, used_file_size, is_file_uniform = client.get_file_quota()
        skill_count, used_skill_count, is_skill_uniform = client.get_skill_quota()
        bot_count, used_bot_count, is_bot_uniform = client.get_bot_quota()
        token_set = client.get_token_quota()
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
            "token_set": token_set,
        }
        return JsonResponse({"result": True, "data": return_data})
