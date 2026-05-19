from datetime import timedelta

from django.utils import timezone

from apps.system_mgmt.models import SystemSettings


USER_STATUS_DISABLED = "disabled"
USER_STATUS_LOCKED = "locked"
USER_STATUS_PASSWORD_EXPIRED = "password_expired"
USER_STATUS_NORMAL = "normal"


def _get_int_setting(key, default):
    setting = SystemSettings.objects.filter(key=key).first()
    if not setting:
        return default

    try:
        return int(setting.value)
    except (TypeError, ValueError):
        return default


def get_password_validity_days(default=180):
    return _get_int_setting("pwd_set_validity_period", default)


def get_password_expiry_reminder_days(default=7):
    return _get_int_setting("pwd_set_expiry_reminder_days", default)


def is_user_locked(user, now=None):
    now = now or timezone.now()
    return bool(user.account_locked_until and user.account_locked_until > now)


def get_password_expiry_info(user, now=None, validity_days=None, default_validity_days=180):
    now = now or timezone.now()
    validity_days = validity_days if validity_days is not None else get_password_validity_days(default_validity_days)
    password_last_modified = getattr(user, "password_last_modified", None)

    if validity_days <= 0 or password_last_modified is None:
        return {
            "validity_days": validity_days,
            "expire_date": None,
            "days_until_expire": None,
            "is_expired": False,
        }

    expire_date = password_last_modified + timedelta(days=validity_days)
    days_until_expire = (expire_date - now).days
    return {
        "validity_days": validity_days,
        "expire_date": expire_date,
        "days_until_expire": days_until_expire,
        "is_expired": days_until_expire <= 0,
    }


def get_user_derived_status(user, now=None, validity_days=None, default_validity_days=180):
    now = now or timezone.now()
    if getattr(user, "disabled", False):
        return USER_STATUS_DISABLED

    if is_user_locked(user, now=now):
        return USER_STATUS_LOCKED

    expiry_info = get_password_expiry_info(
        user,
        now=now,
        validity_days=validity_days,
        default_validity_days=default_validity_days,
    )
    if expiry_info["is_expired"]:
        return USER_STATUS_PASSWORD_EXPIRED

    return USER_STATUS_NORMAL
