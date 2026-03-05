"""危险规则视图"""

from apps.core.utils.viewset_utils import AuthViewSet
from apps.job_mgmt.filters.dangerous_rule import DangerousRuleFilter
from apps.job_mgmt.models import DangerousRule
from apps.job_mgmt.serializers.dangerous_rule import DangerousRuleCreateSerializer, DangerousRuleSerializer, DangerousRuleUpdateSerializer


class DangerousRuleViewSet(AuthViewSet):
    """危险规则视图集"""

    queryset = DangerousRule.objects.all()
    serializer_class = DangerousRuleSerializer
    filterset_class = DangerousRuleFilter
    search_fields = ["name", "pattern"]
    ORGANIZATION_FIELD = "team"

    def get_serializer_class(self):
        if self.action == "create":
            return DangerousRuleCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return DangerousRuleUpdateSerializer
        return DangerousRuleSerializer
