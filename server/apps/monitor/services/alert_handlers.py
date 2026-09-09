"""监控告警认领 / 分派，与处理人名单同一事务写认领 / 分派事件。"""

import uuid

from django.db import transaction
from django.utils import timezone

from apps.core.logger import monitor_logger as logger
from apps.core.utils.viewset_utils import build_json_membership_query
from apps.monitor.models import MonitorAlert, MonitorEvent, MonitorPolicy
from apps.monitor.services.alert_lifecycle_notify import AlertLifecycleNotifier
from apps.monitor.utils.user_display import format_notice_users
from apps.system_mgmt.models import User


class AlertHandlerConflict(Exception):
    """已有处理人或告警非活跃。"""


class AlertHandlerInvalid(Exception):
    """分派名单校验失败。"""


class AlertHandlerForbidden(Exception):
    """看不见或无操作权限。"""


ACTIVE_STATUS = "new"


def _is_int_identifier(value) -> bool:
    if isinstance(value, bool):
        return False
    return isinstance(value, int) or (isinstance(value, str) and value.isdigit())


def current_handler_identifier(actor) -> int | str:
    queryset = User.objects.filter(username=actor.username)
    domain = getattr(actor, "domain", None)
    if domain:
        matched = queryset.filter(domain=domain).first()
        if matched is not None:
            return matched.id
    matched = queryset.first()
    if matched is not None:
        return matched.id
    return actor.username


def is_my_alert_query(request) -> bool:
    query_params = getattr(request, "query_params", None)
    if query_params is not None:
        value = query_params.get("my_alert")
    else:
        value = request.GET.get("my_alert")
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def handler_match_values(actor) -> list:
    values = []
    identifier = current_handler_identifier(actor)
    if identifier not in (None, ""):
        values.append(identifier)
    username = getattr(actor, "username", None)
    if username and username not in values:
        values.append(username)
    return values


def filter_my_handler_alerts(queryset, actor):
    return queryset.filter(build_json_membership_query(queryset, "handlers", handler_match_values(actor)))


def _lock_assignable_alert(alert_id, *, operable_qs=None) -> MonitorAlert:
    try:
        locked = MonitorAlert.objects.select_for_update().get(pk=alert_id)
    except MonitorAlert.DoesNotExist as exc:
        raise AlertHandlerForbidden("没有操作该告警的权限") from exc
    if operable_qs is not None and not operable_qs.filter(pk=locked.pk).exists():
        raise AlertHandlerForbidden("没有操作该告警的权限")
    if locked.status != ACTIVE_STATUS:
        raise AlertHandlerConflict("只有空处理人的活跃告警可以认领或分派")
    if list(locked.handlers or []):
        raise AlertHandlerConflict("告警已有处理人")
    return locked


def _lookup_user(identifier) -> User | None:
    if identifier in (None, "") or isinstance(identifier, bool):
        return None
    if _is_int_identifier(identifier):
        user = User.objects.filter(id=int(identifier)).first()
        if user is not None:
            return user
    return User.objects.filter(username=str(identifier)).first()


def _user_in_organizations(user, organization_ids) -> bool:
    allowed = {int(item) for item in organization_ids or [] if item not in (None, "")}
    if not allowed:
        return False
    for item in user.group_list or []:
        group_id = item.get("id") if isinstance(item, dict) else item
        if group_id in (None, ""):
            continue
        try:
            if int(group_id) in allowed:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _normalize_handlers(identifiers, organization_ids, *, allow_empty: bool, scope_label: str) -> list:
    if not identifiers:
        if allow_empty:
            return []
        raise AlertHandlerInvalid("至少指定一名处理人")
    resolved = []
    seen = set()
    for raw in identifiers:
        user = _lookup_user(raw)
        if user is None:
            raise AlertHandlerInvalid("处理人不存在")
        if user.disabled:
            raise AlertHandlerInvalid("处理人已禁用")
        if not _user_in_organizations(user, organization_ids):
            raise AlertHandlerInvalid(f"处理人不属于{scope_label}所属组织")
        if user.id in seen:
            continue
        seen.add(user.id)
        resolved.append(user.id)
    if not resolved:
        raise AlertHandlerInvalid("至少指定一名处理人")
    return resolved


def normalize_assign_handlers(identifiers, organization_ids) -> list:
    return _normalize_handlers(identifiers, organization_ids, allow_empty=False, scope_label="告警")


def normalize_policy_handlers(identifiers, organization_ids) -> list:
    return _normalize_handlers(identifiers, organization_ids, allow_empty=True, scope_label="策略")


def _schedule_assign_notification(alert: MonitorAlert) -> None:
    policy_id = alert.policy_id
    alert_id = alert.id

    def _notify():
        policy = MonitorPolicy.objects.filter(id=policy_id).first()
        if policy is None or not policy.notice:
            logger.debug(
                "event=assign_notify_skipped alert_id=%s reason=%s",
                alert_id,
                "policy_deleted" if policy is None else "notice_off",
            )
            return
        current = MonitorAlert.objects.filter(id=alert_id).first()
        if current is None:
            return
        AlertLifecycleNotifier(policy).notify_assigned([current])

    transaction.on_commit(_notify)


def _actor_name(actor) -> str:
    return getattr(actor, "username", "") or str(actor)


def _handler_event_content(action, *, actor, handlers) -> str:
    names = "、".join(format_notice_users(handlers)) or str(handlers)
    operator = _actor_name(actor)
    if action == MonitorEvent.Action.CLAIMED:
        return f"{operator} 认领，处理人变为 {names}"
    return f"{operator} 分派给 {names}"


def _write_handler_event(alert: MonitorAlert, *, action, actor) -> None:
    MonitorEvent.objects.create(
        id=uuid.uuid4().hex,
        alert_id=alert.id,
        policy_id=alert.policy_id,
        monitor_instance_id=alert.monitor_instance_id,
        metric_instance_id=alert.metric_instance_id or "",
        dimensions=alert.dimensions or {},
        value=alert.value,
        level=alert.level or "info",
        action=action,
        content=_handler_event_content(action, actor=actor, handlers=alert.handlers),
        notice_result=[],
        event_time=timezone.now(),
    )


def claim_alert(alert: MonitorAlert, *, actor, operable_qs=None) -> MonitorAlert:
    with transaction.atomic():
        locked = _lock_assignable_alert(alert.pk, operable_qs=operable_qs)
        locked.handlers = [current_handler_identifier(actor)]
        locked.save(update_fields=["handlers", "updated_at"])
        _write_handler_event(locked, action=MonitorEvent.Action.CLAIMED, actor=actor)
    logger.info("event=alert_claimed alert_id=%s", alert.pk)
    return MonitorAlert.objects.get(pk=alert.pk)


def assign_alert(alert: MonitorAlert, *, handlers, actor, operable_qs=None) -> MonitorAlert:
    with transaction.atomic():
        locked = _lock_assignable_alert(alert.pk, operable_qs=operable_qs)
        locked.handlers = normalize_assign_handlers(handlers, locked.organizations)
        locked.save(update_fields=["handlers", "updated_at"])
        _write_handler_event(locked, action=MonitorEvent.Action.ASSIGNED, actor=actor)
        _schedule_assign_notification(locked)
    logger.info("event=alert_assigned alert_id=%s handler_count=%s", alert.pk, len(locked.handlers))
    return MonitorAlert.objects.get(pk=alert.pk)
