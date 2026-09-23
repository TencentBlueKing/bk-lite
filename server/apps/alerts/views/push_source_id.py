from rest_framework.decorators import action
from rest_framework.viewsets import ViewSet

from apps.alerts.service.push_source_catalog import default_catalog
from apps.alerts.utils.permission_scope import get_query_group_ids
from apps.alerts.views.alert_source import ALERT_SOURCE_OPTION_PERMISSIONS
from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.web_utils import WebUtils


class PushSourceIdViewSet(ViewSet):
    @HasPermission(ALERT_SOURCE_OPTION_PERMISSIONS)
    @action(detail=False, methods=["get"], url_path="options")
    def options(self, request):
        team_ids = get_query_group_ids(request)
        return WebUtils.response_success(default_catalog().list_for_teams(team_ids))
