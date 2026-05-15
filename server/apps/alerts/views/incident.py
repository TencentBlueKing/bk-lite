# -- coding: utf-8 --
import uuid

from django.db import transaction
from django.db.models import Count, Prefetch
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.alerts.constants.constants import LogAction, LogTargetType
from apps.alerts.filters import IncidentModelFilter
from apps.alerts.models.models import Alert, Incident
from apps.alerts.models.operator_log import OperatorLog
from apps.alerts.serializers import IncidentModelSerializer
from apps.alerts.service.incident_operator import IncidentOperator
from apps.alerts.utils.operator_scope import normalize_usernames
from apps.alerts.utils.permission_scope import (
    filter_alert_queryset_for_request,
    filter_incident_queryset_for_request,
)
from apps.core.decorators.api_permission import HasPermission
from apps.core.logger import alert_logger as logger
from apps.core.utils.web_utils import WebUtils
from apps.system_mgmt.models.user import User
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
        alert_prefetch = Prefetch(
            "alert",
            queryset=Alert.objects.prefetch_related("events__source"),
        )
        queryset = Incident.objects.annotate(alert_count=Count("alert", distinct=True)).prefetch_related(alert_prefetch)
        request = getattr(self, "request", None)
        if request is None:
            return queryset
        return filter_incident_queryset_for_request(queryset, request).distinct()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        request = context.get("request")
        if request is not None:
            context["allowed_alert_queryset"] = filter_alert_queryset_for_request(Alert.objects.all(), request)
        return context

    def _get_allowed_alert_ids(self):
        request = getattr(self, "request", None)
        if request is None:
            return set()
        return set(filter_alert_queryset_for_request(Alert.objects.all(), request).values_list("id", flat=True))

    @staticmethod
    def _parse_alert_ids(payload, required=False):
        if "alert" not in payload:
            return None, None

        raw_alert_ids = payload.get("alert")
        if raw_alert_ids is None:
            return None, Response(
                {"detail": "alert must be a list of ids."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not isinstance(raw_alert_ids, list):
            return None, Response(
                {"detail": "alert must be a list of ids."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        alert_ids = []
        for alert_id in raw_alert_ids:
            try:
                alert_ids.append(int(alert_id))
            except (TypeError, ValueError):
                return None, Response(
                    {"detail": "alert must be a list of ids."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if required and not alert_ids:
            return None, Response(
                {"detail": "must provide at least one alert to create an incident."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return alert_ids, None

    @staticmethod
    def _build_operator_user_map(objects):
        operator_usernames = set()
        for incident in objects:
            if incident.operator:
                operator_usernames.update(incident.operator)
        if not operator_usernames:
            return {}
        return dict(User.objects.filter(username__in=operator_usernames).values_list("username", "display_name"))

    @HasPermission("Incidents-View")
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            operator_user_map = self._build_operator_user_map(page)
            serializer = self.get_serializer(
                page,
                many=True,
                context={
                    **self.get_serializer_context(),
                    "operator_user_map": operator_user_map,
                },
            )
            return self.get_paginated_response(serializer.data)

        operator_user_map = self._build_operator_user_map(queryset)
        serializer = self.get_serializer(
            queryset,
            many=True,
            context={
                **self.get_serializer_context(),
                "operator_user_map": operator_user_map,
            },
        )
        return WebUtils.response_success(serializer.data)

    @HasPermission("Incidents-View")
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(
            instance,
            context={
                **self.get_serializer_context(),
                "operator_user_map": self._build_operator_user_map([instance]),
            },
        )
        return Response(serializer.data)

    @HasPermission("Alarms-Edit")
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        data = request.data
        incident_id = f"INCIDENT-{uuid.uuid4().hex}"
        data["incident_id"] = incident_id
        alert_ids, error_response = self._parse_alert_ids(data, required=True)
        if error_response is not None:
            return error_response

        allowed_alert_ids = self._get_allowed_alert_ids()
        unauthorized_alert_ids = set(alert_ids) - allowed_alert_ids
        if unauthorized_alert_ids:
            return Response(
                {"detail": "Some alerts are out of your authorized scope."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        has_incident_alert_ids = list(Alert.objects.filter(id__in=alert_ids, incident__isnull=False).values_list("id", flat=True))
        not_incident_alert_ids = set(alert_ids) - set(has_incident_alert_ids)
        data["alert"] = list(not_incident_alert_ids)
        if not not_incident_alert_ids:
            logger.warning(
                f"Some alerts {has_incident_alert_ids} are already associated with an incident. They will not be included in the new incident."
            )
            return Response(
                {"detail": "Some alerts are already associated with an incident and will not be included."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not data.get("operator"):
            data["operator"] = [self.request.user.username]
        else:
            data["operator"] = normalize_usernames(data.get("operator"))

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        log_data = {
            "action": LogAction.ADD,
            "target_type": LogTargetType.INCIDENT,
            "operator": request.user.username,
            "operator_object": "事故-创建",
            "target_id": serializer.data["incident_id"],
            "overview": f"手动创建事故[{serializer.data['title']}]",
        }
        OperatorLog.objects.create(**log_data)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @HasPermission("Incidents-Edit")
    @transaction.atomic
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        requested_alert_ids, error_response = self._parse_alert_ids(request.data)
        if error_response is not None:
            return error_response
        if requested_alert_ids is not None:
            unauthorized_alert_ids = set(requested_alert_ids) - self._get_allowed_alert_ids()
            if unauthorized_alert_ids:
                return Response(
                    {"detail": "Some alerts are out of your authorized scope."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        if "operator" in request.data:
            request.data["operator"] = normalize_usernames(request.data.get("operator"))
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        if getattr(instance, "_prefetched_objects_cache", None):
            # If 'prefetch_related' has been applied to a queryset, we need to
            # forcibly invalidate the prefetch cache on the instance.
            instance._prefetched_objects_cache = {}

        log_data = {
            "action": LogAction.MODIFY,
            "target_type": LogTargetType.INCIDENT,
            "operator": request.user.username,
            "operator_object": "事故-更新",
            "target_id": instance.incident_id,
            "overview": f"手动修改事故[{instance.title}]",
        }
        OperatorLog.objects.create(**log_data)

        return Response(serializer.data)

    @HasPermission("Incidents-Edit")
    @transaction.atomic
    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, partial=True, **kwargs)

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
            "overview": f"手动删除事故[{instance.title}]",
        }
        OperatorLog.objects.create(**log_data)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @HasPermission("Incidents-Edit")
    @action(
        methods=["post"],
        detail=False,
        url_path="operator/(?P<operator_action>[^/.]+)",
        url_name="operator",
    )
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
        allowed_incident_ids = set(
            self.filter_queryset(self.get_queryset()).filter(incident_id__in=incident_id_list).values_list("incident_id", flat=True)
        )

        for incident_id in incident_id_list:
            if incident_id not in allowed_incident_ids:
                result = {"result": False, "message": "您没有权限操作此事故", "data": {}}
                result_list[incident_id] = result
                status_list.append(False)
                continue
            result = operator.operate(action=operator_action, incident_id=incident_id, data=request.data)
            result_list[incident_id] = result
            status_list.append(result["result"])

        if all(status_list):
            return WebUtils.response_success(result_list)
        elif not any(status_list):
            return WebUtils.response_error(
                response_data=result_list,
                error_message="操作失败，请检查日志!",
                status_code=500,
            )
        else:
            return WebUtils.response_success(response_data=result_list, message="部分操作成功")
