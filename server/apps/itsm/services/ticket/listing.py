"""工单列表的列契约与有界筛选。"""
from datetime import timedelta

from django.db.models import Exists, OuterRef
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from apps.itsm.models import TicketFollower, TicketTask

COLUMNS = ["sn", "title", "status", "creator", "node", "assignees", "workflow", "created_at", "updated_at", "priority", "sla"]
DEFAULT_COLUMNS = ["sn", "title", "status", "creator", "node", "created_at"]
TABS = {"all", "mine", "created", "following", "history"}
SORTS = {"sn", "title", "status", "creator", "created_at", "updated_at"}
FILTER_KEYS = {"q", "creator", "priority", "tag", "status", "tab", "ordering", "created_after", "created_before", "workflow_id"}


def validate_columns(value):
    if value is None:
        return DEFAULT_COLUMNS.copy()
    if not isinstance(value, list) or not 1 <= len(value) <= len(COLUMNS) or any(not isinstance(key, str) or key not in COLUMNS for key in value):
        raise ValueError("不支持的展示列")
    return list(dict.fromkeys(["sn", "title", *value]))


def validate_filters(value):
    if not isinstance(value, dict) or set(value) - FILTER_KEYS:
        raise ValueError("不支持的筛选条件")
    if any(not isinstance(v, str) or len(v) > 200 for v in value.values()):
        raise ValueError("筛选条件过长或格式错误")
    value = {key: item.strip() for key, item in value.items() if item.strip()}
    if value.get("tab", "all") not in TABS or value.get("ordering", "-created_at") not in SORTS | {f"-{key}" for key in SORTS}:
        raise ValueError("不支持的分组或排序")
    for key in ("created_after", "created_before"):
        if value.get(key):
            date_bound(value[key], key == "created_before")
    return {k: v.strip() for k, v in value.items() if v.strip()}


def date_bound(value, end=False):
    day = parse_date(value)
    if day:
        result = timezone.datetime.combine(day, timezone.datetime.min.time())
        if end:
            result += timedelta(days=1)
    else:
        result = parse_datetime(value)
    if result is None:
        raise ValueError("日期格式错误")
    return timezone.make_aware(result) if timezone.is_naive(result) else result


def personal_group(queryset, tab, username):
    if tab == "created":
        return queryset.filter(creator=username)
    if tab == "following":
        return queryset.filter(Exists(TicketFollower.objects.filter(ticket_id=OuterRef("pk"), username=username)))
    if tab in {"mine", "history"}:
        statuses = ["done"] if tab == "history" else ["pending", "claimed"]
        return queryset.filter(Exists(TicketTask.objects.filter(ticket_id=OuterRef("pk"), assignee=username, status__in=statuses)))
    return queryset
