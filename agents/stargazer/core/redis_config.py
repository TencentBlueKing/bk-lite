# -- coding: utf-8 --
"""
统一的 Redis 配置

作用：
确保 Sanic Server 和 ARQ Worker 使用完全相同的 Redis 配置，
避免因配置不一致导致任务无法正常分发和消费。

使用方式：
    from core.redis_config import REDIS_CONFIG
"""
import os
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# 统一的 Redis 配置 - 所有地方都从这里读取
REDIS_CONFIG = {
    "host": os.getenv("REDIS_HOST", "localhost"),
    "port": int(os.getenv("REDIS_PORT", "6379")),
    "password": os.getenv("REDIS_PASSWORD"),
    "database": int(os.getenv("REDIS_DB", "0")),
}


def validate_redis_config() -> bool:
    """
    验证 Redis 配置是否完整

    Returns:
        bool: 配置是否有效
    """
    if not REDIS_CONFIG["host"]:
        logger.error("REDIS_HOST is not configured")
        return False

    if not REDIS_CONFIG["port"]:
        logger.error("REDIS_PORT is not configured")
        return False

    return True


def print_redis_config():
    """打印 Redis 配置（用于调试）"""
    logger.info(f"Redis Host: {REDIS_CONFIG['host']}")
    logger.info(f"Redis Port: {REDIS_CONFIG['port']}")
    logger.info(f"Redis DB: {REDIS_CONFIG['database']}")
    logger.info(f"Redis Password: {'***' if REDIS_CONFIG['password'] else 'None'}")
