import pytz
from django.utils import timezone as django_timezone
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

DEFAULT_USER_TIMEZONE = "Asia/Shanghai"


def resolve_user_timezone(name: str | None) -> str:
    """合法 IANA 时区原样返回，缺失或非法时回退 Asia/Shanghai。"""
    candidate = str(name or "").strip() or DEFAULT_USER_TIMEZONE
    try:
        pytz.timezone(candidate)
    except pytz.UnknownTimeZoneError:
        return DEFAULT_USER_TIMEZONE
    return candidate


@tool()
def get_current_time(config: RunnableConfig = None) -> str:
    """获取当前用户时区下的当前时间。

    时区来自当前用户配置。缺失或非法时使用 Asia/Shanghai。
    返回 ``YYYY-MM-DD HH:MM:SS (时区名)``。
    """
    configurable = {}
    if isinstance(config, dict):
        configurable = config.get("configurable") or {}
    tz_name = resolve_user_timezone(configurable.get("user_timezone"))
    current = django_timezone.localtime(django_timezone.now(), pytz.timezone(tz_name))
    return f"{current.strftime('%Y-%m-%d %H:%M:%S')} ({tz_name})"
