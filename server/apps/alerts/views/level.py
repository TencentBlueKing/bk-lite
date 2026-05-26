# -- coding: utf-8 --
from django.db import transaction
from rest_framework import status
from rest_framework.response import Response

from apps.alerts.filters import LevelModelFilter
from apps.alerts.models.alert_operator import AlarmStrategy, AlertAssignment, AlertShield
from apps.alerts.models.models import Alert, Event, Incident, Level
from apps.alerts.serializers import LevelModelSerializer
from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.web_utils import WebUtils
from config.drf.pagination import CustomPageNumberPagination
from config.drf.viewsets import ModelViewSet


class LevelModelViewSet(ModelViewSet):
    """
    告警等级视图集
    """

    # TODO 创建的时候动态增加level_id 锁表
    queryset = Level.objects.all()
    serializer_class = LevelModelSerializer
    filterset_class = LevelModelFilter
    ordering_fields = ["level_id"]
    ordering = ["level_id"]
    pagination_class = CustomPageNumberPagination

    @HasPermission("global_config-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("global_config-Edit")
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("global_config-Edit")
    @transaction.atomic
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @HasPermission("global_config-Edit")
    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()

        same_type_queryset = Level.objects.filter(level_type=instance.level_type)
        if same_type_queryset.count() <= 1:
            return WebUtils.response_error(
                error_message="每个等级类型至少保留一个等级，无法删除。",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        level_key = str(instance.level_id)

        data_reference_message = self._get_data_reference_message(instance.level_type, level_key)
        if data_reference_message:
            return WebUtils.response_error(
                error_message=data_reference_message,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        config_reference_message = self._get_config_reference_message(instance.level_type, level_key)
        if config_reference_message:
            return WebUtils.response_error(
                error_message=config_reference_message,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @staticmethod
    def _get_data_reference_message(level_type, level_key):
        model_mapping = {
            "event": (Event, "事件"),
            "alert": (Alert, "告警"),
            "incident": (Incident, "事故"),
        }
        model_config = model_mapping.get(level_type)
        if model_config is None:
            return ""

        model, label = model_config
        count = model.objects.filter(level=level_key).count()
        if not count:
            return ""

        return f"该等级已被{count}条{label}引用，无法删除。"

    @classmethod
    def _get_config_reference_message(cls, level_type, level_key):
        if level_type == "alert":
            for assignment in AlertAssignment.objects.all().only("name", "notification_frequency"):
                if level_key in (assignment.notification_frequency or {}):
                    return f"该等级已被告警分派策略“{assignment.name}”引用，无法删除。"

            assignment_name = cls._find_match_rules_reference_name(AlertAssignment.objects.all(), level_key, "level")
            if assignment_name:
                return f"该等级已被告警分派策略“{assignment_name}”引用，无法删除。"

            for strategy in AlarmStrategy.objects.all().only("name", "params"):
                alert_template = (strategy.params or {}).get("alert_template") or {}
                if str(alert_template.get("level")) == level_key:
                    return f"该等级已被相关性规则“{strategy.name}”引用，无法删除。"

            return ""

        if level_type == "event":
            shield_name = cls._find_match_rules_reference_name(AlertShield.objects.all(), level_key, "level")
            if shield_name:
                return f"该等级已被屏蔽策略“{shield_name}”引用，无法删除。"

            strategy_name = cls._find_match_rules_reference_name(AlarmStrategy.objects.all(), level_key, "level")
            if strategy_name:
                return f"该等级已被相关性规则“{strategy_name}”引用，无法删除。"

        return ""

    @staticmethod
    def _find_match_rules_reference_name(queryset, level_key, rule_key):
        for instance in queryset.only("name", "match_rules"):
            for rule_group in instance.match_rules or []:
                for rule in rule_group or []:
                    if rule.get("key") == rule_key and str(rule.get("value")) == level_key:
                        return instance.name
        return ""
