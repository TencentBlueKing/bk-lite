from typing import Any, Callable, Optional

from django.core.cache import cache
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.core.utils.open_base import login_exempt
from apps.operation_analysis.services.display_service import activate_display, set_display_cookie
from apps.operation_analysis.services.share_audit import log_share_access
from apps.operation_analysis.services.share_service import ShareLinkInvalid, ShareRateLimited
from apps.operation_analysis.services.user_messages import oa_message
from apps.operation_analysis.views.share_view import DashboardShareAccessViewSet

_ACTIVATE_RATE_LIMIT = 30
_ACTIVATE_RATE_WINDOW = 60


def _client_key(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR") or ""
    if forwarded:
        return forwarded.split(",")[0].strip() or "unknown"
    return request.META.get("REMOTE_ADDR") or "unknown"


def _enforce_activate_rate(request):
    key = f"screen_display_activate:{_client_key(request)}"
    if cache.add(key, 1, timeout=_ACTIVATE_RATE_WINDOW):
        return
    try:
        current = cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=_ACTIVATE_RATE_WINDOW)
        return
    if current > _ACTIVATE_RATE_LIMIT:
        raise ShareRateLimited


class ScreenDisplayAccessViewSet(viewsets.ViewSet):
    """电视投屏入口。只转发大屏取数动作，不暴露同事分享的 prepare/exchange。"""

    authentication_classes = []
    permission_classes = [AllowAny]

    @classmethod
    def as_view(cls, actions: Optional[dict] = None, **initkwargs: Any) -> Callable:
        view = super().as_view(actions=actions, **initkwargs)
        return csrf_exempt(login_exempt(view))

    def _forward(self, request, method_name, **kwargs):
        request._screen_display = True
        host = DashboardShareAccessViewSet()
        host.request = request
        host.kwargs = kwargs
        host.format_kwarg = None
        host.action = method_name
        return getattr(host, method_name)(request, session_id="current", **kwargs)

    @action(detail=False, methods=["post"], url_path="activate")
    def activate(self, request):
        token = request.data.get("token") if isinstance(request.data, dict) else None
        if not isinstance(token, str) or not token.strip():
            return Response(
                {"detail": "展示授权无效", "reason": "invalid", "data": {"reason": "invalid"}},
                status=status.HTTP_404_NOT_FOUND,
            )
        try:
            _enforce_activate_rate(request)
            session = activate_display(token=token.strip())
        except ShareRateLimited:
            log_share_access(request, action="display_activate", result="reject", reason="rate_limited")
            return Response({"detail": oa_message("messages.rate_limited", "请求过于频繁")}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        except ShareLinkInvalid as exc:
            reason = exc.args[0] if exc.args else "invalid"
            log_share_access(request, action="display_activate", result="reject", reason=reason if reason in {"paused", "expired"} else "invalid")
            if reason == "paused":
                return Response(
                    {"detail": "展示已停用", "reason": "paused", "data": {"reason": "paused"}},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if reason == "expired":
                return Response(
                    {"detail": "展示已过期", "reason": "expired", "data": {"reason": "expired"}},
                    status=status.HTTP_403_FORBIDDEN,
                )
            return Response(
                {"detail": "展示授权无效", "reason": "invalid", "data": {"reason": "invalid"}},
                status=status.HTTP_404_NOT_FOUND,
            )

        log_share_access(request, action="display_activate", result="ok")
        response = Response({"ok": True})
        return set_display_cookie(response, request, session)

    @action(detail=False, methods=["get"], url_path="current")
    def current(self, request):
        return self._forward(request, "session_detail")

    @action(detail=False, methods=["post"], url_path=r"current/query/(?P<data_source_id>\d+)")
    def current_query(self, request, data_source_id=None):
        return self._forward(request, "query", data_source_id=data_source_id)

    @action(detail=False, methods=["get"], url_path="current/data_sources")
    def current_data_sources(self, request):
        return self._forward(request, "data_sources")

    @action(detail=False, methods=["post"], url_path="current/application3d/wall")
    def current_application3d_wall(self, request):
        return self._forward(request, "application3d_wall")

    @action(detail=False, methods=["post"], url_path="current/application3d/application_detail")
    def current_application3d_application_detail(self, request):
        return self._forward(request, "application3d_application_detail")

    @action(detail=False, methods=["post"], url_path="current/application3d/architecture")
    def current_application3d_architecture(self, request):
        return self._forward(request, "application3d_architecture")

    @action(detail=False, methods=["post"], url_path="current/application3d/alarm_detail")
    def current_application3d_alarm_detail(self, request):
        return self._forward(request, "application3d_alarm_detail")

    @action(detail=False, methods=["post"], url_path="current/application3d/metric")
    def current_application3d_metric(self, request):
        return self._forward(request, "application3d_metric")

    @action(detail=False, methods=["post"], url_path="current/dashboard_scene_permissions")
    def current_dashboard_scene_permissions(self, request):
        return self._forward(request, "dashboard_scene_permissions")

    @action(detail=False, methods=["post"], url_path="current/related_topology")
    def current_related_topology(self, request):
        return self._forward(request, "related_topology")

    @action(detail=False, methods=["post"], url_path="current/application_topology")
    def current_application_topology(self, request):
        return self._forward(request, "application_topology")

    @action(detail=False, methods=["post"], url_path="current/room3d/rooms")
    def current_room3d_rooms(self, request):
        return self._forward(request, "room3d_rooms")

    @action(detail=False, methods=["post"], url_path="current/room3d/layout")
    def current_room3d_layout(self, request):
        return self._forward(request, "room3d_layout")

    @action(detail=False, methods=["post"], url_path="current/network_status_topology")
    def current_network_status_topology(self, request):
        return self._forward(request, "display_network_status_topology")

    @action(detail=False, methods=["post"], url_path="current/network_topology/metric_values")
    def current_network_topology_metric_values(self, request):
        return self._forward(request, "network_topology_metric_values")

    @action(detail=False, methods=["post"], url_path="current/network_topology/link_runtime")
    def current_network_topology_link_runtime(self, request):
        return self._forward(request, "network_topology_link_runtime")
