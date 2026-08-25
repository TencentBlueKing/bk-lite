"""采集协议级异步预检。

默认不做连通性拨测；任务显式开启 ``ip_precheck`` 或环境变量 ``PREFLIGHT_REACHABILITY``
开启时，按插件协议做无凭据连接性探测：

- TCP/TLS/SSH：拨端口；
- SNMP/UDP：方案 B——明确网络层失败判不可达，纯超时放行进凭据探测。

ICMP 不作为采集准入条件。
"""

from __future__ import annotations

import asyncio
import errno
import ipaddress
import os
import socket
import ssl
from urllib.parse import urlsplit

from core.collection.contracts import PreflightResult, PreflightStatus
from core.collection.runtime import CollectionRequest
from core.infra.outbound_policy import OutboundTargetPolicy, OutboundTargetRejected
from core.logger import logger

_REACHABILITY_OFF = {"", "0", "off", "false", "no"}
_TRUTHY = {"1", "true", "yes", "on"}


def reachability_enabled_from_env() -> bool:
    raw = str(os.getenv("PREFLIGHT_REACHABILITY", "off")).strip().lower()
    return raw not in _REACHABILITY_OFF


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in _TRUTHY


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def _normalized_ip(value: str) -> str | None:
    try:
        return str(ipaddress.ip_address(str(value).strip()))
    except ValueError:
        return None


class AsyncProtocolPreflight:
    def __init__(
        self,
        policy: OutboundTargetPolicy | None = None,
        remote_probe=None,
        reachability_enabled: bool | None = None,
    ) -> None:
        self._policy = policy or OutboundTargetPolicy()
        self._remote_probe = remote_probe
        self._reachability_enabled = reachability_enabled_from_env() if reachability_enabled is None else bool(reachability_enabled)

    def _reachability_enabled_for(self, request: CollectionRequest) -> bool:
        if self._reachability_enabled:
            return True
        return _as_bool(request.params.get("ip_precheck"))

    async def check(  # noqa: C901
        self,
        target: str,
        request: CollectionRequest,
        *,
        timeout_seconds: float,
    ) -> PreflightResult:
        try:
            return await self._check_inner(target, request, timeout_seconds=timeout_seconds)
        except Exception as error:  # noqa: BLE001 - 预检组件故障不得阻断采集
            logger.warning(
                "event=preflight_component_failed task_id=%s target=%s " "error_type=%s detail=%s action=pass",
                request.task_id,
                target,
                type(error).__name__,
                str(error).strip() or "-",
            )
            return PreflightResult(
                status=PreflightStatus.UNKNOWN,
                detail=f"preflight component failed: {type(error).__name__}",
            )

    async def _check_inner(
        self,
        target: str,
        request: CollectionRequest,
        *,
        timeout_seconds: float,
    ) -> PreflightResult:
        kind = str(request.params.get("preflight_kind") or "").lower()
        if request.params.get("target_is_logical") and kind in {
            "http",
            "https",
            "tcp",
            "udp",
            "snmp",
            "outbound_only",
            "remote",
        }:
            return PreflightResult(
                status=PreflightStatus.UNREACHABLE,
                error_code="network_target_missing",
                detail="logical target is not a network endpoint",
            )
        host, port, use_tls = self._endpoint(target, request, kind)
        connect_host = host
        trusted_cloud_domains = ()
        if kind == "cloud" and request.params.get("target_is_logical"):
            if request.params.get("target_policy_mode") == "cloud_endpoint" and request.params.get("_yaml_target_policy_verified") is True:
                trusted_cloud_domains = request.params.get("trusted_endpoint_domains") or ()
            try:
                trusted_cloud_domains = self._policy.validate_trusted_domains(trusted_cloud_domains)
            except OutboundTargetRejected as error:
                self._log_outbound_skip(request, target, error)
                return PreflightResult(
                    status=PreflightStatus.UNREACHABLE,
                    error_code="outbound_target_rejected",
                )
        elif kind != "skip" or _is_ip_literal(host):
            try:
                connect_host = await self._policy.resolve_allowed(host, port or 0)
            except (OutboundTargetRejected, socket.gaierror) as error:
                self._log_outbound_skip(request, target, error)
                return PreflightResult(
                    status=PreflightStatus.UNREACHABLE,
                    error_code="outbound_target_rejected",
                )
        if kind == "cloud":
            return PreflightResult(
                status=PreflightStatus.UNKNOWN,
                detail=(
                    f"trusted cloud SDK domains: {','.join(trusted_cloud_domains)}"
                    if trusted_cloud_domains
                    else "cloud endpoint validation is credential-aware"
                ),
                connect_host=connect_host if not use_tls else "",
            )
        if kind == "skip":
            return PreflightResult(
                status=PreflightStatus.REACHABLE,
                connect_host=connect_host if not use_tls else "",
            )
        if kind == "outbound_only":
            return PreflightResult(
                status=PreflightStatus.UNKNOWN,
                detail="outbound allowed; reachability deferred to credential attempt",
                connect_host=connect_host if not use_tls else "",
            )
        if kind == "remote":
            return await self._check_remote(
                target,
                request,
                connect_host=connect_host,
                use_tls=use_tls,
                timeout_seconds=timeout_seconds,
            )
        if kind == "none":
            return PreflightResult(
                status=PreflightStatus.REACHABLE,
                connect_host=connect_host if not use_tls else "",
            )
        if kind in {"udp", "snmp"}:
            if not self._reachability_enabled_for(request):
                logger.debug(
                    "event=preflight_reachability_skipped task_id=%s target=%s kind=%s",
                    request.task_id,
                    target,
                    kind,
                )
                return PreflightResult(
                    status=PreflightStatus.UNKNOWN,
                    detail="outbound allowed; udp reachability disabled",
                    connect_host=connect_host,
                )
            udp_port = port if port is not None else 161
            return await self._udp_dial(
                connect_host=connect_host,
                port=udp_port,
                timeout_seconds=timeout_seconds,
            )

        if port is None:
            return PreflightResult(
                status=PreflightStatus.REACHABLE,
                connect_host=connect_host if not use_tls else "",
            )

        if not self._reachability_enabled_for(request):
            logger.debug(
                "event=preflight_reachability_skipped task_id=%s target=%s kind=%s",
                request.task_id,
                target,
                kind,
            )
            return PreflightResult(
                status=PreflightStatus.UNKNOWN,
                detail="outbound allowed; tcp reachability disabled",
                connect_host=connect_host if not use_tls else "",
            )
        return await self._tcp_dial(
            host=host,
            connect_host=connect_host,
            port=port,
            use_tls=use_tls,
            timeout_seconds=timeout_seconds,
            request=request,
            target=target,
        )

    async def _check_remote(
        self,
        target: str,
        request: CollectionRequest,
        *,
        connect_host: str,
        use_tls: bool,
        timeout_seconds: float,
    ) -> PreflightResult:
        if not self._reachability_enabled_for(request):
            logger.debug(
                "event=preflight_reachability_skipped task_id=%s target=%s kind=remote",
                request.task_id,
                target,
            )
            return PreflightResult(
                status=PreflightStatus.UNKNOWN,
                detail="outbound allowed; remote probe disabled",
                connect_host=connect_host if not use_tls else "",
            )
        # 目标 IP 与执行节点管理 IP 一致：本地执行脚本，跳过预检。
        target_ip = _normalized_ip(target) or _normalized_ip(connect_host)
        node_ip = _normalized_ip(str(request.params.get("executor_node_ip") or ""))
        if target_ip and node_ip and target_ip == node_ip:
            return PreflightResult(
                status=PreflightStatus.REACHABLE,
                detail="target matches executor node; ip precheck skipped",
                connect_host=connect_host if not use_tls else "",
            )
        raw_port = request.params.get("port")
        port = 22 if raw_port in (None, "") else int(raw_port)
        if not 1 <= port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        return await self._tcp_dial(
            host=target,
            connect_host=connect_host,
            port=port,
            use_tls=False,
            timeout_seconds=timeout_seconds,
            request=request,
            target=target,
        )

    async def _tcp_dial(
        self,
        *,
        host: str,
        connect_host: str,
        port: int,
        use_tls: bool,
        timeout_seconds: float,
        request: CollectionRequest,
        target: str,
    ) -> PreflightResult:
        writer = None
        try:
            connect_options = {}
            if use_tls:
                connect_options = {
                    "ssl": ssl.create_default_context(),
                    "server_hostname": host,
                }
            async with asyncio.timeout(timeout_seconds):
                _reader, writer = await asyncio.open_connection(connect_host, port, **connect_options)
            return PreflightResult(
                status=PreflightStatus.REACHABLE,
                connect_host=connect_host if not use_tls else "",
            )
        except TimeoutError:
            return PreflightResult(
                status=PreflightStatus.UNREACHABLE,
                error_code="tcp_connect_timeout",
                detail="TimeoutError",
            )
        except ConnectionRefusedError as error:
            return PreflightResult(
                status=PreflightStatus.UNREACHABLE,
                error_code="tcp_connection_refused",
                detail=type(error).__name__,
            )
        except socket.gaierror as error:
            return PreflightResult(
                status=PreflightStatus.UNREACHABLE,
                error_code="dns_resolution_failed",
                detail=type(error).__name__,
            )
        except OutboundTargetRejected as error:
            self._log_outbound_skip(request, target, error)
            return PreflightResult(
                status=PreflightStatus.UNREACHABLE,
                error_code="outbound_target_rejected",
                detail=type(error).__name__,
            )
        except ssl.SSLCertVerificationError as error:
            # 证书校验失败仍算可达：交给凭据/业务阶段处理。
            return PreflightResult(
                status=PreflightStatus.REACHABLE,
                detail=f"tls certificate deferred: {type(error).__name__}",
                connect_host="",
            )
        except (ConnectionError, OSError) as error:
            return PreflightResult(
                status=PreflightStatus.UNREACHABLE,
                error_code="tcp_connect_failed",
                detail=type(error).__name__,
            )
        finally:
            if writer is not None:
                writer.close()
                await writer.wait_closed()

    async def _udp_dial(
        self,
        *,
        connect_host: str,
        port: int,
        timeout_seconds: float,
    ) -> PreflightResult:
        """方案 B：UDP 短探测。

        - 明确网络层失败（无路由、主机不可达、ICMP Port Unreachable 等）→ unreachable
        - 纯超时（无回应）→ UNKNOWN，放行进入凭据探测（与「community 错误」不可区分）
        """
        loop = asyncio.get_running_loop()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)
        try:
            try:
                sock.connect((connect_host, port))
            except OSError as error:
                return self._udp_oserror_result(error)

            # 发一字节探测；合法 SNMP PDU 非必需，ICMP 错误同样会回灌到已 connect 的 UDP socket。
            try:
                await loop.sock_sendall(sock, b"\x00")
            except OSError as error:
                return self._udp_oserror_result(error)

            # 略短于外层 preflight timeout，避免被 executor 统一收成 preflight_timeout。
            wait_seconds = max(0.05, min(float(timeout_seconds), float(timeout_seconds) * 0.9))
            try:
                async with asyncio.timeout(wait_seconds):
                    await loop.sock_recv(sock, 64)
            except TimeoutError:
                return PreflightResult(
                    status=PreflightStatus.UNKNOWN,
                    detail="udp probe timeout; deferred to credential-aware probe",
                    connect_host=connect_host,
                )
            except ConnectionRefusedError:
                return PreflightResult(
                    status=PreflightStatus.UNREACHABLE,
                    error_code="udp_port_unreachable",
                    detail="ConnectionRefusedError",
                )
            except OSError as error:
                return self._udp_oserror_result(error)

            return PreflightResult(
                status=PreflightStatus.REACHABLE,
                connect_host=connect_host,
            )
        finally:
            sock.close()

    @staticmethod
    def _udp_oserror_result(error: OSError) -> PreflightResult:
        code = getattr(error, "errno", None)
        if code in {
            errno.ENETUNREACH,
            errno.EHOSTUNREACH,
            errno.ENETDOWN,
            errno.EHOSTDOWN,
            getattr(errno, "EAFNOSUPPORT", -1),
        }:
            return PreflightResult(
                status=PreflightStatus.UNREACHABLE,
                error_code="udp_network_unreachable",
                detail=type(error).__name__,
            )
        if code in {errno.ECONNREFUSED, getattr(errno, "ECONNRESET", -1)}:
            return PreflightResult(
                status=PreflightStatus.UNREACHABLE,
                error_code="udp_port_unreachable",
                detail=type(error).__name__,
            )
        return PreflightResult(
            status=PreflightStatus.UNREACHABLE,
            error_code="udp_connect_failed",
            detail=type(error).__name__,
        )

    @staticmethod
    def _log_outbound_skip(request: CollectionRequest, target: str, error: BaseException) -> None:
        reason = str(error).strip() or type(error).__name__
        logger.info(
            "event=outbound_target_skipped task_id=%s target=%s reason=%s",
            request.task_id,
            target,
            reason,
        )

    @staticmethod
    def _endpoint(target: str, request: CollectionRequest, kind: str) -> tuple[str, int | None, bool]:
        if kind in {"http", "https"} or "://" in target or request.params.get("base_url"):
            base_url = str(request.params.get("base_url") or "").strip()
            has_explicit_endpoint = "://" in target or bool(base_url)
            endpoint = target if "://" in target else base_url or f"{kind}://{target}"
            parsed = urlsplit(endpoint)
            use_tls = parsed.scheme == "https"
            raw_port = request.params.get("port")
            port = parsed.port
            if port is None and not has_explicit_endpoint and raw_port not in (None, ""):
                port = int(raw_port)
                if not 1 <= port <= 65535:
                    raise ValueError("port must be between 1 and 65535")
            port = port or (443 if use_tls else 80)
            return parsed.hostname or target, port, use_tls

        raw_port = request.params.get("port")
        if kind == "cloud" and raw_port in (None, ""):
            return target, 443, bool(request.params.get("ssl", True))
        if raw_port in (None, ""):
            return target, None, False
        port = int(raw_port)
        if not 1 <= port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        return target, port, bool(request.params.get("ssl", False))
