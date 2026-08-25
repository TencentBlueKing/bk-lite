"""有上界、按可信团队范围过滤的目标列表查询。"""

import os

from django.db.models import Exists, OuterRef

from apps.job_mgmt.models import Target, TargetTeamMembership

_DEFAULT_PAGE_SIZE_MAX = 100
_HARD_PAGE_SIZE_MAX = 100


def _page_size_max():
    try:
        configured = int(os.getenv("JOB_TARGET_LIST_V2_MAX_PAGE_SIZE", str(_DEFAULT_PAGE_SIZE_MAX)))
    except (TypeError, ValueError):
        return _DEFAULT_PAGE_SIZE_MAX
    if configured < 1 or configured > _HARD_PAGE_SIZE_MAX:
        return _DEFAULT_PAGE_SIZE_MAX
    return configured


def _parse_int(value, error_message):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return None, error_message
    if isinstance(value, str) and not value.isdecimal():
        return None, error_message
    try:
        return int(value), None
    except ValueError:
        return None, error_message


def _parse_page(data):
    max_page_size = _page_size_max()
    page_size, error = _parse_int(data.get("page_size", 20), "page_size 参数非法")
    if error:
        return None, error
    if page_size < 1 or page_size > max_page_size:
        return None, f"page_size 范围为 1-{max_page_size}"

    raw_cursor = data.get("cursor")
    if raw_cursor in (None, ""):
        return (page_size, None), None
    cursor, error = _parse_int(raw_cursor, "cursor 必须为大于 0 的整数")
    if error or cursor < 1:
        return None, "cursor 必须为大于 0 的整数"
    return (page_size, cursor), None


def query_target_list_v2(data, authorized_team_ids):
    """按已由服务端确认的活动团队集合执行键集分页查询。"""
    if not isinstance(data, dict):
        return {"result": False, "message": "请求参数必须为对象"}
    page_info, error = _parse_page(data)
    if error:
        return {"result": False, "message": error}
    page_size, cursor = page_info

    authorized_membership = TargetTeamMembership.objects.filter(target_id=OuterRef("id"), team_id__in=authorized_team_ids)
    queryset = Target.objects.filter(Exists(authorized_membership))
    for field in ("name", "ip", "os_type"):
        value = data.get(field)
        if value:
            lookup = f"{field}__icontains" if field in {"name", "ip"} else field
            queryset = queryset.filter(**{lookup: value})

    if cursor is not None:
        queryset = queryset.filter(id__lt=cursor)
    rows = list(queryset.order_by("-id").values("id", "name", "ip", "os_type", "cloud_region_id")[: page_size + 1])
    has_more = len(rows) > page_size
    rows = rows[:page_size]
    items = [
        {
            "target_id": row["id"],
            "name": row["name"],
            "ip": str(row["ip"]),
            "os_type": row["os_type"],
            "cloud_region_id": row["cloud_region_id"],
        }
        for row in rows
    ]
    return {
        "result": True,
        "data": {
            "items": items,
            "next_cursor": rows[-1]["id"] if has_more else None,
            "has_more": has_more,
        },
    }
