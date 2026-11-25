from rest_framework.viewsets import ViewSet

from apps.core.utils.web_utils import WebUtils
from apps.log.serializers.syslog_source_device import SyslogSourceDeviceQuerySerializer
from apps.log.services.access_scope import LogAccessScopeService
from apps.log.services.syslog_source_device import list_syslog_source_devices
from apps.log.views.extractor import TYPE_SCOPE_VIEW_PERMISSIONS


def _user_log_permissions(request) -> set[str]:
    user_permissions = getattr(request.user, "permission", set())
    if isinstance(user_permissions, dict):
        return set(user_permissions.get("log") or [])
    if isinstance(user_permissions, set):
        return user_permissions
    return set()


def authorize_syslog_source_device_view(request):
    try:
        LogAccessScopeService.get_data_scope(request)
    except ValueError as exc:
        return WebUtils.response_403(str(exc))
    if getattr(request.user, "is_superuser", False):
        return None
    if _user_log_permissions(request).intersection(TYPE_SCOPE_VIEW_PERMISSIONS):
        return None
    return WebUtils.response_403("当前用户无权限查看来源设备")


class SyslogSourceDeviceViewSet(ViewSet):
    def list(self, request):
        denied = authorize_syslog_source_device_view(request)
        if denied is not None:
            return denied
        serializer = SyslogSourceDeviceQuerySerializer(data=request.query_params)
        if not serializer.is_valid():
            return WebUtils.response_error(error_message="invalid query")
        return WebUtils.response_success(list_syslog_source_devices(**serializer.validated_data))
