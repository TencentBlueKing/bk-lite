"""高危路径视图"""

from apps.core.utils.viewset_utils import AuthViewSet
from apps.job_mgmt.filters.dangerous_path import DangerousPathFilter
from apps.job_mgmt.models import DangerousPath
from apps.job_mgmt.serializers.dangerous_path import DangerousPathCreateSerializer, DangerousPathSerializer, DangerousPathUpdateSerializer


class DangerousPathViewSet(AuthViewSet):
    """高危路径视图集"""

    queryset = DangerousPath.objects.all()
    serializer_class = DangerousPathSerializer
    filterset_class = DangerousPathFilter
    search_fields = ["name", "pattern"]
    ORGANIZATION_FIELD = "team"

    def get_serializer_class(self):
        if self.action == "create":
            return DangerousPathCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return DangerousPathUpdateSerializer
        return DangerousPathSerializer
