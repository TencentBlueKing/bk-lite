"""调用方截止时间，与 NATS 请求超时对齐。"""

import time

from django.conf import settings


def resolve_nats_deadline(deadline):
    """保留显式截止时间。未给时，停在这次 NATS 请求会放弃的时刻。"""
    if deadline is not None:
        return deadline
    raw = getattr(settings, "NATS_REQUEST_TIMEOUT", 60)
    try:
        seconds = float(raw)
    except (TypeError, ValueError):
        seconds = 60.0
    if seconds <= 0:
        return None
    return time.monotonic() + seconds


def past_deadline(deadline) -> bool:
    return deadline is not None and time.monotonic() >= deadline
