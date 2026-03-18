from typing import Dict

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from redis.exceptions import RedisError

from apps.opspilot.metis.llm.tools.redis.connection import get_redis_connection
from apps.opspilot.metis.llm.tools.redis.utils import build_error_response, build_success_response


@tool()
def redis_zadd(key: str, members: Dict[str, float], config: RunnableConfig = None):
    """向 Redis sorted set 批量添加带分值的成员。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response({"added": client.zadd(key, members)}, key=key)
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_zrange(key: str, start: int = 0, end: int = -1, withscores: bool = False, config: RunnableConfig = None):
    """读取 Redis sorted set 指定区间内的成员，可选返回分值。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response(client.zrange(key, start, end, withscores=withscores), key=key)
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_zrem(key: str, member: str, config: RunnableConfig = None):
    """从 Redis sorted set 中移除成员。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response({"removed": client.zrem(key, member)}, key=key)
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_zscore(key: str, member: str, config: RunnableConfig = None):
    """获取 Redis sorted set 成员的分值。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response({"key": key, "member": member, "score": client.zscore(key, member)})
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_zcard(key: str, config: RunnableConfig = None):
    """获取 Redis sorted set 的成员数量。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response({"key": key, "count": client.zcard(key)})
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_zrevrange(key: str, start: int = 0, end: int = -1, withscores: bool = False, config: RunnableConfig = None):
    """按分值倒序读取 Redis sorted set 区间成员。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response(client.zrevrange(key, start, end, withscores=withscores), key=key)
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_zrangebyscore(key: str, min_score: float, max_score: float, withscores: bool = False, config: RunnableConfig = None):
    """按分值范围读取 Redis sorted set 成员。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response(client.zrangebyscore(key, min_score, max_score, withscores=withscores), key=key)
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_zrank(key: str, member: str, config: RunnableConfig = None):
    """获取成员在 Redis sorted set 中的排名。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response({"key": key, "member": member, "rank": client.zrank(key, member)})
    except RedisError as e:
        return build_error_response(e)
