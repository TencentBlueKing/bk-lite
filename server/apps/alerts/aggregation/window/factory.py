import re
from datetime import timedelta
from enum import Enum

from django.utils import timezone

from apps.alerts.utils.util import parse_aggregation_window_size

_NON_NEGATIVE_INTEGER_TEXT = re.compile(r"^[0-9]+$")
_SESSION_TIMEOUT_ERROR = "观察时间必须为大于等于 0 的整数分钟。"


def parse_session_timeout_minutes(value):
    """把观察时间收成非负 int。布尔、小数、负数和非数字字符串拒绝。"""
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError(_SESSION_TIMEOUT_ERROR)
    if isinstance(value, str):
        text = value.strip()
        if not _NON_NEGATIVE_INTEGER_TEXT.fullmatch(text):
            raise ValueError(_SESSION_TIMEOUT_ERROR)
        return int(text)
    if value < 0:
        raise ValueError(_SESSION_TIMEOUT_ERROR)
    return value


def coerce_session_timeout_minutes(value, default=0):
    """读取存量配置时使用。收不成的按 default，避免把原字符串交给 timedelta。"""
    try:
        return parse_session_timeout_minutes(value)
    except (TypeError, ValueError):
        return default


class WindowType(str, Enum):
    SLIDING = "sliding"
    SESSION = "session"
    FIXED = "fixed"


class WindowConfig:
    def __init__(
        self,
        window_type: WindowType,
        window_size_minutes: int,
        session_timeout_minutes: int = 0,
        window_end=None,
    ):
        self.window_type = window_type
        self.window_size_minutes = window_size_minutes
        self.session_timeout_minutes = session_timeout_minutes
        self.window_end = window_end

    @property
    def is_session_window(self) -> bool:
        return self.window_type == WindowType.SESSION

    def get_window_end(self):
        if self.window_end is not None:
            return self.window_end
        return timezone.now()

    def get_window_start(self):
        return self.get_window_end() - timedelta(minutes=self.window_size_minutes)

    def get_session_end_time(self):
        timeout = self.session_timeout_minutes or self.window_size_minutes
        return self.get_window_end() + timedelta(minutes=timeout)


class WindowFactory:
    DEFAULT_WINDOW_SIZE = 10
    DEFAULT_SESSION_TIMEOUT = 10

    @staticmethod
    def create_from_strategy(strategy, window_end=None) -> WindowConfig:
        params = strategy.params or {}

        raw_window_size = params.get("window_size")
        window_size, _ = parse_aggregation_window_size(
            raw_window_size,
            default=WindowFactory.DEFAULT_WINDOW_SIZE,
            clamp=True,
        )
        time_out = params.get("time_out", False)
        raw_session_timeout = params.get("time_minutes", WindowFactory.DEFAULT_SESSION_TIMEOUT)
        session_timeout_minutes = coerce_session_timeout_minutes(raw_session_timeout)
        session_enabled = bool(time_out) and session_timeout_minutes > 0

        if session_enabled:
            return WindowConfig(
                window_type=WindowType.SESSION,
                window_size_minutes=window_size,
                session_timeout_minutes=session_timeout_minutes,
                window_end=window_end,
            )

        return WindowConfig(
            window_type=WindowType.SLIDING,
            window_size_minutes=window_size,
            session_timeout_minutes=0,
            window_end=window_end,
        )
