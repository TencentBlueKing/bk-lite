from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from redis.exceptions import RedisError

from apps.opspilot.metis.llm.tools.redis.connection import get_redis_connection
from apps.opspilot.metis.llm.tools.redis.hash import redis_hgetall
from apps.opspilot.metis.llm.tools.redis.json import redis_json_get
from apps.opspilot.metis.llm.tools.redis.list import redis_llen, redis_lrange
from apps.opspilot.metis.llm.tools.redis.set import redis_scard, redis_smembers
from apps.opspilot.metis.llm.tools.redis.sorted_set import redis_zcard, redis_zrange
from apps.opspilot.metis.llm.tools.redis.string import redis_get
from apps.opspilot.metis.llm.tools.redis.utils import build_error_response, build_success_response, require_confirm, truncate_sequence


@tool()
def redis_ping(config: RunnableConfig = None):
    """检查 Redis 连通性并返回 ping 结果。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response({"pong": client.ping()})
    except RedisError as e:
        return build_error_response(e, error_type="connection_error")


@tool()
def redis_dbsize(config: RunnableConfig = None):
    """获取当前 Redis 数据库中的 key 总数。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response({"dbsize": client.dbsize()})
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_info(section: str = "default", config: RunnableConfig = None):
    """获取 Redis 服务端信息，可指定 section。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response(client.info(section), section=section)
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_client_list(config: RunnableConfig = None):
    """获取当前连接到 Redis 的客户端列表。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response(client.client_list())
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_scan_keys(pattern: str = "*", count: int = 100, cursor: int = 0, config: RunnableConfig = None):
    """按 pattern 分页扫描 Redis keys，避免使用高风险的 KEYS *。"""
    try:
        client = get_redis_connection(config=config)
        next_cursor, keys = client.scan(cursor=cursor, match=pattern, count=count)
        return build_success_response(truncate_sequence(keys, max_items=count), cursor=next_cursor, pattern=pattern)
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_key_type(key: str, config: RunnableConfig = None):
    """获取指定 key 的 Redis 数据类型。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response({"key": key, "type": client.type(key)})
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_exists(key: str, config: RunnableConfig = None):
    """检查指定 key 是否存在。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response({"key": key, "exists": bool(client.exists(key))})
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_expire(key: str, seconds: int, config: RunnableConfig = None):
    """为指定 key 设置过期时间（秒）。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response({"key": key, "expire_set": bool(client.expire(key, seconds)), "seconds": seconds})
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_ttl(key: str, config: RunnableConfig = None):
    """获取指定 key 的剩余 TTL。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response({"key": key, "ttl": client.ttl(key)})
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_delete(key: str, config: RunnableConfig = None):
    """删除指定 key。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response({"key": key, "deleted": client.delete(key)})
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_rename(old_key: str, new_key: str, config: RunnableConfig = None):
    """重命名 Redis key。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response({"old_key": old_key, "new_key": new_key, "renamed": client.rename(old_key, new_key)})
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_get_key_value(key: str, max_items: int = 100, config: RunnableConfig = None):
    """自动识别 Redis key 类型并返回详细值信息。"""
    try:
        client = get_redis_connection(config=config)
        exists = bool(client.exists(key))
        if not exists:
            return build_success_response({"key": key, "exists": False, "type": "none", "ttl": -2, "value": None})

        key_type = client.type(key)
        ttl = client.ttl(key)

        if key_type == "string":
            result = redis_get.invoke({"key": key})
            return build_success_response({"key": key, "exists": True, "type": key_type, "ttl": ttl, **result["data"]})

        if key_type == "hash":
            result = redis_hgetall.invoke({"name": key})
            value = result["data"]
            count = len(value) if isinstance(value, dict) else 0
            return build_success_response({"key": key, "exists": True, "type": key_type, "ttl": ttl, "count": count, "value": value})

        if key_type == "list":
            len_result = redis_llen.invoke({"key": key})
            range_result = redis_lrange.invoke({"key": key, "start": 0, "end": max_items - 1})
            count = len_result["data"]["length"]
            value = range_result["data"]
            return build_success_response(
                {"key": key, "exists": True, "type": key_type, "ttl": ttl, "count": count, "truncated": count > max_items, "value": value}
            )

        if key_type == "set":
            count_result = redis_scard.invoke({"key": key})
            members_result = redis_smembers.invoke({"key": key})
            count = count_result["data"]["count"]
            value = members_result["data"]
            return build_success_response(
                {
                    "key": key,
                    "exists": True,
                    "type": key_type,
                    "ttl": ttl,
                    "count": count,
                    "truncated": count > max_items,
                    "value": value[:max_items] if isinstance(value, list) else value,
                }
            )

        if key_type == "zset":
            count_result = redis_zcard.invoke({"key": key})
            range_result = redis_zrange.invoke({"key": key, "start": 0, "end": max_items - 1, "withscores": True})
            count = count_result["data"]["count"]
            value = range_result["data"]
            return build_success_response(
                {"key": key, "exists": True, "type": key_type, "ttl": ttl, "count": count, "truncated": count > max_items, "value": value}
            )

        if key_type in ("ReJSON-RL", "json"):
            result = redis_json_get.invoke({"name": key, "path": "$"})
            return build_success_response({"key": key, "exists": True, "type": key_type, "ttl": ttl, "value": result["data"]})

        return build_success_response(
            {"key": key, "exists": True, "type": key_type, "ttl": ttl, "value": None, "message": f"Unsupported key type: {key_type}"}
        )
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_get_key_summary(key: str, preview_limit: int = 200, config: RunnableConfig = None):
    """获取 Redis key 的摘要信息，适合巡检和快速阅读。"""
    result = redis_get_key_value.invoke({"key": key, "config": config})
    if not result.get("success"):
        return result

    data = result["data"]
    value = data.get("value")
    key_type = data.get("type")

    summary = {
        "key": key,
        "exists": data.get("exists", False),
        "type": key_type,
        "ttl": data.get("ttl"),
    }

    if not data.get("exists", False):
        summary["preview"] = None
        summary["truncated"] = False
        return build_success_response(summary)

    if key_type == "string" and isinstance(value, str):
        summary["preview"] = value[:preview_limit]
        summary["truncated"] = len(value) > preview_limit
        summary["encoding"] = data.get("encoding")
        summary["is_binary"] = data.get("is_binary")
        summary["byte_length"] = data.get("byte_length")
        return build_success_response(summary)

    if key_type in {"hash", "set", "zset", "list"}:
        summary["count"] = data.get("count")
        summary["preview"] = value
        summary["truncated"] = data.get("truncated", False)
        return build_success_response(summary)

    summary["preview"] = value
    summary["truncated"] = False
    return build_success_response(summary)


@tool()
def redis_flushdb(confirm: bool = False, config: RunnableConfig = None):
    """清空当前 Redis 数据库，必须显式 confirm=True。"""
    confirm_error = require_confirm(confirm, "flushdb")
    if confirm_error:
        return confirm_error
    try:
        client = get_redis_connection(config=config)
        return build_success_response({"result": client.flushdb()}, operation="flushdb")
    except RedisError as e:
        return build_error_response(e)
