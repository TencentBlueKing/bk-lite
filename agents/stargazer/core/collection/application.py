"""统一采集运行时的应用装配与 Sanic 生命周期。"""

from __future__ import annotations

import asyncio
import os
import socket
from dataclasses import dataclass

from core.collection.plugins import UnifiedPluginFactory
from core.collection.metrics import CollectionMetrics
from core.collection.runtime import (
    CollectionRequest,
    CollectionRuntime,
    CollectionRuntimeSettings,
    RunLease,
    Submission,
)
from core.collection.credential_policy import CredentialPolicy
from core.infra.event_loop_monitor import EventLoopLagMonitor
from core.collection.preflight import AsyncProtocolPreflight
from core.infra.redis_client import get_redis_client
from core.collection.redis_state import (
    RedisCredentialStateStore,
    RedisRunStateStore,
)
from core.collection.constants import (
    DEFAULT_COLLECTION_REDIS_PREFIX,
    DEFAULT_MAX_ACTIVE_TARGETS,
    DEFAULT_TARGET_TASK_WINDOW,
)
from core.collection.contracts import TargetExecutorSettings
from core.collection.result_publisher import NatsResultPublisher
from core.collection.yaml_target_policy import apply_yaml_target_policy
from core.collection.executor import (
    TargetActivityTracker,
    TargetCollectionExecutor,
    TargetWorkerBudget,
    unlimited_target_gate,
)


def concurrency_limit_from_env(name: str, default: int) -> int:
    """从环境变量读取并发上限；缺省用 default；0 表示不限制。"""
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return int(default)
    value = int(str(raw).strip())
    if value < 0:
        raise ValueError(f"{name} must be >= 0 (0 means unlimited)")
    return value


@dataclass(frozen=True)
class CollectionApplicationSettings:
    max_active_runs: int = 16
    # 0 = 不限制；默认见 DEFAULT_*，运行时由 from_env() 读环境变量
    max_active_targets: int = DEFAULT_MAX_ACTIVE_TARGETS
    target_task_window: int = DEFAULT_TARGET_TASK_WINDOW
    connect_timeout_seconds: float = 5.0
    plugin_timeout_seconds: float = 60.0
    lease_ttl_seconds: float = 600.0
    lease_heartbeat_seconds: float = 30.0
    shutdown_grace_seconds: float = 30.0
    run_deadline_seconds: float = 0.0
    max_no_response_attempts: int = 3
    publish_max_attempts: int = 2

    def __post_init__(self) -> None:
        if self.max_active_runs <= 0:
            raise ValueError("max_active_runs must be greater than zero")
        if self.max_active_targets < 0:
            raise ValueError(
                "max_active_targets must be >= 0 (0 means unlimited)"
            )
        if self.target_task_window < 0:
            raise ValueError(
                "target_task_window must be >= 0 (0 means unlimited)"
            )

    @classmethod
    def from_env(cls) -> "CollectionApplicationSettings":
        return cls(
            max_active_runs=int(os.getenv("MAX_ACTIVE_RUNS", "16")),
            max_active_targets=concurrency_limit_from_env(
                "MAX_ACTIVE_TARGETS", DEFAULT_MAX_ACTIVE_TARGETS
            ),
            target_task_window=concurrency_limit_from_env(
                "TARGET_TASK_WINDOW", DEFAULT_TARGET_TASK_WINDOW
            ),
            connect_timeout_seconds=float(os.getenv("CONNECT_TIMEOUT", "5")),
            plugin_timeout_seconds=float(os.getenv("PLUGIN_TIMEOUT", "60")),
            lease_ttl_seconds=float(os.getenv("RUN_LEASE_TTL", "600")),
            lease_heartbeat_seconds=float(
                os.getenv("RUN_LEASE_HEARTBEAT", "30")
            ),
            shutdown_grace_seconds=float(
                os.getenv("COLLECTION_SHUTDOWN_GRACE", "30")
            ),
            run_deadline_seconds=float(os.getenv("RUN_DEADLINE", "0")),
            max_no_response_attempts=int(
                os.getenv("MAX_NO_RESPONSE_ATTEMPTS", "3")
            ),
            publish_max_attempts=int(os.getenv("PUBLISH_MAX_ATTEMPTS", "2")),
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
        if publisher is None:
            from core.infra.credential_state_cache import CredentialStateCache

            publisher = NatsResultPublisher(
                result_event_sink=CredentialStateCache.append_result_event
            )
        self._publisher = publisher
        self._target_semaphore = (
            unlimited_target_gate()
            if self.settings.max_active_targets <= 0
            else asyncio.Semaphore(self.settings.max_active_targets)
        )
        self._target_activity = TargetActivityTracker()
        self._worker_budget = TargetWorkerBudget(
            self.settings.target_task_window
        )
        self._metrics = CollectionMetrics()
        self._submission_counts: dict[str, int] = {}
        self._loop_lag = EventLoopLagMonitor(
            interval_seconds=float(os.getenv("EVENT_LOOP_LAG_INTERVAL", "1"))
        )
        prefix = os.getenv(
            "COLLECTION_REDIS_PREFIX", DEFAULT_COLLECTION_REDIS_PREFIX
        )
        self._credentials = RedisCredentialStateStore(
            redis_client, key_prefix=f"{prefix}:credential"
        )
        self._credential_policy = CredentialPolicy(store=self._credentials)
        self._target_executor_settings = TargetExecutorSettings(
            max_active_targets=self.settings.max_active_targets,
            target_task_window=self.settings.target_task_window,
            connect_timeout_seconds=self.settings.connect_timeout_seconds,
            plugin_timeout_seconds=self.settings.plugin_timeout_seconds,
            max_no_response_attempts=self.settings.max_no_response_attempts,
            publish_max_attempts=self.settings.publish_max_attempts,
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
        self._submission_counts[status] = (
            self._submission_counts.get(status, 0) + 1
        )
        return submission

    async def shutdown(self) -> None:
        await self.runtime.shutdown(
            grace_seconds=self.settings.shutdown_grace_seconds
        )
        await self._loop_lag.stop()

    def start_observability(self) -> None:
        self._loop_lag.start()

    async def _execute(
        self, request: CollectionRequest, lease: RunLease
    ):
        # 一次 run 用 yaml target_policy 覆盖预检；显式 preflight_kind 仍优先
        request = apply_yaml_target_policy(request)
        plugin = self._plugin_factory.resolve(request)
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
            target_semaphore=self._target_semaphore,
            worker_budget=self._worker_budget,
            activity_tracker=self._target_activity,
            metrics=self._metrics,
            settings=self._target_executor_settings,
        )
        return await executor.execute(request, lease)

    async def stats(self) -> dict:
        redis_ok = False
        try:
            redis_ok = bool(await self._redis.ping())
        except Exception:  # readiness 会据此返回 503
            pass
        return {
            "healthy": redis_ok,
            "active_runs": self.active_runs,
            "active_targets": self._target_activity.active,
            "target_worker_tasks": self._worker_budget.active,
            "max_active_runs": self.settings.max_active_runs,
            "max_active_targets": self.settings.max_active_targets,
            "target_task_window": self.settings.target_task_window,
            "event_loop_lag_seconds": self._loop_lag.latest_seconds,
            "event_loop_lag_p99_seconds": self._loop_lag.p99_seconds,
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
        owner_id = os.getenv("POD_NAME") or (
            f"{socket.gethostname()}:{os.getpid()}"
        )
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
