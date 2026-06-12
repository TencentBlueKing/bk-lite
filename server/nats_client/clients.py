__all__ = ["nat_request", "request", "request_sync", "publish", "publish_sync", "js_publish", "js_publish_sync", "request_v2", "subscribe_lines_sync", "publish_raw", "publish_raw_sync", "ensure_stream", "ensure_stream_sync", "iter_jetstream_subject"]

import asyncio
import functools
import json
import queue
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

import jsonpickle
from django.conf import settings
from nats.aio.client import Client

from apps.core.logger import nats_logger as logger
from apps.rpc.sensitive import sanitize_sensitive_data

from .exceptions import NatsClientException
from .types import ResponseType
from .utils import parse_arguments

DEFAULT_REQUEST_TIMEOUT = 60


def _mask_server_url(server_url: str) -> str:
    """脱敏 NATS server URL，避免日志泄露用户名/密码"""
    if not server_url:
        return server_url
    try:
        parsed = urlsplit(server_url)
        if parsed.username or parsed.password:
            host = parsed.hostname or ""
            if parsed.port:
                host = f"{host}:{parsed.port}"
            netloc = f"***:***@{host}"
            return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
    except Exception:
        return "***"
    return server_url


def _mask_servers(servers) -> str:
    if isinstance(servers, (list, tuple)):
        return ",".join(_mask_server_url(str(s)) for s in servers)
    return _mask_server_url(str(servers))


def _stringify_error_detail(detail) -> str:
    sanitized = sanitize_sensitive_data(detail)
    if isinstance(sanitized, str):
        return sanitized
    return str(sanitized)


async def nat_request(
    namespace: str,
    method_name: str,
    _timeout: float = 0,
    _raw=False,
    **kwargs,
) -> ResponseType:
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


async def get_nc_client(nc=None, server: str = "") -> Client:
    if nc is None:
        nc = Client()
    if not server:
        servers = get_default_nats_server()
    else:
        servers = [server]

    options = getattr(settings, "NATS_OPTIONS", {})

    # 连接超时保护：避免 connect 阶段无上限阻塞
    connect_timeout = options.pop("connect_timeout", getattr(settings, "NATS_CONNECT_TIMEOUT", 10))
    try:
        await asyncio.wait_for(nc.connect(servers=servers, **options), timeout=connect_timeout)
    except Exception as e:
        logger.error("NATS connect failed, servers=%s, error=%s", _mask_servers(servers), str(e))
        raise
    return nc


async def request(namespace: str, method_name: str, *args, _timeout: Optional[float] = None, _raw=False, **kwargs) -> ResponseType:
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

        def _decode_pickled_exception_message() -> Optional[str]:
            try:
                decoded_exc = jsonpickle.decode(parsed["pickled_exc"])
                decoded_message = str(decoded_exc)
                return decoded_message or None
            except (TypeError, KeyError):
                return None

        # 优先使用新的error字段（Go服务的规范化错误格式）
        if "error" in parsed and parsed["error"]:
            error_message = parsed["error"]
            if "message" in parsed and parsed["message"]:
                error_message += f": {_stringify_error_detail(parsed['message'])}"
            elif error_message == "BaseAppException":
                decoded_message = _decode_pickled_exception_message()
                if decoded_message:
                    error_message += f": {_stringify_error_detail(decoded_message)}"
            # 如果有result字段，将其作为详细信息添加
            if "result" in parsed and parsed["result"]:
                error_message += f" | Output: {_stringify_error_detail(parsed['result'])}"
            exc = NatsClientException(error_message)
        elif "result" in parsed and parsed["result"]:
            # 兼容仅返回 result 的服务端实现
            exc = NatsClientException(_stringify_error_detail(parsed["result"]))
        else:
            # 向后兼容：尝试使用旧的pickled_exc格式
            decoded_message = _decode_pickled_exception_message()
            if decoded_message:
                exc = NatsClientException(_stringify_error_detail(decoded_message))
            else:
                # 最后的降级方案：打印完整响应便于排查
                logger.error("NATS error response missing error details, full response: %s", sanitize_sensitive_data(parsed))
                fallback_message = parsed.get("message", "Unknown error occurred")
                exc = NatsClientException(_stringify_error_detail(fallback_message))

        raise exc

    if "result" not in parsed:
        return parsed

    return parsed["result"]


async def request_v2(
    namespace: str, method_name: str, server: str = "", *args, _timeout: Optional[float] = None, _raw=False, **kwargs
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

        def _decode_pickled_exception_message() -> Optional[str]:
            try:
                decoded_exc = jsonpickle.decode(parsed["pickled_exc"])
                decoded_message = str(decoded_exc)
                return decoded_message or None
            except (TypeError, KeyError):
                return None

        # 优先使用新的error字段（Go服务的规范化错误格式）
        if "error" in parsed and parsed["error"]:
            error_message = parsed["error"]
            if "message" in parsed and parsed["message"]:
                error_message += f": {_stringify_error_detail(parsed['message'])}"
            elif error_message == "BaseAppException":
                decoded_message = _decode_pickled_exception_message()
                if decoded_message:
                    error_message += f": {_stringify_error_detail(decoded_message)}"
            # 如果有result字段，将其作为详细信息添加
            if "result" in parsed and parsed["result"]:
                error_message += f" | Output: {_stringify_error_detail(parsed['result'])}"
            exc = NatsClientException(error_message)
        elif "result" in parsed and parsed["result"]:
            # 兼容仅返回 result 的服务端实现
            exc = NatsClientException(_stringify_error_detail(parsed["result"]))
        else:
            # 向后兼容：尝试使用旧的pickled_exc格式
            decoded_message = _decode_pickled_exception_message()
            if decoded_message:
                exc = NatsClientException(_stringify_error_detail(decoded_message))
            else:
                # 最后的降级方案：打印完整响应便于排查
                logger.error("NATS error response missing error details, full response: %s", sanitize_sensitive_data(parsed))
                fallback_message = parsed.get("message", "Unknown error occurred")
                exc = NatsClientException(_stringify_error_detail(fallback_message))

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


def subscribe_lines_sync(subject: str, timeout: Optional[float] = None, stop_event=None):
    result_queue: "queue.Queue[dict]" = queue.Queue()

    async def runner():
        nc = await get_nc_client()

        async def callback(msg):
            try:
                payload = json.loads(msg.data.decode())
            except json.JSONDecodeError:
                payload = {"line": msg.data.decode(errors="ignore")}
            result_queue.put(payload)

        sub = await nc.subscribe(subject, cb=callback)
        try:
            start = asyncio.get_event_loop().time()
            while True:
                if stop_event is not None and stop_event.is_set():
                    break
                if timeout and (asyncio.get_event_loop().time() - start) > timeout:
                    break
                await asyncio.sleep(0.1)
        finally:
            await sub.unsubscribe()
            await nc.close()

    def start():
        asyncio.run(runner())

    return result_queue, start


# --- 流式输出原语（job_mgmt 脚本执行实时日志） ---

async def publish_raw(subject: str, payload: dict) -> None:
    """向原始 subject 发布一条扁平 JSON（不走 RPC 的 args/kwargs 包装）。"""
    nc = await get_nc_client()
    try:
        await nc.publish(subject, json.dumps(payload).encode())
        await nc.flush()
    finally:
        await nc.close()


def publish_raw_sync(subject: str, payload: dict) -> None:
    return asyncio.run(publish_raw(subject, payload))


async def ensure_stream(name: str, subjects, max_age: int, max_bytes: int) -> None:
    """幂等声明 JetStream 流：不存在则创建，存在则更新配置。"""
    from nats.js.api import DiscardPolicy, StreamConfig

    nc = await get_nc_client()
    try:
        js = nc.jetstream()
        # 注意：nats-py StreamConfig.max_age 单位以安装版本为准（秒/纳秒），
        # 仅影响保留时长，不影响功能正确性；本地集成时核对一次。
        cfg = StreamConfig(
            name=name,
            subjects=list(subjects),
            max_age=max_age,
            max_bytes=max_bytes,
            discard=DiscardPolicy.OLD,
        )
        try:
            await js.add_stream(cfg)
        except Exception:
            await js.update_stream(cfg)
    finally:
        await nc.close()


def ensure_stream_sync(name: str, subjects, max_age: int, max_bytes: int) -> None:
    return asyncio.run(ensure_stream(name, subjects, max_age, max_bytes))


async def iter_jetstream_subject(filter_subject: str, idle_timeout: float = 300):  # pragma: no cover
    """JetStream 有序消费者：从头回放 + 实时 tail。空闲超时即结束。

    胶水代码，依赖真实 NATS/JetStream，单测以注入 fake source 覆盖上层逻辑；
    本函数本身由本地集成验证。yield (subject, payload_dict)。
    """
    nc = await get_nc_client()
    sub = None
    try:
        js = nc.jetstream()
        sub = await js.subscribe(filter_subject, ordered_consumer=True)
        while True:
            try:
                msg = await sub.next_msg(timeout=idle_timeout)
            except Exception:
                break
            try:
                payload = json.loads(msg.data.decode())
            except json.JSONDecodeError:
                payload = {"line": msg.data.decode(errors="ignore")}
            yield msg.subject, payload
    finally:
        if sub is not None:
            try:
                await sub.unsubscribe()
            except Exception:
                pass
        await nc.close()
