"""高危路径视图"""

from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import AuthViewSet
from apps.job_mgmt.constants import DangerousLevel
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
    permission_key = "job"

    def get_serializer_class(self):
        if self.action == "create":
            return DangerousPathCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return DangerousPathUpdateSerializer
        return DangerousPathSerializer

    @HasPermission("dangerous_path-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("dangerous_path-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("dangerous_path-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("dangerous_path-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @HasPermission("dangerous_path-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=["GET"])
    def enabled_paths(self, request):
        """获取当前组启用的所有高危路径规则"""
        current_team = int(request.COOKIES.get("current_team", 0))
        paths = DangerousPath.objects.filter(is_enabled=True, team__contains=current_team)
        result = {DangerousLevel.CONFIRM: [], DangerousLevel.FORBIDDEN: []}
        for path in paths:
            result[path.level].append(path.pattern)
        return Response(result)
