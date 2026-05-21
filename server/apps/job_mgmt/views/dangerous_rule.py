"""危险规则视图"""

from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import AuthViewSet
from apps.job_mgmt.constants import DangerousLevel
from apps.job_mgmt.filters.dangerous_rule import DangerousRuleFilter
from apps.job_mgmt.models import DangerousRule
from apps.job_mgmt.serializers.dangerous_rule import DangerousRuleCreateSerializer, DangerousRuleSerializer, DangerousRuleUpdateSerializer
from apps.system_mgmt.utils.operation_log_utils import log_operation


class DangerousRuleViewSet(AuthViewSet):
    """危险规则视图集"""

    queryset = DangerousRule.objects.all()
    serializer_class = DangerousRuleSerializer
    filterset_class = DangerousRuleFilter
    search_fields = ["name", "pattern"]
    ORGANIZATION_FIELD = "team"
    permission_key = "job"

    def get_serializer_class(self):
        if self.action == "create":
            return DangerousRuleCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return DangerousRuleUpdateSerializer
        return DangerousRuleSerializer

    @HasPermission("dangerous_command-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("dangerous_command-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("dangerous_command-Add")
    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        if response.status_code == 201:
            rule_name = response.data.get("name") if isinstance(response.data, dict) else request.data.get("name", "")
            log_operation(request, "create", "job", f"新增危险规则: {rule_name}")
        return response

    @HasPermission("dangerous_command-Edit")
    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        if response.status_code == 200:
            rule_name = response.data.get("name") if isinstance(response.data, dict) else request.data.get("name", "")
            log_operation(request, "update", "job", f"编辑危险规则: {rule_name}")
        return response

    @HasPermission("dangerous_command-Delete")
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        response = super().destroy(request, *args, **kwargs)
        if response.status_code in (200, 204):
            log_operation(request, "delete", "job", f"删除危险规则: {instance.name}")
        return response

    @action(detail=False, methods=["GET"])
    def enabled_rules(self, request):
        current_team = int(request.COOKIES.get("current_team", 0))
        rules = DangerousRule.objects.filter(is_enabled=True, team__contains=current_team)
        result = {DangerousLevel.CONFIRM: [], DangerousLevel.FORBIDDEN: []}
        for rule in rules:
            result[rule.level].append(rule.pattern)
        return Response(result)
