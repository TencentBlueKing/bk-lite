from typing import Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from loguru import logger
from redis.exceptions import RedisError

from apps.opspilot.metis.llm.tools.common.credentials import execute_with_credentials
from apps.opspilot.metis.llm.tools.redis.connection import build_redis_normalized_from_runnable, get_redis_connection_from_item
from apps.opspilot.metis.llm.tools.redis.hash import redis_hgetall
from apps.opspilot.metis.llm.tools.redis.json import redis_json_get
from apps.opspilot.metis.llm.tools.redis.list import redis_llen, redis_lrange
from apps.opspilot.metis.llm.tools.redis.set import redis_scard, redis_smembers
from apps.opspilot.metis.llm.tools.redis.sorted_set import redis_zcard, redis_zrange
from apps.opspilot.metis.llm.tools.redis.string import redis_get
from apps.opspilot.metis.llm.tools.redis.utils import build_error_response, build_success_response, require_confirm, truncate_sequence


@tool()
def redis_ping(instance_name: Optional[str] = None, instance_id: Optional[str] = None, config: RunnableConfig = None):
    """检查 Redis 连通性并返回 ping 结果。"""
    normalized = build_redis_normalized_from_runnable(config, instance_name, instance_id)

    def _executor(item):
        try:
            client = get_redis_connection_from_item(item)
            return build_success_response({"pong": client.ping()})
        except (RedisError, ValueError) as e:
            return build_error_response(e, error_type="connection_error")

    return execute_with_credentials(normalized, _executor)


@tool()
def redis_dbsize(instance_name: Optional[str] = None, instance_id: Optional[str] = None, config: RunnableConfig = None):
    """获取当前 Redis 数据库中的 key 总数。"""
    normalized = build_redis_normalized_from_runnable(config, instance_name, instance_id)

    def _executor(item):
        try:
            client = get_redis_connection_from_item(item)
            return build_success_response({"dbsize": client.dbsize()})
        except (RedisError, ValueError) as e:
            return build_error_response(e)

    return execute_with_credentials(normalized, _executor)


@tool()
def redis_info(
    section: str = "default", instance_name: Optional[str] = None, instance_id: Optional[str] = None, config: RunnableConfig = None
):
    """获取 Redis 服务端信息，可指定 section。"""
    normalized = build_redis_normalized_from_runnable(config, instance_name, instance_id)

    def _executor(item):
        try:
            client = get_redis_connection_from_item(item)
            return build_success_response(client.info(section), section=section)
        except (RedisError, ValueError) as e:
            return build_error_response(e)

    return execute_with_credentials(normalized, _executor)


@tool()
def redis_client_list(instance_name: Optional[str] = None, instance_id: Optional[str] = None, config: RunnableConfig = None):
    """获取当前连接到 Redis 的客户端列表。"""
    normalized = build_redis_normalized_from_runnable(config, instance_name, instance_id)

    def _executor(item):
        try:
            client = get_redis_connection_from_item(item)
            return build_success_response(client.client_list())
        except (RedisError, ValueError) as e:
            return build_error_response(e)

    return execute_with_credentials(normalized, _executor)


@tool()
def redis_scan_keys(
    pattern: str = "*",
    count: int = 100,
    cursor: int = 0,
    instance_name: Optional[str] = None,
    instance_id: Optional[str] = None,
    config: RunnableConfig = None,
):
    """按 pattern 分页扫描 Redis keys，避免使用高风险的 KEYS *。"""
    normalized = build_redis_normalized_from_runnable(config, instance_name, instance_id)

    def _executor(item):
        try:
            client = get_redis_connection_from_item(item)
            next_cursor, keys = client.scan(cursor=cursor, match=pattern, count=count)
            return build_success_response(truncate_sequence(keys, max_items=count), cursor=next_cursor, pattern=pattern)
        except (RedisError, ValueError) as e:
            return build_error_response(e)

    return execute_with_credentials(normalized, _executor)


@tool()
def redis_key_type(key: str, instance_name: Optional[str] = None, instance_id: Optional[str] = None, config: RunnableConfig = None):
    """获取指定 key 的 Redis 数据类型。"""
    normalized = build_redis_normalized_from_runnable(config, instance_name, instance_id)

    def _executor(item):
        try:
            client = get_redis_connection_from_item(item)
            return build_success_response({"key": key, "type": client.type(key)})
        except (RedisError, ValueError) as e:
            return build_error_response(e)

    return execute_with_credentials(normalized, _executor)


@tool()
def redis_exists(key: str, instance_name: Optional[str] = None, instance_id: Optional[str] = None, config: RunnableConfig = None):
    """检查指定 key 是否存在。"""
    normalized = build_redis_normalized_from_runnable(config, instance_name, instance_id)

    def _executor(item):
        try:
            client = get_redis_connection_from_item(item)
            return build_success_response({"key": key, "exists": bool(client.exists(key))})
        except (RedisError, ValueError) as e:
            return build_error_response(e)

    return execute_with_credentials(normalized, _executor)


@tool()
def redis_expire(
    key: str, seconds: int, instance_name: Optional[str] = None, instance_id: Optional[str] = None, config: RunnableConfig = None
):
    """为指定 key 设置过期时间（秒）。"""
    normalized = build_redis_normalized_from_runnable(config, instance_name, instance_id)

    def _executor(item):
        try:
            client = get_redis_connection_from_item(item)
            return build_success_response({"key": key, "expire_set": bool(client.expire(key, seconds)), "seconds": seconds})
        except (RedisError, ValueError) as e:
            return build_error_response(e)

    return execute_with_credentials(normalized, _executor)


@tool()
def redis_ttl(key: str, instance_name: Optional[str] = None, instance_id: Optional[str] = None, config: RunnableConfig = None):
    """获取指定 key 的剩余 TTL。"""
    normalized = build_redis_normalized_from_runnable(config, instance_name, instance_id)

    def _executor(item):
        try:
            client = get_redis_connection_from_item(item)
            return build_success_response({"key": key, "ttl": client.ttl(key)})
        except (RedisError, ValueError) as e:
            return build_error_response(e)

    return execute_with_credentials(normalized, _executor)


@tool()
def redis_delete(key: str, instance_name: Optional[str] = None, instance_id: Optional[str] = None, config: RunnableConfig = None):
    """删除指定 key。"""
    normalized = build_redis_normalized_from_runnable(config, instance_name, instance_id)

    def _executor(item):
        try:
            client = get_redis_connection_from_item(item)
            return build_success_response({"key": key, "deleted": client.delete(key)})
        except (RedisError, ValueError) as e:
            return build_error_response(e)

    return execute_with_credentials(normalized, _executor)


@tool()
def redis_rename(
    old_key: str, new_key: str, instance_name: Optional[str] = None, instance_id: Optional[str] = None, config: RunnableConfig = None
):
    """重命名 Redis key。"""
    normalized = build_redis_normalized_from_runnable(config, instance_name, instance_id)

    def _executor(item):
        try:
            client = get_redis_connection_from_item(item)
            return build_success_response({"old_key": old_key, "new_key": new_key, "renamed": client.rename(old_key, new_key)})
        except (RedisError, ValueError) as e:
            return build_error_response(e)

    return execute_with_credentials(normalized, _executor)


@tool()
def redis_get_key_value(
    key: str,
    max_items: int = 100,
    instance_name: Optional[str] = None,
    instance_id: Optional[str] = None,
    config: RunnableConfig = None,
):
    """自动识别 Redis key 类型并返回详细值信息。"""
    normalized = build_redis_normalized_from_runnable(config, instance_name, instance_id)

    def _executor(item):
        try:
            client = get_redis_connection_from_item(item)
            exists = bool(client.exists(key))
            if not exists:
                return build_success_response({"key": key, "exists": False, "type": "none", "ttl": -2, "value": None})

            key_type = client.type(key)
            ttl = client.ttl(key)

            if key_type == "string":
                result = redis_get.invoke({"key": key, "instance_name": instance_name, "instance_id": instance_id, "config": config})
                return build_success_response({"key": key, "exists": True, "type": key_type, "ttl": ttl, **result["data"]})

            if key_type == "hash":
                result = redis_hgetall.invoke({"name": key, "instance_name": instance_name, "instance_id": instance_id, "config": config})
                value = result["data"]
                count = len(value) if isinstance(value, dict) else 0
                return build_success_response({"key": key, "exists": True, "type": key_type, "ttl": ttl, "count": count, "value": value})

            if key_type == "list":
                len_result = redis_llen.invoke({"key": key, "instance_name": instance_name, "instance_id": instance_id, "config": config})
                range_result = redis_lrange.invoke(
                    {"key": key, "start": 0, "end": max_items - 1, "instance_name": instance_name, "instance_id": instance_id, "config": config}
                )
                count = len_result["data"]["length"]
                value = range_result["data"]
                return build_success_response(
                    {"key": key, "exists": True, "type": key_type, "ttl": ttl, "count": count, "truncated": count > max_items, "value": value}
                )

            if key_type == "set":
                count_result = redis_scard.invoke({"key": key, "instance_name": instance_name, "instance_id": instance_id, "config": config})
                members_result = redis_smembers.invoke({"key": key, "instance_name": instance_name, "instance_id": instance_id, "config": config})
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
                count_result = redis_zcard.invoke({"key": key, "instance_name": instance_name, "instance_id": instance_id, "config": config})
                range_result = redis_zrange.invoke(
                    {"key": key, "start": 0, "end": max_items - 1, "withscores": True, "instance_name": instance_name, "instance_id": instance_id, "config": config}
                )
                count = count_result["data"]["count"]
                value = range_result["data"]
                return build_success_response(
                    {"key": key, "exists": True, "type": key_type, "ttl": ttl, "count": count, "truncated": count > max_items, "value": value}
                )

            if key_type in ("ReJSON-RL", "json"):
                result = redis_json_get.invoke({"name": key, "path": "$", "instance_name": instance_name, "instance_id": instance_id, "config": config})
                return build_success_response({"key": key, "exists": True, "type": key_type, "ttl": ttl, "value": result["data"]})

            return build_success_response(
                {"key": key, "exists": True, "type": key_type, "ttl": ttl, "value": None, "message": f"Unsupported key type: {key_type}"}
            )
        except (RedisError, ValueError) as e:
            return build_error_response(e)

    return execute_with_credentials(normalized, _executor)


@tool()
def redis_get_key_summary(
    key: str,
    preview_limit: int = 200,
    instance_name: Optional[str] = None,
    instance_id: Optional[str] = None,
    config: RunnableConfig = None,
):
    """获取 Redis key 的摘要信息，适合巡检和快速阅读。"""
    result = redis_get_key_value.invoke(
        {"key": key, "config": config, "instance_name": instance_name, "instance_id": instance_id}
    )
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
def redis_flushdb(
    confirm: bool = False, instance_name: Optional[str] = None, instance_id: Optional[str] = None, config: RunnableConfig = None
):
    """清空当前 Redis 数据库，必须显式 confirm=True。"""
    confirm_error = require_confirm(confirm, "flushdb")
    if confirm_error:
        return confirm_error
    normalized = build_redis_normalized_from_runnable(config, instance_name, instance_id)

    def _executor(item):
        try:
            client = get_redis_connection_from_item(item)
            connection_kwargs = getattr(getattr(client, "connection_pool", None), "connection_kwargs", {}) or {}
            target_host = connection_kwargs.get("host")
            target_port = connection_kwargs.get("port")
            target_db = connection_kwargs.get("db")
            # TODO(security F023): require out-of-band human confirmation; disable by default
            logger.warning(
                "UNGATED DESTRUCTIVE redis FLUSHDB about to execute: wiping entire database "
                "(host={}, port={}, db={}, instance_name={}, instance_id={}). "
                "Gated only by an LLM-supplied confirm flag (confirm={}); no human approval required.",
                target_host,
                target_port,
                target_db,
                instance_name,
                instance_id,
                confirm,
            )
            return build_success_response({"result": client.flushdb()}, operation="flushdb")
        except (RedisError, ValueError) as e:
            return build_error_response(e)

    return execute_with_credentials(normalized, _executor)
