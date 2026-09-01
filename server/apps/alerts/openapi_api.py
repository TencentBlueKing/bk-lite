"""告警中心统一 OpenAPI 网关端点。"""

from apps.alerts.open_api.auth import AlertsOpenAPIContext
from apps.alerts.open_api.errors import AlertsOpenAPIError
from apps.alerts.open_api.services import GATEWAY_MAX_PAGE_SIZE, AlertsOpenAPIService
from apps.alerts.openapi_serializers import (
    AlertAcknowledgeRequestSerializer,
    AlertAssignRequestSerializer,
    AlertBatchActionRequestSerializer,
    AlertCloseRequestSerializer,
    AlertEventsRequestSerializer,
    AlertIdRequestSerializer,
    AlertListRequestSerializer,
)
from apps.core.openapi.decorators import openapi_expose

_ORG_SCOPE = "组织口径：API 令牌绑定组织精确匹配，不级联子组织"


def _run_alerts_openapi(handler):
    try:
        return handler()
    except AlertsOpenAPIError as exc:
        return {"result": False, "message": exc.message}


def _service(team, user_info):
    return AlertsOpenAPIService(AlertsOpenAPIContext.from_gateway(user_info=user_info, team_ids=team))


def _omit_blank(params):
    return {key: value for key, value in params.items() if value not in (None, "")}


@openapi_expose(
    path="alerts/list",
    method="GET",
    schema=AlertListRequestSerializer,
    inject="team_list_with_user",
    permission="Alarms-View",
    permission_app="alarm",
    summary=f"分页查询告警列表，筛选与告警中心页面一致（{_ORG_SCOPE}）",
)
def openapi_list_alerts(
    page=1,
    page_size=20,
    ordering="-created_at",
    title="",
    content="",
    alert_id="",
    activate="",
    my_alert="",
    level="",
    status="",
    source_name="",
    created_at_after="",
    created_at_before="",
    incident_id="",
    has_incident="",
    rule_id="",
    resource_type="",
    resource_id="",
    *,
    team=None,
    user_info=None,
):
    query = _omit_blank(
        {
            "page": page,
            "page_size": page_size,
            "ordering": ordering,
            "title": title,
            "content": content,
            "alert_id": alert_id,
            "activate": activate,
            "my_alert": my_alert,
            "level": level,
            "status": status,
            "source_name": source_name,
            "created_at_after": created_at_after,
            "created_at_before": created_at_before,
            "incident_id": incident_id,
            "has_incident": has_incident,
            "rule_id": rule_id,
            "resource_type": resource_type,
            "resource_id": resource_id,
        }
    )
    return _run_alerts_openapi(lambda: _service(team, user_info).list_alerts(query, max_page_size=GATEWAY_MAX_PAGE_SIZE))


@openapi_expose(
    path="alerts/detail",
    method="GET",
    schema=AlertIdRequestSerializer,
    inject="team_list_with_user",
    permission="Alarms-View",
    permission_app="alarm",
    summary=f"按业务告警 ID 查询告警详情（{_ORG_SCOPE}）",
)
def openapi_get_alert(alert_id, *, team=None, user_info=None):
    return _run_alerts_openapi(lambda: _service(team, user_info).get_alert(alert_id))


@openapi_expose(
    path="alerts/events",
    method="GET",
    schema=AlertEventsRequestSerializer,
    inject="team_list_with_user",
    permission="Alarms-View",
    permission_app="alarm",
    summary=f"按业务告警 ID 分页查询关联事件（{_ORG_SCOPE}）",
)
def openapi_list_alert_events(alert_id, page=1, page_size=20, *, team=None, user_info=None):
    query = {"page": page, "page_size": page_size}
    return _run_alerts_openapi(lambda: _service(team, user_info).list_alert_events(alert_id, query, max_page_size=GATEWAY_MAX_PAGE_SIZE))


def _operate(team, user_info, alert_id, action, data):
    return _run_alerts_openapi(lambda: _service(team, user_info).operate_alert(alert_id, action, data))


@openapi_expose(
    path="alerts/assign",
    method="POST",
    schema=AlertAssignRequestSerializer,
    inject="team_list_with_user",
    permission="Alarms-Edit",
    permission_app="alarm",
    summary=f"按业务告警 ID 分派告警（{_ORG_SCOPE}）",
)
def openapi_assign_alert(alert_id, assignee, assignment_id=None, *, team=None, user_info=None):
    data = {"assignee": assignee}
    if assignment_id is not None:
        data["assignment_id"] = assignment_id
    return _operate(team, user_info, alert_id, "assign", data)


@openapi_expose(
    path="alerts/acknowledge",
    method="POST",
    schema=AlertAcknowledgeRequestSerializer,
    inject="team_list_with_user",
    permission="Alarms-Edit",
    permission_app="alarm",
    summary=f"按业务告警 ID 认领告警（{_ORG_SCOPE}）",
)
def openapi_acknowledge_alert(alert_id, *, team=None, user_info=None):
    return _operate(team, user_info, alert_id, "acknowledge", {})


@openapi_expose(
    path="alerts/reassign",
    method="POST",
    schema=AlertAssignRequestSerializer,
    inject="team_list_with_user",
    permission="Alarms-Edit",
    permission_app="alarm",
    summary=f"按业务告警 ID 转派告警（{_ORG_SCOPE}）",
)
def openapi_reassign_alert(alert_id, assignee, assignment_id=None, *, team=None, user_info=None):
    data = {"assignee": assignee}
    if assignment_id is not None:
        data["assignment_id"] = assignment_id
    return _operate(team, user_info, alert_id, "reassign", data)


@openapi_expose(
    path="alerts/close",
    method="POST",
    schema=AlertCloseRequestSerializer,
    inject="team_list_with_user",
    permission="Alarms-Edit",
    permission_app="alarm",
    summary=f"按业务告警 ID 关闭告警；待响应/处理中可关，不校验是否处理人（{_ORG_SCOPE}）",
)
def openapi_close_alert(alert_id, reason="", *, team=None, user_info=None):
    data = _omit_blank({"reason": reason})
    return _operate(team, user_info, alert_id, "close", data)


@openapi_expose(
    path="alerts/batch-action",
    method="POST",
    schema=AlertBatchActionRequestSerializer,
    inject="team_list_with_user",
    permission="Alarms-Edit",
    permission_app="alarm",
    summary=f"按业务告警 ID 批量操作告警（{_ORG_SCOPE}）",
)
def openapi_batch_alert_action(action, alert_ids, assignee=None, assignment_id=None, reason="", *, team=None, user_info=None):
    data = {"alert_ids": alert_ids}
    if assignee:
        data["assignee"] = assignee
    if assignment_id is not None:
        data["assignment_id"] = assignment_id
    if reason:
        data["reason"] = reason
    return _run_alerts_openapi(lambda: _service(team, user_info).operate_alerts_batch(action, data))
