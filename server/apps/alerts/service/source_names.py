"""Alert 告警源名称：从非恢复关联事件读取，不持久化第二份来源事实。"""
from functools import reduce
from operator import and_

from django.db.models import Exists, OuterRef, Q

from apps.alerts.constants.constants import EventAction
from apps.alerts.models.models import Alert


def source_members(using="default"):
    return (
        Alert.events.through.objects.using(using)
        .exclude(event__action=EventAction.RECOVERY)
        .exclude(event__source__name__isnull=True)
        .exclude(event__source__name__regex=r"^\s*$")
    )


def source_names_by_alert(alert_pks, using="default"):
    """为已限定的一页/一批告警读取来源，调用方负责候选权限和批次上界。"""
    result = {pk: [] for pk in alert_pks}
    if not result:
        return result
    rows = source_members(using).filter(alert_id__in=result).order_by().values_list("alert_id", "event__source__name").distinct()
    for pk, name in rows:
        result[pk].append(name)
    return {pk: sorted(names) for pk, names in result.items()}


def source_names_q(operator, names):
    members = source_members().filter(alert_id=OuterRef("pk"))
    selected = members.filter(event__source__name__in=names)
    if operator == "any_of":
        return Q(Exists(selected))
    if operator == "none_of":
        return Q(Exists(members)) & ~Q(Exists(selected))
    if operator == "all_of":
        return reduce(and_, (Q(Exists(members.filter(event__source__name=name))) for name in set(names)))
    raise ValueError("无效的告警源操作符")
