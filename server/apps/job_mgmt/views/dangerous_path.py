"""高危路径视图"""

from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import AuthViewSet
from apps.job_mgmt.constants import DangerousLevel, MatchType
from apps.job_mgmt.filters.dangerous_path import DangerousPathFilter
from apps.job_mgmt.models import DangerousPath
from apps.job_mgmt.serializers.dangerous_path import DangerousPathCreateSerializer, DangerousPathSerializer, DangerousPathUpdateSerializer
from apps.system_mgmt.utils.operation_log_utils import log_operation


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
        response = super().create(request, *args, **kwargs)
        if response.status_code == 201:
            path = response.data.get("pattern") if isinstance(response.data, dict) else request.data.get("pattern", "")
            log_operation(request, "create", "job", f"新增危险路径: {path}")
        return response

    @HasPermission("dangerous_path-Edit")
    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        if response.status_code == 200:
            path = response.data.get("pattern") if isinstance(response.data, dict) else request.data.get("pattern", "")
            log_operation(request, "update", "job", f"编辑危险路径: {path}")
        return response

    @HasPermission("dangerous_path-Delete")
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        response = super().destroy(request, *args, **kwargs)
        if response.status_code in (200, 204):
            log_operation(request, "delete", "job", f"删除危险路径: {instance.pattern}")
        return response

    @action(detail=False, methods=["GET"])
    def enabled_paths(self, request):
        """获取当前组启用的所有高危路径规则"""
        current_team = int(request.COOKIES.get("current_team", 0))
        paths = DangerousPath.objects.filter(is_enabled=True, team__contains=current_team)

        result = {
            DangerousLevel.CONFIRM: {MatchType.EXACT: [], MatchType.REGEX: []},
            DangerousLevel.FORBIDDEN: {MatchType.EXACT: [], MatchType.REGEX: []},
        }
        for path in paths:
            level = path.level
            match_type = path.match_type
            if level not in result:
                result[level] = {MatchType.EXACT: [], MatchType.REGEX: []}
            if match_type not in result[level]:
                result[level][match_type] = []
            result[level][match_type].append(path.pattern)

        return Response(result)
