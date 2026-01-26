from enum import Enum
from datetime import timedelta
from django.utils import timezone


class WindowType(str, Enum):
    SLIDING = "sliding"
    SESSION = "session"
    FIXED = "fixed"


class WindowConfig:
    def __init__(
        self,
        window_type: WindowType,
        window_size_minutes: int,
        session_timeout_minutes: int = 10,
    ):
        self.window_type = window_type
        self.window_size_minutes = window_size_minutes
        self.session_timeout_minutes = session_timeout_minutes

    @property
    def is_session_window(self) -> bool:
        return self.window_type == WindowType.SESSION

    def get_window_start(self):
        return timezone.now() - timedelta(minutes=self.window_size_minutes)

    def get_session_end_time(self):
        timeout = self.session_timeout_minutes or self.window_size_minutes
        return timezone.now() + timedelta(minutes=timeout)


class WindowFactory:
    DEFAULT_WINDOW_SIZE = 10
    DEFAULT_SESSION_TIMEOUT = 10

    @staticmethod
    def create_from_strategy(strategy) -> WindowConfig:
        params = strategy.params or {}

        window_size = params.get("window_size", WindowFactory.DEFAULT_WINDOW_SIZE)
        time_out = params.get("time_out", False)
        session_timeout = params.get(
            "time_minutes", WindowFactory.DEFAULT_SESSION_TIMEOUT
        )

        if time_out:
            return WindowConfig(
                window_type=WindowType.SESSION,
                window_size_minutes=window_size,
                session_timeout_minutes=session_timeout,
            )

        return WindowConfig(
            window_type=WindowType.SLIDING,
            window_size_minutes=window_size,
        )
