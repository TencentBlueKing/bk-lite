# -- coding: utf-8 --
# @File: task_queue.py
# @Time: 2025/12/19
# @Author: AI Assistant
"""
异步任务队列模块 - 使用统一的 Redis 配置
"""
import os
import json
import time
import traceback
import hashlib
import asyncio
from typing import Optional, Dict, Any
from arq import create_pool
from arq.connections import RedisSettings, ArqRedis
from arq.jobs import JobStatus, Job
from sanic import Sanic
from sanic.log import logger
from core.redis_config import REDIS_CONFIG, print_redis_config


class TaskQueue:
    """任务队列管理器 - 使用统一的 Redis 配置"""

    def __init__(self, app: Optional[Sanic] = None):
        self.app = app
        self.pool: Optional[ArqRedis] = None
        self._health_check_task: Optional[asyncio.Task] = None
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

        @self.app.listener('before_server_start')
        async def start_task_queue(app, loop):
            await self.connect()
            app.ctx.task_queue = self
            # 启动健康检查
            self._health_check_task = asyncio.create_task(self._health_check_loop())
            logger.info("Task queue initialized with health check")

        @self.app.listener('after_server_stop')
        async def stop_task_queue(app, loop):
            # 停止健康检查
            if self._health_check_task:
                self._health_check_task.cancel()
                try:
                    await self._health_check_task
                except asyncio.CancelledError:
                    pass
            await self.close()
            logger.info("Task queue closed")

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
                logger.info("Redis connection closed gracefully")
            except Exception as e:
                logger.error(f"Error closing Redis connection: {e}")
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
        key_params = {
            "monitor_type": params.get("monitor_type"),
            "plugin_name": params.get("plugin_name"),
            "host": params.get("host"),
            "port": params.get("port"),
            "instance_id": params.get("tags", {}).get("instance_id"),
            "collect_type": params.get("collect_type"),
        }

        # 移除空值
        key_params = {k: v for k, v in key_params.items() if v is not None}

        # 生成稳定的哈希值
        param_str = json.dumps(key_params, sort_keys=True)
        param_hash = hashlib.md5(param_str.encode()).hexdigest()

        # 生成任务ID
        task_type = params.get("monitor_type") or params.get("plugin_name", "unknown")
        task_id = f"collect_{task_type}_{param_hash}"

        return task_id

    async def enqueue_collect_task(
        self,
        params: Dict[str, Any],
        task_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        将采集任务加入队列

        ⚠️ 去重逻辑：
        - 如果任务正在执行或在队列中 → 不重复入队
        - 如果任务已完成 → 允许再次入队
        """
        # 健康检查
        if not self._is_healthy:
            logger.warning("Redis connection unhealthy, attempting to reconnect...")
            try:
                await self.connect()
            except Exception as e:
                self.metrics["tasks_failed"] += 1
                raise RuntimeError(f"Task queue unavailable: {e}")

        if not self.pool:
            await self.connect()

        # 生成任务ID（用于业务去重）
        if not task_id:
            task_id = self._generate_task_id(params)

        try:
            # ✅ 应用层去重：检查我们自己维护的任务状态键
            # 使用 Redis 键来跟踪正在执行的任务：task:running:{task_id}
            running_key = f"task:running:{task_id}"

            # 检查任务是否正在运行
            is_running = await self.pool.get(running_key)
            if is_running:
                self.metrics["tasks_skipped"] += 1
                logger.warning(
                    f"Task {task_id} is already running or queued, skipping enqueue"
                )
                return {
                    "task_id": task_id,
                    "status": "skipped",
                    "reason": "Task already running or queued",
                    "timestamp": int(time.time() * 1000)
                }

            # 将任务加入队列
            logger.info(f"[Task Queue] Enqueuing task: {task_id}")
            logger.info(f"[Task Queue] Function: 'collect_task', Params keys: {list(params.keys())}")

            # ⚠️ 关键：不使用 _job_id，让 ARQ 自动生成唯一的 job_id
            job = await self.pool.enqueue_job(
                'collect_task',      # 函数名（字符串）
                params=params,       # kwargs 传递
                task_id=task_id,     # kwargs 传递（业务 ID）
            )

            logger.info(f"[Task Queue] enqueue_job returned: {job}, type: {type(job)}")

            if not job:
                logger.error(f"[Task Queue] ❌ enqueue_job returned None for task {task_id}")
                logger.error(f"[Task Queue] This means Worker is NOT running or NOT registered!")
                print_redis_config()
                raise RuntimeError(f"Failed to enqueue job {task_id}, enqueue_job returned None")

            # ✅ 标记任务为运行中（设置 TTL，防止任务失败后永久锁定）
            # TTL 设置为 job_timeout + 60 秒的缓冲时间
            ttl = int(os.getenv("TASK_JOB_TIMEOUT", "300")) + 60
            await self.pool.set(running_key, job.job_id, ex=ttl)

            self.metrics["tasks_enqueued"] += 1
            logger.info(f"[Task Queue] ✅ Task enqueued successfully: {task_id}, ARQ job_id: {job.job_id}")

            return {
                "task_id": task_id,
                "job_id": job.job_id,
                "status": "queued",
                "enqueued_at": int(time.time() * 1000)
            }
        except Exception as e:
            self.metrics["tasks_failed"] += 1
            logger.error(f"Failed to enqueue task {task_id}: {e}")
            logger.error(traceback.format_exc())
            raise

    async def mark_task_completed(self, task_id: str):
        """
        标记任务完成，清除运行中标记
        这个方法应该在 Worker 任务完成后调用
        """
        running_key = f"task:running:{task_id}"
        await self.pool.delete(running_key)
        logger.info(f"[Task Queue] Task {task_id} marked as completed, can be re-queued now")

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
                    "enqueued_time": job.enqueue_time.isoformat() if job.enqueue_time else None,
                }
            return None
        except Exception as e:
            logger.debug(f"Job {job_id} not found or error: {e}")
            return None

    async def get_queue_stats(self) -> Dict[str, Any]:
        """获取队列统计信息"""
        if not self.pool:
            return {
                "healthy": False,
                "error": "Redis not connected"
            }

        try:
            queued_count = await self.pool.zcard("arq:queue")

            return {
                "healthy": self._is_healthy,
                "queued_jobs": queued_count,
                "metrics": self.metrics.copy(),
                "redis_info": REDIS_CONFIG.copy(),
                "timestamp": int(time.time() * 1000)
            }
        except Exception as e:
            logger.error(f"Failed to get queue stats: {e}")
            return {
                "healthy": False,
                "error": str(e)
            }


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
        raise RuntimeError("Task queue not initialized. Call initialize_task_queue() first.")
    return _task_queue_instance
