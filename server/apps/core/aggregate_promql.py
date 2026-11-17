"""聚合库 PromQL 查询客户端。

只读 ``AGG_VICTORIAMETRICS_QUERY_URL``、``AGG_VICTORIAMETRICS_USER``、
``AGG_VICTORIAMETRICS_PASSWORD``。不读取、不回落 ``VICTORIAMETRICS_HOST``。
未配置查询地址时客户端不可用，构造和导入都不会访问网络。

刷出间隔读 ``APM_AGG_FLUSH_INTERVAL``（默认 60 秒）和 ``RUM_AGG_BATCH_TIMEOUT``
（默认 60 秒），写法与采集端的 Go duration 相同。对齐只用整秒。
"""

from __future__ import annotations

import json
import math
import os
import threading
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

import requests

from apps.core.logger import logger

APM_FLUSH_INTERVAL_ENV = "APM_AGG_FLUSH_INTERVAL"
RUM_FLUSH_INTERVAL_ENV = "RUM_AGG_BATCH_TIMEOUT"
DEFAULT_APM_FLUSH_SECONDS = 60
DEFAULT_RUM_FLUSH_SECONDS = 60
_DURATION_UNITS = (
    ("ms", 0.001),
    ("us", 1e-6),
    ("µs", 1e-6),
    ("μs", 1e-6),
    ("ns", 1e-9),
    ("h", 3600.0),
    ("m", 60.0),
    ("s", 1.0),
)
_flush_intervals: dict[tuple[str, str], int] = {}
_flush_intervals_lock = threading.Lock()

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
DEFAULT_TIMEOUT = (3.0, 10.0)


class AggregateMetricsUnavailable(RuntimeError):
    """聚合库未配置、超时或返回了不可用的响应。消息只含阶段名。"""

    def __init__(self, stage: str):
        super().__init__(stage)
        self.stage = stage


class AggregateMetricsTooLarge(AggregateMetricsUnavailable):
    def __init__(self):
        super().__init__("too_large")


def _whole_seconds(raw: str) -> int | None:
    """Parse a collector duration, rounding up so alignment covers the whole flush."""

    text = raw.strip()
    if not text or text[0] in "+-":
        return None
    total = 0.0
    index = 0
    length = len(text)
    while index < length:
        start = index
        while index < length and text[index].isdigit():
            index += 1
        if index < length and text[index] == ".":
            index += 1
            fraction = index
            while index < length and text[index].isdigit():
                index += 1
            if index == fraction:
                return None
        if index == start:
            return None
        try:
            number = float(text[start:index])
        except ValueError:
            return None
        if not math.isfinite(number):
            return None
        unit_name = ""
        scale = 0.0
        for name, unit_scale in _DURATION_UNITS:
            if text.startswith(name, index):
                unit_name = name
                scale = unit_scale
                break
        if not unit_name:
            return None
        total += number * scale
        index += len(unit_name)
    if not math.isfinite(total) or total <= 0:
        return None
    micros = round(total * 1_000_000)
    if micros <= 0:
        return None
    return -(-micros // 1_000_000)


def flush_interval_seconds(name: str, default_seconds: int) -> int:
    """Read one flush interval. The same invalid value warns once."""

    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default_seconds
    key = (name, raw)
    with _flush_intervals_lock:
        cached = _flush_intervals.get(key)
        if cached is not None:
            return cached
        parsed = _whole_seconds(raw)
        if parsed is None:
            logger.warning(
                "event=aggregate_flush_interval_invalid name=%s default_seconds=%s",
                name,
                default_seconds,
            )
            _flush_intervals[key] = default_seconds
            return default_seconds
        _flush_intervals[key] = parsed
        return parsed


def apm_flush_seconds() -> int:
    return flush_interval_seconds(APM_FLUSH_INTERVAL_ENV, DEFAULT_APM_FLUSH_SECONDS)


def rum_flush_seconds() -> int:
    return flush_interval_seconds(RUM_FLUSH_INTERVAL_ENV, DEFAULT_RUM_FLUSH_SECONDS)


def align_query_end(ended_at: datetime, *, now: datetime, flush_seconds: int) -> datetime:
    """对齐到最近一个完整分钟，再留出一个刷出周期。"""

    def as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    moment = min(as_utc(ended_at), as_utc(now))
    complete_minute = moment.replace(second=0, microsecond=0)
    return complete_minute - timedelta(seconds=flush_seconds)


def escape_promql_label_value(value: object) -> str:
    """转义 PromQL 标签字符串，避免标签值闭合选择器。"""

    text = str(value)
    return text.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _query_base(url: str) -> str:
    trimmed = url.strip().rstrip("/")
    parsed = urlsplit(trimmed)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    if parsed.username or parsed.password:
        return ""
    for suffix in ("/api/v1/query_range", "/api/v1/query", "/api/v1"):
        if trimmed.endswith(suffix):
            trimmed = trimmed[: -len(suffix)].rstrip("/")
            break
    return trimmed


class AggregatePromqlClient:
    def __init__(
        self,
        *,
        base_url: str = "",
        username: str = "",
        password: str = "",
        timeout: tuple[float, float] = DEFAULT_TIMEOUT,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
        session: requests.Session | None = None,
    ):
        user = username.strip()
        secret = password if user and password else ""
        self.base_url = "" if bool(user) != bool(password) else _query_base(base_url)
        self._auth = (user, secret) if self.base_url and user and secret else None
        self.timeout = timeout
        self.max_response_bytes = max_response_bytes
        self._session = session

    @classmethod
    def from_env(cls, *, session: requests.Session | None = None) -> AggregatePromqlClient:
        return cls(
            base_url=os.environ.get("AGG_VICTORIAMETRICS_QUERY_URL", ""),
            username=os.environ.get("AGG_VICTORIAMETRICS_USER", ""),
            password=os.environ.get("AGG_VICTORIAMETRICS_PASSWORD", ""),
            session=session,
        )

    @property
    def available(self) -> bool:
        return bool(self.base_url)

    def query_instant(self, expression: str, *, at: datetime) -> list[dict]:
        return self._query(
            "/api/v1/query",
            {"query": expression, "time": f"{at.timestamp():.3f}"},
        )

    def query_range(
        self,
        expression: str,
        *,
        start: datetime,
        end: datetime,
        step_seconds: int,
    ) -> list[dict]:
        return self._query(
            "/api/v1/query_range",
            {
                "query": expression,
                "start": f"{start.timestamp():.3f}",
                "end": f"{end.timestamp():.3f}",
                "step": str(max(int(step_seconds), 1)),
            },
        )

    def _query(self, path: str, params: dict[str, str]) -> list[dict]:
        if not self.available:
            raise AggregateMetricsUnavailable("unconfigured")
        session = self._session or requests.Session()
        owns_session = self._session is None
        response = None
        try:
            response = session.get(
                f"{self.base_url}{path}",
                params=params,
                timeout=self.timeout,
                auth=self._auth,
                headers={"Accept": "application/json"},
                stream=True,
                allow_redirects=False,
            )
            if response.status_code != 200:
                raise AggregateMetricsUnavailable("http")
            payload = json.loads(self._read_bounded(response))
        except AggregateMetricsUnavailable:
            raise
        except requests.Timeout as exc:
            raise AggregateMetricsUnavailable("timeout") from exc
        except (requests.RequestException, UnicodeDecodeError, ValueError, TypeError) as exc:
            raise AggregateMetricsUnavailable("http") from exc
        finally:
            if response is not None:
                response.close()
            if owns_session:
                session.close()
        if not isinstance(payload, dict) or payload.get("status") != "success":
            raise AggregateMetricsUnavailable("invalid_response")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise AggregateMetricsUnavailable("invalid_response")
        if data.get("resultType") == "scalar":
            result = data.get("result")
            if not isinstance(result, list):
                raise AggregateMetricsUnavailable("invalid_response")
            return [{"value": result}]
        result = data.get("result")
        if not isinstance(result, list):
            raise AggregateMetricsUnavailable("invalid_response")
        return result

    def _read_bounded(self, response: requests.Response) -> bytes:
        content_length = response.headers.get("Content-Length")
        if content_length:
            try:
                advertised = int(content_length)
            except ValueError as exc:
                raise AggregateMetricsUnavailable("invalid_response") from exc
            if advertised > self.max_response_bytes:
                raise AggregateMetricsTooLarge()
        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            size += len(chunk)
            if size > self.max_response_bytes:
                raise AggregateMetricsTooLarge()
            chunks.append(chunk)
        return b"".join(chunks)
