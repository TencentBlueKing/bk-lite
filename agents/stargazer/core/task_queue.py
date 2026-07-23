# -- coding: utf-8 --
# @File: task_queue.py
# @Time: 2025/12/19
# @Author: AI Assistant
"""
异步任务队列模块 - 使用统一的 Redis 配置
"""
import asyncio
import hashlib
import json
import os
import time
import traceback
import uuid
from typing import Any, Dict, Optional

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from arq.jobs import Job
from core.redis_config import REDIS_CONFIG, print_redis_config
from core.task_queue_startup_cleanup import (
    StartupCleanupConfig,
    StartupCleanupConfigError,
    cleanup_startup_orphan_markers,
)
from redis.exceptions import RedisError
from sanic import Sanic
from sanic.log import logger

_STARTUP_CLEANUP_LOG_LEVELS = {
    ("success", None): "info",
    ("skipped", "disabled"): "info",
    ("skipped", "lock_not_acquired"): "info",
    ("warning", "timeout"): "warning",
    ("warning", "redis_error"): "warning",
    ("warning", "limit_reached"): "warning",
    ("warning", "marker_errors"): "warning",
}


def _safe_task_queue_log(level: str, message: str, *args) -> None:
    """日志基础设施故障不能影响队列生命周期。"""
    try:
        getattr(logger, level)(message, *args)
    except Exception:
        pass


def _safe_cleanup_count(value: object) -> int:
    return (
        value if isinstance(value, int) and not isinstance(value, bool) else 0
    )


async def _is_host_remote_callback_pending(task_id: str) -> bool:
    try:
        import core.host_remote_callback as host_remote_callback

        callback_context = (
            await host_remote_callback.load_host_remote_callback_context(
                task_id
            )
        )
        if not callback_context:
            return False

        status = callback_context.get("status") or {}
        return (
            status.get("execution") == "waiting_callback"
            and callback_context.get("callback_received_at") is None
        )
    except Exception as err:
        logger.warning(
            "[Task Queue] Failed to inspect host remote callback context "
            f"for task {task_id}: {err}",
            exc_info=True,
        )
        return False


def _resolve_running_flag_ttl(params: Dict[str, Any]) -> int:
    base_ttl = int(os.getenv("TASK_JOB_TIMEOUT", "600")) + 60
    if (params or {}).get("monitor_type") != "host":
        return base_ttl

    callback_deadline = (
        int(os.getenv("HOST_REMOTE_CALLBACK_DEADLINE_SECONDS", "1200")) + 60
    )
    submit_accept_timeout = (
        int(os.getenv("HOST_REMOTE_SUBMIT_ACCEPT_TIMEOUT_SECONDS", "300")) + 60
    )
    return max(base_ttl, callback_deadline, submit_accept_timeout)


def _resolve_dedupe_ttl() -> int:
    return int(os.getenv("TASK_DEDUPE_TTL", "86400"))


def generate_dedupe_key(params: Dict[str, Any]) -> str:
    key_params = {
        "monitor_type": params.get("monitor_type"),
        "plugin_name": params.get("plugin_name"),
        "host": params.get("host"),
        "port": params.get("port"),
        "credential_id": params.get("credential_id"),
        "instance_id": params.get("tags", {}).get("instance_id"),
        "collect_type": params.get("collect_type"),
    }

    collect_task_id = params.get("collect_task_id")
    if collect_task_id is not None:
        key_params["collect_task_id"] = collect_task_id

    config_file_path = str(params.get("config_file_path") or "").strip()
    if config_file_path:
        key_params["config_file_path"] = config_file_path

    key_params = {
        key: value for key, value in key_params.items() if value is not None
    }
    param_str = json.dumps(key_params, sort_keys=True)
    param_hash = hashlib.md5(param_str.encode()).hexdigest()
    task_type = params.get("monitor_type") or params.get(
        "plugin_name", "unknown"
    )
    return f"collect_{task_type}_{param_hash}"


class TaskQueue:
    """任务队列管理器 - 使用统一的 Redis 配置"""

    def __init__(self, app: Optional[Sanic] = None):
        self.app = app
        self.pool: Optional[ArqRedis] = None
        self._health_check_task: Optional[asyncio.Task] = None
        self._startup_cleanup_task: Optional[asyncio.Task] = None
        self._is_healthy = False

        # 监控指标
        self.metrics = {
            "tasks_enqueued": 0,
            "tasks_skipped": 0,
            "tasks_failed": 0,
            "redis_connection_errors": 0,
        }

        if app:
            self._register_lifecycle()

    def _register_lifecycle(self):
        """注册 Sanic 生命周期事件"""

        @self.app.listener("before_server_start")
        async def start_task_queue(app, loop):
            await self.connect()
            app.ctx.task_queue = self
            # 启动健康检查
            self._health_check_task = asyncio.create_task(
                self._health_check_loop()
            )
            logger.info("Task queue initialized with health check")

        @self.app.listener("after_server_start")
        async def start_orphan_cleanup(app, loop):
            existing_task = self._startup_cleanup_task
            if existing_task:
                if not existing_task.done():
                    _safe_task_queue_log(
                        "info",
                        "event=task_queue_startup_cleanup status=skipped "
                        "reason=already_scheduled",
                    )
                    return
                self._consume_completed_startup_cleanup_task(existing_task)
                self._startup_cleanup_task = None
            try:
                config = StartupCleanupConfig.from_env()
            except StartupCleanupConfigError:
                _safe_task_queue_log(
                    "warning",
                    "event=task_queue_startup_cleanup status=warning "
                    "reason=invalid_config",
                )
                return
            if not config.enabled:
                _safe_task_queue_log(
                    "info",
                    "event=task_queue_startup_cleanup status=skipped "
                    "reason=disabled",
                )
                return
            self._startup_cleanup_task = asyncio.create_task(
                self._run_startup_cleanup(config),
                name="stargazer-startup-orphan-cleanup",
            )

        @self.app.listener("after_server_stop")
        async def stop_task_queue(app, loop):
            cancellation_requested = False
            startup_cleanup_task = self._startup_cleanup_task
            if startup_cleanup_task:
                startup_cleanup_task.cancel()
                cancellation_requested |= await self._await_shutdown_task(
                    startup_cleanup_task,
                    reason="stop_failed",
                )
                self._startup_cleanup_task = None
            # 停止健康检查
            if self._health_check_task:
                self._health_check_task.cancel()
                cancellation_requested |= await self._await_shutdown_task(
                    self._health_check_task,
                    reason="health_check_stop_failed",
                )
            close_task = asyncio.create_task(self.close())
            cancellation_requested |= await self._await_shutdown_task(
                close_task,
                reason="close_failed",
            )
            _safe_task_queue_log("info", "Task queue closed")
            current_task = asyncio.current_task()
            if cancellation_requested or (
                current_task is not None and current_task.cancelling() > 0
            ):
                raise asyncio.CancelledError

    async def _await_shutdown_task(
        self, task: asyncio.Task, *, reason: str
    ) -> bool:
        """等待停服子任务；保留外部取消，仍完成必要的资源收束。"""
        cancellation_requested = False
        current_task = asyncio.current_task()
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                if current_task is not None and current_task.cancelling() > 0:
                    cancellation_requested = True
                if task.done():
                    break
            except Exception:
                break

        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception as error:
            _safe_task_queue_log(
                "warning",
                "event=task_queue_startup_cleanup status=warning "
                "reason=%s exception_type=%s",
                reason,
                type(error).__name__,
            )
        return cancellation_requested

    def _consume_completed_startup_cleanup_task(
        self, task: asyncio.Task
    ) -> None:
        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception as error:
            _safe_task_queue_log(
                "warning",
                "event=task_queue_startup_cleanup status=warning "
                "reason=completed_task_failed exception_type=%s",
                type(error).__name__,
            )

    async def _run_startup_cleanup(self, config: StartupCleanupConfig) -> None:
        """执行启动孤儿标记清理；任何失败都不能影响 Sanic 启动。"""
        try:
            result = await cleanup_startup_orphan_markers(self.pool, config)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            reason = (
                "redis_error"
                if isinstance(error, RedisError)
                else "cleanup_failed"
            )
            _safe_task_queue_log(
                "warning",
                "event=task_queue_startup_cleanup status=warning "
                "reason=%s exception_type=%s",
                reason,
                type(error).__name__,
            )
            return

        try:
            log_level = _STARTUP_CLEANUP_LOG_LEVELS.get(
                (result.status, result.reason)
            )
        except TypeError:
            log_level = None
        if log_level is None:
            status = "warning"
            reason = "unknown_result"
            log_level = "warning"
        else:
            status = result.status
            reason = result.reason
        safe_reason = f" reason={reason}" if reason else ""
        _safe_task_queue_log(
            log_level,
            "event=task_queue_startup_cleanup status=%s%s "
            "scanned=%d candidates=%d deleted=%d preserved=%d errors=%d "
            "truncated=%s",
            status,
            safe_reason,
            _safe_cleanup_count(result.scanned),
            _safe_cleanup_count(result.candidates),
            _safe_cleanup_count(result.deleted),
            _safe_cleanup_count(result.preserved),
            _safe_cleanup_count(result.errors),
            result.truncated is True,
        )

    async def connect(self):
        """连接到Redis - 使用统一配置"""
        if self.pool is None:
            try:
                # ✅ 使用统一的 Redis 配置
                redis_settings = RedisSettings(
                    host=REDIS_CONFIG["host"],
                    port=REDIS_CONFIG["port"],
                    password=REDIS_CONFIG["password"],
                    database=REDIS_CONFIG["database"],
                )

                self.pool = await create_pool(redis_settings)
                self._is_healthy = True

                logger.info("=" * 70)
                logger.info("Task Queue Connected to Redis")
                logger.info("=" * 70)
                print_redis_config()
                logger.info("=" * 70)

            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}")
                raise ConnectionError(f"Redis connection failed: {e}")

    async def close(self):
        """关闭连接"""
        if self.pool:
            try:
                await self.pool.close()
                self._is_healthy = False
                _safe_task_queue_log(
                    "info", "Redis connection closed gracefully"
                )
            except Exception:
                _safe_task_queue_log("error", "Error closing Redis connection")
            finally:
                self.pool = None

    async def _health_check_loop(self):
        """健康检查循环"""
        health_check_interval = int(os.getenv("HEALTH_CHECK_INTERVAL", "30"))

        while True:
            try:
                await asyncio.sleep(health_check_interval)

                if self.pool:
                    try:
                        await self.pool.ping()
                        if not self._is_healthy:
                            logger.info("Redis connection recovered")
                        self._is_healthy = True
                    except Exception as e:
                        logger.error(f"Health check failed: {e}")
                        self._is_healthy = False
                        self.metrics["redis_connection_errors"] += 1
                else:
                    self._is_healthy = False

            except asyncio.CancelledError:
                logger.info("Health check stopped")
                break
            except Exception as e:
                logger.error(f"Unexpected error in health check: {e}")

    def _generate_task_id(self, params: Dict[str, Any]) -> str:
        """根据采集参数生成唯一的任务ID"""
        return generate_dedupe_key(params)

    def _generate_dedupe_key(self, params: Dict[str, Any]) -> str:
        """生成稳定去重键；host 远程任务 task_id 每次唯一，但 dedupe_key 必须稳定。"""
        return generate_dedupe_key(params)

    async def _is_job_active(self, job_id: str) -> bool:
        in_queue = await self.pool.zscore("arq:queue", job_id) is not None
        in_progress = await self.pool.exists(f"arq:in-progress:{job_id}")
        return bool(in_queue or in_progress)

    async def enqueue_collect_task(
        self, params: Dict[str, Any], task_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        将采集任务加入队列

        ⚠️ 去重逻辑：
        - 如果任务正在执行或在队列中 → 不重复入队
        - 如果任务已完成 → 允许再次入队
        """
        # 健康检查
        if not self._is_healthy:
            logger.warning(
                "Redis connection unhealthy, attempting to reconnect..."
            )
            try:
                await self.connect()
            except Exception as e:
                self.metrics["tasks_failed"] += 1
                raise RuntimeError(f"Task queue unavailable: {e}")

        if not self.pool:
            await self.connect()

        # 生成任务ID（用于业务去重）
        if not task_id:
            if (params or {}).get("monitor_type") == "host":
                task_id = f"collect_host_{uuid.uuid4().hex}"
            else:
                task_id = self._generate_task_id(params)
        dedupe_key = self._generate_dedupe_key(params)
        dedupe_redis_key = f"task:dedupe:{dedupe_key}"

        try:
            existing_dedupe_job_id = await self.pool.get(dedupe_redis_key)
            if existing_dedupe_job_id:
                existing_job_id = (
                    existing_dedupe_job_id.decode()
                    if isinstance(existing_dedupe_job_id, (bytes, bytearray))
                    else str(existing_dedupe_job_id)
                )
                if await self._is_job_active(existing_job_id):
                    self.metrics["tasks_skipped"] += 1
                    remaining_ttl = await self.pool.ttl(dedupe_redis_key)
                    instance_id = params.get("tags", {}).get("instance_id")
                    logger.warning(
                        "event=task_enqueue status=skipped "
                        "reason=dedupe_job_active "
                        f"task_id={task_id} job_id={existing_job_id} "
                        f"dedupe_key={dedupe_key} ttl={remaining_ttl}s "
                        f"monitor_type={params.get('monitor_type')} "
                        f"model_id={params.get('model_id')} "
                        f"plugin_name={params.get('plugin_name')} "
                        f"host={params.get('host')} "
                        f"instance_id={instance_id}"
                    )
                    return {
                        "task_id": task_id,
                        "job_id": existing_job_id,
                        "status": "skipped",
                        "reason": (
                            "Task already queued or running for dedupe key"
                        ),
                        "dedupe_key": dedupe_key,
                        "dedupe_ttl": remaining_ttl,
                        "timestamp": int(time.time() * 1000),
                    }

                logger.warning(
                    "event=task_dedupe_stale action=clear "
                    f"task_id={task_id} job_id={existing_job_id} "
                    f"dedupe_key={dedupe_key}"
                )
                await self.pool.delete(dedupe_redis_key)

            # ✅ 应用层去重：检查我们自己维护的任务状态键
            # 使用 Redis 键来跟踪正在执行的任务：task:running:{task_id}
            running_key = f"task:running:{task_id}"

            # 检查任务是否正在运行
            is_running = await self.pool.get(running_key)
            if is_running:
                existing_job_id = (
                    is_running.decode()
                    if isinstance(is_running, (bytes, bytearray))
                    else str(is_running)
                )

                if await self._is_job_active(existing_job_id):
                    self.metrics["tasks_skipped"] += 1
                    remaining_ttl = await self.pool.ttl(running_key)
                    instance_id = params.get("tags", {}).get("instance_id")
                    logger.warning(
                        "event=task_enqueue status=skipped "
                        "reason=running_job_active "
                        f"task_id={task_id} job_id={existing_job_id} "
                        f"dedupe_key={dedupe_key} ttl={remaining_ttl}s "
                        f"monitor_type={params.get('monitor_type')} "
                        f"model_id={params.get('model_id')} "
                        f"plugin_name={params.get('plugin_name')} "
                        f"host={params.get('host')} "
                        f"instance_id={instance_id}"
                    )
                    return {
                        "task_id": task_id,
                        "job_id": existing_job_id,
                        "status": "skipped",
                        "reason": "Task already running or queued",
                        "dedupe_ttl": remaining_ttl,
                        "timestamp": int(time.time() * 1000),
                    }

                if (params or {}).get("monitor_type") == "host":
                    callback_pending = await _is_host_remote_callback_pending(
                        task_id
                    )
                    if callback_pending:
                        self.metrics["tasks_skipped"] += 1
                        remaining_ttl = await self.pool.ttl(running_key)
                        logger.warning(
                            f"Task {task_id} is still waiting for host remote "
                            "callback, skipping enqueue "
                            f"(job_id={existing_job_id}, ttl={remaining_ttl}s)"
                        )
                        return {
                            "task_id": task_id,
                            "job_id": existing_job_id,
                            "status": "skipped",
                            "reason": "Host remote callback still pending",
                            "dedupe_ttl": remaining_ttl,
                            "timestamp": int(time.time() * 1000),
                        }

                logger.warning(
                    f"Detected stale running marker for task {task_id}, "
                    "clearing and re-enqueueing"
                )
                await self.pool.delete(running_key)

            # 将任务加入队列
            logger.info(
                "event=task_enqueue_start function=collect_task "
                f"task_id={task_id} dedupe_key={dedupe_key} "
                f"params_keys={list(params.keys())}"
            )

            # ⚠️ 关键：不使用 _job_id，让 ARQ 自动生成唯一的 job_id
            job = await self.pool.enqueue_job(
                "collect_task",  # 函数名（字符串）
                params=params,  # kwargs 传递
                task_id=task_id,  # kwargs 传递（业务 ID）
            )

            logger.info(
                f"[Task Queue] enqueue_job returned: {job}, type: {type(job)}"
            )

            if not job:
                logger.error(
                    "[Task Queue] ❌ enqueue_job returned None for task "
                    f"{task_id}"
                )
                logger.error(
                    "[Task Queue] This means Worker is NOT running or NOT "
                    "registered!"
                )
                print_redis_config()
                raise RuntimeError(
                    f"Failed to enqueue job {task_id}, enqueue_job returned "
                    "None"
                )

            # ✅ 标记任务为运行中（设置 TTL，防止任务失败后永久锁定）
            # TTL 设置为 job_timeout + 60 秒的缓冲时间；host remote 任务需覆盖 callback 等待窗口
            ttl = _resolve_running_flag_ttl(params)
            await self.pool.set(running_key, job.job_id, ex=ttl)
            await self.pool.set(
                dedupe_redis_key, job.job_id, ex=_resolve_dedupe_ttl()
            )

            self.metrics["tasks_enqueued"] += 1
            logger.info(
                "event=task_enqueue status=queued "
                f"task_id={task_id} job_id={job.job_id} "
                f"dedupe_key={dedupe_key} "
                f"monitor_type={params.get('monitor_type')} "
                f"model_id={params.get('model_id')} "
                f"plugin_name={params.get('plugin_name')} "
                f"host={params.get('host')} "
                f"instance_id={params.get('tags', {}).get('instance_id')}"
            )

            return {
                "task_id": task_id,
                "job_id": job.job_id,
                "status": "queued",
                "dedupe_key": dedupe_key,
                "enqueued_at": int(time.time() * 1000),
            }
        except Exception as e:
            self.metrics["tasks_failed"] += 1
            logger.error(f"Failed to enqueue task {task_id}: {e}")
            logger.error(traceback.format_exc())
            raise

    async def enqueue_host_remote_processing_task(
        self,
        task_id: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not self._is_healthy:
            logger.warning(
                "Redis connection unhealthy, attempting to reconnect..."
            )
            try:
                await self.connect()
            except Exception as e:
                self.metrics["tasks_failed"] += 1
                raise RuntimeError(f"Task queue unavailable: {e}")

        if not self.pool:
            await self.connect()

        processing_task_id = str(task_id).strip()
        if not processing_task_id:
            raise ValueError(
                "task_id is required for host remote processing task"
            )

        processing_job_id = (
            f"process_host_remote_callback:{processing_task_id}"
        )
        logger.info(
            "[Task Queue] Enqueuing host remote processing task: "
            f"{processing_task_id}"
        )
        job = await self.pool.enqueue_job(
            "process_host_remote_callback_task",
            params=params or {},
            task_id=processing_task_id,
            _job_id=processing_job_id,
        )

        if not job:
            existing_status = await self.get_job_status(processing_job_id)
            if existing_status is not None:
                return {
                    "task_id": processing_task_id,
                    "job_id": processing_job_id,
                    "status": "queued",
                    "enqueued_at": int(time.time() * 1000),
                }

            raise RuntimeError(
                "Failed to enqueue host remote processing task "
                f"{processing_task_id}"
            )

        self.metrics["tasks_enqueued"] += 1
        return {
            "task_id": processing_task_id,
            "job_id": job.job_id,
            "status": "queued",
            "enqueued_at": int(time.time() * 1000),
        }

    async def mark_task_completed(self, task_id: str):
        """
        标记任务完成，清除运行中标记
        这个方法应该在 Worker 任务完成后调用
        """
        running_key = f"task:running:{task_id}"
        await self.pool.delete(running_key)
        logger.info(
            f"[Task Queue] Task {task_id} marked as completed, can be "
            "re-queued now"
        )

    async def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态（保留用于其他用途）"""
        if not self.pool:
            await self.connect()

        try:
            job = await Job.deserialize(job_id, redis=self.pool)
            if job:
                return {
                    "job_id": job.job_id,
                    "status": await job.status(),
                    "enqueued_time": job.enqueue_time.isoformat()
                    if job.enqueue_time
                    else None,
                }
            return None
        except Exception as e:
            logger.debug(f"Job {job_id} not found or error: {e}")
            return None

    async def get_queue_stats(self) -> Dict[str, Any]:
        """获取队列统计信息"""
        if not self.pool:
            return {"healthy": False, "error": "Redis not connected"}

        try:
            queued_count = await self.pool.zcard("arq:queue")

            return {
                "healthy": self._is_healthy,
                "queued_jobs": queued_count,
                "metrics": self.metrics.copy(),
                "redis_info": REDIS_CONFIG.copy(),
                "timestamp": int(time.time() * 1000),
            }
        except Exception as e:
            logger.error(f"Failed to get queue stats: {e}")
            return {"healthy": False, "error": str(e)}


# 全局任务队列实例
_task_queue_instance: Optional[TaskQueue] = None


def initialize_task_queue(app: Sanic) -> TaskQueue:
    """初始化任务队列"""
    global _task_queue_instance
    _task_queue_instance = TaskQueue(app)
    return _task_queue_instance


def get_task_queue() -> TaskQueue:
    """获取任务队列实例"""
    if _task_queue_instance is None:
        raise RuntimeError(
            "Task queue not initialized. Call initialize_task_queue() first."
        )
    return _task_queue_instance
