"""日志只读查询。组织集合只接受网关注入。"""

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from apps.core.utils.time_util import format_rfc3339_utc
from apps.log.models.log_group import LogGroup, LogGroupOrganization
from apps.log.services.search import SearchService

LOG_SEARCH_WINDOW = timedelta(hours=1)
MESSAGE_LIMIT = 2048
FIELD_LIMIT = 512
MAX_FIELDS = 32
_SKIPPED_FIELDS = {"message", "_time", "_msg", "log_message", "raw_message", "trap_message"}


def team_ids(team):
    ids = []
    for item in team or []:
        try:
            value = int(item)
        except (TypeError, ValueError):
            continue
        if value > 0:
            ids.append(value)
    return ids


def list_groups(*, team, page, page_size, keyword):
    ids = team_ids(team)
    if not ids:
        return _page(LogGroup.objects.none(), page, page_size)
    owned = LogGroupOrganization.objects.filter(organization__in=ids).values("log_group_id")
    queryset = LogGroup.objects.filter(id__in=owned).order_by("name", "id")
    if keyword:
        queryset = queryset.filter(Q(name__icontains=keyword))
    return _page(queryset, page, page_size)


def search_logs(*, team, log_group_id, start, end, query="*", limit=20):
    start, end = _aware(start), _aware(end)
    if end <= start:
        return {"result": False, "message": "开始时间必须早于结束时间"}
    if end - start > LOG_SEARCH_WINDOW:
        return {"result": False, "message": "查询时间范围不能超过 1 小时"}
    group = _owned_group(team, log_group_id)
    if group is None:
        return {"result": False, "message": "日志分组不存在"}
    try:
        rows = SearchService.search_logs(
            query or "*",
            format_rfc3339_utc(start),
            format_rfc3339_utc(end),
            limit,
            [group.id],
            resolved_groups=[group],
        )
    except Exception:
        return {"result": False, "message": "日志查询失败"}
    if not isinstance(rows, list):
        return {"result": False, "message": "日志查询失败"}
    return {"items": [_public_event(row) for row in rows[:limit]], "limit": limit}


def _owned_group(team, log_group_id):
    ids = team_ids(team)
    if not ids:
        return None
    return (
        LogGroup.objects.filter(
            id=log_group_id,
            loggrouporganization__organization__in=ids,
        )
        .distinct()
        .first()
    )


def _page(queryset, page, page_size):
    total = queryset.count()
    start = (page - 1) * page_size
    return {
        "count": total,
        "page": page,
        "page_size": page_size,
        "items": [{"id": row.id, "name": row.name} for row in queryset[start : start + page_size]],
    }


def _public_event(event):
    if not isinstance(event, dict):
        return {"message": "", "fields": {}, "truncated": False}
    message = event.get("message")
    text = message if isinstance(message, str) else ""
    truncated = len(text) > MESSAGE_LIMIT
    fields = {}
    for key, value in event.items():
        if key in _SKIPPED_FIELDS or not isinstance(key, str):
            continue
        if isinstance(value, (dict, list)) or value is None:
            truncated = True
            continue
        if not isinstance(value, (str, int, float, bool)):
            truncated = True
            continue
        rendered = value[:FIELD_LIMIT] if isinstance(value, str) else value
        if isinstance(value, str) and len(value) > FIELD_LIMIT:
            truncated = True
        fields[key[:64]] = rendered
        if len(fields) >= MAX_FIELDS:
            truncated = True
            break
    item = {"message": text[:MESSAGE_LIMIT], "fields": fields, "truncated": truncated}
    timestamp = event.get("_time")
    if isinstance(timestamp, (str, int, float)):
        item["time"] = timestamp if not isinstance(timestamp, str) else timestamp[:64]
    return item


def _aware(value):
    if timezone.is_naive(value):
        return timezone.make_aware(value, timezone.utc)
    return value
