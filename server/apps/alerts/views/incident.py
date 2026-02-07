# -- coding: utf-8 --
import uuid

from django.db.models import Count
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction

from apps.alerts.constants.constants import LogAction, LogTargetType
from apps.alerts.filters import IncidentModelFilter
from apps.alerts.models.models import Alert, Incident
from apps.alerts.models.operator_log import OperatorLog
from apps.alerts.serializers import IncidentModelSerializer
from apps.alerts.service.incident_operator import IncidentOperator
from apps.core.decorators.api_permission import HasPermission
from apps.core.logger import alert_logger as logger
from apps.core.utils.web_utils import WebUtils
from config.drf.pagination import CustomPageNumberPagination
from config.drf.viewsets import ModelViewSet


class IncidentModelViewSet(ModelViewSet):
    """
    事故视图集
    """
    queryset = Incident.objects.all()
    serializer_class = IncidentModelSerializer
    ordering_fields = ["created_at", "id"]  # 允许按创建时间和ID排序 ?ordering=-id
    ordering = ["-created_at"]  # 默认按创建时间降序排序
    filterset_class = IncidentModelFilter
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        queryset = Incident.objects.annotate(
            alert_count=Count('alert')
        ).prefetch_related('alert')
        return queryset

    @HasPermission("Incidents-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("Alarms-Edit")
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        data = request.data
        incident_id = f"INCIDENT-{uuid.uuid4().hex}"
        data["incident_id"] = incident_id
        if not data["alert"]:
            return Response(
                {"detail": "must provide at least one alert to create an incident."},
                status=status.HTTP_400_BAD_REQUEST
            )
        else:
            not_incident_alert_ids = list(
                Alert.objects.filter(id__in=data["alert"], incident__isnull=False).values_list('id', flat=True))
            has_incident_alert_ids = set(data["alert"]) - set(not_incident_alert_ids)
            data["alert"] = list(has_incident_alert_ids)
            if not has_incident_alert_ids:
                logger.warning(
                    f"Some alerts {has_incident_alert_ids} are already associated with an incident. "
                    "They will not be included in the new incident."
                )
                return Response(
                    {"detail": "Some alerts are already associated with an incident and will not be included."},
                    status=status.HTTP_400_BAD_REQUEST
                )
        if not data["operator"]:
            data["operator"] = self.request.user.username

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        log_data = {
            "action": LogAction.ADD,
            "target_type": LogTargetType.INCIDENT,
            "operator": request.user.username,
            "operator_object": "事故-创建",
            "target_id": serializer.data["incident_id"],
            "overview": f"手动创建事故[{serializer.data['title']}]"
        }
        OperatorLog.objects.create(**log_data)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @HasPermission("Incidents-Edit")
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
            "target_type": LogTargetType.INCIDENT,
            "operator": request.user.username,
            "operator_object": "事故-更新",
            "target_id": instance.incident_id,
            "overview": f"手动修改事故[{instance.title}]"
        }
        OperatorLog.objects.create(**log_data)

        return Response(serializer.data)

    @HasPermission("Incidents-Delete")
    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)

        log_data = {
            "action": LogAction.DELETE,
            "target_type": LogTargetType.INCIDENT,
            "operator": request.user.username,
            "operator_object": "事故-删除",
            "target_id": instance.incident_id,
            "overview": f"手动删除事故[{instance.title}]"
        }
        OperatorLog.objects.create(**log_data)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @HasPermission("Incidents-Edit")
    @action(methods=['post'], detail=False, url_path='operator/(?P<operator_action>[^/.]+)', url_name='operator')
    @transaction.atomic
    def operator(self, request, operator_action, *args, **kwargs):
        """
        事故操作方法
        """
        incident_id_list = request.data.get("incident_id", [])
        if not incident_id_list:
            return WebUtils.response_error(error_message="incident_id参数不能为空")

        operator = IncidentOperator(user=self.request.user.username)
        result_list = {}
        status_list = []

        for incident_id in incident_id_list:
            result = operator.operate(action=operator_action, incident_id=incident_id, data=request.data)
            result_list[incident_id] = result
            status_list.append(result["result"])

        if all(status_list):
            return WebUtils.response_success(result_list)
        elif not any(status_list):
            return WebUtils.response_error(
                response_data=result_list,
                error_message="操作失败，请检查日志!",
                status_code=500
            )
        else:
            return WebUtils.response_success(response_data=result_list, message="部分操作成功")
