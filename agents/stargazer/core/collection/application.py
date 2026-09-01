"""统一采集运行时的应用装配与 Sanic 生命周期。"""

from __future__ import annotations

import asyncio
import os
import socket
import threading
from dataclasses import dataclass

from core.collection.capacity_observer import CapacityUsageReporter, with_capacity_utilization
from core.collection.constants import (
    DEFAULT_COLLECTION_REDIS_PREFIX,
    DEFAULT_MAX_ACTIVE_TARGETS,
    DEFAULT_NETWORK_TOPOLOGY_MAX_ACTIVE_TARGETS,
    DEFAULT_TARGET_TASK_WINDOW,
)
from core.collection.contracts import TargetExecutorSettings
from core.collection.credential_policy import CredentialPolicy
from core.collection.execution_plan import ExecutionPlanResolver, TimeoutDefaults
from core.collection.executor import TargetActivityTracker, TargetCollectionExecutor
from core.collection.metrics import CollectionMetrics
from core.collection.plugins import UnifiedPluginFactory
from core.collection.preflight import AsyncProtocolPreflight
from core.collection.redis_state import RedisCredentialStateStore, RedisRunStateStore
from core.collection.result_publisher import BufferedResultPublisher, NatsResultPublisher
from core.collection.runtime import CollectionRequest, CollectionRuntime, CollectionRuntimeSettings, RunLease, Submission
from core.collection.scheduler import CollectionScheduler
from core.collection.yaml_target_policy import apply_executor_target_policy, apply_yaml_target_policy_async
from core.infra.event_loop_monitor import EventLoopLagMonitor
from core.infra.nats_utils import close_shared_nats, nats_metrics_connection_stats
from core.infra.process_resources import ProcessResourceSampler
from core.infra.redis_client import get_redis_client
from core.logger import logger, safe_exception_info, safe_log_value


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
    network_topology_max_active_targets: int = DEFAULT_NETWORK_TOPOLOGY_MAX_ACTIVE_TARGETS
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
    publish_worker_count: int = 1
    capacity_log_interval_seconds: float = 180.0

    def __post_init__(self) -> None:
        if self.max_active_runs <= 0:
            raise ValueError("max_active_runs must be greater than zero")
        if self.max_active_targets < 0:
            raise ValueError("max_active_targets must be >= 0 (0 means unlimited)")
        if (
            isinstance(self.network_topology_max_active_targets, bool)
            or not isinstance(self.network_topology_max_active_targets, int)
            or not 1 <= self.network_topology_max_active_targets <= 100
        ):
            raise ValueError("NETWORK_TOPOLOGY_MAX_ACTIVE_TARGETS must be an integer between 1 and 100")
        if self.max_active_targets > 0 and self.network_topology_max_active_targets >= self.max_active_targets:
            raise ValueError("NETWORK_TOPOLOGY_MAX_ACTIVE_TARGETS must be less than MAX_ACTIVE_TARGETS")
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
        if self.publish_worker_count <= 0:
            raise ValueError("publish_worker_count must be greater than zero")

    @classmethod
    def from_env(cls) -> CollectionApplicationSettings:
        max_active_targets = concurrency_limit_from_env("MAX_ACTIVE_TARGETS", DEFAULT_MAX_ACTIVE_TARGETS)
        jetstream_publish_enabled = str(os.getenv("NATS_METRICS_JETSTREAM_ENABLED", "false")).strip().lower() in {"1", "true", "yes", "on"}
        topology_raw = os.getenv("NETWORK_TOPOLOGY_MAX_ACTIVE_TARGETS")
        if topology_raw is None or not str(topology_raw).strip():
            network_topology_max_active_targets = DEFAULT_NETWORK_TOPOLOGY_MAX_ACTIVE_TARGETS
        else:
            try:
                network_topology_max_active_targets = int(str(topology_raw).strip())
            except ValueError as exc:
                raise ValueError("NETWORK_TOPOLOGY_MAX_ACTIVE_TARGETS must be an integer between 1 and 100") from exc
        return cls(
            max_active_runs=int(os.getenv("MAX_ACTIVE_RUNS", "16")),
            max_active_targets=max_active_targets,
            network_topology_max_active_targets=network_topology_max_active_targets,
            target_task_window=concurrency_limit_from_env("TARGET_TASK_WINDOW", DEFAULT_TARGET_TASK_WINDOW),
            connect_timeout_seconds=float(os.getenv("PREFLIGHT_TIMEOUT", os.getenv("CONNECT_TIMEOUT", "15"))),
            probe_timeout_seconds=float(os.getenv("PROBE_TIMEOUT", os.getenv("CONNECT_TIMEOUT", "15"))),
            plugin_timeout_seconds=float(os.getenv("COLLECTION_TIMEOUT", os.getenv("PLUGIN_TIMEOUT", "60"))),
            publish_timeout_seconds=float(os.getenv("PUBLISH_DELIVERY_TIMEOUT", os.getenv("PUBLISH_TIMEOUT", "30"))),
            publish_queue_timeout_seconds=float(os.getenv("PUBLISH_QUEUE_TIMEOUT", "60")),
            publish_total_timeout_seconds=float(os.getenv("PUBLISH_TOTAL_TIMEOUT", "120")),
            lease_ttl_seconds=float(os.getenv("RUN_LEASE_TTL", "600")),
            lease_heartbeat_seconds=float(os.getenv("RUN_LEASE_HEARTBEAT", "30")),
            shutdown_grace_seconds=float(os.getenv("COLLECTION_SHUTDOWN_GRACE", "30")),
            run_deadline_seconds=float(os.getenv("RUN_DEADLINE", "0")),
            max_no_response_attempts=int(os.getenv("MAX_NO_RESPONSE_ATTEMPTS", "3")),
            publish_max_attempts=int(os.getenv("PUBLISH_MAX_ATTEMPTS", "2")),
            publish_worker_count=int(os.getenv("PUBLISH_WORKERS", "4") if jetstream_publish_enabled else "1"),
            capacity_log_interval_seconds=float(os.getenv("CAPACITY_LOG_INTERVAL", "180")),
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
        resource_sampler=None,
    ) -> None:
        self.settings = settings or CollectionApplicationSettings()
        self._redis = redis_client
        self._metrics = CollectionMetrics()
        if plugin_factory is None:
            from service.collection_service import CollectionService
            from service.node_info_loader import load_node_infos

            plugin_factory = UnifiedPluginFactory(
                configuration_service_factory=CollectionService,
                configuration_node_info_loader=load_node_infos,
                metrics=self._metrics,
            )
        self._plugin_factory = plugin_factory
        self._preflight = preflight or AsyncProtocolPreflight()
        if publisher is None:
            from core.infra.credential_state_cache import CredentialStateCache

            publisher = NatsResultPublisher(
                result_event_sink=CredentialStateCache.append_result_event,
                metrics=self._metrics,
                event_max_attempts=self.settings.publish_max_attempts,
            )
        publish_capacity = self.settings.target_task_window or self.settings.max_active_targets or DEFAULT_TARGET_TASK_WINDOW
        self._publisher = (
            publisher
            if isinstance(publisher, BufferedResultPublisher)
            else BufferedResultPublisher(
                publisher,
                capacity=publish_capacity,
                worker_count=self.settings.publish_worker_count,
                metrics=self._metrics,
            )
        )
        self._execution_plan_resolver = execution_plan_resolver or ExecutionPlanResolver(
            defaults=TimeoutDefaults(
                preflight_seconds=self.settings.connect_timeout_seconds,
                probe_seconds=self.settings.probe_timeout_seconds,
                collection_seconds=self.settings.plugin_timeout_seconds,
                publish_seconds=self.settings.publish_timeout_seconds,
            ),
            metrics=self._metrics,
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
            topology_max_in_flight=self.settings.network_topology_max_active_targets,
            # 两个全局边界都显式关闭时，不以内部哨兵容量计算借槽上限。
            allow_topology_idle_borrow=bool(scheduler_limits),
            metrics=self._metrics,
        )
        self._submission_counts: dict[str, int] = {}
        self._loop_lag = EventLoopLagMonitor(interval_seconds=float(os.getenv("EVENT_LOOP_LAG_INTERVAL", "1")))
        self._resource_sampler = resource_sampler or ProcessResourceSampler()
        self._capacity_reporter = CapacityUsageReporter(
            snapshot=self.capacity_snapshot,
            emit=self._emit_capacity_log,
            interval_seconds=self.settings.capacity_log_interval_seconds,
        )
        prefix = os.getenv("COLLECTION_REDIS_PREFIX", DEFAULT_COLLECTION_REDIS_PREFIX)
        self._credentials = RedisCredentialStateStore(redis_client, key_prefix=f"{prefix}:credential")
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
        metric_snapshot = self._metrics.snapshot()
        resource_snapshot = self._resource_sampler.sample()
        return with_capacity_utilization(
            {
                "active_runs": self.active_runs,
                "target_slots_used": self._scheduler.active,
                "target_slots_capacity": self._scheduler.capacity,
                "configured_max_active_targets": self.settings.max_active_targets,
                "configured_network_topology_max_active_targets": self.settings.network_topology_max_active_targets,
                "configured_target_task_window": self.settings.target_task_window,
                "target_slots_peak": self._scheduler.peak,
                "network_topology_active_targets": self._scheduler.topology_active,
                "active_targets": self._target_activity.active,
                "pending_targets": self._scheduler.pending,
                "completed_targets": self._scheduler.completed,
                "completed_targets_total": self._scheduler.completed_total,
                "pending_runs": self._scheduler.pending_runs,
                "publish_queue_depth": self._publisher.queue_depth,
                "publish_queue_capacity": self._publisher.capacity,
                "publish_batch_age_ms": round(self._publisher.current_batch_age_seconds * 1000, 2),
                "publish_queue_residence_p99_ms": round(
                    metric_snapshot.get("publish_queue_residence_seconds_p99", 0.0) * 1000,
                    2,
                ),
                "event_loop_lag_ms": round(self._loop_lag.latest_seconds * 1000, 2),
                "event_loop_lag_p99_ms": round(self._loop_lag.p99_seconds * 1000, 2),
                **resource_snapshot,
            }
        )

    @staticmethod
    def _emit_capacity_log(snapshot: dict[str, float | int]) -> None:
        status, hint = _capacity_status(snapshot)
        logger.info(
            "event=collection_capacity 状态=%s 提示=%s | "
            "采集任务[正在执行=%s 调度中=%s] | "
            "目标任务[等待执行=%s 正在执行=%s 本轮已完成=%s 累计已完成=%s] | "
            "目标并发槽位[已用=%s/%s 可用=%s 使用率=%s 峰值=%s] | "
            "配置[最大目标并发=%s 任务窗口=%s] | "
            "发布队列[深度=%s/%s 使用率=%s 最老批次=%s P99等待=%s] | "
            "事件循环[当前延迟=%s P99延迟=%s] | "
            "进程[CPU=%s CPU配额使用率=%s RSS内存=%s 线程=%s FD=%s] | "
            "容器[内存=%s/%s 使用率=%s CPU限额=%s CPU限流增量=%s/%s]",
            status,
            hint,
            snapshot.get("active_runs", 0),
            snapshot.get("pending_runs", 0),
            snapshot.get("pending_targets", 0),
            snapshot.get("target_slots_used", 0),
            snapshot.get("completed_targets", 0),
            snapshot.get("completed_targets_total", 0),
            snapshot.get("target_slots_used", 0),
            snapshot.get("target_slots_capacity", 0),
            snapshot.get("target_slots_available", 0),
            _capacity_value(snapshot, "target_slots_utilization_percent", "%", missing_default=0),
            snapshot.get("target_slots_peak", 0),
            snapshot.get("configured_max_active_targets", 0),
            snapshot.get("configured_target_task_window", 0),
            snapshot.get("publish_queue_depth", 0),
            snapshot.get("publish_queue_capacity", 0),
            _capacity_value(snapshot, "publish_queue_utilization_percent", "%", missing_default=0),
            _capacity_value(snapshot, "publish_batch_age_ms", "ms", missing_default=0),
            _capacity_value(snapshot, "publish_queue_residence_p99_ms", "ms", missing_default=0),
            _capacity_value(snapshot, "event_loop_lag_ms", "ms", missing_default=0),
            _capacity_value(snapshot, "event_loop_lag_p99_ms", "ms", missing_default=0),
            _capacity_value(snapshot, "process_cpu_percent", "%"),
            _capacity_value(snapshot, "process_cpu_quota_utilization_percent", "%"),
            _capacity_value(snapshot, "process_rss_mb", "MiB"),
            _capacity_value(snapshot, "process_threads"),
            _capacity_value(snapshot, "process_open_fds"),
            _capacity_value(snapshot, "cgroup_memory_current_mb", "MiB"),
            _capacity_value(snapshot, "cgroup_memory_limit_mb", "MiB"),
            _capacity_value(snapshot, "cgroup_memory_utilization_percent", "%"),
            _capacity_value(snapshot, "cgroup_cpu_limit_cores", "核"),
            _capacity_value(snapshot, "cgroup_cpu_throttled_seconds_delta", "秒"),
            _capacity_value(snapshot, "cgroup_cpu_throttled_periods_delta", "次"),
        )

    async def _execute(self, request: CollectionRequest, lease: RunLease):
        plugin = self._plugin_factory.resolve(request)
        prepare_plugin = getattr(plugin, "prepare", None)
        if callable(prepare_plugin):
            await prepare_plugin(request)
        prepared_executor_config = getattr(plugin, "prepared_executor_config", None)
        if prepared_executor_config is None:
            # 非配置采集插件仍按 YAML 解析策略与执行计划。
            request = await apply_yaml_target_policy_async(request)
            plan = self._execution_plan_resolver.resolve(request)
        else:
            # Enterprise Collector 加载失败时，策略与计划必须跟随最终 OSS 配置。
            request = apply_executor_target_policy(request, prepared_executor_config)
            plan = self._execution_plan_resolver.resolve(
                request,
                executor_config=prepared_executor_config,
            )
        # 有 probe 且未显式关闭时启用廉价 AccessProbe；否则 CredentialAttempt=collect
        access_probe = None
        if callable(getattr(plugin, "probe", None)) and getattr(plugin, "supports_access_probe", True):
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
        try:
            return await executor.execute(request, lease)
        finally:
            close_plugin = getattr(plugin, "close", None)
            if callable(close_plugin):
                try:
                    await close_plugin()
                except Exception as exc:  # noqa: BLE001 - 清理失败不覆盖 Run 原始结果
                    logger.exception(
                        "event=collection_plugin_close_failed task_id=%s plugin_ref=%s " "failed_stage=plugin_close error_type=PluginCloseFailure",
                        safe_log_value(request.task_id),
                        safe_log_value(request.plugin_ref),
                        exc_info=safe_exception_info(exc),
                    )

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
            "network_topology_max_active_targets": self.settings.network_topology_max_active_targets,
            "target_task_window": self.settings.target_task_window,
            **capacity,
            "event_loop_lag_seconds": self._loop_lag.latest_seconds,
            "event_loop_lag_p99_seconds": self._loop_lag.p99_seconds,
            "thread_count": threading.active_count(),
            "open_file_descriptors": _open_file_descriptor_count(),
            "submissions": dict(self._submission_counts),
            "redis_pool_wait_seconds_total": float(getattr(self._redis, "pool_wait_seconds_total", 0.0) or 0.0),
            "redis_pool_timeout_total": float(getattr(self._redis, "pool_timeout_total", 0) or 0),
            "redis_pool_exhaustion_total": float(getattr(self._redis, "pool_exhaustion_total", 0) or 0),
            **nats_metrics_connection_stats(),
            **self._metrics.snapshot(),
        }


def _capacity_value(
    snapshot: dict[str, float | int],
    key: str,
    unit: str = "",
    *,
    missing_default: float | int = -1,
) -> str:
    value = snapshot.get(key, missing_default)
    if not isinstance(value, (int, float)) or value < 0:
        return "不可用"
    return f"{value}{unit}"


def _capacity_status(snapshot: dict[str, float | int]) -> tuple[str, str]:
    issues = []
    if snapshot.get("cgroup_cpu_throttled_seconds_delta", 0) > 0:
        issues.append("CPU发生限流")
    if snapshot.get("event_loop_lag_p99_ms", 0) >= 1000:
        issues.append("事件循环P99延迟超过1秒")
    if snapshot.get("process_cpu_quota_utilization_percent", 0) >= 80:
        issues.append("CPU配额使用率超过80%")
    if snapshot.get("cgroup_memory_utilization_percent", 0) >= 80:
        issues.append("容器内存使用率超过80%")
    if snapshot.get("publish_queue_utilization_percent", 0) >= 80:
        issues.append("发布队列使用率超过80%")
    if issues:
        return "需关注", "、".join(issues)
    if snapshot.get("active_runs", 0) == 0 and snapshot.get("target_slots_used", 0) == 0:
        return "空闲", "当前无采集任务"
    if snapshot.get("pending_targets", 0) > 0 or snapshot.get("target_slots_utilization_percent", 0) >= 80:
        return "繁忙", "存在排队目标或并发使用率较高"
    return "正常", "资源余量充足"


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
