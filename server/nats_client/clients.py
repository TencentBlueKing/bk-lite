__all__ = ["nat_request", "request", "request_sync", "publish", "publish_sync", "js_publish", "js_publish_sync",
           "request_v2"]

import asyncio
import functools
import json

import jsonpickle
from django.conf import settings
from nats.aio.client import Client

from .exceptions import NatsClientException
from .types import ResponseType
from .utils import parse_arguments
from apps.core.logger import nats_logger as logger

DEFAULT_REQUEST_TIMEOUT = 60


async def nat_request(namespace: str, method_name: str, _timeout: float = None, _raw=False, **kwargs) -> ResponseType:
    payload = json.dumps(kwargs).encode()
    nc = await get_nc_client()
    timeout = _timeout or getattr(settings, "NATS_REQUEST_TIMEOUT", DEFAULT_REQUEST_TIMEOUT)
    try:
        response = await nc.request(f"{namespace}.{method_name}", payload, timeout=timeout)
    finally:
        await nc.close()
    data = response.data.decode()
    parsed = json.loads(data)
    return parsed


def get_default_nats_server():
    server = getattr(settings, "NATS_SERVER", None)
    servers = [server] if server else getattr(settings, "NATS_SERVERS", [])
    return servers


async def get_nc_client(nc: Client = None, server: str = "") -> Client:
    if nc is None:
        nc = Client()
    if not server:
        servers = get_default_nats_server()
    else:
        servers = [server]

    options = getattr(settings, "NATS_OPTIONS", {})

    await nc.connect(servers=servers, **options)
    return nc


async def request(
        namespace: str, method_name: str, *args, _timeout: float = None, _raw=False, **kwargs
) -> ResponseType:
    payload = parse_arguments(args, kwargs)

    nc = await get_nc_client()

    timeout = _timeout or getattr(settings, "NATS_REQUEST_TIMEOUT", DEFAULT_REQUEST_TIMEOUT)
    try:
        response = await nc.request(f"{namespace}.{method_name}", payload, timeout=timeout)
    finally:
        await nc.close()

    data = response.data.decode()
    parsed = json.loads(data)

    if _raw:
        parsed.pop("pickled_exc", None)
        return parsed

    if not parsed["success"]:
        # 优先使用新的error字段（Go服务的规范化错误格式）
        if "error" in parsed and parsed["error"]:
            error_message = parsed["error"]
            # 如果有result字段，将其作为详细信息添加
            if "result" in parsed and parsed["result"]:
                error_message += f" | Output: {parsed['result']}"
            exc = NatsClientException(error_message)
        else:
            # 向后兼容：尝试使用旧的pickled_exc格式
            try:
                exc = jsonpickle.decode(parsed["pickled_exc"])
            except (TypeError, KeyError):
                # 最后的降级方案
                fallback_message = parsed.get("message", "Unknown error occurred")
                exc = NatsClientException(fallback_message)

        raise exc

    return parsed["result"]


async def request_v2(
        namespace: str, method_name: str, server: str = "", *args, _timeout: float = None, _raw=False, **kwargs
) -> ResponseType:
    payload = parse_arguments(args, kwargs)

    try:
        nc = await get_nc_client(server=server)
    except Exception as e:  # noqa
        import traceback
        logger.error("==request_v2 nast connect method_name={}, error={}".format(method_name, traceback.format_exc()))
        raise NatsClientException(f"Cannot connect to NATS server: {server}")

    timeout = _timeout or getattr(settings, "NATS_REQUEST_TIMEOUT", DEFAULT_REQUEST_TIMEOUT)
    try:
        response = await nc.request(f"{namespace}.{method_name}", payload, timeout=timeout)
    finally:
        await nc.close()

    data = response.data.decode()
    parsed = json.loads(data)

    if _raw:
        parsed.pop("pickled_exc", None)
        return parsed

    if not parsed["success"]:
        # 优先使用新的error字段（Go服务的规范化错误格式）
        if "error" in parsed and parsed["error"]:
            error_message = parsed["error"]
            # 如果有result字段，将其作为详细信息添加
            if "result" in parsed and parsed["result"]:
                error_message += f" | Output: {parsed['result']}"
            exc = NatsClientException(error_message)
        else:
            # 向后兼容：尝试使用旧的pickled_exc格式
            try:
                exc = jsonpickle.decode(parsed["pickled_exc"])
            except (TypeError, KeyError):
                # 最后的降级方案
                fallback_message = parsed.get("message", "Unknown error occurred")
                exc = NatsClientException(fallback_message)

        raise exc

    return parsed["result"]


def request_sync(*args, **kwargs):
    return asyncio.run(request(*args, **kwargs))


async def publish(namespace: str, method_name: str, *args, _js=False, **kwargs) -> None:
    payload = parse_arguments(args, kwargs)

    nc = await get_nc_client()

    try:
        if _js:
            js = nc.jetstream()
            await js.publish(f"{namespace}.js.{method_name}", payload)
        else:
            await nc.publish(f"{namespace}.{method_name}", payload)
    finally:
        await nc.close()


def publish_sync(*args, **kwargs):
    return asyncio.run(publish(*args, **kwargs))


js_publish = functools.partial(publish, _js=True)
js_publish_sync = functools.partial(publish_sync, _js=True)
