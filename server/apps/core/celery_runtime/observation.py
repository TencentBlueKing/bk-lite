"""公共生命周期观测：进程内有界聚合，不保存参数或任务结果。"""

import math
import os
import threading
from datetime import datetime
from functools import wraps
from random import random
from time import monotonic, time

from celery import signals

from apps.core.celery_runtime.manifest import TASK_ROUTES
from apps.core.celery_runtime.routing import QUEUE_NAMES
from apps.core.logger import celery_logger as logger

BUCKETS = (0.05, 0.1, 0.5, 1, 5, 15, 60, float("inf"))


def queue_wait(headers, now):
    try:
        published = float(headers["bklite_published_at"])
        eta = headers.get("eta")
        planned = datetime.fromisoformat(eta) if eta else None
        if planned is not None and planned.tzinfo is None:
            return None, "unknown"
        eligible = max(published, planned.timestamp()) if planned else published
        if not math.isfinite(eligible):
            return None, "unknown"
        return (now - eligible, "known") if now >= eligible else (None, "clock_skew")
    except (KeyError, TypeError, ValueError, OverflowError):
        return None, "unknown"


def guarded(method):
    @wraps(method)
    def run(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except Exception:
            # 观测是旁路；不传播日志异常，也不输出可能含凭据的异常文本。
            return None

    return run


def emit_log(event):
    logger.info("celery_runtime %s", event)


class Observer:
    def __init__(self, emit=emit_log):
        self.emit = emit
        self.reset()

    def reset(self, **kwargs):
        self.pid = os.getpid()
        self.lock = threading.Lock()
        self.rows = {}
        self.last_flush = monotonic()
        self.count = 0

    def record(self, name, queue, phase, state="", wait=None, duration=None, wait_status="unknown"):
        if os.getpid() != self.pid:
            self.reset()
        name = name if name in TASK_ROUTES else "unknown"
        queue = queue if queue in QUEUE_NAMES else "unknown"
        state = state if state in ("SUCCESS", "FAILURE", "RETRY", "REVOKED", "") else "unknown"
        key = name, queue, phase, state
        with self.lock:
            row = self.rows.setdefault(
                key,
                {
                    "task": name,
                    "queue": queue,
                    "phase": phase,
                    "state": state,
                    "count": 0,
                    "wait_buckets": [0] * len(BUCKETS),
                    "duration_sum": 0,
                    "wait_unknown": 0,
                    "clock_skew": 0,
                },
            )
            row["count"] += 1
            row["duration_sum"] += duration or 0
            if wait is not None:
                row["wait_buckets"][next(i for i, bound in enumerate(BUCKETS) if wait <= bound)] += 1
            elif wait_status == "clock_skew":
                row["clock_skew"] += 1
            else:
                row["wait_unknown"] += 1
            self.count += 1
            flush = self.count >= 100 or monotonic() - self.last_flush >= 60
        if flush:
            self.flush()

    @guarded
    def published(self, sender=None, headers=None, routing_key=None, **kwargs):
        if headers is None:
            return
        headers["bklite_published_at"] = time()
        self.record(sender, routing_key, "published")

    @guarded
    def started(self, task=None, **kwargs):
        request = task.request
        request._bklite_started = monotonic()
        headers = dict(request.headers or {})
        headers["eta"] = request.eta
        wait, status = queue_wait(headers, time())
        queue = (request.delivery_info or {}).get("routing_key")
        self.record(task.name, queue, "started", wait=wait, wait_status=status)
        if random() < 0.01:
            self.emit(
                {
                    "event": "wait_sample",
                    "task": task.name if task.name in TASK_ROUTES else "unknown",
                    "queue": queue if queue in QUEUE_NAMES else "unknown",
                    "wait_seconds": wait,
                    "wait_status": status,
                }
            )

    @guarded
    def finished(self, task=None, state=None, **kwargs):
        request = task.request
        start = getattr(request, "_bklite_started", None)
        duration = max(0, monotonic() - start) if start is not None else None
        self.record(task.name, (request.delivery_info or {}).get("routing_key"), "finished", state=state, duration=duration)

    @guarded
    def flush(self, **kwargs):
        with self.lock:
            if not self.rows:
                return
            event = {
                "event": "counts_delta",
                "pid": self.pid,
                "window_seconds": monotonic() - self.last_flush,
                "wait_bucket_bounds": [*BUCKETS[:-1], "+Inf"],
                "rows": list(self.rows.values()),
            }
            self.rows = {}
            self.count = 0
            self.last_flush = monotonic()
        self.emit(event)


def install_observer():
    observer = Observer()
    for signal, handler, uid in (
        (signals.before_task_publish, observer.published, "published"),
        (signals.task_prerun, observer.started, "started"),
        (signals.task_postrun, observer.finished, "finished"),
        (signals.worker_process_init, observer.reset, "fork_reset"),
        (signals.worker_process_shutdown, observer.flush, "child_flush"),
        (signals.worker_shutdown, observer.flush, "worker_flush"),
    ):
        signal.connect(handler, weak=False, dispatch_uid=f"bklite_runtime_{uid}")
    return observer
