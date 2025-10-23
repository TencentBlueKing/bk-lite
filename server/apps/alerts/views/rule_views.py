from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Prefetch
from django.db import transaction

from apps.alerts.constants import LogAction, LogTargetType
from apps.alerts.filters import CorrelationRulesModelFilter, AggregationRulesModelFilter
from apps.alerts.models import AggregationRules, CorrelationRules, OperatorLog
from apps.alerts.serializers.rule_serializers import AggregationRulesSerializer, CorrelationRulesSerializer
from apps.core.decorators.api_permission import HasPermission
from config.drf.pagination import CustomPageNumberPagination
from apps.core.logger import alert_logger as logger


class AggregationRulesViewSet(viewsets.ModelViewSet):
    """聚合规则视图集"""

    queryset = AggregationRules.objects.filter(is_active=True)
    serializer_class = AggregationRulesSerializer
    filterset_class = AggregationRulesModelFilter
    ordering_fields = ["created_at"]
    ordering = ["-created_at"]
    pagination_class = CustomPageNumberPagination

    @HasPermission("correlation_rules-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        """获取聚合规则查询集，预加载关联规则数据"""
        return AggregationRules.objects.filter(is_active=True).prefetch_related(
            Prefetch(
                'correlation_rules',
                queryset=CorrelationRules.objects.only('name'),
                to_attr='related_rules_names'
            )
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        log_data = {
            "action": LogAction.ADD,
            "target_type": LogTargetType.SYSTEM,
            "operator": request.user.username,
            "operator_object": "聚合规则-新增",
            "target_id": serializer.data['rule_id'],
            "overview": f"创建聚合规则: 规则名称:{serializer.data['name']}"
        }
        OperatorLog.objects.create(**log_data)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        if getattr(instance, '_prefetched_objects_cache', None):
            # If 'prefetch_related' has been applied to a queryset, we need to
            # forcibly invalidate the prefetch cache on the instance.
            instance._prefetched_objects_cache = {}

        log_data = {
            "action": LogAction.MODIFY,
            "target_type": LogTargetType.SYSTEM,
            "operator": request.user.username,
            "operator_object": "聚合规则-修改",
            "target_id": serializer.data.rule_id,
            "overview": f"修改聚合规则: 规则名称:{instance.name}"
        }
        OperatorLog.objects.create(**log_data)

        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def reload_rules(self, request):
        """重新加载数据库规则到告警引擎"""
        try:
            # 移动导入到函数内部避免循环导入
            from apps.alerts.common.rules.rule_manager import get_rule_manager

            rule_manager = get_rule_manager()
            rule_manager.reload_rules_from_database()

            # 统计规则信息
            stats = rule_manager.get_rule_statistics()
            window_types = rule_manager.get_window_types()

            return Response({
                'success': True,
                'message': f'成功重新加载 {stats["total_rules"]} 条规则到告警引擎',
                'window_types': len(window_types),
                'window_type': window_types[0] if window_types else None,
                'stats': stats
            })
        except Exception as e:
            logger.error(f"重新加载规则失败: {str(e)}")
            return Response({
                'success': False,
                'message': f'重新加载规则失败: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CorrelationRulesViewSet(viewsets.ModelViewSet):
    """关联规则视图集"""

    queryset = CorrelationRules.objects.all()
    serializer_class = CorrelationRulesSerializer
    ordering_fields = ["created_at"]
    ordering = ["-created_at"]
    filterset_class = CorrelationRulesModelFilter
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        """获取关联规则查询集，预加载聚合规则数据"""
        return CorrelationRules.objects.prefetch_related(
            Prefetch(
                'aggregation_rules',
                queryset=AggregationRules.objects.only('name'),
                to_attr='related_rules_names'
            )
        )

    @HasPermission("correlation_rules-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("correlation_rules-Add")
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """创建关联规则"""
        aggregation_rules = request.data["aggregation_rules"]
        if not aggregation_rules:
            return Response(
                {"detail": "必须提供至少一个聚合规则来创建关联规则。"},
                status=status.HTTP_400_BAD_REQUEST
            )
        if CorrelationRules.objects.filter(aggregation_rules__in=aggregation_rules).exists():
            return Response(
                {"detail": "所选聚合规则已被其他关联规则使用，请选择其他聚合规则。"},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        log_data = {
            "action": LogAction.ADD,
            "target_type": LogTargetType.SYSTEM,
            "operator": request.user.username,
            "operator_object": "关联规则-新增",
            "target_id": serializer.data["id"],
            "overview": f"创关联规则: 规则名称:{serializer.data['name']}"
        }
        OperatorLog.objects.create(**log_data)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @HasPermission("correlation_rules-Edit")
    @transaction.atomic
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        if getattr(instance, '_prefetched_objects_cache', None):
            # If 'prefetch_related' has been applied to a queryset, we need to
            # forcibly invalidate the prefetch cache on the instance.
            instance._prefetched_objects_cache = {}

        log_data = {
            "action": LogAction.MODIFY,
            "target_type": LogTargetType.SYSTEM,
            "operator": request.user.username,
            "operator_object": "关联规则-修改",
            "target_id": instance.id,
            "overview": f"修改关联规则: 规则名称:{instance.name}"
        }
        OperatorLog.objects.create(**log_data)

        return Response(serializer.data)

    @HasPermission("correlation_rules-Delete")
    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        log_data = {
            "action": LogAction.DELETE,
            "target_type": LogTargetType.SYSTEM,
            "operator": request.user.username,
            "operator_object": "关联规则-删除",
            "target_id": instance.id,
            "overview": f"删除关联规则: 规则名称:{instance.name}"
        }
        OperatorLog.objects.create(**log_data)
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)
