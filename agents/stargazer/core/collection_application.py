"""统一采集运行时的应用装配与 Sanic 生命周期。"""

from __future__ import annotations

import asyncio
import os
import socket
from dataclasses import dataclass

from core.collection_plugins import UnifiedPluginFactory
from core.collection_metrics import CollectionMetrics
from core.collection_runtime import (
    CollectionRequest,
    CollectionRuntime,
    CollectionRuntimeSettings,
    RunLease,
    Submission,
)
from core.credential_policy import CredentialPolicy
from core.event_loop_monitor import EventLoopLagMonitor
from core.preflight import AsyncProtocolPreflight
from core.redis_client import get_redis_client
from core.redis_collection_state import (
    RedisCredentialStateStore,
    RedisRunStateStore,
    RedisTargetCheckpointStore,
)
from core.result_publisher import NatsResultPublisher
from core.target_collection_executor import (
    TargetCollectionExecutor,
    TargetActivityTracker,
    TargetExecutorSettings,
    TargetWorkerBudget,
)


@dataclass(frozen=True)
class CollectionApplicationSettings:
    max_active_runs: int = 16
    max_active_targets: int = 200
    target_task_window: int = 200
    connect_timeout_seconds: float = 5.0
    plugin_timeout_seconds: float = 60.0
    lease_ttl_seconds: float = 600.0
    lease_heartbeat_seconds: float = 30.0
    shutdown_grace_seconds: float = 30.0
    run_deadline_seconds: float = 0.0

    @classmethod
    def from_env(cls) -> "CollectionApplicationSettings":
        return cls(
            max_active_runs=int(os.getenv("MAX_ACTIVE_RUNS", "16")),
            max_active_targets=int(os.getenv("MAX_ACTIVE_TARGETS", "200")),
            target_task_window=int(os.getenv("TARGET_TASK_WINDOW", "200")),
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
        self._plugin_factory = plugin_factory or UnifiedPluginFactory()
        self._preflight = preflight or AsyncProtocolPreflight()
        if publisher is None:
            from core.credential_state_cache import CredentialStateCache

            publisher = NatsResultPublisher(
                result_event_sink=CredentialStateCache.append_result_event
            )
        self._publisher = publisher
        self._target_semaphore = asyncio.Semaphore(
            self.settings.max_active_targets
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
            "COLLECTION_REDIS_PREFIX", "stargazer:collection:v1"
        )
        self._checkpoints = RedisTargetCheckpointStore(
            redis_client, key_prefix=prefix
        )
        self._credentials = RedisCredentialStateStore(
            redis_client, key_prefix=f"{prefix}:credential"
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
        if submission.status.value == "accepted" and submission.fence > 1:
            self._metrics.increment("lease_takeover_total")
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
        executor = TargetCollectionExecutor(
            preflight=self._preflight,
            plugin=self._plugin_factory.resolve(request),
            publisher=self._publisher,
            checkpoint_store=self._checkpoints,
            credential_policy=CredentialPolicy(store=self._credentials),
            target_semaphore=self._target_semaphore,
            worker_budget=self._worker_budget,
            activity_tracker=self._target_activity,
            metrics=self._metrics,
            settings=TargetExecutorSettings(
                max_active_targets=self.settings.max_active_targets,
                target_task_window=self.settings.target_task_window,
                connect_timeout_seconds=self.settings.connect_timeout_seconds,
                plugin_timeout_seconds=self.settings.plugin_timeout_seconds,
            ),
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
