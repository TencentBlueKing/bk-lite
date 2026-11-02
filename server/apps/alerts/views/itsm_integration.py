from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.alerts.itsm.config import ItsmError
from apps.alerts.itsm.integration import public_config, save_configuration, test_configuration
from apps.alerts.models.itsm import AlertItsmIntegration
from apps.alerts.utils.permission_scope import get_authorized_group_ids, get_current_team_from_request
from apps.core.decorators.api_permission import HasPermission


def current_team(request):
    team = get_current_team_from_request(request, required=True)
    if not team or team not in get_authorized_group_ids(request):
        raise PermissionDenied("请先选择有权访问的团队")
    return team


class ItsmIntegrationViewSet(viewsets.ViewSet):
    @HasPermission("global_config-View")
    def list(self, request):
        return Response(public_config(AlertItsmIntegration.objects.filter(team_id=current_team(request)).first()))

    @action(detail=False, methods=["put"])
    @HasPermission("global_config-Edit")
    def configure(self, request):
        return Response(public_config(save_configuration(current_team(request), request.data, request.user.username)))

    @action(detail=False, methods=["post"])
    @HasPermission("global_config-Edit")
    def test_connection(self, request):
        try:
            test_configuration(current_team(request), request.data)
        except ItsmError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"connected": True, "message": "连接和认证成功；未创建工单，流程可用性需单独验证"})

    @action(detail=False, methods=["get"])
    @HasPermission("action_rule-Edit")
    def services(self, request):
        instance = AlertItsmIntegration.objects.filter(team_id=current_team(request), enabled=True).first()
        if instance is None:
            return Response({"detail": "请先启用 ITSM 连接"}, status=400)
        from apps.alerts.itsm.client import ItsmClient

        try:
            services = ItsmClient(instance.connection_config()).services()
        except ItsmError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response([{"value": item["workflow_key"], "label": item["label"]} for item in services])

    @action(detail=False, methods=["get"])
    @HasPermission("action_rule-Edit")
    def form_fields(self, request):
        workflow_key = str(request.query_params.get("workflow_key") or "").strip()
        if not workflow_key:
            return Response({"detail": "请填写流程标识"}, status=400)
        instance = AlertItsmIntegration.objects.filter(team_id=current_team(request), enabled=True).first()
        if instance is None:
            return Response({"detail": "请先启用 ITSM 连接"}, status=400)
        from apps.alerts.itsm.client import ItsmClient

        try:
            fields = ItsmClient(instance.connection_config()).form_fields(workflow_key)
        except ItsmError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(fields)
