from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.utils import timezone

DEFAULT_CREATOR_TIMEZONE = "Asia/Shanghai"


def normalize_creator_timezone(timezone_name: str | None) -> str:
    if not timezone_name or not isinstance(timezone_name, str):
        return DEFAULT_CREATOR_TIMEZONE
    candidate = timezone_name.strip()
    if not candidate:
        return DEFAULT_CREATOR_TIMEZONE
    try:
        ZoneInfo(candidate)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return DEFAULT_CREATOR_TIMEZONE
    return candidate


def resolve_creator_timezone(
    creator_username: str,
    *,
    domain: str | None = None,
) -> str:
    from apps.system_mgmt.models import User

    queryset = User.objects.filter(username=creator_username)
    if domain:
        queryset = queryset.filter(domain=domain)
    user = queryset.order_by("id").first()
    return normalize_creator_timezone(
        getattr(user, "timezone", None) if user else None
    )


def format_report_local_time(
    value: datetime,
    timezone_name: str | None,
    fmt: str,
) -> str:
    zone_name = normalize_creator_timezone(timezone_name)
    try:
        zone = ZoneInfo(zone_name)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        zone = ZoneInfo(DEFAULT_CREATOR_TIMEZONE)
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.utc)
    return value.astimezone(zone).strftime(fmt)
