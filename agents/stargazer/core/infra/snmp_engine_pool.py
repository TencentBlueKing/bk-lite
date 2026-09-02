"""进程级共享 pysnmp ``SnmpEngine`` 池。

pysnmp 5.1.0 的每个 ``SnmpEngine`` 都持有独立的 MibBuilder；第一次解析 OID 时
``ObjectIdentity.resolveWithMib`` 会给这个 MibBuilder 新建一个 pysmi ``MibCompiler``，
而 pysmi 解析器在构造时用 PLY 现场重算整张 SMI 语法 LR 表。每个 engine 连同
MIB 模块与 LR 表约 2 MiB 常驻、约 50 ms 纯 Python CPU；SNMP 采集若每个目标都新建
engine，100 并发一批就会阻塞事件循环数秒，而 uvloop 的 sendto 地址缓存
（``uvloop/dns.pyx`` 的 ``sockaddrs`` LRU，2048 项）又以 pysnmp 的
``UdpTransportAddress`` 为键、经其 ``_localAddress`` 拖住整个已关闭 engine 的 MIB 树，
内存因此随目标数线性增长且不回落。

设计要点：

- pysnmp 的 asyncio dispatcher 本身多路复用，一个 engine 能并发服务任意多目标，
  所以同一事件循环内按“凭据作用域”共享 engine：v1/v2c 目标共用一个（不同
  community 在 snmpCommunityTable 中可以共存）；v3 按用户名、协议与密钥组合
  各一个，避免 pysnmp LCD 以 ``(userName, engineId)`` 为键把不同密钥混用。
- 每个不同目标地址都会在 engine 的 LCD 里留下约 20 KiB 的 snmpTargetAddrTable
  行，并发在途时无法安全删除，因此按“不同目标数”做代际轮换：达到
  ``SNMP_ENGINE_MAX_TARGETS`` 后新目标换用新 engine，旧 engine 在途请求排空后关闭。
- engine 空闲超过 ``SNMP_ENGINE_IDLE_SECONDS`` 后关闭 dispatcher 并释放；进程
  退出（Sanic ``after_server_stop``）时统一关闭。
- MIB 编译器进程内只构建一次（PLY LR 表只算一次），之后每一代 engine 都复用
  同一个编译器对象；数值 OID 采集永远不会真正触发 MIB 编译。
"""

from __future__ import annotations

import asyncio
import hashlib
import itertools
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from core.logger import logger

DEFAULT_SNMP_ENGINE_MAX_TARGETS = 2000
DEFAULT_SNMP_ENGINE_IDLE_SECONDS = 300.0

_COMMUNITY_SCOPE = "community"


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return int(default)
    try:
        return int(str(raw).strip())
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer") from exc


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return float(default)
    try:
        return float(str(raw).strip())
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive number of seconds") from exc


@dataclass(frozen=True)
class SnmpEnginePoolSettings:
    """共享 engine 的轮换与空闲回收阈值，只从环境变量读取。"""

    max_targets: int = DEFAULT_SNMP_ENGINE_MAX_TARGETS
    idle_seconds: float = DEFAULT_SNMP_ENGINE_IDLE_SECONDS

    def __post_init__(self) -> None:
        if isinstance(self.max_targets, bool) or not isinstance(self.max_targets, int) or self.max_targets <= 0:
            raise ValueError("SNMP_ENGINE_MAX_TARGETS must be a positive integer")
        if not self.idle_seconds > 0:
            raise ValueError("SNMP_ENGINE_IDLE_SECONDS must be greater than zero")

    @classmethod
    def from_env(cls) -> SnmpEnginePoolSettings:
        return cls(
            max_targets=_int_env("SNMP_ENGINE_MAX_TARGETS", DEFAULT_SNMP_ENGINE_MAX_TARGETS),
            idle_seconds=_float_env("SNMP_ENGINE_IDLE_SECONDS", DEFAULT_SNMP_ENGINE_IDLE_SECONDS),
        )


class _SharedEngine:
    __slots__ = (
        "scope",
        "label",
        "generation",
        "loop",
        "engine",
        "opened_at",
        "in_flight",
        "acquisitions",
        "targets",
        "idle_handle",
        "retired",
        "retire_reason",
        "closed",
    )

    def __init__(self, *, scope: str, label: str, generation: int, loop: asyncio.AbstractEventLoop, engine: Any) -> None:
        self.scope = scope
        self.label = label
        self.generation = generation
        self.loop = loop
        self.engine = engine
        self.opened_at = time.monotonic()
        self.in_flight = 0
        self.acquisitions = 0
        self.targets: set[tuple[str, int]] = set()
        self.idle_handle: asyncio.TimerHandle | None = None
        self.retired = False
        self.retire_reason = ""
        self.closed = False


_settings: SnmpEnginePoolSettings | None = None
_active: dict[str, _SharedEngine] = {}
_draining: list[_SharedEngine] = []
_scope_labels: dict[str, str] = {}
_generations = itertools.count(1)
_shared_mib_compiler: Any = None
_shared_mib_destination: str | None = None


def snmp_engine_pool_settings() -> SnmpEnginePoolSettings:
    """首次调用时从环境变量读取；配置非法直接抛 ValueError。"""

    global _settings
    if _settings is None:
        _settings = SnmpEnginePoolSettings.from_env()
    return _settings


def configure_snmp_engine_pool(settings: SnmpEnginePoolSettings | None) -> None:
    """测试或诊断脚本显式覆盖阈值；传 None 恢复为按环境变量读取。"""

    global _settings
    _settings = settings


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _secret_bytes(value: Any) -> bytes:
    if value is None:
        return b""
    as_octets = getattr(value, "asOctets", None)
    if callable(as_octets):
        return bytes(as_octets())
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    return str(value).encode("utf-8")


def snmp_engine_scope(auth_data: Any) -> str:
    """把 pysnmp 认证对象映射到共享 engine 的作用域键。

    v1/v2c 共用一个作用域；v3 按用户名、安全级别、协议与密钥材料摘要区分，
    摘要只用于内存字典键，不会被写入日志。
    """

    from pysnmp.hlapi.auth import CommunityData, UsmUserData

    if isinstance(auth_data, UsmUserData):
        material = (
            _text(auth_data.userName),
            _text(auth_data.securityName),
            _secret_bytes(auth_data.securityEngineId),
            _text(auth_data.securityLevel),
            _text(auth_data.authProtocol),
            _text(auth_data.authKeyType),
            _secret_bytes(auth_data.authKey),
            _text(auth_data.privProtocol),
            _text(auth_data.privKeyType),
            _secret_bytes(auth_data.privKey),
        )
        digest = hashlib.blake2b(repr(material).encode("utf-8"), digest_size=16).hexdigest()
        return f"v3:{digest}"
    if isinstance(auth_data, CommunityData):
        return _COMMUNITY_SCOPE
    raise TypeError(f"unsupported SNMP auth data: {type(auth_data).__name__}")


def _scope_label(scope: str) -> str:
    """日志与快照里使用的稳定标签：community 或 v3#N，不含任何密钥材料。"""

    label = _scope_labels.get(scope)
    if label is None:
        if scope == _COMMUNITY_SCOPE:
            label = _COMMUNITY_SCOPE
        else:
            v3_count = sum(1 for existing in _scope_labels.values() if existing != _COMMUNITY_SCOPE)
            label = f"v3#{v3_count + 1}"
        _scope_labels[scope] = label
    return label


def _attach_shared_mib_compiler(engine: Any) -> None:
    """让每一代 engine 复用进程内唯一的 MIB 编译器，避免重复构建 PLY 解析器。"""

    global _shared_mib_compiler, _shared_mib_destination
    mib_builder = engine.getMibBuilder()
    if _shared_mib_compiler is not None:
        mib_builder.setMibCompiler(_shared_mib_compiler, _shared_mib_destination)
        return
    from pysnmp.smi import compiler as smi_compiler

    smi_compiler.addMibCompiler(mib_builder, ifAvailable=True, ifNotAdded=True)
    compiler = mib_builder.getMibCompiler()
    if compiler is not None:
        _shared_mib_compiler = compiler
        _shared_mib_destination = smi_compiler.defaultDest


def create_snmp_engine() -> Any:
    """创建一个已装配共享 MIB 编译器的 SnmpEngine；测试可整体替换本函数。"""

    from pysnmp.hlapi.asyncio import SnmpEngine

    engine = SnmpEngine()
    _attach_shared_mib_compiler(engine)
    return engine


def close_snmp_engine(engine: Any) -> None:
    """关闭 engine 的 transport dispatcher；未曾发过请求的 engine 没有 dispatcher。"""

    dispatcher = getattr(engine, "transportDispatcher", None)
    close = getattr(dispatcher, "closeDispatcher", None)
    if callable(close):
        close()


def _target_key(target: Any) -> tuple[str, int]:
    host, port = target
    return str(host), int(port)


def _open(scope: str, loop: asyncio.AbstractEventLoop) -> _SharedEngine:
    started = time.monotonic()
    engine = create_snmp_engine()
    holder = _SharedEngine(
        scope=scope,
        label=_scope_label(scope),
        generation=next(_generations),
        loop=loop,
        engine=engine,
    )
    _active[scope] = holder
    logger.info(
        "event=snmp_engine_opened scope=%s generation=%s active_engines=%s draining_engines=%s init_seconds=%.3f",
        holder.label,
        holder.generation,
        len(_active),
        len(_draining),
        time.monotonic() - started,
    )
    return holder


def _close(holder: _SharedEngine, reason: str) -> None:
    if holder.closed:
        return
    holder.closed = True
    if holder in _draining:
        _draining.remove(holder)
    if holder.idle_handle is not None:
        holder.idle_handle.cancel()
        holder.idle_handle = None
    if holder.loop.is_closed():
        # 事件循环已经结束，dispatcher 随之失效，只能丢弃引用。
        logger.debug(
            "event=snmp_engine_dropped scope=%s generation=%s reason=%s",
            holder.label,
            holder.generation,
            reason,
        )
        return
    try:
        close_snmp_engine(holder.engine)
    except Exception as exc:  # noqa: BLE001 - 关闭失败不影响采集结果，无需 traceback
        logger.warning(
            "event=snmp_engine_close_failed scope=%s generation=%s reason=%s error_type=%s",
            holder.label,
            holder.generation,
            reason,
            type(exc).__name__,
        )
        return
    logger.info(
        "event=snmp_engine_closed scope=%s generation=%s reason=%s acquisitions=%s distinct_targets=%s "
        "lifetime_seconds=%.1f active_engines=%s draining_engines=%s",
        holder.label,
        holder.generation,
        reason,
        holder.acquisitions,
        len(holder.targets),
        time.monotonic() - holder.opened_at,
        len(_active),
        len(_draining),
    )


def _retire(holder: _SharedEngine, reason: str) -> None:
    """把 engine 移出活跃表；在途请求排空（或事件循环已结束）后关闭。"""

    if _active.get(holder.scope) is holder:
        del _active[holder.scope]
    if holder.idle_handle is not None:
        holder.idle_handle.cancel()
        holder.idle_handle = None
    holder.retired = True
    holder.retire_reason = reason
    if holder.in_flight == 0 or holder.loop.is_closed():
        _close(holder, reason)
    elif holder not in _draining:
        _draining.append(holder)


def _close_idle(holder: _SharedEngine) -> None:
    holder.idle_handle = None
    if holder.closed or holder.in_flight:
        return
    if _active.get(holder.scope) is holder:
        del _active[holder.scope]
    _close(holder, "idle")


def _acquire(scope: str, target: tuple[str, int]) -> _SharedEngine:
    loop = asyncio.get_running_loop()
    settings = snmp_engine_pool_settings()
    holder = _active.get(scope)
    if holder is not None and holder.loop is not loop:
        _retire(holder, "loop_changed")
        holder = None
    if holder is not None and target not in holder.targets and len(holder.targets) >= settings.max_targets:
        _retire(holder, "target_limit")
        holder = None
    if holder is None:
        holder = _open(scope, loop)
    if holder.idle_handle is not None:
        holder.idle_handle.cancel()
        holder.idle_handle = None
    holder.in_flight += 1
    holder.acquisitions += 1
    holder.targets.add(target)
    return holder


def _release(holder: _SharedEngine) -> None:
    holder.in_flight -= 1
    if holder.in_flight > 0 or holder.closed:
        return
    if holder.retired:
        _close(holder, holder.retire_reason)
        return
    holder.idle_handle = holder.loop.call_later(snmp_engine_pool_settings().idle_seconds, _close_idle, holder)


@asynccontextmanager
async def shared_snmp_engine(auth_data: Any, *, target: Any):
    """借用当前事件循环内与 ``auth_data`` 同作用域的共享 engine。

    ``target`` 为 ``(host, port)``，用于统计该 engine 已服务的不同目标数以触发代际
    轮换。上下文退出只是归还引用，不关闭 engine。
    """

    holder = _acquire(snmp_engine_scope(auth_data), _target_key(target))
    try:
        yield holder.engine
    finally:
        _release(holder)


def close_shared_snmp_engines(reason: str = "shutdown") -> int:
    """关闭本进程所有共享 engine（包括仍在排空的旧代），返回关闭数量。"""

    holders = list(_active.values()) + list(_draining)
    _active.clear()
    _draining.clear()
    closed = 0
    for holder in holders:
        if not holder.closed:
            _close(holder, reason)
            closed += 1
    return closed


def snmp_engine_pool_snapshot() -> dict[str, Any]:
    engines = [
        {
            "scope": holder.label,
            "generation": holder.generation,
            "state": "draining" if holder.retired else "active",
            "in_flight": holder.in_flight,
            "acquisitions": holder.acquisitions,
            "distinct_targets": len(holder.targets),
        }
        for holder in list(_active.values()) + list(_draining)
    ]
    return {
        "active_engines": len(_active),
        "draining_engines": len(_draining),
        "mib_compiler_shared": _shared_mib_compiler is not None,
        "engines": engines,
    }


def reset_snmp_engine_pool(*, drop_mib_compiler: bool = False) -> None:
    """测试用：关闭全部 engine 并清空作用域标签与配置缓存。"""

    global _settings, _generations, _shared_mib_compiler, _shared_mib_destination
    close_shared_snmp_engines(reason="reset")
    _scope_labels.clear()
    _generations = itertools.count(1)
    _settings = None
    if drop_mib_compiler:
        _shared_mib_compiler = None
        _shared_mib_destination = None


def register_snmp_engine_lifecycle(app) -> None:
    @app.listener("before_server_start")
    async def validate_snmp_engine_pool(_app, _loop):
        # 阈值配置非法时启动失败，而不是在第一批 SNMP 目标上才暴露。
        snmp_engine_pool_settings()

    @app.listener("after_server_stop")
    async def close_snmp_engines(_app, _loop):
        close_shared_snmp_engines(reason="server_stop")


__all__ = [
    "DEFAULT_SNMP_ENGINE_IDLE_SECONDS",
    "DEFAULT_SNMP_ENGINE_MAX_TARGETS",
    "SnmpEnginePoolSettings",
    "close_shared_snmp_engines",
    "close_snmp_engine",
    "configure_snmp_engine_pool",
    "create_snmp_engine",
    "register_snmp_engine_lifecycle",
    "reset_snmp_engine_pool",
    "shared_snmp_engine",
    "snmp_engine_pool_settings",
    "snmp_engine_pool_snapshot",
    "snmp_engine_scope",
]
