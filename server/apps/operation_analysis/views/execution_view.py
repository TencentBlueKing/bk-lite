from django.views.decorators.csrf import csrf_exempt
from rest_framework import mixins, status, viewsets
from rest_framework.authentication import BaseAuthentication
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.open_base import login_exempt
from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
)
from apps.operation_analysis.serializers.execution_serializers import (
    DashboardReportExecutionSerializer,
    DashboardReportExecutionSnapshotSerializer,
    DashboardReportRenderSnapshotSerializer,
)
from apps.operation_analysis.services.render_token_service import (
    DashboardReportRenderTokenError,
    DashboardReportRenderTokenService,
)
from apps.operation_analysis.services.render_scope_service import (
    DashboardReportRenderScopeError,
    DashboardReportRenderScopeService,
)


class DashboardReportRenderPrincipalAuthentication(BaseAuthentication):
    """把 middleware 已验证的 scoped principal 交给 DRF，不建立 Session。"""

    def authenticate(self, request):
        raw_request = request._request
        claims = getattr(
            raw_request, "dashboard_report_render_scope", None
        )
        user = getattr(raw_request, "user", None)
        if claims is None or user is None or not user.is_authenticated:
            return None
        return user, claims


class DashboardReportExecutionViewSet(
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = DashboardReportExecutionSerializer
    http_method_names = ["get", "post", "head", "options"]

    @classmethod
    def as_view(cls, actions=None, **initkwargs):
        view = super().as_view(actions=actions, **initkwargs)
        if actions and "render_token_exchange" in actions.values():
            return csrf_exempt(login_exempt(view))
        return view

    def initialize_request(self, request, *args, **kwargs):
        self.action = self.action_map.get(request.method.lower())
        return super().initialize_request(request, *args, **kwargs)

    def get_permissions(self):
        if getattr(self, "action", None) == "render_token_exchange":
            return [AllowAny()]
        return super().get_permissions()

    def get_authenticators(self):
        if getattr(self, "action", None) == "render_token_exchange":
            return []
        return [
            DashboardReportRenderPrincipalAuthentication(),
            *super().get_authenticators(),
        ]

    def get_queryset(self):
        queryset = DashboardReportExecution.objects.select_related(
            "subscription",
            "dashboard",
            "snapshot",
            "render_snapshot",
            "pdf_artifact",
        )
        if not getattr(self.request.user, "is_superuser", False):
            queryset = queryset.filter(
                creator=self.request.user.username,
                creator_domain=self.request.user.domain,
            )
        return queryset

    @HasPermission("view-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("view-View")
    @action(
        detail=True,
        methods=["get"],
        url_path="render-input",
    )
    def render_input(self, request, *args, **kwargs):
        execution = self.get_object()
        token_header = request.META.get("HTTP_AUTHORIZATION", "")
        raw_token = (
            token_header[7:].strip()
            if token_header.startswith("Bearer ")
            else ""
        )
        try:
            DashboardReportRenderScopeService.authorize_request(
                request,
                raw_token,
            )
        except DashboardReportRenderScopeError as exc:
            raise PermissionDenied("仅 Render Session 可读取渲染输入") from exc
        if (
            execution.creator != request.user.username
            or execution.creator_domain != request.user.domain
        ):
            raise PermissionDenied("只能读取自己的报告渲染输入")
        if execution.status != DashboardReportExecution.Status.RUNNING:
            raise ValidationError(
                {"status": "仅 running Execution 可读取渲染输入"}
            )
        try:
            input_snapshot = execution.snapshot
            render_snapshot = execution.render_snapshot
        except (
            DashboardReportExecution.snapshot.RelatedObjectDoesNotExist,
            DashboardReportExecution.render_snapshot.RelatedObjectDoesNotExist,
        ) as exc:
            raise ValidationError(
                {"snapshot": "Execution 渲染快照不完整"}
            ) from exc

        return Response(
            {
                "execution_id": execution.id,
                "input_snapshot": (
                    DashboardReportExecutionSnapshotSerializer(
                        input_snapshot
                    ).data
                ),
                "render_snapshot": (
                    DashboardReportRenderSnapshotSerializer(
                        render_snapshot
                    ).data
                ),
            }
        )

    @action(
        detail=True,
        methods=["post"],
        url_path="render-token-exchange",
    )
    def render_token_exchange(self, request, *args, **kwargs):
        plaintext = request.data.get("token")
        if not isinstance(plaintext, str) or not plaintext:
            return Response(
                {"detail": "Render Token 无效或已失效"},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            session_user = DashboardReportRenderTokenService.consume(
                execution_id=int(kwargs["pk"]),
                plaintext=plaintext,
            )
        except (DashboardReportRenderTokenError, ValueError):
            return Response(
                {"detail": "Render Token 无效或已失效"},
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response({"session_user": session_user})
