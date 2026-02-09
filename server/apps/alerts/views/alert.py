# -- coding: utf-8 --
from django.contrib.postgres.aggregates import StringAgg
from django.db.models import Count
from django.db import transaction
from rest_framework.decorators import action

from apps.alerts.constants.constants import SessionStatus
from apps.alerts.filters import AlertModelFilter
from apps.alerts.models.models import Alert
from apps.alerts.serializers import AlertModelSerializer
from apps.alerts.service.alter_operator import AlertOperator
from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.web_utils import WebUtils
from config.drf.pagination import CustomPageNumberPagination
from config.drf.viewsets import ModelViewSet


class AlterModelViewSet(ModelViewSet):
    """
    告警视图集
    """
    # -level 告警等级排序
    queryset = Alert.objects.exclude(session_status__in=SessionStatus.NO_CONFIRMED)
    serializer_class = AlertModelSerializer
    ordering_fields = ["created_at"]
    ordering = ["-created_at"]
    filterset_class = AlertModelFilter
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        queryset = Alert.objects.annotate(
            event_count_annotated=Count('events'),
            # 通过事件获取告警源名称（去重）
            source_names_annotated=StringAgg('events__source__name', delimiter=', ', distinct=True),
            incident_title_annotated=StringAgg('incident__title', delimiter=', ', distinct=True)
        ).prefetch_related('events__source')
        return queryset

    @HasPermission("Alarms-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("Alarms-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @HasPermission("Alarms-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("Alarms-Edit")
    @action(methods=['post'], detail=False, url_path='operator/(?P<operator_action>[^/.]+)', url_name='operator')
    @transaction.atomic
    def operator(self, request, operator_action, *args, **kwargs):
        """
        Custom operator method to handle alert operations.
        """
        alert_id_list = request.data["alert_id"]
        operator = AlertOperator(user=self.request.user.username)
        result_list = {}
        status_list = []
        for alert_id in alert_id_list:
            result = operator.operate(action=operator_action, alert_id=alert_id, data=request.data)
            result_list[alert_id] = result
            status_list.append(result["result"])

        if all(status_list):
            return WebUtils.response_success(result_list)
        elif not all(status_list):
            return WebUtils.response_error(
                response_data=result_list,
                error_message="操作失败，请检查日志!",
                status_code=500
            )
        else:
            return WebUtils.response_success(response_data=result_list, message="部分操作成功")
