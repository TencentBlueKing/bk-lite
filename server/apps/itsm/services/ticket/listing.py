"""工单列表的列契约与有界筛选。"""
from datetime import timedelta

from django.contrib.postgres.search import SearchQuery, SearchVector
from django.db import connection
from django.db.models import Exists, F, OuterRef, Prefetch, Q
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from apps.itsm.models import TicketFollower, TicketSLARecord, TicketTask
from apps.itsm.models.extend import VipUser
from apps.itsm.services.ticket.form_filters import InvalidFormFilter, apply_form_filters, field_catalog, read_form_filters
from apps.itsm.views.access import domain_of

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
    if not isinstance(value, dict) or set(value) - FILTER_KEYS - {"form_filters"}:
        raise ValueError("不支持的筛选条件")
    form_filters = read_form_filters(value.get("form_filters", []))
    value = {key: item for key, item in value.items() if key in FILTER_KEYS}
    if any(not isinstance(v, str) or len(v) > 200 for v in value.values()):
        raise ValueError("筛选条件过长或格式错误")
    value = {key: item.strip() for key, item in value.items() if item.strip()}
    if value.get("tab", "all") not in TABS or value.get("ordering", "-created_at") not in SORTS | {f"-{key}" for key in SORTS}:
        raise ValueError("不支持的分组或排序")
    for key in ("created_after", "created_before"):
        if value.get(key):
            date_bound(value[key], key == "created_before")
    if value.get("workflow_id"):
        workflow_id = value["workflow_id"]
        if not workflow_id.isascii() or not workflow_id.isdecimal() or len(workflow_id) > 18 or int(workflow_id) < 1:
            raise ValueError("流程标识无效")
    if form_filters:
        if "workflow_id" not in value:
            raise InvalidFormFilter("请先选择流程")
        value["form_filters"] = form_filters
    return value


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


def filtered_tickets(request, scoped_tickets, filters, catalog=None):
    queryset = scoped_tickets
    ordering = filters.get("ordering")
    if ordering:
        queryset = queryset.order_by(ordering.replace("status", "status__key"), "-id")
    else:
        queryset = queryset.annotate(
            _vip=Exists(VipUser.objects.filter(domain=domain_of(request), username=OuterRef("creator"), is_enabled=True))
        ).order_by("-_vip", "-id")
    if status := filters.get("status"):
        queryset = queryset.filter(status__key__in=status.split(","))
    for key, lookup in {"creator": "creator", "workflow_id": "workflow_id", "priority": "form_data__priority"}.items():
        if key in filters:
            queryset = queryset.filter(**{lookup: filters[key]})
    if tag := filters.get("tag"):
        queryset = queryset.filter(tags__name=tag).distinct()
    if after := filters.get("created_after"):
        queryset = queryset.filter(created_at__gte=date_bound(after))
    if before := filters.get("created_before"):
        queryset = queryset.filter(created_at__lt=date_bound(before, end=True))
    if keyword := filters.get("q"):
        conditions = Q(title__icontains=keyword) | Q(sn__icontains=keyword)
        if connection.vendor == "postgresql":
            queryset = queryset.alias(_search=SearchVector("title", "sn", config="simple"))
            conditions |= Q(_search=SearchQuery(keyword, config="simple"))
        queryset = queryset.filter(conditions)
    if clauses := filters.get("form_filters"):
        if catalog is None:
            catalog = field_catalog(request, scoped_tickets, filters["workflow_id"])
        queryset = apply_form_filters(queryset, catalog, clauses)
    return personal_group(queryset, filters.get("tab", "all"), request.user.username)


def project_columns(queryset, wanted):
    queryset = queryset.defer("form_data")
    if "status" in wanted:
        queryset = queryset.select_related("status")
    if "workflow" in wanted:
        queryset = queryset.select_related("workflow")
    if wanted.intersection({"node", "assignees"}):
        queryset = queryset.prefetch_related(Prefetch("tasks", queryset=TicketTask.objects.filter(status__in=["pending", "claimed"])))
    if "sla" in wanted:
        queryset = queryset.prefetch_related(
            Prefetch("sla_records", queryset=TicketSLARecord.objects.filter(finished_at__isnull=True).order_by("id"))
        )
    if "priority" in wanted:
        queryset = queryset.annotate(_priority=F("form_data__priority"))
    return queryset
