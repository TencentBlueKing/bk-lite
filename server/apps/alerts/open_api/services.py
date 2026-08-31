from types import SimpleNamespace

from django.db.models import Count, Q

from apps.alerts.constants.constants import SessionStatus
from apps.alerts.filters.alert import AlertModelFilter
from apps.alerts.models.models import Alert, Event
from apps.alerts.open_api.errors import AlertsOpenAPIError
from apps.alerts.open_api.serializers import (
    parse_batch_payload,
    parse_operator_payload,
    parse_ordering,
    parse_pagination,
    serialize_alert,
    serialize_event,
)
from apps.alerts.service.alter_operator import AlertOperator
from apps.core.utils.permission_utils import get_permission_rules
from apps.core.utils.viewset_utils import build_json_membership_query

ALLOWED_ACTIONS = {"assign", "acknowledge", "reassign", "close"}
GATEWAY_MAX_PAGE_SIZE = 500
LEGACY_OPENAPI_MAX_PAGE_SIZE = 100


class AlertsOpenAPIService:
    ALLOWED_ACTIONS = ALLOWED_ACTIONS

    def __init__(self, context):
        self.context = context

    def _base_alert_qs(self):
        queryset = Alert.objects.exclude(session_status__in=SessionStatus.NO_CONFIRMED)
        team_query = build_json_membership_query(queryset, "team", [self.context.team_id])
        queryset = queryset.filter(team_query)

        if not getattr(self.context.user, "is_superuser", False):
            permission_data = get_permission_rules(
                self.context.user,
                self.context.team_id,
                app_name="alerts",
                permission_key="alert",
                include_children=False,
            )
            instance_ids = [item["id"] for item in permission_data.get("instance", [])]
            team_ids = permission_data.get("team", [])
            permission_query = Q()
            if instance_ids:
                permission_query |= Q(id__in=instance_ids)
            permission_query |= build_json_membership_query(queryset, "team", team_ids)
            if not instance_ids and not team_ids:
                queryset = queryset.filter(id=0)
            else:
                queryset = queryset.filter(permission_query)

        return queryset.annotate(event_count_annotated=Count("events", distinct=True))

    def _not_found(self):
        raise AlertsOpenAPIError("alerts.alert.not_found", "告警不存在", 404)

    def _map_operator_result(self, alert_id: str, result: dict):
        if result.get("result"):
            return result.get("data") or {}
        message = result.get("message") or ""
        if "不存在" in message:
            raise AlertsOpenAPIError("alerts.alert.not_found", message, 404)
        if "无法进行" in message:
            raise AlertsOpenAPIError("alerts.operator.invalid_state", message, 409)
        if any(token in message for token in ("没有权限认领", "没有权限转派", "没有权限关闭", "没有权限操作")):
            raise AlertsOpenAPIError("alerts.operator.not_assignee", message, 403)
        if any(
            token in message
            for token in (
                "请指定处理人",
                "请指定新的处理人",
                "处理人不存在",
                "处理人不在",
                "处理人已禁用",
                "分派目标",
            )
        ):
            raise AlertsOpenAPIError("alerts.operator.assignee_invalid", message, 400)
        raise AlertsOpenAPIError("alerts.validation.failed", message, 400)

    def operate_alert(self, alert_id: str, action: str, data: dict):
        self.context.require_feature("Alarms-Edit")
        if action not in self.ALLOWED_ACTIONS:
            raise AlertsOpenAPIError("alerts.validation.failed", f"不支持的操作: {action}", 400)
        payload = parse_operator_payload(action, data)
        if not self._base_alert_qs().filter(alert_id=alert_id).exists():
            self._not_found()
        operator = AlertOperator(user=self.context.username, allowed_alert_ids={alert_id}, api_close=True)
        result = operator.operate(action=action, alert_id=alert_id, data=payload)
        return self._map_operator_result(alert_id, result)

    def operate_alerts_batch(self, action: str, data: dict):
        self.context.require_feature("Alarms-Edit")
        if action not in self.ALLOWED_ACTIONS:
            raise AlertsOpenAPIError("alerts.validation.failed", f"不支持的操作: {action}", 400)
        batch = parse_batch_payload(action, data)
        alert_ids = batch.pop("alert_ids")
        succeeded, failed = [], []
        for alert_id in alert_ids:
            try:
                self.operate_alert(alert_id, action, batch)
                succeeded.append(alert_id)
            except AlertsOpenAPIError as exc:
                failed.append({"alert_id": alert_id, "code": exc.code, "message": exc.message})
        return {"succeeded": succeeded, "failed": failed}

    def _paginate(self, queryset, query_params, *, max_page_size=LEGACY_OPENAPI_MAX_PAGE_SIZE):
        page, page_size = parse_pagination(query_params, max_page_size=max_page_size)
        count = queryset.count()
        start = (page - 1) * page_size
        items = queryset[start : start + page_size]
        return count, page, page_size, items

    def list_alerts(self, query_params, *, max_page_size=LEGACY_OPENAPI_MAX_PAGE_SIZE):
        self.context.require_feature("Alarms-View")
        queryset = self._base_alert_qs()
        request = SimpleNamespace(user=self.context.user)
        filterset = AlertModelFilter(data=query_params, queryset=queryset, request=request)
        queryset = filterset.qs.order_by(parse_ordering(query_params))
        count, page, page_size, page_items = self._paginate(queryset, query_params, max_page_size=max_page_size)
        return {
            "count": count,
            "page": page,
            "page_size": page_size,
            "items": [serialize_alert(alert, detail=False) for alert in page_items],
        }

    def get_alert(self, alert_id):
        self.context.require_feature("Alarms-View")
        try:
            alert = self._base_alert_qs().get(alert_id=alert_id)
        except Alert.DoesNotExist:
            self._not_found()
        return serialize_alert(alert, detail=True)

    def list_alert_events(self, alert_id, query_params, *, max_page_size=LEGACY_OPENAPI_MAX_PAGE_SIZE):
        self.context.require_feature("Alarms-View")
        try:
            alert = self._base_alert_qs().get(alert_id=alert_id)
        except Alert.DoesNotExist:
            self._not_found()
        events_qs = Event.objects.select_related("source").filter(alert=alert).order_by("-received_at")
        count, page, page_size, page_items = self._paginate(events_qs, query_params, max_page_size=max_page_size)
        return {
            "count": count,
            "page": page,
            "page_size": page_size,
            "items": [serialize_event(event) for event in page_items],
        }
