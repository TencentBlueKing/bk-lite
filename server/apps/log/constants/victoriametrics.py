import os
from datetime import datetime, timedelta, timezone

from apps.core.utils.time_util import format_rfc3339_utc, parse_rfc3339_utc


class VictoriaLogsConstants:
    """VictoriaLogs服务相关常量"""

    # VictoriaLogs服务信息
    HOST = os.getenv("VICTORIALOGS_HOST")
    USER = os.getenv("VICTORIALOGS_USER")
    PWD = os.getenv("VICTORIALOGS_PWD")

    # SSL验证配置，支持环境变量控制
    SSL_VERIFY = os.getenv("VICTORIALOGS_SSL_VERIFY", "false").lower() == "true"

    # SSE连接配置
    MAX_CONNECTION_TIME = int(os.getenv("SSE_MAX_CONNECTION_TIME", "1800"))  # 默认30分钟
    KEEPALIVE_INTERVAL = int(os.getenv("SSE_KEEPALIVE_INTERVAL", "45"))  # 默认45秒

    # 查询保护：避免单次日志检索返回过大结果集，拖慢 VMLogs 和 Web 响应。
    QUERY_LIMIT_MAX = int(os.getenv("VICTORIALOGS_QUERY_LIMIT_MAX", "1000"))
    FIELD_VALUES_LIMIT_MAX = int(os.getenv("VICTORIALOGS_FIELD_VALUES_LIMIT_MAX", "1000"))
    HITS_FIELDS_LIMIT_MAX = int(os.getenv("VICTORIALOGS_HITS_FIELDS_LIMIT_MAX", "100"))

    DEFAULT_TIME_WINDOW_MINUTES = 15
    QUERY_MAX_WINDOW_MINUTES_FLOOR = 10080
    QUERY_MAX_WINDOW_MINUTES_DEFAULT = 43200
    QUERY_MAX_WINDOW_MINUTES = max(
        int(os.getenv("VICTORIALOGS_QUERY_MAX_WINDOW_MINUTES", str(QUERY_MAX_WINDOW_MINUTES_DEFAULT))),
        QUERY_MAX_WINDOW_MINUTES_FLOOR,
    )

    @staticmethod
    def normalize_bounded_int(value, field_name: str, default: int, max_value: int, clamp: bool = False) -> int:
        if value in (None, ""):
            return default
        try:
            normalized = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} 必须是整数") from exc
        if normalized < 1:
            raise ValueError(f"{field_name} 必须大于等于 1")
        if normalized > max_value:
            if clamp:
                return max_value
            raise ValueError(f"{field_name} 不能大于 {max_value}")
        return normalized

    @classmethod
    def normalize_query_limit(cls, value, default: int = 10, clamp: bool = False) -> int:
        return cls.normalize_bounded_int(value, "limit", default, cls.QUERY_LIMIT_MAX, clamp=clamp)

    @classmethod
    def normalize_field_values_limit(cls, value, default: int = 100, clamp: bool = False) -> int:
        return cls.normalize_bounded_int(value, "limit", default, cls.FIELD_VALUES_LIMIT_MAX, clamp=clamp)

    @classmethod
    def normalize_hits_fields_limit(cls, value, default: int = 5, clamp: bool = False) -> int:
        return cls.normalize_bounded_int(value, "fields_limit", default, cls.HITS_FIELDS_LIMIT_MAX, clamp=clamp)

    @classmethod
    def normalize_query_max_window_minutes(cls, value) -> int:
        if value in (None, ""):
            return cls.QUERY_MAX_WINDOW_MINUTES_DEFAULT
        try:
            minutes = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("VICTORIALOGS_QUERY_MAX_WINDOW_MINUTES 必须是整数") from exc
        return max(minutes, cls.QUERY_MAX_WINDOW_MINUTES_FLOOR)

    @classmethod
    def ensure_query_window_span(cls, start: datetime, end: datetime) -> None:
        if end <= start:
            raise ValueError("time range end must be later than start")
        span_minutes = (end - start).total_seconds() / 60
        if span_minutes > cls.QUERY_MAX_WINDOW_MINUTES:
            raise ValueError(f"查询时间范围不能超过 {cls.QUERY_MAX_WINDOW_MINUTES} 分钟")

    @staticmethod
    def _blank_time(value) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            return not value.strip()
        return False

    @classmethod
    def normalize_query_time_window(cls, start_time="", end_time="", *, now=None) -> tuple[str, str]:
        now = now or datetime.now(timezone.utc)
        start_blank = cls._blank_time(start_time)
        end_blank = cls._blank_time(end_time)

        if start_blank and end_blank:
            end_dt = now
            start_dt = now - timedelta(minutes=cls.DEFAULT_TIME_WINDOW_MINUTES)
        elif end_blank:
            start_dt = parse_rfc3339_utc(start_time)
            end_dt = now
        elif start_blank:
            end_dt = parse_rfc3339_utc(end_time)
            start_dt = end_dt - timedelta(minutes=cls.DEFAULT_TIME_WINDOW_MINUTES)
        else:
            start_dt = parse_rfc3339_utc(start_time)
            end_dt = parse_rfc3339_utc(end_time)

        cls.ensure_query_window_span(start_dt, end_dt)
        return format_rfc3339_utc(start_dt), format_rfc3339_utc(end_dt)
