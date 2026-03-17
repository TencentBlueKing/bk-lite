from typing import Any, Dict, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from redis.exceptions import RedisError

from apps.opspilot.metis.llm.tools.redis.connection import get_redis_connection
from apps.opspilot.metis.llm.tools.redis.utils import build_error_response, build_success_response


@tool()
def redis_xadd(key: str, fields: Dict[str, Any], expiration: Optional[int] = None, config: RunnableConfig = None):
    """向 Redis stream 追加消息。"""
    try:
        client = get_redis_connection(config=config)
        entry_id = client.xadd(key, fields)
        if expiration is not None:
            client.expire(key, expiration)
        return build_success_response({"key": key, "entry_id": entry_id, "expiration": expiration})
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_xread(streams: Dict[str, str], count: Optional[int] = None, block: Optional[int] = None, config: RunnableConfig = None):
    """从一个或多个 Redis stream 读取消息。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response(client.xread(streams=streams, count=count, block=block))
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_xrange(key: str, min_id: str = "-", max_id: str = "+", count: Optional[int] = None, config: RunnableConfig = None):
    """正序读取 Redis stream 范围消息。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response(client.xrange(key, min=min_id, max=max_id, count=count), key=key)
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_xrevrange(key: str, max_id: str = "+", min_id: str = "-", count: Optional[int] = None, config: RunnableConfig = None):
    """倒序读取 Redis stream 范围消息。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response(client.xrevrange(key, max=max_id, min=min_id, count=count), key=key)
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_xdel(key: str, entry_id: str, config: RunnableConfig = None):
    """删除 Redis stream 指定消息。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response({"key": key, "deleted": client.xdel(key, entry_id), "entry_id": entry_id})
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_xgroup_create(key: str, group_name: str, id: str = "$", mkstream: bool = False, config: RunnableConfig = None):
    """创建 Redis stream consumer group。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response(
            {"created": client.xgroup_create(key, group_name, id=id, mkstream=mkstream), "key": key, "group_name": group_name}
        )
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_xreadgroup(
    group_name: str,
    consumer_name: str,
    streams: Dict[str, str],
    count: Optional[int] = None,
    block: Optional[int] = None,
    config: RunnableConfig = None,
):
    """以 consumer group 方式读取 Redis stream。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response(client.xreadgroup(group_name, consumer_name, streams=streams, count=count, block=block))
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_xack(key: str, group_name: str, entry_ids: list[str], config: RunnableConfig = None):
    """确认 Redis stream consumer group 消息。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response({"acked": client.xack(key, group_name, *entry_ids), "key": key, "group_name": group_name})
    except RedisError as e:
        return build_error_response(e)
