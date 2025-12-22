# -- coding: utf-8 --
# @File: task_queue.py
# @Time: 2025/12/19
# @Author: AI Assistant
"""
异步任务队列模块 - 基于 arq
用于处理采集任务的异步执行

生产环境增强：
- Redis 连接池配置
- 连接重试机制
- 健康检查
- 监控指标
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
from dotenv import load_dotenv

load_dotenv()


class TaskQueueConfig:
    """任务队列配置 - 生产环境增强版"""

    def __init__(self):
        # Redis 基础配置
        self.redis_host = os.getenv("REDIS_HOST", "localhost")
        self.redis_port = int(os.getenv("REDIS_PORT", "6379"))
        self.redis_password = os.getenv("REDIS_PASSWORD")
        self.redis_db = int(os.getenv("REDIS_DB", "0"))

        # 连接池配置（生产环境重要）
        self.socket_timeout = int(os.getenv("REDIS_SOCKET_TIMEOUT", "5"))
        self.socket_connect_timeout = int(os.getenv("REDIS_CONNECT_TIMEOUT", "5"))

        # 任务配置
        self.max_jobs = int(os.getenv("TASK_MAX_JOBS", "10"))
        self.job_timeout = int(os.getenv("TASK_JOB_TIMEOUT", "300"))

        # 健康检查配置
        self.health_check_interval = int(os.getenv("HEALTH_CHECK_INTERVAL", "30"))
        self.max_retry_attempts = int(os.getenv("REDIS_MAX_RETRY", "3"))

    def get_redis_settings(self) -> RedisSettings:
        """获取Redis配置 - 生产环境优化"""
        return RedisSettings(
            host=self.redis_host,
            port=self.redis_port,
            password=self.redis_password,
            database=self.redis_db,
            # 生产环境关键配置
            conn_timeout=self.socket_connect_timeout,
            conn_retries=self.max_retry_attempts,
            conn_retry_delay=1,  # 重试间隔 1秒
        )


class TaskQueue:
    """任务队列管理器 - 生产环境增强版"""

    def __init__(self, app: Optional[Sanic] = None):
        self.app = app
        self.config = TaskQueueConfig()
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
        """连接到Redis - 带重试机制"""
        if self.pool is None:
            retry_count = 0
            last_error = None

            while retry_count < self.config.max_retry_attempts:
                try:
                    self.pool = await create_pool(self.config.get_redis_settings())
                    self._is_healthy = True
                    logger.info(
                        f"Connected to Redis: {self.config.redis_host}:{self.config.redis_port}"
                    )
                    return
                except Exception as e:
                    retry_count += 1
                    last_error = e
                    self.metrics["redis_connection_errors"] += 1
                    logger.warning(
                        f"Failed to connect to Redis (attempt {retry_count}/{self.config.max_retry_attempts}): {e}"
                    )
                    if retry_count < self.config.max_retry_attempts:
                        await asyncio.sleep(1 * retry_count)  # 指数退避

            # 所有重试都失败
            logger.error(f"Failed to connect to Redis after {self.config.max_retry_attempts} attempts")
            raise ConnectionError(f"Redis connection failed: {last_error}")

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
        """健康检查循环 - 定期检查 Redis 连接"""
        logger.info(f"Health check started (interval: {self.config.health_check_interval}s)")

        while True:
            try:
                await asyncio.sleep(self.config.health_check_interval)

                if self.pool:
                    try:
                        # 执行简单的 ping 检查
                        await self.pool.ping()
                        if not self._is_healthy:
                            logger.info("Redis connection recovered")
                        self._is_healthy = True
                    except Exception as e:
                        logger.error(f"Health check failed: {e}")
                        self._is_healthy = False
                        self.metrics["redis_connection_errors"] += 1
                        # 尝试重连
                        try:
                            await self.close()
                            await self.connect()
                        except Exception as reconnect_error:
                            logger.error(f"Reconnection failed: {reconnect_error}")
                else:
                    self._is_healthy = False

            except asyncio.CancelledError:
                logger.info("Health check stopped")
                break
            except Exception as e:
                logger.error(f"Unexpected error in health check: {e}")

    def _generate_task_id(self, params: Dict[str, Any]) -> str:
        """根据采集参数生成唯一的任务ID

        基于以下参数生成：
        - monitor_type / plugin_name: 采集类型
        - 关键参数（host, instance_id 等）

        这样相同的采集请求会生成相同的 task_id，实现去重
        """
        # 提取关键参数用于生成唯一ID
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

        # 生成稳定的哈希值（使用完整 MD5，避免碰撞）
        param_str = json.dumps(key_params, sort_keys=True)
        param_hash = hashlib.md5(param_str.encode()).hexdigest()  # 使用完整 32 字符

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
        将采集任务加入队列（带去重检查）

        Args:
            params: 采集参数
            task_id: 任务ID（可选，如果不提供则自动生成）

        Returns:
            包含任务信息的字典
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

        # 生成任务ID（用于去重）
        if not task_id:
            task_id = self._generate_task_id(params)

        try:
            # 检查任务是否已存在
            existing_job = await self.get_job_status(task_id)
            if existing_job:
                status = existing_job.get("status")

                # 如果任务还在队列中或正在执行，不重复入队
                if status in [JobStatus.queued, JobStatus.in_progress]:
                    self.metrics["tasks_skipped"] += 1
                    logger.warning(
                        f"Task {task_id} already exists with status: {status}, skipping enqueue"
                    )
                    return {
                        "task_id": task_id,
                        "job_id": existing_job.get("job_id"),
                        "status": "skipped",
                        "reason": f"Task already {status}",
                        "existing_job": existing_job,
                        "timestamp": int(time.time() * 1000)
                    }

            # 将任务加入队列
            job = await self.pool.enqueue_job(
                'collect_task',  # 函数名
                params,          # 位置参数：params
                task_id,         # 位置参数：task_id
                _job_id=task_id, # 指定 job_id
            )

            if not job:
                raise RuntimeError(f"Failed to enqueue job {task_id}, enqueue_job returned None")

            self.metrics["tasks_enqueued"] += 1
            logger.info(f"Task enqueued: {task_id}, job_id: {job.job_id}")

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

    async def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        if not self.pool:
            await self.connect()

        try:
            # 使用 Job.deserialize 从 Redis 获取任务对象（注意是美式拼写）
            job = await Job.deserialize(job_id, redis=self.pool)
            if job:
                return {
                    "job_id": job.job_id,
                    "status": await job.status(),
                    "enqueued_time": job.enqueue_time.isoformat() if job.enqueue_time else None,
                }
            return None
        except Exception as e:
            # Job 不存在时会抛出异常，这是正常情况
            logger.debug(f"Job {job_id} not found or error: {e}")
            return None

    async def cancel_job(self, job_id: str) -> bool:
        """取消任务"""
        if not self.pool:
            await self.connect()

        try:
            # 使用 Job.deserialize 从 Redis 获取任务对象（注意是美式拼写）
            job = await Job.deserialize(job_id, redis=self.pool)
            if job:
                await job.abort()
                logger.info(f"Job {job_id} cancelled")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to cancel job {job_id}: {e}")
            return False

    async def get_queue_stats(self) -> Dict[str, Any]:
        """获取队列统计信息 - 用于监控"""
        if not self.pool:
            return {
                "healthy": False,
                "error": "Redis not connected"
            }

        try:
            # 获取队列信息
            queued_count = await self.pool.zcard("arq:queue")

            return {
                "healthy": self._is_healthy,
                "queued_jobs": queued_count,
                "metrics": self.metrics.copy(),
                "redis_info": {
                    "host": self.config.redis_host,
                    "port": self.config.redis_port,
                    "db": self.config.redis_db,
                },
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
    """初始化任务队列（在 server.py 中调用）"""
    global _task_queue_instance
    _task_queue_instance = TaskQueue(app)
    return _task_queue_instance


def get_task_queue() -> TaskQueue:
    """获取任务队列实例"""
    if _task_queue_instance is None:
        raise RuntimeError("Task queue not initialized. Call initialize_task_queue() first.")
    return _task_queue_instance
