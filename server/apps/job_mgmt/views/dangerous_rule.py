"""危险规则视图"""

from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.job_mgmt.constants import DangerousLevel
from apps.job_mgmt.filters.dangerous_rule import DangerousRuleFilter
from apps.job_mgmt.models import DangerousRule
from apps.job_mgmt.serializers.dangerous_rule import DangerousRuleCreateSerializer, DangerousRuleSerializer, DangerousRuleUpdateSerializer
from apps.job_mgmt.views.dangerous_base import BaseDangerousItemViewSet
from apps.core.utils.team_utils import get_current_team


class DangerousRuleViewSet(BaseDangerousItemViewSet):
    """危险规则视图集"""

    queryset = DangerousRule.objects.all()
    serializer_class = DangerousRuleSerializer
    filterset_class = DangerousRuleFilter
    search_fields = ["name", "pattern"]

    create_serializer_class = DangerousRuleCreateSerializer
    update_serializer_class = DangerousRuleUpdateSerializer
    dangerous_log_label = "危险规则"
    dangerous_name_field = "name"

    @HasPermission("dangerous_command-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("dangerous_command-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("dangerous_command-Add")
    def create(self, request, *args, **kwargs):
        return self.create_with_log(request, *args, **kwargs)

    @HasPermission("dangerous_command-Edit")
    def update(self, request, *args, **kwargs):
        return self.update_with_log(request, *args, **kwargs)

    @HasPermission("dangerous_command-Delete")
    def destroy(self, request, *args, **kwargs):
        return self.destroy_with_log(request, *args, **kwargs)

    @action(detail=False, methods=["GET"])
    @HasPermission("dangerous_command-View")
    def enabled_rules(self, request):
        current_team = int(get_current_team(request, 0))
        rules = DangerousRule.objects.filter(is_enabled=True, team__contains=current_team)
        result = {DangerousLevel.CONFIRM: [], DangerousLevel.FORBIDDEN: []}
        for rule in rules:
            result[rule.level].append(rule.pattern)
        return Response(result)
