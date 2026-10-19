"""告警展示时间。

页面和接口按当前用户的时区出钟面，通知按第一个接收人的账号时区。
没有用户或时区无效时回退 Asia/Shanghai。格式固定为秒级、不带偏移。
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.utils import timezone

from apps.core.logger import alert_logger as logger

DEFAULT_DISPLAY_TIMEZONE = "Asia/Shanghai"
DISPLAY_FORMAT = "%Y-%m-%d %H:%M:%S"


def coerce_display_timezone(timezone_name):
    """合法时区名转成 ZoneInfo，否则回退默认展示时区。"""
    if isinstance(timezone_name, str) and timezone_name.strip():
        try:
            return ZoneInfo(timezone_name.strip())
        except Exception:
            logger.warning("invalid display timezone %s, fallback to %s", timezone_name, DEFAULT_DISPLAY_TIMEZONE)
    return ZoneInfo(DEFAULT_DISPLAY_TIMEZONE)


def resolve_display_timezone(usernames):
    """按名单顺序取第一个账号时区；查不到或时区无效时回退默认展示时区。"""
    names = []
    for item in usernames or []:
        name = str(item or "").strip()
        if name and name not in names:
            names.append(name)
    if not names:
        return DEFAULT_DISPLAY_TIMEZONE
    try:
        from apps.system_mgmt.models.user import User

        found = {user.username: user.timezone for user in User.objects.filter(username__in=names).only("username", "timezone")}
    except Exception:
        logger.warning("failed to resolve display timezone, fallback to %s", DEFAULT_DISPLAY_TIMEZONE)
        return DEFAULT_DISPLAY_TIMEZONE
    for name in names:
        tz_name = found.get(name)
        if not isinstance(tz_name, str) or not tz_name.strip():
            continue
        try:
            ZoneInfo(tz_name.strip())
        except Exception:
            logger.warning("invalid user timezone %s, fallback to %s", tz_name, DEFAULT_DISPLAY_TIMEZONE)
            continue
        return tz_name.strip()
    return DEFAULT_DISPLAY_TIMEZONE


def format_template_datetime(value, timezone_name=None):
    """把时刻转成指定时区的钟面。非时间值原样返回。"""
    if isinstance(value, datetime):
        if timezone.is_naive(value):
            value = timezone.make_aware(value, timezone.utc)
        return timezone.localtime(value, coerce_display_timezone(timezone_name)).strftime(DISPLAY_FORMAT)
    if isinstance(value, date):
        return value.isoformat()
    return value
