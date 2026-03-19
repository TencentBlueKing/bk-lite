from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from redis.exceptions import RedisError

from apps.opspilot.metis.llm.tools.redis.connection import get_redis_connection
from apps.opspilot.metis.llm.tools.redis.utils import build_error_response, build_success_response


@tool()
def redis_lpush(key: str, value: str, config: RunnableConfig = None):
    """向 Redis list 左侧压入一个元素。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response({"length": client.lpush(key, value)}, key=key)
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_lrange(key: str, start: int = 0, end: int = -1, config: RunnableConfig = None):
    """读取 Redis list 指定区间内的元素。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response(client.lrange(key, start, end), key=key)
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_rpush(key: str, value: str, config: RunnableConfig = None):
    """向 Redis list 右侧压入一个元素。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response({"length": client.rpush(key, value)}, key=key)
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_lpop(key: str, config: RunnableConfig = None):
    """从 Redis list 左侧弹出一个元素。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response({"key": key, "value": client.lpop(key)})
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_rpop(key: str, config: RunnableConfig = None):
    """从 Redis list 右侧弹出一个元素。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response({"key": key, "value": client.rpop(key)})
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_llen(key: str, config: RunnableConfig = None):
    """获取 Redis list 的长度。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response({"key": key, "length": client.llen(key)})
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_lindex(key: str, index: int, config: RunnableConfig = None):
    """读取 Redis list 指定索引位置的元素。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response({"key": key, "index": index, "value": client.lindex(key, index)})
    except RedisError as e:
        return build_error_response(e)
