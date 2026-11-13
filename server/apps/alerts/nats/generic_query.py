"""告警中心通用查询 NATS handler。告警与事件不混用。"""

from django.db.models import Q

import nats_client
from apps.alerts.constants.constants import PERMISSION_EVENT
from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Event
from apps.alerts.nats.nats import _build_permission_user, _get_authorized_alert_queryset
from apps.alerts.services.generic_query import GenericQueryError, ensure_payload_limit
from apps.alerts.services.generic_query import query_alert_center as run_alert_center_query
from apps.core.logger import alert_logger as logger
from apps.core.utils.permission_utils import get_permission_rules
from apps.core.utils.viewset_utils import GenericViewSetFun, build_json_membership_query


def _ok(data) -> dict:
    ensure_payload_limit(data)
    return {"result": True, "data": data, "message": ""}


def _fail(message: str, status: str = "failed") -> dict:
    return {"result": False, "data": {"status": status}, "message": message}


def _guard(stage: str):
    def decorate(func):
        def wrapped(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except GenericQueryError as exc:
                return _fail(exc.message, exc.status)
            except Exception as exc:
                logger.exception(
                    "event=alert_generic_query_failed failed_stage=%s error_type=%s",
                    stage,
                    type(exc).__name__,
                )
                return _fail("查询失败", "failed")

        wrapped.__name__ = func.__name__
        return wrapped

    return decorate


def _app_permissions(user_info: dict) -> set[str]:
    permission_data = (user_info or {}).get("permission", {})
    if isinstance(permission_data, dict):
        values = permission_data.get("alarm", [])
    elif isinstance(permission_data, (set, list, tuple)):
        values = permission_data
    else:
        values = []
    return {str(item) for item in values}


def _event_view_allowed(user_info: dict) -> bool:
    if (user_info or {}).get("is_superuser"):
        return True
    granted = _app_permissions(user_info)
    return "Integration-View" in granted or "Alarms-View" in granted


def _scoped_team_ids(user_info: dict) -> list[int]:
    current_team = (user_info or {}).get("team")
    team_ids = [int(current_team)]
    if (user_info or {}).get("include_children"):
        children = GenericViewSetFun.extract_child_group_ids((user_info or {}).get("group_tree", []), int(current_team))
        if children:
            team_ids = [int(item) for item in children]
    return team_ids


def _reject_unsupported_filters(kwargs: dict) -> None:
    filters = kwargs.get("filters") if isinstance(kwargs, dict) else None
    if filters not in (None, "", []):
        raise GenericQueryError("当前查询不支持 filters")


def _event_queryset(user_info: dict):
    """对齐事件列表：Integration-View 或 Alarms-View，再加上 PERMISSION_EVENT 的实例和团队规则。"""
    user_info = user_info or {}
    if user_info.get("team") in (None, ""):
        raise GenericQueryError("缺少组织信息", status="forbidden")
    if not _event_view_allowed(user_info):
        raise GenericQueryError("权限不足", status="forbidden")
    base = Event.objects.select_related("source")
    org_query = build_json_membership_query(base, "team", _scoped_team_ids(user_info))
    if user_info.get("is_superuser"):
        return base.filter(org_query)
    permission_user = _build_permission_user(user_info)
    if not permission_user:
        raise GenericQueryError("缺少用户信息", status="forbidden")
    permission_data = get_permission_rules(
        permission_user,
        int(user_info.get("team")),
        "alerts",
        PERMISSION_EVENT,
        bool(user_info.get("include_children", False)),
    )
    if not isinstance(permission_data, dict):
        permission_data = {}
    instance_ids = [item["id"] for item in permission_data.get("instance", []) if isinstance(item, dict) and item.get("id") is not None]
    permission_teams = permission_data.get("team") or []
    if not instance_ids and not permission_teams:
        return Event.objects.none()
    permission_query = Q()
    if instance_ids:
        permission_query |= Q(id__in=instance_ids)
    if permission_teams:
        permission_query |= build_json_membership_query(base, "team", permission_teams)
    return base.filter(org_query & permission_query)


@nats_client.register
@_guard("query_alert_center")
def query_alert_center(
    query_object=None,
    analysis_mode=None,
    source=None,
    level=None,
    status=None,
    time_field=None,
    time_range=None,
    group_by=None,
    order=None,
    page=None,
    page_size=None,
    user_info=None,
    **kwargs,
):
    _reject_unsupported_filters(kwargs)
    del kwargs
    target = str(query_object or "").strip()
    if target == "alert":
        queryset, error = _get_authorized_alert_queryset(user_info or {})
        if error:
            message = error.get("message") or "无权限"
            if message == "Insufficient permissions":
                message = "权限不足"
            status_name = "forbidden" if message != "查询失败" else "failed"
            raise GenericQueryError(message, status=status_name)
        if not (user_info or {}).get("is_superuser"):
            queryset = queryset.filter(build_json_membership_query(queryset, "team", _scoped_team_ids(user_info or {})))
    elif target == "event":
        queryset = _event_queryset(user_info or {})
    else:
        raise GenericQueryError("查询对象必须是告警或事件")
    data = run_alert_center_query(
        queryset,
        query_object=target,
        analysis_mode=analysis_mode or "detail",
        source=source,
        level=level,
        status=status,
        time_field=time_field,
        time_range=time_range,
        group_by=group_by,
        order=order,
        page=page,
        page_size=page_size,
    )
    return _ok(data)


@nats_client.register
@_guard("list_alert_source_options")
def list_alert_source_options(user_info=None, **kwargs):
    del kwargs
    alerts, error = _get_authorized_alert_queryset(user_info or {})
    if error:
        message = error.get("message") or "无权限"
        if message == "Insufficient permissions":
            message = "权限不足"
        raise GenericQueryError(message, status="forbidden")
    if not (user_info or {}).get("is_superuser"):
        alerts = alerts.filter(build_json_membership_query(alerts, "team", _scoped_team_ids(user_info or {})))
    # 告警来源没有组织字段。只返回当前可见告警实际用到的启用来源。
    visible_ids = alerts.filter(events__source__is_active=True).values_list("events__source__source_id", flat=True).distinct()
    sources = AlertSource.objects.filter(is_active=True, source_id__in=list(visible_ids)).order_by("name", "source_id")
    data = [{"source_id": item.source_id, "name": item.name} for item in sources]
    ensure_payload_limit(data)
    return {"result": True, "data": data, "message": ""}
