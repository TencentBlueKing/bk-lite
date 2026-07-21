# -- coding: utf-8 --
import uuid

from django.db import transaction
from django.db.models import Count, Prefetch
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.alerts.constants import PERMISSION_ALERT, PERMISSION_INCIDENT
from apps.alerts.constants.constants import LogAction, LogTargetType
from apps.alerts.filters import IncidentModelFilter
from apps.alerts.models.models import Alert, Incident
from apps.alerts.utils.operator_log import record_operator_log
from apps.alerts.serializers import AlertModelSerializer, IncidentModelSerializer
from apps.alerts.service.incident_operator import IncidentOperator
from apps.alerts.utils.operator_scope import normalize_usernames
from apps.alerts.utils.permission_scope import normalize_team_ids
from apps.core.decorators.api_permission import HasPermission
from apps.core.logger import alert_logger as logger
from apps.core.utils.web_utils import WebUtils
from apps.core.utils.viewset_utils import AuthViewSet
from apps.system_mgmt.models.user import User
from config.drf.pagination import CustomPageNumberPagination


class IncidentModelViewSet(AuthViewSet):
    """
    事故视图集
    """

    queryset = Incident.objects.all()
    serializer_class = IncidentModelSerializer
    ordering_fields = ["created_at", "id"]  # 允许按创建时间和ID排序 ?ordering=-id
    ordering = ["-created_at"]  # 默认按创建时间降序排序
    filterset_class = IncidentModelFilter
    pagination_class = CustomPageNumberPagination
    ORGANIZATION_FIELD = "team"
    permission_key = PERMISSION_INCIDENT

    def get_queryset(self):
        alert_prefetch = Prefetch(
            "alert",
            queryset=Alert.objects.prefetch_related("events__source"),
        )
        return Incident.objects.annotate(alert_count=Count("alert", distinct=True)).prefetch_related(alert_prefetch)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        request = context.get("request")
        if request is not None:
            context["allowed_alert_queryset"] = self.get_queryset_by_permission(request, Alert.objects.all(),
                                                                                permission_key=PERMISSION_ALERT)
        return context

    def _get_allowed_alert_ids(self):
        request = getattr(self, "request", None)
        if request is None:
            return set()
        return set(
            self.get_queryset_by_permission(request, Alert.objects.all(), permission_key=PERMISSION_ALERT).values_list(
                "id", flat=True))

    def _validate_alert_access(self, alert_ids):
        unauthorized_alert_ids = set(alert_ids) - self._get_allowed_alert_ids()
        if not unauthorized_alert_ids:
            return None
        return Response(
            {
                "detail": "告警ID列表中包含您没有权限访问的告警。",
                "unauthorized_alert_ids": sorted(unauthorized_alert_ids),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    def _get_permission_filtered_queryset(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        return self.get_queryset_by_permission(request, queryset)

    def _get_authorized_incident(self, request, *, check_view_permission=False, denied_message=None):
        instance = self.get_object()
        user = getattr(request, "user", None)
        if getattr(user, "is_superuser", False):
            return instance, None

        try:
            current_team = self._validate_current_team_permission(request)
        except PermissionDenied:
            raise

        include_children = request.COOKIES.get("include_children", "0") == "1"
        has_permission = self.get_has_permission(
            user,
            instance,
            current_team,
            is_check=check_view_permission,
            include_children=include_children,
        )
        if has_permission:
            return instance, None

        return None, self.value_error(denied_message or "您没有权限访问此事故")

    @staticmethod
    def _normalize_team_payload(payload):
        if "team" not in payload:
            return None
        payload["team"] = normalize_team_ids(payload.get("team"))
        return payload["team"]

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
        usernames = set()
        for incident in objects:
            if incident.operator:
                usernames.update(incident.operator)
            if incident.collaborators:
                usernames.update(incident.collaborators)
        if not usernames:
            return {}
        return dict(User.objects.filter(username__in=usernames).values_list("username", "display_name"))

    @HasPermission("Incidents-View")
    def list(self, request, *args, **kwargs):
        queryset = self._get_permission_filtered_queryset(request)
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
        instance, error_response = self._get_authorized_incident(
            request,
            check_view_permission=True,
            denied_message="您没有权限查看此事故",
        )
        if error_response is not None:
            return error_response
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
        try:
            self._normalize_team_payload(data)
        except ValueError as err:
            return Response({"detail": str(err)}, status=status.HTTP_400_BAD_REQUEST)
        incident_id = f"INCIDENT-{uuid.uuid4().hex}"
        data["incident_id"] = incident_id
        alert_ids, error_response = self._parse_alert_ids(data, required=True)
        if error_response is not None:
            return error_response

        access_error = self._validate_alert_access(alert_ids)
        if access_error is not None:
            return access_error

        data["alert"] = alert_ids
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
        record_operator_log(**log_data)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @HasPermission("Incidents-Edit")
    @transaction.atomic
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance, error_response = self._get_authorized_incident(
            request,
            denied_message="您没有权限修改此事故",
        )
        if error_response is not None:
            return error_response
        try:
            self._normalize_team_payload(request.data)
        except ValueError as err:
            return Response({"detail": str(err)}, status=status.HTTP_400_BAD_REQUEST)
        requested_alert_ids, error_response = self._parse_alert_ids(request.data)
        if error_response is not None:
            return error_response
        if requested_alert_ids is not None:
            access_error = self._validate_alert_access(requested_alert_ids)
            if access_error is not None:
                return access_error
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
        record_operator_log(**log_data)

        return Response(serializer.data)

    @HasPermission("Incidents-Edit")
    @transaction.atomic
    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, partial=True, **kwargs)

    @HasPermission("Incidents-Delete")
    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        instance, error_response = self._get_authorized_incident(
            request,
            denied_message="您没有权限删除此事故",
        )
        if error_response is not None:
            return error_response
        self.perform_destroy(instance)

        log_data = {
            "action": LogAction.DELETE,
            "target_type": LogTargetType.INCIDENT,
            "operator": request.user.username,
            "operator_object": "事故-删除",
            "target_id": instance.incident_id,
            "overview": f"手动删除事故[{instance.title}]",
        }
        record_operator_log(**log_data)
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

        allowed_incident_ids = set(
            self._get_permission_filtered_queryset(request).filter(incident_id__in=incident_id_list).values_list(
                "incident_id", flat=True)
        )
        operator = IncidentOperator(
            user=self.request.user.username,
            allowed_incident_ids=allowed_incident_ids,
        )
        result_list = {}
        status_list = []

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

    @HasPermission("Incidents-Edit")
    @action(methods=["post"], detail=True, url_path="alerts/add", url_name="add_alerts")
    @transaction.atomic
    def add_alerts(self, request, *args, **kwargs):
        instance, error_response = self._get_authorized_incident(
            request,
            denied_message="您没有权限修改此事故",
        )
        if error_response is not None:
            return error_response
        alert_ids, error_response = self._parse_alert_ids(request.data, required=True)
        if error_response is not None:
            return error_response

        access_error = self._validate_alert_access(alert_ids)
        if access_error is not None:
            return access_error
        already_in_incident = set(instance.alert.values_list("id", flat=True))
        new_alert_ids = set(alert_ids) - already_in_incident
        if new_alert_ids:
            instance.alert.add(*new_alert_ids)
            record_operator_log(
                action=LogAction.MODIFY,
                target_type=LogTargetType.INCIDENT,
                operator=request.user.username,
                operator_object="事故-添加告警",
                target_id=instance.incident_id,
                overview=f"添加告警到事故[{instance.title}]: {list(new_alert_ids)}",
            )

        return Response({"added": list(new_alert_ids), "skipped": list(set(alert_ids) & already_in_incident)})

    @HasPermission("Incidents-Edit")
    @action(methods=["post"], detail=True, url_path="alerts/remove", url_name="remove_alerts")
    @transaction.atomic
    def remove_alerts(self, request, *args, **kwargs):
        instance, error_response = self._get_authorized_incident(
            request,
            denied_message="您没有权限修改此事故",
        )
        if error_response is not None:
            return error_response
        alert_ids, error_response = self._parse_alert_ids(request.data, required=True)
        if error_response is not None:
            return error_response

        access_error = self._validate_alert_access(alert_ids)
        if access_error is not None:
            return access_error

        current_alert_ids = set(instance.alert.values_list("id", flat=True))
        to_remove = set(alert_ids) & current_alert_ids
        not_in_incident = set(alert_ids) - current_alert_ids

        if to_remove:
            instance.alert.remove(*to_remove)
            record_operator_log(
                action=LogAction.MODIFY,
                target_type=LogTargetType.INCIDENT,
                operator=request.user.username,
                operator_object="事故-移除告警",
                target_id=instance.incident_id,
                overview=f"从事故[{instance.title}]移除告警: {list(to_remove)}",
            )

        return Response({"removed": list(to_remove), "not_in_incident": list(not_in_incident)})

    @HasPermission("Incidents-View")
    @action(methods=["get"], detail=True, url_path="alerts", url_name="alerts")
    def alerts(self, request, *args, **kwargs):
        incident, error_response = self._get_authorized_incident(
            request,
            check_view_permission=True,
            denied_message="您没有权限查看此事故",
        )
        if error_response is not None:
            return error_response
        queryset = self.get_queryset_by_permission(
            request,
            Alert.objects.filter(incident=incident).prefetch_related("events__source", "incident_set"),
            permission_key=PERMISSION_ALERT,
        ).order_by("-created_at")

        from apps.alerts.views import AlertModelViewSet
        page = self.paginate_queryset(queryset)
        if page is not None:
            operator_user_map = AlertModelViewSet._build_operator_user_map(page)
            serializer = AlertModelSerializer(
                page,
                many=True,
                context={
                    **self.get_serializer_context(),
                    "operator_user_map": operator_user_map,
                },
            )
            return self.get_paginated_response(serializer.data)

        operator_user_map = AlertModelViewSet._build_operator_user_map(queryset)
        serializer = AlertModelSerializer(
            queryset,
            many=True,
            context={
                **self.get_serializer_context(),
                "operator_user_map": operator_user_map,
            },
        )
        return Response(serializer.data)
