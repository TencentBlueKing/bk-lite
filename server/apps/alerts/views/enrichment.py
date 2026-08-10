# -- coding: utf-8 --
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction

from apps.alerts.constants.constants import LogAction, LogTargetType
from apps.alerts.filters import EnrichmentRuleModelFilter
from apps.alerts.serializers import EnrichmentRuleModelSerializer
from apps.alerts.models.enrichment import EnrichmentRule
from apps.alerts.models.models import Alert
from apps.alerts.utils.operator_log import record_operator_log
from apps.alerts.utils.permission_scope import apply_team_scope_for_request
from apps.alerts.utils.permission_scope import get_current_team_from_request
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
        return apply_team_scope_for_request(super().get_queryset(), self.request)

    @HasPermission("alert_enrichment-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("alert_enrichment-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("alert_enrichment-Add")
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if "team" in serializer.validated_data:
            self.perform_create(serializer)
        else:
            current_team = get_current_team_from_request(request, required=True)
            if not current_team:
                from rest_framework.exceptions import ValidationError

                raise ValidationError({"team": "缺少当前团队"})
            serializer.save(team=[current_team])
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
        return super().partial_update(request, *args, **kwargs)

    @HasPermission("alert_enrichment-Delete")
    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
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
        rules = self.get_queryset()
        total_rules = rules.count()
        active_rules = rules.filter(is_active=True).count()
        # 用户自建 = 非内置预设（内置规则名以"内置-"开头）
        user_created_rules = rules.exclude(name__startswith="内置-").count()

        alerts = apply_team_scope_for_request(Alert.objects.all(), request)
        total_alerts = alerts.count()
        enriched_alerts = alerts.exclude(enrichment={}).count()
        enriched_alert_ratio = round(enriched_alerts / total_alerts, 4) if total_alerts else 0.0

        return Response({
            "total_rules": total_rules,
            "active_rules": active_rules,
            "active_rule_ratio": round(active_rules / total_rules, 4) if total_rules else 0.0,
            "user_created_rules": user_created_rules,
            "total_alerts": total_alerts,
            "enriched_alerts": enriched_alerts,
            "enriched_alert_ratio": enriched_alert_ratio,
        })
