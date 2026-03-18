import json
from typing import Any, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from redis.exceptions import RedisError

from apps.opspilot.metis.llm.tools.redis.connection import get_binary_redis_connection, get_redis_connection
from apps.opspilot.metis.llm.tools.redis.utils import build_error_response, build_success_response


def _encode_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


def _normalize_string_value(value: Any) -> dict:
    if value is None:
        return {"value": None, "encoding": None, "is_binary": False, "byte_length": 0}

    if isinstance(value, bytes):
        try:
            decoded = value.decode("utf-8")
            return {
                "value": decoded,
                "encoding": "utf-8",
                "is_binary": False,
                "byte_length": len(value),
            }
        except UnicodeDecodeError:
            return {
                "value": value.hex(),
                "encoding": "hex",
                "is_binary": True,
                "byte_length": len(value),
            }

    return {
        "value": value,
        "encoding": "utf-8",
        "is_binary": False,
        "byte_length": len(str(value).encode("utf-8")),
    }


@tool()
def redis_set(key: str, value: Any, expiration: Optional[int] = None, config: RunnableConfig = None):
    """设置 Redis string 值，可选过期时间。"""
    try:
        client = get_redis_connection(config=config)
        encoded_value = _encode_value(value)
        if expiration is not None:
            client.setex(key, expiration, encoded_value)
        else:
            client.set(key, encoded_value)
        return build_success_response({"key": key, "expiration": expiration})
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_get(key: str, config: RunnableConfig = None):
    """读取指定 Redis string key 的值。"""
    try:
        client = get_binary_redis_connection(config=config)
        value = client.get(key)
        normalized = _normalize_string_value(value)
        return build_success_response({"key": key, **normalized})
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_mget(keys: list[str], config: RunnableConfig = None):
    """批量读取多个 Redis string key 的值。"""
    try:
        client = get_binary_redis_connection(config=config)
        values = client.mget(keys)
        normalized_values = [_normalize_string_value(value) for value in values]
        return build_success_response({"keys": keys, "values": normalized_values})
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_append(key: str, value: str, config: RunnableConfig = None):
    """向已有 Redis string 末尾追加字符串。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response({"key": key, "length": client.append(key, value)})
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_strlen(key: str, config: RunnableConfig = None):
    """获取 Redis string 的长度。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response({"key": key, "length": client.strlen(key)})
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_getdel(key: str, config: RunnableConfig = None):
    """读取指定 key 的值并删除该 key。"""
    try:
        client = get_binary_redis_connection(config=config)
        normalized = _normalize_string_value(client.getdel(key))
        return build_success_response({"key": key, **normalized})
    except RedisError as e:
        return build_error_response(e)
