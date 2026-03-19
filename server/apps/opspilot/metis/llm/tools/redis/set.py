from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from redis.exceptions import RedisError

from apps.opspilot.metis.llm.tools.redis.connection import get_redis_connection
from apps.opspilot.metis.llm.tools.redis.utils import build_error_response, build_success_response


@tool()
def redis_sadd(key: str, member: str, config: RunnableConfig = None):
    """向 Redis set 添加成员。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response({"added": client.sadd(key, member)}, key=key)
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_smembers(key: str, config: RunnableConfig = None):
    """读取 Redis set 的全部成员。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response(list(client.smembers(key)), key=key)
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_srem(key: str, member: str, config: RunnableConfig = None):
    """从 Redis set 中移除成员。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response({"removed": client.srem(key, member)}, key=key)
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_sismember(key: str, member: str, config: RunnableConfig = None):
    """检查成员是否属于指定 Redis set。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response({"key": key, "member": member, "is_member": bool(client.sismember(key, member))})
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_scard(key: str, config: RunnableConfig = None):
    """获取 Redis set 的成员数量。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response({"key": key, "count": client.scard(key)})
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_sinter(keys: list[str], config: RunnableConfig = None):
    """获取多个 Redis set 的交集。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response(list(client.sinter(keys)))
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_sunion(keys: list[str], config: RunnableConfig = None):
    """获取多个 Redis set 的并集。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response(list(client.sunion(keys)))
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_sdiff(keys: list[str], config: RunnableConfig = None):
    """获取多个 Redis set 的差集。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response(list(client.sdiff(keys)))
    except RedisError as e:
        return build_error_response(e)
