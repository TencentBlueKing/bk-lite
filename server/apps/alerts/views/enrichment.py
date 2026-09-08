# -- coding: utf-8 --
from django.db import transaction
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.alerts.constants.constants import LogAction, LogTargetType
from apps.alerts.filters import EnrichmentRuleModelFilter
from apps.alerts.models.enrichment import EnrichmentRule
from apps.alerts.models.models import Alert
from apps.alerts.serializers import EnrichmentRuleModelSerializer
from apps.alerts.utils.operator_log import record_operator_log
from apps.alerts.utils.permission_scope import apply_team_scope_for_request, get_current_team_from_request
from apps.core.decorators.api_permission import HasPermission
from config.drf.pagination import CustomPageNumberPagination
from config.drf.viewsets import ModelViewSet


class EnrichmentRuleModelViewSet(ModelViewSet):
    """告警丰富规则视图集。"""

    queryset = EnrichmentRule.objects.all()
    serializer_class = EnrichmentRuleModelSerializer
    ordering_fields = ["created_at"]
    ordering = ["-created_at"]
    filterset_class = EnrichmentRuleModelFilter
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        scoped = apply_team_scope_for_request(super().get_queryset(), self.request)
        global_presets = super().get_queryset().filter(preset_key__gt="", team=[]).distinct()
        return (scoped | global_presets).distinct()

    @staticmethod
    def _ensure_mutable(instance, request):
        if instance.is_builtin and not getattr(request.user, "is_superuser", False):
            raise ValidationError({"detail": "只有超级管理员可以修改全局内置规则"})

    @HasPermission("alert_enrichment-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("alert_enrichment-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("alert_enrichment-Add")
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        payload = request.data.copy()
        if "team" not in payload:
            current_team = get_current_team_from_request(request, required=True)
            if not current_team:
                raise ValidationError({"team": "缺少当前团队"})
            payload["team"] = [current_team]
        serializer = self.get_serializer(data=payload)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        log_data = {
            "action": LogAction.ADD,
            "target_type": LogTargetType.SYSTEM,
            "operator": request.user.username,
            "operator_object": "告警丰富规则-创建",
            "target_id": serializer.data["id"],
            "overview": f"创建告警丰富规则[{serializer.data['name']}]",
        }
        record_operator_log(**log_data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @HasPermission("alert_enrichment-Edit")
    @transaction.atomic
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        self._ensure_mutable(instance, request)
        log_data = {
            "action": LogAction.MODIFY,
            "target_type": LogTargetType.SYSTEM,
            "operator": request.user.username,
            "operator_object": "告警丰富规则-修改",
            "target_id": instance.id,
            "overview": f"修改告警丰富规则[{instance.name}]",
        }
        record_operator_log(**log_data)
        return super().update(request, *args, **kwargs)

    @HasPermission("alert_enrichment-Edit")
    @transaction.atomic
    def partial_update(self, request, *args, **kwargs):
        self._ensure_mutable(self.get_object(), request)
        return super().partial_update(request, *args, **kwargs)

    @HasPermission("alert_enrichment-Delete")
    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self._ensure_mutable(instance, request)
        log_data = {
            "action": LogAction.DELETE,
            "target_type": LogTargetType.SYSTEM,
            "operator": request.user.username,
            "operator_object": "告警丰富规则-删除",
            "target_id": instance.id,
            "overview": f"删除告警丰富规则[{instance.name}]",
        }
        record_operator_log(**log_data)
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["get"])
    @HasPermission("alert_enrichment-View")
    def metrics(self, request, *args, **kwargs):
        from apps.alerts.enrichment.telemetry import read_runtime_metrics

        rules = self.get_queryset()
        total_rules = rules.count()
        active_rules = rules.filter(is_active=True).count()
        user_created_rules = rules.filter(preset_key="").count()

        alerts = apply_team_scope_for_request(Alert.objects.all(), request)
        total_alerts = alerts.count()
        enriched_alerts = alerts.exclude(enrichment={}).count()
        enriched_alert_ratio = round(enriched_alerts / total_alerts, 4) if total_alerts else 0.0

        return Response(
            {
                "total_rules": total_rules,
                "active_rules": active_rules,
                "active_rule_ratio": round(active_rules / total_rules, 4) if total_rules else 0.0,
                "user_created_rules": user_created_rules,
                "total_alerts": total_alerts,
                "enriched_alerts": enriched_alerts,
                "enriched_alert_ratio": enriched_alert_ratio,
                "runtime": read_runtime_metrics(),
            }
        )
