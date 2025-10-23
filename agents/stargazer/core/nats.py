# -- coding: utf-8 --
# @File: nats.py
# @Time: 2025/10/20
# @Author: Optimized
"""
NATS 统一模块 - 简洁高效的 NATS 集成

提供两种使用方式：
1. 独立客户端：用于命令行工具和脚本
2. Sanic 集成：用于 Web 服务
"""
import os
import ssl
import json
import asyncio
from typing import Optional, List, Callable, Dict, Any, Awaitable
from dataclasses import dataclass, field
from nats.aio.client import Client as NATS
from sanic import Sanic
from sanic.log import logger


# ==================== 配置类 ====================

@dataclass
class NATSConfig:
    """NATS 配置（统一管理所有配置项）"""
    servers: List[str] = field(default_factory=lambda: ["nats://localhost:4222"])
    name: str = "nats-client"
    connect_timeout: int = 5
    max_reconnect_attempts: int = 5
    reconnect_time_wait: int = 2

    # TLS 配置
    tls_enabled: bool = False
    tls_insecure: bool = False
    tls_ca_file: Optional[str] = None
    tls_cert_file: Optional[str] = None
    tls_key_file: Optional[str] = None
    tls_hostname: Optional[str] = None

    @classmethod
    def from_env(cls, service_name: str = "nats-client") -> "NATSConfig":
        """从环境变量加载配置"""
        nats_urls = os.getenv("NATS_URLS", "nats://localhost:4222")
        servers = [url.strip() for url in nats_urls.split(",")]

        return cls(
            servers=servers,
            name=service_name,
            connect_timeout=int(os.getenv("NATS_CONNECT_TIMEOUT", "5")),
            max_reconnect_attempts=int(os.getenv("NATS_MAX_RECONNECT_ATTEMPTS", "5")),
            reconnect_time_wait=int(os.getenv("NATS_RECONNECT_TIME_WAIT", "2")),
            tls_enabled=os.getenv("NATS_TLS_ENABLED", "false").lower() == "true",
            tls_insecure=os.getenv("NATS_TLS_INSECURE", "false").lower() == "true",
            tls_ca_file=os.getenv("NATS_TLS_CA_FILE"),
            tls_cert_file=os.getenv("NATS_TLS_CERT_FILE"),
            tls_key_file=os.getenv("NATS_TLS_KEY_FILE"),
            tls_hostname=os.getenv("NATS_TLS_HOSTNAME"),
        )

    def create_ssl_context(self) -> Optional[ssl.SSLContext]:
        """创建 SSL 上下文"""
        if not self.tls_enabled:
            return None

        logger.info("TLS is enabled for NATS connection")
        tls_context = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)

        if self.tls_insecure:
            logger.warning("TLS certificate verification is disabled (insecure mode)")
            tls_context.check_hostname = False
            tls_context.verify_mode = ssl.CERT_NONE
            return tls_context

        if self.tls_ca_file and os.path.exists(self.tls_ca_file):
            logger.info(f"Loading CA certificate: {self.tls_ca_file}")
            tls_context.load_verify_locations(cafile=self.tls_ca_file)

        if self.tls_cert_file and self.tls_key_file:
            if os.path.exists(self.tls_cert_file) and os.path.exists(self.tls_key_file):
                logger.info(f"Loading client certificate: {self.tls_cert_file}")
                tls_context.load_cert_chain(certfile=self.tls_cert_file, keyfile=self.tls_key_file)

        return tls_context

    def to_connect_options(self) -> dict:
        """转换为 NATS 连接选项"""
        options = {
            "servers": self.servers,
            "name": self.name,
            "connect_timeout": self.connect_timeout,
            "max_reconnect_attempts": self.max_reconnect_attempts,
            "reconnect_time_wait": self.reconnect_time_wait,
        }

        tls_context = self.create_ssl_context()
        if tls_context:
            options["tls"] = tls_context
            if self.tls_hostname:
                options["tls_hostname"] = self.tls_hostname

        return options


# ==================== 独立客户端 ====================

class NATSClient:
    """
    独立的 NATS 客户端
    用于命令行工具、脚本等场景
    """

    def __init__(self, config: Optional[NATSConfig] = None):
        self.config = config or NATSConfig.from_env()
        self.nc: Optional[NATS] = None

    async def connect(self) -> None:
        """连接到 NATS 服务器"""
        if self.nc and not self.nc.is_closed:
            return

        self.nc = await NATS().connect(**self.config.to_connect_options())
        logger.info(f"Connected to NATS: {self.config.servers}")

    async def request(self, subject: str, data: Any, timeout: float = 60.0) -> Any:
        """发送请求并等待响应"""
        if not self.nc or self.nc.is_closed:
            raise ConnectionError("Not connected to NATS")

        payload = json.dumps(data).encode()
        response = await self.nc.request(subject, payload=payload, timeout=timeout)
        return json.loads(response.data.decode())

    async def publish(self, subject: str, data: Any) -> None:
        """发布消息"""
        if not self.nc or self.nc.is_closed:
            raise ConnectionError("Not connected to NATS")

        payload = json.dumps(data).encode()
        await self.nc.publish(subject, payload)

    async def close(self) -> None:
        """关闭连接"""
        if self.nc and not self.nc.is_closed:
            await self.nc.drain()

    @property
    def is_connected(self) -> bool:
        return self.nc is not None and not self.nc.is_closed

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


# ==================== Sanic 集成 ====================

class NATSSanic:
    """
    Sanic 框架的 NATS 集成
    自动管理连接生命周期，支持消息订阅和处理
    """

    def __init__(self, app: Sanic, service_name: str, config: Optional[NATSConfig] = None):
        self.app = app
        self.service_name = service_name
        self.config = config or NATSConfig.from_env(service_name)
        self.nc = NATS()
        self.handlers: Dict[str, Callable] = {}
        self._pending_handlers: List[tuple] = []
        self._is_connecting = False
        self._shutting_down = False

        self._register_lifecycle()

    def _register_lifecycle(self):
        """注册 Sanic 生命周期事件"""

        @self.app.listener('before_server_start')
        async def start_nats(app, loop):
            await self._connect()
            await self._register_pending_handlers()

        @self.app.listener('after_server_stop')
        async def stop_nats(app, loop):
            await self._disconnect()

    async def _connect(self):
        """连接到 NATS"""
        if self._is_connecting:
            return

        self._is_connecting = True
        try:
            options = self.config.to_connect_options()
            options.update({
                "closed_cb": self._on_closed,
                "disconnected_cb": self._on_disconnected,
                "reconnected_cb": self._on_reconnected,
                "error_cb": self._on_error
            })

            await self.nc.connect(**options)
            self.app.ctx.nats_connected = True
            self.app.ctx.nats = self
            logger.info(f"NATS service '{self.service_name}' started")
        except Exception as e:
            logger.error(f"Failed to connect NATS: {e}")
            self.app.ctx.nats_connected = False
            raise
        finally:
            self._is_connecting = False

    async def _disconnect(self):
        """断开连接"""
        if self._shutting_down or self.nc.is_closed:
            return

        self._shutting_down = True
        try:
            await self.nc.drain()
            logger.info("NATS service stopped")
        except Exception as e:
            logger.error(f"Error stopping NATS: {e}")
        finally:
            self.app.ctx.nats_connected = False

    async def _on_closed(self):
        if not self._shutting_down:
            logger.warning("NATS connection closed unexpectedly")
            self.app.ctx.nats_connected = False

    async def _on_disconnected(self):
        logger.warning("Disconnected from NATS")
        self.app.ctx.nats_connected = False

    async def _on_reconnected(self):
        logger.info("Reconnected to NATS")
        self.app.ctx.nats_connected = True

    async def _on_error(self, e):
        logger.error(f"NATS error: {e}")

    async def _register_pending_handlers(self):
        """注册所有待处理的消息处理器"""
        for subject, handler, queue in self._pending_handlers:
            await self.subscribe(subject, handler, queue)
        self._pending_handlers.clear()

    def register_handler(self, subject: str, queue: Optional[str] = None):
        """装饰器：注册消息处理器"""
        def decorator(handler: Callable[[dict], Awaitable[dict]]):
            self._pending_handlers.append((subject, handler, queue))
            return handler
        return decorator

    async def subscribe(self, subject: str, handler: Callable, queue: Optional[str] = None):
        """订阅主题"""
        full_subject = f"{self.service_name}.{subject}"

        async def message_handler(msg):
            try:
                data = json.loads(msg.data.decode()) if msg.data else {}
                result = await handler(data)

                if msg.reply:
                    response = {"success": True, **result}
                    await self.nc.publish(msg.reply, json.dumps(response).encode())
            except Exception as e:
                logger.error(f"Error processing {msg.subject}: {e}", exc_info=True)
                if msg.reply:
                    error_response = {"success": False, "error": str(e)}
                    await self.nc.publish(msg.reply, json.dumps(error_response).encode())

        await self.nc.subscribe(full_subject, queue=queue, cb=message_handler)
        self.handlers[subject] = handler
        logger.info(f"Subscribed to '{full_subject}'")

    async def publish(self, subject: str, data: Any):
        """发布消息"""
        if self.nc.is_closed:
            raise ConnectionError("NATS not connected")
        await self.nc.publish(subject, json.dumps(data).encode())

    async def request(self, subject: str, data: Any, timeout: float = 5.0) -> Any:
        """发送请求并等待响应"""
        if self.nc.is_closed:
            raise ConnectionError("NATS not connected")

        payload = json.dumps(data).encode()
        msg = await self.nc.request(subject, payload, timeout=timeout)
        return json.loads(msg.data.decode())

    @property
    def is_connected(self) -> bool:
        return not self.nc.is_closed and getattr(self.app.ctx, 'nats_connected', False)


# ==================== 全局管理器（便捷接口）====================

_nats_instance: Optional[NATSSanic] = None


def initialize_nats(app: Sanic, service_name: str = "stargazer") -> NATSSanic:
    """初始化 NATS（在 server.py 中调用）"""
    global _nats_instance
    _nats_instance = NATSSanic(app, service_name)
    return _nats_instance


def register_handler(subject: str, queue: Optional[str] = None):
    """装饰器：注册消息处理器"""
    if _nats_instance is None:
        raise RuntimeError("NATS not initialized. Call initialize_nats() first.")
    return _nats_instance.register_handler(subject, queue)


def get_nats() -> NATSSanic:
    """获取 NATS 实例"""
    if _nats_instance is None:
        raise RuntimeError("NATS not initialized. Call initialize_nats() first.")
    return _nats_instance

