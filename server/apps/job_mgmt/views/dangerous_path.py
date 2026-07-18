"""高危路径视图"""

from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.job_mgmt.constants import DangerousLevel, MatchType
from apps.job_mgmt.filters.dangerous_path import DangerousPathFilter
from apps.job_mgmt.models import DangerousPath
from apps.job_mgmt.serializers.dangerous_path import DangerousPathCreateSerializer, DangerousPathSerializer, DangerousPathUpdateSerializer
from apps.job_mgmt.views.dangerous_base import BaseDangerousItemViewSet
from apps.core.utils.team_utils import get_current_team


class DangerousPathViewSet(BaseDangerousItemViewSet):
    """高危路径视图集"""

    queryset = DangerousPath.objects.all()
    serializer_class = DangerousPathSerializer
    filterset_class = DangerousPathFilter
    search_fields = ["name", "pattern"]

    create_serializer_class = DangerousPathCreateSerializer
    update_serializer_class = DangerousPathUpdateSerializer
    dangerous_log_label = "危险路径"
    dangerous_name_field = "pattern"

    @HasPermission("dangerous_path-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("dangerous_path-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("dangerous_path-Add")
    def create(self, request, *args, **kwargs):
        return self.create_with_log(request, *args, **kwargs)

    @HasPermission("dangerous_path-Edit")
    def update(self, request, *args, **kwargs):
        return self.update_with_log(request, *args, **kwargs)

    @HasPermission("dangerous_path-Delete")
    def destroy(self, request, *args, **kwargs):
        return self.destroy_with_log(request, *args, **kwargs)

    @action(detail=False, methods=["GET"])
    @HasPermission("dangerous_path-View")
    def enabled_paths(self, request):
        """获取当前组启用的所有高危路径规则"""
        current_team = int(get_current_team(request, 0))
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
