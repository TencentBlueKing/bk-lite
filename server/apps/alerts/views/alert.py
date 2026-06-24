# -- coding: utf-8 --
from django.db import connection
from django.db.models import Count
from django.http import Http404
from rest_framework.response import Response
from rest_framework.decorators import action

from apps.alerts.constants import PERMISSION_ALERT
from apps.alerts.constants.constants import SessionStatus, PERMISSION_EVENT
from apps.alerts.filters import AlertModelFilter
from apps.alerts.models.models import Alert, Event
from apps.alerts.serializers import AlertModelSerializer, EventModelSerializer
from apps.alerts.service.related_alerts import RelatedAlertsService
from apps.alerts.service.alter_operator import AlertOperator
from apps.alerts.utils.permission_scope import get_authorized_group_ids
from apps.core.decorators.api_permission import HasPermission
from apps.core.logger import alert_logger as logger
from apps.core.utils.web_utils import WebUtils
from apps.core.utils.viewset_utils import AuthViewSet
from apps.system_mgmt.models.user import User
from config.drf.pagination import CustomPageNumberPagination


class AlertModelViewSet(AuthViewSet):
    # -level 告警等级排序
    queryset = Alert.objects.exclude(session_status__in=SessionStatus.NO_CONFIRMED)
    serializer_class = AlertModelSerializer
    ordering_fields = ["created_at"]
    ordering = ["-created_at"]
    filterset_class = AlertModelFilter
    pagination_class = CustomPageNumberPagination
    ORGANIZATION_FIELD = "team"
    permission_key = PERMISSION_ALERT

    def get_queryset(self):
        queryset = (
            super()
            .get_queryset()
            .annotate(
                event_count_annotated=Count("events", distinct=True),
            )
            .prefetch_related("events__source", "incident_set")
        )

        # StringAgg 是 PostgreSQL 专属函数，其他数据库通过 serializer fallback 处理
        if connection.vendor == "postgresql":
            from django.contrib.postgres.aggregates import StringAgg

            queryset = (
                super()
                .get_queryset()
                .annotate(
                    event_count_annotated=Count("events", distinct=True),
                    # 通过事件获取告警源名称（去重）
                    source_names_annotated=StringAgg("events__source__name", delimiter=", ", distinct=True),
                    incident_title_annotated=StringAgg("incident__title", delimiter=", ", distinct=True),
                )
                .prefetch_related("events__source", "incident_set")
            )

        return queryset

    @staticmethod
    def _build_operator_user_map(page):
        operator_usernames = set()
        for alert in page:
            if alert.operator:
                operator_usernames.update(alert.operator)
        if not operator_usernames:
            return {}
        return dict(User.objects.filter(username__in=operator_usernames).values_list("username", "display_name"))

    def _get_permission_filtered_queryset(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        return self.get_queryset_by_permission(request, queryset)

    @HasPermission("Alarms-View")
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

    @HasPermission("Alarms-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("Alarms-Edit")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("Alarms-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @HasPermission("Alarms-Edit")
    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    @HasPermission("Alarms-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("Alarms-View")
    @action(methods=["get"], detail=True, url_path="events", url_name="events")
    def events(self, request, *args, **kwargs):
        alert_queryset = self.get_queryset_by_permission(request, self.get_queryset())
        alert = alert_queryset.get(pk=kwargs["pk"])
        queryset = self.get_queryset_by_permission(request, Event.objects.select_related("source").filter(alert=alert),
                                                   permission_key=PERMISSION_EVENT)
        queryset = queryset.order_by("-received_at")

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = EventModelSerializer(page, many=True, context=self.get_serializer_context())
            return self.get_paginated_response(serializer.data)

        serializer = EventModelSerializer(queryset, many=True, context=self.get_serializer_context())
        return Response(serializer.data)

    @HasPermission("Alarms-View")
    @action(methods=["get"], detail=True, url_path="related", url_name="related")
    def related(self, request, *args, **kwargs):
        alert_queryset = self.get_queryset_by_permission(request, self.get_queryset())
        try:
            alert = alert_queryset.get(pk=kwargs["pk"])
        except Alert.DoesNotExist as err:
            raise Http404 from err
        try:
            time_window = int(request.query_params.get("time_window", 60))
        except (TypeError, ValueError):
            time_window = 60

        try:
            limit = int(request.query_params.get("limit", 10))
        except (TypeError, ValueError):
            limit = 10

        group_ids = get_authorized_group_ids(request)
        result = RelatedAlertsService.find_related_alerts(
            alert,
            time_window_minutes=time_window,
            limit=limit,
            group_ids=group_ids,
        )
        return Response(result)

    @HasPermission("Alarms-Edit")
    @action(
        methods=["post"],
        detail=False,
        url_path="operator/(?P<operator_action>[^/.]+)",
        url_name="operator",
    )
    def operator(self, request, operator_action, *args, **kwargs):
        """
        Custom operator method to handle alert operations.
        """
        alert_id_list = request.data["alert_id"]
        allowed_alert_ids = set(
            self._get_permission_filtered_queryset(request).filter(alert_id__in=alert_id_list).values_list("alert_id",
                                                                                                           flat=True)
        )
        operator = AlertOperator(
            user=self.request.user.username,
            allowed_alert_ids=allowed_alert_ids,
        )
        result_list = {}
        status_list = []
        for alert_id in alert_id_list:
            if alert_id not in allowed_alert_ids:
                result = {"result": False, "message": "您没有权限操作此告警", "data": {}}
                result_list[alert_id] = result
                status_list.append(False)
                continue
            # 每条告警独立处理：单条意外异常不应回滚/中断整批（operate 自身已管理事务）。
            try:
                result = operator.operate(action=operator_action, alert_id=alert_id, data=request.data)
            except Exception as exc:  # noqa
                logger.exception("[AlertOperator] 批量操作单条失败: alert_id=%s", alert_id)
                result = {"result": False, "message": str(exc), "data": {}}
            result_list[alert_id] = result
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
