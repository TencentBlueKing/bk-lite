from typing import List, Optional

import numpy as np
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from redis.exceptions import RedisError

from apps.opspilot.metis.llm.tools.redis.connection import get_binary_redis_connection, get_redis_connection
from apps.opspilot.metis.llm.tools.redis.utils import build_error_response, build_success_response


@tool()
def redis_hset(name: str, key: str, value: str | int | float, expire_seconds: Optional[int] = None, config: RunnableConfig = None):
    """设置 Redis hash 中的字段值，可选过期时间。"""
    try:
        client = get_redis_connection(config=config)
        client.hset(name, key, value)
        if expire_seconds is not None:
            client.expire(name, expire_seconds)
        return build_success_response({"name": name, "key": key, "expire_seconds": expire_seconds})
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_hgetall(name: str, config: RunnableConfig = None):
    """读取 Redis hash 的全部字段和值。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response(client.hgetall(name), name=name)
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_hget(name: str, key: str, config: RunnableConfig = None):
    """读取 Redis hash 指定字段的值。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response({"name": name, "key": key, "value": client.hget(name, key)})
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_hdel(name: str, key: str, config: RunnableConfig = None):
    """删除 Redis hash 指定字段。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response({"name": name, "key": key, "deleted": client.hdel(name, key)})
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_hexists(name: str, key: str, config: RunnableConfig = None):
    """检查 Redis hash 中字段是否存在。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response({"name": name, "key": key, "exists": bool(client.hexists(name, key))})
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_hkeys(name: str, config: RunnableConfig = None):
    """获取 Redis hash 的全部字段名。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response(client.hkeys(name))
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_hvals(name: str, config: RunnableConfig = None):
    """获取 Redis hash 的全部字段值。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response(client.hvals(name))
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_hlen(name: str, config: RunnableConfig = None):
    """获取 Redis hash 的字段数量。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response({"name": name, "length": client.hlen(name)})
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_set_vector_in_hash(name: str, vector: List[float], vector_field: str = "vector", config: RunnableConfig = None):
    """将向量以 float32 二进制形式写入 Redis hash。"""
    try:
        client = get_redis_connection(config=config)
        vector_blob = np.array(vector, dtype=np.float32).tobytes()
        client.hset(name, vector_field, vector_blob)
        return build_success_response({"name": name, "vector_field": vector_field, "stored": True})
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_get_vector_from_hash(name: str, vector_field: str = "vector", config: RunnableConfig = None):
    """从 Redis hash 读取 float32 二进制向量并还原。"""
    try:
        client = get_binary_redis_connection(config=config)
        binary_blob = client.hget(name, vector_field)
        if not binary_blob:
            return build_success_response([])
        vector_array = np.frombuffer(binary_blob, dtype=np.float32)
        return build_success_response(vector_array.tolist())
    except RedisError as e:
        return build_error_response(e)
