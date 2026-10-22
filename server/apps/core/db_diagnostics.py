"""临时启用的 ASGI/PG 连接观测：不查询、不关闭连接、不延长 wrapper 生命周期。"""

import os
import threading
import time
import traceback
import uuid
import weakref
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from hashlib import sha256
from pathlib import Path

from django.core.signals import request_finished, request_started
from django.db import connections
from django.db.backends.signals import connection_created

from apps.core.logger import logger, safe_log_value

current_trace = ContextVar("db_diagnostic_trace", default=None)
MAX_CONNECTIONS_PER_REQUEST = 64


def diagnostics_enabled():
    return os.getenv("DB_CONNECTION_DIAGNOSTICS", "").lower() == "true"


def diagnostic_guard(func):
    """观测失败仅降级诊断，不替换业务返回值或异常。"""

    @wraps(func)
    def guarded(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as error:
            trace = current_trace.get()
            logger.warning(
                "event=db_diagnostic_failed request_id=%s failed_stage=%s error_type=%s",
                trace.request_id if trace else "-",
                func.__name__,
                type(error).__name__,
            )

    return guarded


class ConnectionObservation:
    def __init__(self, connection):
        self.wrapper = weakref.ref(connection)
        # psycopg/psycopg2 均支持弱引用；不能用可被复用的 id() 代表驱动身份。
        self.driver = weakref.ref(connection.connection)
        self.connection_id = uuid.uuid4().hex
        self.owner_thread = threading.get_ident()
        self.alias = safe_log_value(connection.alias, max_length=64)
        driver = connection.connection
        self.pg_pid = driver.info.backend_pid if hasattr(driver, "info") else driver.get_backend_pid()
        self.conn_max_age = connection.settings_dict.get("CONN_MAX_AGE", 0)
        self.cleanup_state = "not_seen"

    def snapshot(self):
        # 只读取本地字段；跨线程不调用连接方法，更不执行探活查询。
        wrapper = self.wrapper()
        if wrapper is None:
            return "wrapper_gone_unknown", "unknown", "unknown", "unknown"
        driver = wrapper.connection
        atomic, errors, autocommit = wrapper.in_atomic_block, wrapper.errors_occurred, wrapper.autocommit
        if driver is None:
            return "closed", atomic, errors, autocommit
        if driver is not self.driver():
            return "replaced_unknown", atomic, errors, autocommit
        return "closed" if driver.closed else "open", atomic, errors, autocommit


class RequestTrace:
    def __init__(self, scope):
        self.request_id = uuid.uuid4().hex
        # 原始 URL 可能携带凭据；只记录指纹，路由匹配后另记静态 route 模板。
        self.path_hash = sha256(scope.get("path", "").encode()).hexdigest()[:16]
        self.started = time.monotonic()
        self.stage = "read_body"
        self.route = "-"
        self.status_code = 0
        self.response_closed = False
        self.cleanup_fallback = False
        self.observations = []
        self.finished_threads = set()
        self.dropped = 0
        self.lock = threading.Lock()

    @diagnostic_guard
    def begin(self):
        logger.info(
            "event=db_request_begin request_id=%s worker_pid=%s path_hash=%s",
            self.request_id,
            os.getpid(),
            self.path_hash,
        )

    @diagnostic_guard
    def observe(self, connection, origin):
        if connection.vendor != "postgresql" or connection.connection is None:
            return
        with self.lock:
            if len(self.observations) >= MAX_CONNECTIONS_PER_REQUEST:
                self.dropped += 1
                return
            observation = ConnectionObservation(connection)
            self.observations.append(observation)
        log_observed(observation, self.request_id, origin)

    @diagnostic_guard
    def phase(self, stage):
        self.stage = stage
        logger.debug("event=db_request_phase request_id=%s stage=%s thread_id=%s", self.request_id, stage, threading.get_ident())

    @diagnostic_guard
    def finish(self, outcome, error_type):
        with self.lock:
            observations = tuple(self.observations)
            finished_threads = set(self.finished_threads)
        for observation in observations:
            state, atomic, errors, autocommit = observation.snapshot()
            logger.info(
                "event=db_connection_request_end request_id=%s worker_pid=%s connection_id=%s pg_pid=%s "
                "alias=%s owner_thread=%s observer_thread=%s state=%s cleanup_seen=%s cleanup_state=%s "
                "conn_max_age=%s in_atomic=%s autocommit=%s errors_occurred=%s",
                self.request_id,
                os.getpid(),
                observation.connection_id,
                observation.pg_pid,
                observation.alias,
                observation.owner_thread,
                threading.get_ident(),
                state,
                observation.owner_thread in finished_threads,
                observation.cleanup_state,
                observation.conn_max_age,
                atomic,
                autocommit,
                errors,
            )
        logger.info(
            "event=db_request_end request_id=%s worker_pid=%s path_hash=%s route=%s outcome=%s status_code=%s "
            "last_stage=%s failed_stage=%s error_type=%s response_closed=%s cleanup_fallback=%s cleanup_threads=%s "
            "observed_connections=%s dropped_connections=%s elapsed_ms=%s",
            self.request_id,
            os.getpid(),
            self.path_hash,
            self.route,
            outcome,
            self.status_code,
            self.stage,
            self.stage if outcome == "raised" else "-",
            error_type,
            self.response_closed,
            self.cleanup_fallback,
            len(finished_threads),
            len(observations),
            self.dropped,
            round((time.monotonic() - self.started) * 1000),
        )


def log_observed(observation, request_id, origin):
    # 只取文件名/函数名/行号，不包含源代码、异常正文、绝对目录或 locals。
    frames = traceback.extract_stack(limit=32)[:-2]
    project_frames = [frame for frame in frames if "/apps/" in frame.filename and frame.filename != __file__]
    callsite = ">".join(
        "%s:%s:%s" % (safe_log_value(Path(frame.filename).name, max_length=48), frame.lineno, safe_log_value(frame.name, max_length=48))
        for frame in (project_frames or frames)[-6:]
    )
    logger.info(
        "event=db_connection_observed request_id=%s worker_pid=%s connection_id=%s pg_pid=%s alias=%s "
        "owner_thread=%s origin=%s conn_max_age=%s callsite=%s",
        request_id,
        os.getpid(),
        observation.connection_id,
        observation.pg_pid,
        observation.alias,
        observation.owner_thread,
        origin,
        observation.conn_max_age,
        callsite,
    )


@diagnostic_guard
def on_connection_created(sender, connection, **kwargs):
    if not diagnostics_enabled():
        return
    trace = current_trace.get()
    if trace is not None:
        trace.observe(connection, "created")
    elif connection.vendor == "postgresql":
        # 原生线程池不会自动传播 ContextVar；保留建连线程和调用点，不伪造请求关联。
        log_observed(ConnectionObservation(connection), "-", "unscoped_created")


@diagnostic_guard
def on_request_started(sender, **kwargs):
    trace = current_trace.get()
    if trace is not None:
        trace.phase("request_started")
        for connection in connections.all(initialized_only=True):
            trace.observe(connection, "existing_at_start")


@diagnostic_guard
def on_request_finished(sender, **kwargs):
    trace = current_trace.get()
    if trace is not None:
        # 在 Django 默认 close_old_connections receiver 之后注册。
        with trace.lock:
            trace.finished_threads.add(threading.get_ident())
            for observation in trace.observations:
                if observation.owner_thread == threading.get_ident():
                    observation.cleanup_state = observation.snapshot()[0]
        logger.debug("event=db_request_cleanup_signal request_id=%s thread_id=%s", trace.request_id, threading.get_ident())


def install_diagnostics():
    if diagnostics_enabled():
        connection_created.connect(on_connection_created, dispatch_uid="db_diagnostics_created", weak=False)
        request_started.connect(on_request_started, dispatch_uid="db_diagnostics_started", weak=False)
        request_finished.connect(on_request_finished, dispatch_uid="db_diagnostics_finished", weak=False)


@contextmanager
def trace_request(scope):
    if not diagnostics_enabled() or scope.get("type") != "http":
        yield
        return
    trace = RequestTrace(scope)
    token = current_trace.set(trace)
    outcome, error_type = "returned", "-"
    try:
        trace.begin()
        yield
    except BaseException as error:
        outcome, error_type = "raised", type(error).__name__
        raise
    finally:
        try:
            trace.finish(outcome, error_type)
        finally:
            current_trace.reset(token)
