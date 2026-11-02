from datetime import datetime

from django.utils import timezone


def is_account_expired(user, now=None) -> bool:
    expires_at = getattr(user, "account_expires_at", None)
    if not isinstance(expires_at, datetime):
        return False
    current = now or timezone.now()
    if timezone.is_naive(expires_at):
        expires_at = timezone.make_aware(expires_at, timezone.get_current_timezone())
    return expires_at <= current


def is_user_access_disabled(user) -> bool:
    return bool(getattr(user, "disabled", False))
