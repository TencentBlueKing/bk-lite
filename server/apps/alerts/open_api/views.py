from rest_framework.exceptions import (
    APIException,
    MethodNotAllowed,
    NotAuthenticated,
    PermissionDenied,
    ValidationError,
)
from rest_framework.permissions import BasePermission
from rest_framework.views import APIView

from apps.core.exceptions.base_app_exception import BaseAppException

from .auth import AlertsOpenAPIContext
from .errors import AlertsOpenAPIError
from .responses import open_api_error, open_api_success
from .services import ALLOWED_ACTIONS, AlertsOpenAPIService


class APISecretRequired(BasePermission):
    def has_permission(self, request, view):
        return bool(getattr(request, "api_pass", False))


class AlertsOpenAPIView(APIView):
    permission_classes = [APISecretRequired]

    def service(self, request):
        return AlertsOpenAPIService(AlertsOpenAPIContext.from_request(request))

    def permission_denied(self, request, message=None, code=None):
        if not getattr(request, "api_pass", False):
            raise AlertsOpenAPIError("alerts.auth.api_secret_required", "必须使用 API Secret", 403)
        return super().permission_denied(request, message=message, code=code)

    def handle_exception(self, exc):
        if isinstance(exc, AlertsOpenAPIError):
            return open_api_error(exc)
        if isinstance(exc, BaseAppException):
            return open_api_error(
                AlertsOpenAPIError("alerts.validation.failed", exc.message, 400)
            )
        if isinstance(exc, NotAuthenticated):
            return open_api_error(
                AlertsOpenAPIError("alerts.auth.authentication_required", "需要认证", exc.status_code)
            )
        if isinstance(exc, PermissionDenied):
            return open_api_error(
                AlertsOpenAPIError("alerts.permission.denied", "权限不足", exc.status_code)
            )
        if isinstance(exc, MethodNotAllowed):
            return open_api_error(
                AlertsOpenAPIError("alerts.request.method_not_allowed", "请求方法不被允许", exc.status_code)
            )
        if isinstance(exc, ValidationError):
            return open_api_error(
                AlertsOpenAPIError("alerts.validation.failed", "请求参数非法", exc.status_code)
            )
        if isinstance(exc, APIException):
            return open_api_error(
                AlertsOpenAPIError("alerts.request.failed", "请求处理失败", exc.status_code)
            )
        return super().handle_exception(exc)


class OpenAlertListView(AlertsOpenAPIView):
    def get(self, request):
        return open_api_success(self.service(request).list_alerts(request.query_params))


class OpenAlertDetailView(AlertsOpenAPIView):
    def get(self, request, alert_id):
        return open_api_success(self.service(request).get_alert(alert_id))


class OpenAlertEventsView(AlertsOpenAPIView):
    def get(self, request, alert_id):
        return open_api_success(
            self.service(request).list_alert_events(alert_id, request.query_params)
        )


class OpenAlertActionView(AlertsOpenAPIView):
    def post(self, request, alert_id, action):
        if action not in ALLOWED_ACTIONS:
            raise AlertsOpenAPIError("alerts.validation.failed", f"不支持的操作: {action}", 400)
        return open_api_success(
            self.service(request).operate_alert(alert_id, action, request.data)
        )


class OpenAlertBatchActionView(AlertsOpenAPIView):
    def post(self, request, action):
        if action not in ALLOWED_ACTIONS:
            raise AlertsOpenAPIError("alerts.validation.failed", f"不支持的操作: {action}", 400)
        return open_api_success(
            self.service(request).operate_alerts_batch(action, request.data)
        )
