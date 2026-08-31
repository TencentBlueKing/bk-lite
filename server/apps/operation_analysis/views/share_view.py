from typing import Any, Callable, Optional

from django.views.decorators.csrf import csrf_exempt
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.core.utils.open_base import login_exempt
from apps.operation_analysis.common.datasource_visibility import can_access_datasource_in_org
from apps.operation_analysis.constants.canvas_refresh import normalize_canvas_refresh_interval
from apps.operation_analysis.models.datasource_models import DataSourceAPIModel
from apps.operation_analysis.serializers.share_serializers import (
    ShareExchangeSerializer,
    ShareNetworkTopologyLinkRuntimeSerializer,
    ShareNetworkTopologyMetricValuesSerializer,
    SharePrepareSerializer,
)
from apps.operation_analysis.services.named_option_datasources import (
    collect_named_option_datasource_ids,
    collect_named_option_datasource_ids_from_filters,
)
from apps.operation_analysis.services.network_status_topology_overlay import (
    collect_network_status_topology_overlay_datasource_ids,
    view_sets_has_network_status_topology,
)
from apps.operation_analysis.services.network_topology.runtime import NetworkTopologyRuntimeService
from apps.operation_analysis.services.network_topology.weops_adapter import WeOpsTopologyAdapterError
from apps.operation_analysis.services.share_audit import log_share_access
from apps.operation_analysis.services.share_network_topology import (
    ShareNetworkTopologyRuntimeDenied,
    reject_forbidden_topology_body_keys,
    validate_share_link_runtime,
    validate_share_metric_values,
)
from apps.operation_analysis.services.share_service import (
    SHARE_DATASOURCE_RESOURCE_TYPES,
    SHARE_PREPARE_COOKIE,
    SHARE_PREPARE_TTL,
    ShareLinkInvalid,
    ShareQueryParamsDenied,
    ShareRateLimited,
    _resource_filter_definitions,
    exchange_share,
    filter_share_query_params,
    prepare_share_exchange,
    resolve_session,
)
from apps.operation_analysis.services.share_throttle import (
    DashboardShareAccessUserThrottle,
    DashboardShareExchangeUserThrottle,
    DashboardShareInvalidTokenThrottle,
    DashboardSharePrepareThrottle,
)
from apps.operation_analysis.views.datasource_view import DataSourceAPIModelViewSet
from apps.system_mgmt.nats.auth import build_user_authorization_context

INVALID_SHARE_RESPONSE = {"detail": "分享链接无效或已失效"}


def _walk_data_source_ids(value):
    found = set()
    if isinstance(value, dict):
        source_id = value.get("dataSource")
        if isinstance(source_id, int) or (isinstance(source_id, str) and source_id.isdigit()):
            found.add(int(source_id))
        for child in value.values():
            found.update(_walk_data_source_ids(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_walk_data_source_ids(child))
    return found


def _canvas_data_source_ids(resource):
    view_sets = getattr(resource, "view_sets", None)
    found = _walk_data_source_ids(view_sets)
    if view_sets_has_network_status_topology(view_sets):
        found.update(collect_network_status_topology_overlay_datasource_ids())
    found.update(collect_named_option_datasource_ids(found))
    found.update(collect_named_option_datasource_ids_from_filters(_resource_filter_definitions(resource)))
    return found


def _view_sets_has_scene_widget(value, scene_widget_type: str) -> bool:
    if isinstance(value, dict):
        if any(value.get(key) == scene_widget_type for key in ("type", "chartType", "widgetType", "sceneWidgetType")):
            return True
        return any(_view_sets_has_scene_widget(child, scene_widget_type) for child in value.values())
    if isinstance(value, list):
        return any(_view_sets_has_scene_widget(child, scene_widget_type) for child in value)
    return False


def _serialize_shared_resource(principal):
    resource = principal.resource
    if principal.resource_type == "networkTopology":
        # Phase A：只返回脱敏配置；禁止 token / base_url / runtime cache 等 WeOps 凭证面。
        return {
            "resource_type": principal.resource_type,
            "id": resource.id,
            "name": resource.name,
            "desc": getattr(resource, "desc", "") or "",
            "view_sets": getattr(resource, "view_sets", None) or {},
            "is_build_in": bool(getattr(resource, "is_build_in", False)),
            "refresh_interval": normalize_canvas_refresh_interval(getattr(resource, "refresh_interval", 0)),
            "status": getattr(resource, "status", "") or "",
        }
    payload = {
        "resource_type": principal.resource_type,
        "id": resource.id,
        "name": resource.name,
        "desc": getattr(resource, "desc", "") or "",
        "view_sets": getattr(resource, "view_sets", None),
        "is_build_in": bool(getattr(resource, "is_build_in", False)),
    }
    if hasattr(resource, "filters"):
        payload["filters"] = resource.filters
    if hasattr(resource, "other"):
        payload["other"] = resource.other
    if hasattr(resource, "refresh_interval"):
        payload["refresh_interval"] = normalize_canvas_refresh_interval(resource.refresh_interval)
    return payload


def _delegated_sharer_user(user):
    """Restore the runtime attributes normally attached by token authentication."""
    context = build_user_authorization_context(user)
    user.is_authenticated = True
    user.permission = {app: set(permissions) for app, permissions in (context.get("permission") or {}).items()}
    user.group_tree = context.get("group_tree") or []
    user.is_superuser = bool(context.get("is_superuser", False))
    user.timezone = context.get("timezone") or getattr(user, "timezone", None)
    return user


class DashboardShareAccessViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @classmethod
    def as_view(cls, actions: Optional[dict] = None, **initkwargs: Any) -> Callable:
        """prepare 需在 AuthMiddleware 层豁免，否则无 Bearer 会 401 并误触发前端「登录已过期」。"""
        view = super().as_view(actions=actions, **initkwargs)
        if actions and "prepare" in actions.values():
            return csrf_exempt(login_exempt(view))
        return view

    def initialize_request(self, request, *args, **kwargs):
        # 必须在 get_authenticators 之前写入 action，prepare 才能匿名访问
        method = request.method.lower()
        self.action = self.action_map.get(method)
        return super().initialize_request(request, *args, **kwargs)

    def get_throttles(self):
        action = getattr(self, "action", None)
        if action == "prepare":
            return [DashboardSharePrepareThrottle()]
        if action == "exchange":
            return [DashboardShareExchangeUserThrottle()]
        return [DashboardShareAccessUserThrottle()]

    def get_permissions(self):
        if getattr(self, "action", None) == "prepare":
            return [AllowAny()]
        return [IsAuthenticated()]

    def get_authenticators(self):
        if getattr(self, "action", None) == "prepare":
            return []
        return super().get_authenticators()

    @action(detail=False, methods=["post"], url_path="prepare")
    def prepare(self, request):
        serializer = SharePrepareSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            state, nonce = prepare_share_exchange(token=serializer.validated_data["token"])
        except ShareLinkInvalid:
            # 不区分无效 token，仍返回假 state 会浪费；统一 404 且记审计
            log_share_access(request, action="prepare", result="reject", reason="invalid_token")
            invalid_throttle = DashboardShareInvalidTokenThrottle()
            if not invalid_throttle.allow_request(request, self):
                return Response({"detail": "请求过于频繁"}, status=status.HTTP_429_TOO_MANY_REQUESTS)
            return Response(INVALID_SHARE_RESPONSE, status=status.HTTP_404_NOT_FOUND)
        log_share_access(request, action="prepare", result="ok")
        response = Response({"state": state})
        response.set_cookie(
            SHARE_PREPARE_COOKIE,
            nonce,
            max_age=SHARE_PREPARE_TTL,
            httponly=True,
            samesite="Lax",
            path="/",
        )
        return response

    @action(detail=False, methods=["post"], url_path="exchange")
    def exchange(self, request):
        serializer = ShareExchangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            session = exchange_share(
                token=serializer.validated_data.get("token"),
                state=serializer.validated_data.get("state"),
                prepare_nonce=request.COOKIES.get(SHARE_PREPARE_COOKIE),
                visitor=request.user,
            )
        except ShareRateLimited:
            log_share_access(request, action="exchange", result="reject", reason="rate_limited")
            return Response({"detail": "请求过于频繁"}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        except ShareLinkInvalid as exc:
            log_share_access(
                request,
                action="exchange",
                result="reject",
                reason=getattr(exc, "reason", "invalid"),
            )
            invalid_throttle = DashboardShareInvalidTokenThrottle()
            if not invalid_throttle.allow_request(request, self):
                return Response({"detail": "请求过于频繁"}, status=status.HTTP_429_TOO_MANY_REQUESTS)
            return Response(INVALID_SHARE_RESPONSE, status=status.HTTP_404_NOT_FOUND)

        log_share_access(
            request,
            action="exchange",
            link=session.share_link,
            visitor=request.user,
            result="ok",
        )
        response = Response(
            {
                "session_id": str(session.session_id),
                "expires_at": session.expires_at,
            }
        )
        response.delete_cookie(SHARE_PREPARE_COOKIE, path="/")
        return response

    @action(detail=False, methods=["get"], url_path=r"session/(?P<session_id>[^/.]+)")
    def session_detail(self, request, session_id=None):
        try:
            principal = resolve_session(session_id=session_id, visitor=request.user)
        except ShareRateLimited:
            log_share_access(request, action="open", result="reject", reason="rate_limited")
            return Response({"detail": "请求过于频繁"}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        except ShareLinkInvalid:
            log_share_access(request, action="open", result="reject", reason="invalid")
            return Response(INVALID_SHARE_RESPONSE, status=status.HTTP_404_NOT_FOUND)

        log_share_access(request, action="open", principal=principal, visitor=request.user, result="ok")
        return Response(_serialize_shared_resource(principal))

    @action(
        detail=False,
        methods=["post"],
        url_path=r"session/(?P<session_id>[^/.]+)/query/(?P<data_source_id>\d+)",
    )
    def query(self, request, session_id=None, data_source_id=None):
        try:
            principal = resolve_session(session_id=session_id, visitor=request.user)
        except ShareRateLimited:
            log_share_access(request, action="query", result="reject", reason="rate_limited")
            return Response({"detail": "请求过于频繁"}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        except ShareLinkInvalid:
            log_share_access(request, action="query", result="reject", reason="invalid")
            return Response(INVALID_SHARE_RESPONSE, status=status.HTTP_404_NOT_FOUND)

        if principal.resource_type not in SHARE_DATASOURCE_RESOURCE_TYPES:
            log_share_access(
                request,
                action="query",
                principal=principal,
                visitor=request.user,
                result="reject",
                reason="resource_type_not_queryable",
            )
            return Response({"detail": "当前画布不支持数据源查询"}, status=status.HTTP_403_FORBIDDEN)

        if int(data_source_id) not in _canvas_data_source_ids(principal.resource):
            log_share_access(
                request,
                action="query",
                principal=principal,
                visitor=request.user,
                result="reject",
                reason="datasource_not_declared",
            )
            return Response({"detail": "无权访问当前数据源"}, status=status.HTTP_403_FORBIDDEN)

        try:
            safe_params = filter_share_query_params(
                dashboard=principal.resource,
                data_source_id=int(data_source_id),
                request_data=dict(request.data),
            )
        except ShareQueryParamsDenied as exc:
            log_share_access(
                request,
                action="query",
                principal=principal,
                visitor=request.user,
                result="reject",
                reason="undeclared_params",
            )
            return Response({"detail": str(exc) or "存在未声明参数"}, status=status.HTTP_400_BAD_REQUEST)

        factory = APIRequestFactory()
        delegated_request = factory.post("/", safe_params, format="json")
        delegated_request.COOKIES["current_team"] = str(principal.space_id)
        force_authenticate(delegated_request, user=_delegated_sharer_user(principal.user))
        view = DataSourceAPIModelViewSet.as_view({"post": "get_source_data"})
        response = view(delegated_request, pk=data_source_id)
        log_share_access(
            request,
            action="query",
            principal=principal,
            visitor=request.user,
            result="ok" if getattr(response, "status_code", 500) < 400 else "reject",
        )
        return response

    @action(
        detail=False,
        methods=["get"],
        url_path=r"session/(?P<session_id>[^/.]+)/data_sources",
    )
    def data_sources(self, request, session_id=None):
        try:
            principal = resolve_session(session_id=session_id, visitor=request.user)
        except ShareRateLimited:
            return Response({"detail": "请求过于频繁"}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        except ShareLinkInvalid:
            log_share_access(request, action="data_sources", result="reject", reason="invalid")
            return Response(INVALID_SHARE_RESPONSE, status=status.HTTP_404_NOT_FOUND)

        if principal.resource_type not in SHARE_DATASOURCE_RESOURCE_TYPES:
            return Response([])

        allowed_ids = _canvas_data_source_ids(principal.resource)
        data_sources = [
            item
            for item in DataSourceAPIModel.objects.filter(id__in=allowed_ids).prefetch_related("namespaces", "tag")
            if can_access_datasource_in_org(item, principal.space_id)
        ]
        log_share_access(
            request,
            action="data_sources",
            principal=principal,
            visitor=request.user,
            result="ok",
        )
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

    def _application3d_operation(self, request, session_id, *, action_name: str, view_action: str):
        try:
            principal = resolve_session(session_id=session_id, visitor=request.user)
        except ShareRateLimited:
            log_share_access(request, action=action_name, result="reject", reason="rate_limited")
            return Response({"detail": "请求过于频繁"}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        except ShareLinkInvalid:
            log_share_access(request, action=action_name, result="reject", reason="invalid")
            return Response(INVALID_SHARE_RESPONSE, status=status.HTTP_404_NOT_FOUND)

        if principal.resource_type != "screen" or not _view_sets_has_scene_widget(
            getattr(principal.resource, "view_sets", None),
            "application3D",
        ):
            log_share_access(
                request,
                action=action_name,
                principal=principal,
                visitor=request.user,
                result="reject",
                reason="application3d_not_declared",
            )
            return Response({"detail": "分享大屏未声明 3D 应用组件"}, status=status.HTTP_403_FORBIDDEN)

        factory = APIRequestFactory()
        delegated_request = factory.post("/", request.data or {}, format="json")
        delegated_request.COOKIES["current_team"] = str(principal.space_id)
        delegated_request.COOKIES["include_children"] = "0"
        force_authenticate(delegated_request, user=_delegated_sharer_user(principal.user))

        from apps.operation_analysis.views.scene_widget_view import SceneWidgetViewSet

        response = SceneWidgetViewSet.as_view({"post": view_action})(delegated_request)
        log_share_access(
            request,
            action=action_name,
            principal=principal,
            visitor=request.user,
            result="ok" if getattr(response, "status_code", 500) < 400 else "reject",
        )
        return response

    @action(
        detail=False,
        methods=["post"],
        url_path=r"session/(?P<session_id>[^/.]+)/application3d/wall",
    )
    def application3d_wall(self, request, session_id=None):
        return self._application3d_operation(
            request,
            session_id,
            action_name="application3d_wall",
            view_action="application3d_wall",
        )

    @action(
        detail=False,
        methods=["post"],
        url_path=r"session/(?P<session_id>[^/.]+)/application3d/application_detail",
    )
    def application3d_application_detail(self, request, session_id=None):
        return self._application3d_operation(
            request,
            session_id,
            action_name="application3d_application_detail",
            view_action="application3d_application_detail",
        )

    @action(
        detail=False,
        methods=["post"],
        url_path=r"session/(?P<session_id>[^/.]+)/application3d/alarm_detail",
    )
    def application3d_alarm_detail(self, request, session_id=None):
        return self._application3d_operation(
            request,
            session_id,
            action_name="application3d_alarm_detail",
            view_action="application3d_alarm_detail",
        )

    @action(
        detail=False,
        methods=["post"],
        url_path=r"session/(?P<session_id>[^/.]+)/application3d/metric",
    )
    def application3d_metric(self, request, session_id=None):
        return self._application3d_operation(
            request,
            session_id,
            action_name="application3d_metric",
            view_action="application3d_metric",
        )

    def _resolve_network_topology_principal(self, request, session_id, *, action_name: str):
        try:
            principal = resolve_session(session_id=session_id, visitor=request.user)
        except ShareRateLimited:
            log_share_access(request, action=action_name, result="reject", reason="rate_limited")
            return None, Response({"detail": "请求过于频繁"}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        except ShareLinkInvalid:
            log_share_access(request, action=action_name, result="reject", reason="invalid")
            return None, Response(INVALID_SHARE_RESPONSE, status=status.HTTP_404_NOT_FOUND)

        if principal.resource_type != "networkTopology":
            log_share_access(
                request,
                action=action_name,
                principal=principal,
                visitor=request.user,
                result="reject",
                reason="resource_type_mismatch",
            )
            return None, Response(
                {"detail": "当前分享会话不是网络拓扑"},
                status=status.HTTP_403_FORBIDDEN,
            )
        return principal, None

    @action(
        detail=False,
        methods=["post"],
        url_path=r"session/(?P<session_id>[^/.]+)/network_topology/metric_values",
    )
    def network_topology_metric_values(self, request, session_id=None):
        principal, error = self._resolve_network_topology_principal(request, session_id, action_name="nt_metric_values")
        if error is not None:
            return error

        try:
            reject_forbidden_topology_body_keys(request.data)
            serializer = ShareNetworkTopologyMetricValuesSerializer(data=request.data or {})
            serializer.is_valid(raise_exception=True)
            items = validate_share_metric_values(
                view_sets=getattr(principal.resource, "view_sets", None),
                items=serializer.validated_data.get("items") or [],
            )
            from apps.operation_analysis.views.network_topology_view import NetworkTopologyViewSet, _adapter_for

            adapter = _adapter_for(principal.resource)
            payload = adapter.batch_metric_values(items)
        except ShareNetworkTopologyRuntimeDenied as exc:
            log_share_access(
                request,
                action="nt_metric_values",
                principal=principal,
                visitor=request.user,
                result="reject",
                reason="not_in_view_sets",
            )
            return Response({"detail": str(exc.detail)}, status=status.HTTP_403_FORBIDDEN)
        except WeOpsTopologyAdapterError as exc:
            log_share_access(
                request,
                action="nt_metric_values",
                principal=principal,
                visitor=request.user,
                result="reject",
                reason=getattr(exc, "code", "weops_error"),
            )
            from apps.operation_analysis.views.network_topology_view import NetworkTopologyViewSet

            return NetworkTopologyViewSet._adapter_error_response(exc)

        log_share_access(
            request,
            action="nt_metric_values",
            principal=principal,
            visitor=request.user,
            result="ok",
        )
        return Response(payload)

    @action(
        detail=False,
        methods=["post"],
        url_path=r"session/(?P<session_id>[^/.]+)/network_topology/link_runtime",
    )
    def network_topology_link_runtime(self, request, session_id=None):
        principal, error = self._resolve_network_topology_principal(request, session_id, action_name="nt_link_runtime")
        if error is not None:
            return error

        try:
            reject_forbidden_topology_body_keys(request.data)
            serializer = ShareNetworkTopologyLinkRuntimeSerializer(data=request.data or {})
            serializer.is_valid(raise_exception=True)
            link_payload, nodes_payload = validate_share_link_runtime(
                view_sets=getattr(principal.resource, "view_sets", None),
                link_payload=serializer.validated_data.get("link"),
                nodes_payload=serializer.validated_data.get("nodes"),
            )
            from apps.operation_analysis.views.network_topology_view import NetworkTopologyViewSet, _adapter_for

            adapter = _adapter_for(principal.resource)
            response = NetworkTopologyRuntimeService.build_link_runtime_preview(
                principal.resource,
                adapter,
                link_payload,
                nodes_payload=nodes_payload,
            )
        except ShareNetworkTopologyRuntimeDenied as exc:
            log_share_access(
                request,
                action="nt_link_runtime",
                principal=principal,
                visitor=request.user,
                result="reject",
                reason="not_in_view_sets",
            )
            return Response({"detail": str(exc.detail)}, status=status.HTTP_403_FORBIDDEN)
        except WeOpsTopologyAdapterError as exc:
            log_share_access(
                request,
                action="nt_link_runtime",
                principal=principal,
                visitor=request.user,
                result="reject",
                reason=getattr(exc, "code", "weops_error"),
            )
            from apps.operation_analysis.views.network_topology_view import NetworkTopologyViewSet

            return NetworkTopologyViewSet._adapter_error_response(exc)

        data = response.get("data", response) if isinstance(response, dict) else response
        log_share_access(
            request,
            action="nt_link_runtime",
            principal=principal,
            visitor=request.user,
            result="ok",
        )
        return Response(data)
