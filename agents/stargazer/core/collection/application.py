"""统一采集运行时的应用装配与 Sanic 生命周期。"""

from __future__ import annotations

import asyncio
import os
import socket
import threading
from dataclasses import dataclass

from core.collection.capacity_observer import (
    CapacityUsageReporter,
    with_capacity_utilization,
)
from core.collection.constants import (
    DEFAULT_COLLECTION_REDIS_PREFIX,
    DEFAULT_MAX_ACTIVE_TARGETS,
    DEFAULT_TARGET_TASK_WINDOW,
)
from core.collection.contracts import TargetExecutorSettings
from core.collection.credential_policy import CredentialPolicy
from core.collection.execution_plan import ExecutionPlanResolver, TimeoutDefaults
from core.collection.executor import TargetActivityTracker, TargetCollectionExecutor
from core.collection.metrics import CollectionMetrics
from core.collection.plugins import UnifiedPluginFactory
from core.collection.preflight import (
    AsyncProtocolPreflight,
    reachability_enabled_from_env,
)
from core.collection.redis_state import RedisCredentialStateStore, RedisRunStateStore
from core.collection.result_publisher import (
    BufferedResultPublisher,
    NatsResultPublisher,
)
from core.collection.runtime import (
    CollectionRequest,
    CollectionRuntime,
    CollectionRuntimeSettings,
    RunLease,
    Submission,
)
from core.collection.scheduler import CollectionScheduler
from core.collection.yaml_target_policy import apply_yaml_target_policy
from core.infra.event_loop_monitor import EventLoopLagMonitor
from core.infra.nats_utils import close_shared_nats, nats_metrics_connection_stats
from core.infra.redis_client import get_redis_client
from core.logger import logger


def concurrency_limit_from_env(name: str, default: int) -> int:
    """从环境变量读取并发上限；缺省用 default；0 表示不限制。"""
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return int(default)
    value = int(str(raw).strip())
    if value < 0:
        raise ValueError(f"{name} must be >= 0 (0 means unlimited)")
    return value


def _open_file_descriptor_count() -> int:
    for path in ("/proc/self/fd", "/dev/fd"):
        try:
            return len(os.listdir(path))
        except OSError:
            continue
    return -1


@dataclass(frozen=True)
class CollectionApplicationSettings:
    max_active_runs: int = 16
    # 0 = 不限制；默认见 DEFAULT_*，运行时由 from_env() 读环境变量
    max_active_targets: int = DEFAULT_MAX_ACTIVE_TARGETS
    target_task_window: int = DEFAULT_TARGET_TASK_WINDOW
    connect_timeout_seconds: float = 15.0
    probe_timeout_seconds: float = 15.0
    plugin_timeout_seconds: float = 60.0
    publish_timeout_seconds: float = 30.0
    publish_queue_timeout_seconds: float = 60.0
    publish_total_timeout_seconds: float = 120.0
    lease_ttl_seconds: float = 600.0
    lease_heartbeat_seconds: float = 30.0
    shutdown_grace_seconds: float = 30.0
    run_deadline_seconds: float = 0.0
    max_no_response_attempts: int = 3
    publish_max_attempts: int = 2
    access_probe_enabled: bool = True
    capacity_log_interval_seconds: float = 180.0

    def __post_init__(self) -> None:
        if self.max_active_runs <= 0:
            raise ValueError("max_active_runs must be greater than zero")
        if self.max_active_targets < 0:
            raise ValueError("max_active_targets must be >= 0 (0 means unlimited)")
        if self.target_task_window < 0:
            raise ValueError("target_task_window must be >= 0 (0 means unlimited)")
        if self.publish_timeout_seconds <= 0:
            raise ValueError("publish_timeout_seconds must be greater than zero")
        if self.publish_queue_timeout_seconds <= 0:
            raise ValueError("publish_queue_timeout_seconds must be greater than zero")
        if self.publish_total_timeout_seconds <= 0:
            raise ValueError("publish_total_timeout_seconds must be greater than zero")
        if self.capacity_log_interval_seconds <= 0:
            raise ValueError("capacity_log_interval_seconds must be greater than zero")

    @classmethod
    def from_env(cls) -> CollectionApplicationSettings:
        return cls(
            max_active_runs=int(os.getenv("MAX_ACTIVE_RUNS", "16")),
            max_active_targets=concurrency_limit_from_env(
                "MAX_ACTIVE_TARGETS", DEFAULT_MAX_ACTIVE_TARGETS
            ),
            target_task_window=concurrency_limit_from_env(
                "TARGET_TASK_WINDOW", DEFAULT_TARGET_TASK_WINDOW
            ),
            connect_timeout_seconds=float(
                os.getenv("PREFLIGHT_TIMEOUT", os.getenv("CONNECT_TIMEOUT", "15"))
            ),
            probe_timeout_seconds=float(
                os.getenv("PROBE_TIMEOUT", os.getenv("CONNECT_TIMEOUT", "15"))
            ),
            plugin_timeout_seconds=float(
                os.getenv("COLLECTION_TIMEOUT", os.getenv("PLUGIN_TIMEOUT", "60"))
            ),
            publish_timeout_seconds=float(
                os.getenv(
                    "PUBLISH_DELIVERY_TIMEOUT", os.getenv("PUBLISH_TIMEOUT", "30")
                )
            ),
            publish_queue_timeout_seconds=float(
                os.getenv("PUBLISH_QUEUE_TIMEOUT", "60")
            ),
            publish_total_timeout_seconds=float(
                os.getenv("PUBLISH_TOTAL_TIMEOUT", "120")
            ),
            lease_ttl_seconds=float(os.getenv("RUN_LEASE_TTL", "600")),
            lease_heartbeat_seconds=float(os.getenv("RUN_LEASE_HEARTBEAT", "30")),
            shutdown_grace_seconds=float(os.getenv("COLLECTION_SHUTDOWN_GRACE", "30")),
            run_deadline_seconds=float(os.getenv("RUN_DEADLINE", "0")),
            max_no_response_attempts=int(os.getenv("MAX_NO_RESPONSE_ATTEMPTS", "3")),
            publish_max_attempts=int(os.getenv("PUBLISH_MAX_ATTEMPTS", "2")),
            access_probe_enabled=reachability_enabled_from_env(),
            capacity_log_interval_seconds=float(
                os.getenv("CAPACITY_LOG_INTERVAL", "180")
            ),
        )


class CollectionApplication:
    def __init__(
        self,
        *,
        redis_client,
        schedule,
        owner_id: str,
        settings: CollectionApplicationSettings | None = None,
        plugin_factory=None,
        preflight=None,
        publisher=None,
        execution_plan_resolver=None,
    ) -> None:
        self.settings = settings or CollectionApplicationSettings()
        self._redis = redis_client
        if plugin_factory is None:
            from service.collection_service import CollectionService

            plugin_factory = UnifiedPluginFactory(
                configuration_service_factory=CollectionService
            )
        self._plugin_factory = plugin_factory
        self._preflight = preflight or AsyncProtocolPreflight()
        self._metrics = CollectionMetrics()
        if publisher is None:
            from core.infra.credential_state_cache import CredentialStateCache

            publisher = NatsResultPublisher(
                result_event_sink=CredentialStateCache.append_result_event,
                metrics=self._metrics,
                event_max_attempts=self.settings.publish_max_attempts,
            )
        publish_capacity = (
            self.settings.target_task_window
            or self.settings.max_active_targets
            or DEFAULT_TARGET_TASK_WINDOW
        )
        self._publisher = (
            publisher
            if isinstance(publisher, BufferedResultPublisher)
            else BufferedResultPublisher(
                publisher, capacity=publish_capacity, metrics=self._metrics
            )
        )
        self._execution_plan_resolver = (
            execution_plan_resolver
            or ExecutionPlanResolver(
                defaults=TimeoutDefaults(
                    preflight_seconds=self.settings.connect_timeout_seconds,
                    probe_seconds=self.settings.probe_timeout_seconds,
                    collection_seconds=self.settings.plugin_timeout_seconds,
                    publish_seconds=self.settings.publish_timeout_seconds,
                ),
                preflight_enabled=self.settings.access_probe_enabled,
            )
        )
        self._target_activity = TargetActivityTracker()
        scheduler_limits = tuple(
            limit
            for limit in (
                self.settings.max_active_targets,
                self.settings.target_task_window,
            )
            if limit > 0
        )
        self._scheduler = CollectionScheduler(
            max_in_flight=min(scheduler_limits) if scheduler_limits else 1_000_000,
            metrics=self._metrics,
        )
        self._submission_counts: dict[str, int] = {}
        self._loop_lag = EventLoopLagMonitor(
            interval_seconds=float(os.getenv("EVENT_LOOP_LAG_INTERVAL", "1"))
        )
        self._capacity_reporter = CapacityUsageReporter(
            snapshot=self.capacity_snapshot,
            emit=self._emit_capacity_log,
            interval_seconds=self.settings.capacity_log_interval_seconds,
        )
        prefix = os.getenv("COLLECTION_REDIS_PREFIX", DEFAULT_COLLECTION_REDIS_PREFIX)
        self._credentials = RedisCredentialStateStore(
            redis_client, key_prefix=f"{prefix}:credential"
        )
        self._credential_policy = CredentialPolicy(store=self._credentials)
        self._target_executor_settings = TargetExecutorSettings(
            max_active_targets=self.settings.max_active_targets,
            target_task_window=self.settings.target_task_window,
            connect_timeout_seconds=self.settings.connect_timeout_seconds,
            plugin_timeout_seconds=self.settings.plugin_timeout_seconds,
            publish_guard_seconds=self.settings.publish_timeout_seconds,
            publish_queue_timeout_seconds=self.settings.publish_queue_timeout_seconds,
            publish_total_timeout_seconds=self.settings.publish_total_timeout_seconds,
            max_no_response_attempts=self.settings.max_no_response_attempts,
            publish_max_attempts=self.settings.publish_max_attempts,
            access_probe_enabled=self.settings.access_probe_enabled,
        )
        self.runtime = CollectionRuntime(
            state_store=RedisRunStateStore(redis_client, key_prefix=prefix),
            execute=self._execute,
            schedule=schedule,
            settings=CollectionRuntimeSettings(
                max_active_runs=self.settings.max_active_runs,
                lease_ttl_seconds=self.settings.lease_ttl_seconds,
                lease_heartbeat_seconds=self.settings.lease_heartbeat_seconds,
                run_deadline_seconds=self.settings.run_deadline_seconds,
            ),
            owner_id=owner_id,
        )

    @property
    def active_runs(self) -> int:
        return self.runtime.active_runs

    async def submit(self, request: CollectionRequest) -> Submission:
        submission = await self.runtime.submit(request)
        status = submission.status.value
        self._submission_counts[status] = self._submission_counts.get(status, 0) + 1
        return submission

    async def shutdown(self) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.settings.shutdown_grace_seconds
        await self.runtime.shutdown(grace_seconds=self.settings.shutdown_grace_seconds)
        await self._scheduler.shutdown()
        await self._publisher.shutdown(grace_seconds=max(0.0, deadline - loop.time()))
        await close_shared_nats()
        await self._capacity_reporter.stop()
        await self._loop_lag.stop()

    def start_observability(self) -> None:
        self._loop_lag.start()
        self._capacity_reporter.start()

    def capacity_snapshot(self) -> dict[str, float | int]:
        """返回 MAX_ACTIVE_TARGETS 全局异步槽位及发布背压的即时使用情况。"""
        return with_capacity_utilization(
            {
                "active_runs": self.active_runs,
                "target_slots_used": self._scheduler.active,
                "target_slots_capacity": self._scheduler.capacity,
                "configured_max_active_targets": self.settings.max_active_targets,
                "configured_target_task_window": self.settings.target_task_window,
                "target_slots_peak": self._scheduler.peak,
                "active_targets": self._target_activity.active,
                "pending_targets": self._scheduler.pending,
                "pending_runs": self._scheduler.pending_runs,
                "publish_queue_depth": self._publisher.queue_depth,
                "publish_queue_capacity": self._publisher.capacity,
                "event_loop_lag_ms": round(self._loop_lag.latest_seconds * 1000, 2),
                "event_loop_lag_p99_ms": round(self._loop_lag.p99_seconds * 1000, 2),
            }
        )

    @staticmethod
    def _emit_capacity_log(snapshot: dict[str, float | int]) -> None:
        logger.info(
            "event=collection_capacity active_runs=%s target_slots_used=%s "
            "target_slots_capacity=%s target_slots_available=%s target_slots_utilization_percent=%s "
            "configured_max_active_targets=%s configured_target_task_window=%s "
            "target_slots_peak=%s active_targets=%s pending_targets=%s pending_runs=%s "
            "publish_queue_depth=%s publish_queue_capacity=%s publish_queue_utilization_percent=%s "
            "event_loop_lag_ms=%s event_loop_lag_p99_ms=%s",
            snapshot.get("active_runs", 0),
            snapshot.get("target_slots_used", 0),
            snapshot.get("target_slots_capacity", 0),
            snapshot.get("target_slots_available", 0),
            snapshot.get("target_slots_utilization_percent", 0),
            snapshot.get("configured_max_active_targets", 0),
            snapshot.get("configured_target_task_window", 0),
            snapshot.get("target_slots_peak", 0),
            snapshot.get("active_targets", 0),
            snapshot.get("pending_targets", 0),
            snapshot.get("pending_runs", 0),
            snapshot.get("publish_queue_depth", 0),
            snapshot.get("publish_queue_capacity", 0),
            snapshot.get("publish_queue_utilization_percent", 0),
            snapshot.get("event_loop_lag_ms", 0),
            snapshot.get("event_loop_lag_p99_ms", 0),
        )

    async def _execute(self, request: CollectionRequest, lease: RunLease):
        # 一次 run 用 yaml target_policy 覆盖预检；显式 preflight_kind 仍优先
        request = apply_yaml_target_policy(request)
        plugin = self._plugin_factory.resolve(request)
        plan = self._execution_plan_resolver.resolve(request)
        # 有 probe 且未显式关闭时启用廉价 AccessProbe；否则 CredentialAttempt=collect
        access_probe = None
        if callable(getattr(plugin, "probe", None)) and getattr(
            plugin, "supports_access_probe", True
        ):
            access_probe = plugin
        executor = TargetCollectionExecutor(
            preflight=self._preflight,
            access_probe=access_probe,
            plugin=plugin,
            publisher=self._publisher,
            credential_policy=self._credential_policy,
            activity_tracker=self._target_activity,
            metrics=self._metrics,
            settings=self._target_executor_settings,
            plan=plan,
            scheduler=self._scheduler,
        )
        return await executor.execute(request, lease)

    async def stats(self) -> dict:
        redis_ok = False
        try:
            redis_ok = bool(await self._redis.ping())
        except Exception:  # readiness 会据此返回 503
            pass
        capacity = self.capacity_snapshot()
        return {
            "healthy": redis_ok,
            "active_runs": self.active_runs,
            "active_targets": self._target_activity.active,
            "target_worker_tasks": self._scheduler.active,
            "pending_targets": self._scheduler.pending,
            "pending_runs": self._scheduler.pending_runs,
            "target_worker_tasks_peak": self._scheduler.peak,
            "publish_queue_depth": self._publisher.queue_depth,
            "publish_queue_peak": self._publisher.peak_queue_depth,
            "publish_queue_capacity": self._publisher.capacity,
            "max_active_runs": self.settings.max_active_runs,
            "max_active_targets": self.settings.max_active_targets,
            "target_task_window": self.settings.target_task_window,
            **capacity,
            "event_loop_lag_seconds": self._loop_lag.latest_seconds,
            "event_loop_lag_p99_seconds": self._loop_lag.p99_seconds,
            "thread_count": threading.active_count(),
            "open_file_descriptors": _open_file_descriptor_count(),
            "submissions": dict(self._submission_counts),
            "redis_pool_wait_seconds_total": float(
                getattr(self._redis, "pool_wait_seconds_total", 0.0) or 0.0
            ),
            "redis_pool_timeout_total": float(
                getattr(self._redis, "pool_timeout_total", 0) or 0
            ),
            "redis_pool_exhaustion_total": float(
                getattr(self._redis, "pool_exhaustion_total", 0) or 0
            ),
            **nats_metrics_connection_stats(),
            **self._metrics.snapshot(),
        }


_application: CollectionApplication | None = None


def get_collection_application() -> CollectionApplication:
    if _application is None:
        raise RuntimeError("collection runtime is not initialized")
    return _application


def initialize_collection_application(app) -> None:
    @app.listener("before_server_start")
    async def start_collection_application(app, _loop):
        global _application
        redis_client = getattr(app.ctx, "redis", None)
        if redis_client is None:
            redis_client = await get_redis_client()
            await redis_client.ping()
            app.ctx.redis = redis_client
        owner_id = os.getenv("POD_NAME") or (f"{socket.gethostname()}:{os.getpid()}")
        _application = CollectionApplication(
            redis_client=redis_client,
            schedule=app.add_task,
            owner_id=owner_id,
            settings=CollectionApplicationSettings.from_env(),
        )
        app.ctx.collection_application = _application

    @app.listener("after_server_start")
    async def start_collection_observability(app, _loop):
        app.ctx.collection_application.start_observability()

    @app.listener("before_server_stop")
    async def stop_collection_application(app, _loop):
        global _application
        application = getattr(app.ctx, "collection_application", None)
        if application is not None:
            await application.shutdown()
        _application = None
