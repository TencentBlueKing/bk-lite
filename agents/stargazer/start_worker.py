#!/usr/bin/env python
# -- coding: utf-8 --
"""
ARQ Worker 启动脚本

使用方法：
    python start_worker.py

或使用 ARQ CLI（推荐生产环境）：
    arq core.worker.WorkerSettings
"""
import os
import sys
import logging
from dotenv import load_dotenv

# 加载环境变量（必须在导入其他模块之前）
load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


def main():
    """启动 ARQ Worker"""
    logger.info("=" * 70)
    logger.info("Starting ARQ Worker")
    logger.info("=" * 70)
    logger.info(f"Redis: {os.getenv('REDIS_HOST')}:{os.getenv('REDIS_PORT')}/DB={os.getenv('REDIS_DB')}")
    logger.info("=" * 70)

    try:
        from arq import run_worker
        from core.worker import WorkerSettings

        # 验证配置
        logger.info(f"Max jobs: {WorkerSettings.max_jobs}")
        logger.info(f"Job timeout: {WorkerSettings.job_timeout}s")
        logger.info(f"Registered functions: {[f.__name__ for f in WorkerSettings.functions]}")
        logger.info("=" * 70)

        # 启动 Worker
        run_worker(WorkerSettings)

    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
    except Exception as e:
        logger.error(f"Failed to start worker: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
