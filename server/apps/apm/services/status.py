from datetime import datetime, timedelta

from django.utils import timezone


ACTIVE_WINDOW = timedelta(minutes=15)
ARCHIVE_WINDOW = timedelta(days=7)


def catalog_status(*, last_seen_at: datetime, archived_at: datetime | None, observed_at: datetime | None = None) -> str:
    if archived_at is not None:
        return "archived"
    now = observed_at or timezone.now()
    if last_seen_at >= now - ACTIVE_WINDOW:
        return "active"
    return "silent"
