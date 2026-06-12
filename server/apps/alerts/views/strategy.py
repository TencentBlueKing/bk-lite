from rest_framework import viewsets, status
from rest_framework.response import Response
from django.db import transaction

from apps.alerts.constants.constants import LogAction, LogTargetType
from apps.alerts.filters import AlarmStrategyModelFilter
from apps.alerts.models.alert_operator import AlarmStrategy
from apps.alerts.models.operator_log import OperatorLog
from apps.alerts.serializers import AlarmStrategySerializer
from apps.alerts.utils.permission_scope import apply_team_scope_for_request
from apps.core.decorators.api_permission import HasPermission
from config.drf.pagination import CustomPageNumberPagination
from apps.core.logger import alert_logger as logger


class AlarmStrategyModelViewSet(viewsets.ModelViewSet):
    """告警策略"""

    queryset = AlarmStrategy.objects.all()
    serializer_class = AlarmStrategySerializer
    filterset_class = AlarmStrategyModelFilter
    ordering_fields = ["created_at"]
    ordering = ["-created_at"]
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        queryset = AlarmStrategy.objects.all()
        request = getattr(self, "request", None)
        if request is None:
            return queryset

        user = getattr(request, "user", None)
        if getattr(user, "is_superuser", False):
            return queryset

        return apply_team_scope_for_request(queryset, request, field_name="team")

    @HasPermission("correlation_rules-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("correlation_rules-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("correlation_rules-Add")
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """
                {
            "name": "测试规则", //策略名称
            "strategy_type": "smart_denoise", //智能降噪  missing_detection 缺失检测
            "description": "描述",
            "team": [
                1
            ], //组织
            "dispatch_team": [
                1
            ], //分派组织
            "match_rules": [
                [
                    {
                        "key": "title",
                        "value": "1",
                        "operator": "eq"
                    },
                    {
                        "key": "description",
                        "operator": "re",
                        "value": "2"
                    }
                ],
                [
                    {
                        "key": "level_id",
                        "value": 2,
                        "operator": "eq"
                    }
                ]
            ], //匹配规则
            "params": {
                "group_by": [
                    "service"
                ], //策略，service应用，location基础设施,resource_name实例,[""]其他
                "window_size": 10, //窗口
                "time_out": true, //自愈检查
                "time_minutes": 10 //观察时间
            },
            "auto_close": true, //是否自动关闭告警
            "close_minutes": 120 //自动关闭时间
        }
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        log_data = {
            "action": LogAction.ADD,
            "target_type": LogTargetType.SYSTEM,
            "operator": request.user.username,
            "operator_object": "告警策略-新增",
            "target_id": serializer.data["id"],
            "overview": f"创建告警策略: 策略名称:{serializer.data['name']}",
        }
        OperatorLog.objects.create(**log_data)
        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )

    @HasPermission("correlation_rules-Edit")
    @transaction.atomic
    def update(self, request, *args, **kwargs):
        return self._update_strategy(request, *args, **kwargs)

    @HasPermission("correlation_rules-Edit")
    @transaction.atomic
    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self._update_strategy(request, *args, **kwargs)

    def _update_strategy(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()

        old_params = instance.params or {}
        old_time_out = old_params.get("time_out", False)
        old_time_minutes = old_params.get("time_minutes", 0)

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        if getattr(instance, "_prefetched_objects_cache", None):
            instance._prefetched_objects_cache = {}

        new_params = instance.params or {}
        new_time_out = new_params.get("time_out", False)
        new_time_minutes = new_params.get("time_minutes", 0)

        session_disabled = (
            old_time_out
            and old_time_minutes > 0
            and (not new_time_out or new_time_minutes == 0)
        )

        if session_disabled:
            from apps.alerts.aggregation.recovery.timeout_checker import TimeoutChecker

            confirmed_count = TimeoutChecker.confirm_observing_alerts_by_strategy(
                instance.id
            )
            logger.info(
                "[AlertView] 策略修改关闭会话窗口: strategy_id=%s, 策略名=%s, 确认观察中告警数=%s",
                instance.id, instance.name, confirmed_count,
            )

        log_data = {
            "action": LogAction.MODIFY,
            "target_type": LogTargetType.SYSTEM,
            "operator": request.user.username,
            "operator_object": "告警策略-修改",
            "target_id": instance.id,
            "overview": f"修改告警策略: 策略名称:{instance.name}",
        }
        OperatorLog.objects.create(**log_data)

        return Response(serializer.data)

    @HasPermission("correlation_rules-Delete")
    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance_id = instance.id
        rule_name = instance.name

        params = instance.params or {}
        is_session_strategy = (
            params.get("time_out", False) and params.get("time_minutes", 0) > 0
        )

        if is_session_strategy:
            from apps.alerts.aggregation.recovery.timeout_checker import (
                TimeoutChecker,
            )

            closed_count = TimeoutChecker.close_observing_session_alerts_by_strategy(
                instance_id
            )
            logger.info(
                "[AlertView] 删除会话策略关闭观察中告警: strategy_id=%s, 策略名=%s, 关闭告警数=%s",
                instance_id, rule_name, closed_count,
            )

        self.perform_destroy(instance)

        log_data = {
            "action": LogAction.DELETE,
            "target_type": LogTargetType.SYSTEM,
            "operator": request.user.username,
            "operator_object": "告警策略-删除",
            "target_id": instance_id,
            "overview": f"删除告警策略: 策略名称:{rule_name}",
        }
        OperatorLog.objects.create(**log_data)
        return Response(status=status.HTTP_204_NO_CONTENT)
