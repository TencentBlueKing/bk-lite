from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework.throttling import ScopedRateThrottle

from apps.operation_analysis.views.datasource_view import DataSourceAPIModelViewSet
from apps.operation_analysis.models.datasource_models import DataSourceAPIModel
from apps.operation_analysis.serializers.share_serializers import ShareExchangeSerializer
from apps.operation_analysis.services.share_service import ShareLinkInvalid, exchange_share, resolve_session
from apps.system_mgmt.nats.auth import build_user_authorization_context


INVALID_SHARE_RESPONSE = {"detail": "分享链接无效或已失效"}


def _dashboard_data_source_ids(value):
    found = set()
    if isinstance(value, dict):
        source_id = value.get("dataSource")
        if isinstance(source_id, int) or (isinstance(source_id, str) and source_id.isdigit()):
            found.add(int(source_id))
        for child in value.values():
            found.update(_dashboard_data_source_ids(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_dashboard_data_source_ids(child))
    return found


def _delegated_sharer_user(user):
    """Restore the runtime attributes normally attached by token authentication."""
    context = build_user_authorization_context(user)
    user.is_authenticated = True
    user.permission = {
        app: set(permissions)
        for app, permissions in (context.get("permission") or {}).items()
    }
    user.group_tree = context.get("group_tree") or []
    user.is_superuser = bool(context.get("is_superuser", False))
    user.timezone = context.get("timezone") or getattr(user, "timezone", None)
    return user


class DashboardShareAccessViewSet(viewsets.ViewSet):
    throttle_classes = [ScopedRateThrottle]

    def get_throttles(self):
        self.throttle_scope = (
            "dashboard_share_exchange"
            if getattr(self, "action", None) == "exchange"
            else "dashboard_share_access"
        )
        return super().get_throttles()

    @action(detail=False, methods=["post"], url_path="exchange")
    def exchange(self, request):
        serializer = ShareExchangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            session = exchange_share(token=serializer.validated_data["token"], visitor=request.user)
        except ShareLinkInvalid:
            return Response(INVALID_SHARE_RESPONSE, status=status.HTTP_404_NOT_FOUND)
        return Response(
            {
                "session_id": str(session.session_id),
                "expires_at": session.expires_at,
            }
        )

    @action(detail=False, methods=["get"], url_path=r"session/(?P<session_id>[^/.]+)")
    def session_detail(self, request, session_id=None):
        try:
            principal = resolve_session(session_id=session_id, visitor=request.user)
        except ShareLinkInvalid:
            return Response(INVALID_SHARE_RESPONSE, status=status.HTTP_404_NOT_FOUND)
        dashboard = principal.dashboard
        return Response(
            {
                "id": dashboard.id,
                "name": dashboard.name,
                "desc": dashboard.desc,
                "filters": dashboard.filters,
                "other": dashboard.other,
                "view_sets": dashboard.view_sets,
                "is_build_in": dashboard.is_build_in,
            }
        )

    @action(
        detail=False,
        methods=["post"],
        url_path=r"session/(?P<session_id>[^/.]+)/query/(?P<data_source_id>\d+)",
    )
    def query(self, request, session_id=None, data_source_id=None):
        try:
            principal = resolve_session(session_id=session_id, visitor=request.user)
        except ShareLinkInvalid:
            return Response(INVALID_SHARE_RESPONSE, status=status.HTTP_404_NOT_FOUND)
        if int(data_source_id) not in _dashboard_data_source_ids(principal.dashboard.view_sets):
            return Response({"detail": "无权访问当前数据源"}, status=status.HTTP_403_FORBIDDEN)

        factory = APIRequestFactory()
        delegated_request = factory.post("/", request.data, format="json")
        delegated_request.COOKIES["current_team"] = str(principal.space_id)
        force_authenticate(delegated_request, user=_delegated_sharer_user(principal.user))
        view = DataSourceAPIModelViewSet.as_view({"post": "get_source_data"})
        return view(delegated_request, pk=data_source_id)

    @action(
        detail=False,
        methods=["get"],
        url_path=r"session/(?P<session_id>[^/.]+)/data_sources",
    )
    def data_sources(self, request, session_id=None):
        try:
            principal = resolve_session(session_id=session_id, visitor=request.user)
        except ShareLinkInvalid:
            return Response(INVALID_SHARE_RESPONSE, status=status.HTTP_404_NOT_FOUND)
        allowed_ids = _dashboard_data_source_ids(principal.dashboard.view_sets)
        data_sources = [
            item
            for item in DataSourceAPIModel.objects.filter(id__in=allowed_ids).prefetch_related("namespaces", "tag")
            if principal.space_id in (item.groups or [])
        ]
        return Response(
            [
                {
                    "id": item.id,
                    "name": item.name,
                    "desc": item.desc or "",
                    "source_type": item.source_type,
                    "params": item.params or [],
                    "chart_type": item.chart_type or [],
                    "field_schema": item.field_schema or [],
                    "namespaces": list(item.namespaces.values_list("id", flat=True)),
                    "namespace_options": list(item.namespaces.values("id", "name")),
                    "groups": [principal.space_id],
                }
                for item in data_sources
            ]
        )
