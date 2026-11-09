import hashlib

from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.alerts.itsm.config import ItsmError, connections, get_connection, validate_connection
from apps.alerts.itsm.reconcile import reconcile
from apps.alerts.itsm.service import _teams, authorized_rule
from apps.alerts.models.action import ActionExecution
from apps.alerts.models.itsm import AlertItsmTicket
from apps.alerts.models.models import Alert
from apps.alerts.utils.permission_scope import apply_team_scope_for_request, get_authorized_group_ids
from apps.core.decorators.api_permission import HasPermission


def error_response(error):
    return Response({"detail": str(error)}, status={"forbidden": 403, "conflict": 409, "failed": 502}.get(error.outcome, 400))


def has_permission(request, permission):
    return getattr(request.user, "is_superuser", False) or permission in HasPermission()._get_user_permissions(request, "alerts")


class ReconcileInput(serializers.Serializer):
    alert_id = serializers.CharField(max_length=100)
    execution_id = serializers.IntegerField(min_value=1)
    ticket_id = serializers.CharField(max_length=128)
    evidence = serializers.CharField(max_length=500, required=False, default="")
    confirm = serializers.BooleanField(default=False)

    def validate(self, attrs):
        if attrs["confirm"] and not attrs["evidence"].strip():
            raise serializers.ValidationError("请填写核查依据，确认工单属于该告警")
        return attrs


class ItsmExecutionMixin:
    @action(detail=False, methods=["get"])
    @HasPermission("Alarms-View")
    def itsm_ticket(self, request):
        alert = apply_team_scope_for_request(Alert.objects.all(), request).filter(alert_id=request.query_params.get("alert_id")).first()
        if not alert:
            return Response({"detail": "告警不存在或无权访问"}, status=404)
        link = AlertItsmTicket.objects.select_related("current_execution", "rule").filter(alert=alert).first()
        if not link:
            failed_input = ActionExecution.objects.filter(alert=alert, idempotency_key=f"itsm-evaluation:{alert.pk}").first()
            if failed_input:
                return Response(
                    {
                        "execution_id": failed_input.pk,
                        "execution_status": failed_input.status,
                        "message": failed_input.result.get("message", ""),
                        "ticket_id": None,
                        "notification": failed_input.result.get("notification", ""),
                        "allowed_actions": [],
                    }
                )
            return Response(None)
        if not _teams(link.team, get_authorized_group_ids(request)):
            return Response({"detail": "无权访问工单关联"}, status=403)
        execution = link.current_execution
        authorized = authorized_rule(link, alert, link.rule, get_authorized_group_ids(request))
        try:
            get_connection((link.rule.action_config or {}).get("connection") if link.rule else link.connection, link.team)
        except ItsmError:
            authorized = False
        allowed = []
        if authorized and has_permission(request, "action_exec-Manual") and execution:
            if execution.status in {"failed", "config_error"} and not link.ticket_id:
                allowed.append("retry")
            if execution.status == "unknown" and has_permission(request, "action_rule-Edit"):
                allowed.append("reconcile")
            if link.comment_error and has_permission(request, "action_exec-Manual"):
                allowed.append("recomment")
        return Response(
            {
                "rule_id": link.rule_id,
                "rule_name": link.rule_name,
                "workflow_key": (link.rule.action_config if link.rule else {}).get("workflow_key", ""),
                "execution_id": link.current_execution_id,
                "execution_status": execution.status if execution else None,
                "message": execution.result.get("message", "") if execution else "",
                "notification": execution.result.get("notification", "") if execution else "",
                "ticket_id": link.ticket_id,
                "ticket_number": link.ticket_number,
                "ticket_title": link.ticket_title,
                "ticket_status": link.ticket_status,
                "status_label": link.status_label,
                "last_synced_at": link.last_synced_at,
                "sync_error": link.sync_error,
                "is_closed": link.is_closed,
                "comment_error": link.comment_error,
                "close_result": link.close_result,
                "close_error": link.close_error,
                "allowed_actions": allowed,
            }
        )

    @action(detail=False, methods=["post"])
    @HasPermission("action_exec-Manual")
    @HasPermission("action_rule-Edit")
    def itsm_retry_close(self, request):
        return Response({"detail": "工单结束不再关闭告警"}, status=409)

    @action(detail=False, methods=["post"])
    @HasPermission("action_exec-Manual")
    def itsm_recomment(self, request):
        client_key = request.headers.get("Idempotency-Key", "").strip()
        if not client_key or len(client_key) > 128:
            return Response({"detail": "Idempotency-Key 必填，最多 128 字符"}, status=400)
        alert = apply_team_scope_for_request(Alert.objects.all(), request).filter(alert_id=request.data.get("alert_id")).first()
        if not alert:
            return Response({"detail": "告警不存在或无权访问"}, status=404)
        link = AlertItsmTicket.objects.filter(alert=alert).first()
        if not link or not link.comment_error or not link.comment_event:
            return Response({"detail": "当前没有需要重发的留言"}, status=409)
        if not _teams(link.team, get_authorized_group_ids(request)):
            return Response({"detail": "无权访问工单关联"}, status=403)
        from apps.alerts.itsm.comments import enqueue_comment

        if enqueue_comment(alert, link.comment_event, retry_key=hashlib.sha256(client_key.encode()).hexdigest()) is None:
            return Response({"detail": "当前没有需要重发的留言"}, status=409)
        return Response({"accepted": True}, status=202)

    @action(detail=False, methods=["post"])
    @HasPermission("action_exec-Manual")
    @HasPermission("action_rule-Edit")
    def itsm_reconcile(self, request):
        data = ReconcileInput(data=request.data)
        data.is_valid(raise_exception=True)
        fields = data.validated_data
        alert = apply_team_scope_for_request(Alert.objects.all(), request).filter(alert_id=fields["alert_id"]).first()
        if not alert:
            return Response({"detail": "告警不存在或无权访问"}, status=404)
        try:
            result = reconcile(
                alert.pk,
                fields["execution_id"],
                fields["ticket_id"],
                fields["evidence"],
                fields["confirm"],
                request.user.username,
                get_authorized_group_ids(request),
            )
        except ItsmError as exc:
            return error_response(exc)
        return Response(result)


class ItsmRuleMixin:
    @action(detail=False, methods=["get"])
    @HasPermission("action_rule-View")
    def itsm_connections(self, request):
        teams = get_authorized_group_ids(request)
        result = []
        try:
            for reference, value in connections(teams).items():
                shared = set(map(str, teams)) & set(map(str, value.get("teams", [])))
                if not shared:
                    continue
                try:
                    validate_connection(value, shared)
                except ItsmError:
                    continue
                result.append({"value": reference, "label": value.get("name", reference)})
        except ItsmError as exc:
            return error_response(exc)
        return Response(result)
