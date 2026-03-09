"""危险规则视图"""

from apps.core.decorators.api_permission import HasPermission
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
        return super().create(request, *args, **kwargs)

    @HasPermission("dangerous_command-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @HasPermission("dangerous_command-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)
