from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from redis.exceptions import RedisError

from apps.opspilot.metis.llm.tools.redis.connection import get_redis_connection
from apps.opspilot.metis.llm.tools.redis.utils import build_error_response, build_success_response


@tool()
def redis_publish(channel: str, message: str, config: RunnableConfig = None):
    """向 Redis channel 发布消息。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response({"channel": channel, "receivers": client.publish(channel, message)})
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_pubsub_channels(pattern: str = "*", config: RunnableConfig = None):
    """列出当前 Redis pubsub channels。"""
    try:
        client = get_redis_connection(config=config)
        return build_success_response(client.pubsub_channels(pattern))
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_subscribe(channel: str, config: RunnableConfig = None):
    """短调用方式订阅 Redis channel。"""
    try:
        client = get_redis_connection(config=config)
        pubsub = client.pubsub()
        pubsub.subscribe(channel)
        return build_success_response({"channel": channel, "subscribed": True})
    except RedisError as e:
        return build_error_response(e)


@tool()
def redis_unsubscribe(channel: str, config: RunnableConfig = None):
    """短调用方式取消订阅 Redis channel。"""
    try:
        client = get_redis_connection(config=config)
        pubsub = client.pubsub()
        pubsub.unsubscribe(channel)
        return build_success_response({"channel": channel, "unsubscribed": True})
    except RedisError as e:
        return build_error_response(e)
