"""采集协议级异步预检。

默认不做连通性拨测；单次任务通过 ``request.params["ip_precheck"]`` 显式开启时，
按插件协议做无凭据连接性探测：

- TCP/TLS/SSH：拨端口；
- SNMP/UDP：无凭据层只做出站安全检查，可选探测交给带凭据的插件 probe。

ICMP 不作为采集准入条件。
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import ssl
from urllib.parse import urlsplit

from core.collection.contracts import PreflightResult, PreflightStatus
from core.collection.enums import FailureStage
from core.collection.runtime import CollectionRequest
from core.infra.outbound_policy import OutboundTargetPolicy, OutboundTargetRejected
from core.logger import logger, safe_log_value


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
    ) -> None:
        self._policy = policy or OutboundTargetPolicy()
        self._remote_probe = remote_probe

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
                "event=preflight_component_failed task_id=%s target=%s " "failed_stage=preflight_component error_type=%s action=pass",
                safe_log_value(request.task_id),
                safe_log_value(target, max_length=255),
                type(error).__name__,
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
                failed_stage=FailureStage.OUTBOUND_POLICY,
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
                    failed_stage=FailureStage.OUTBOUND_POLICY,
                )
        elif kind != "skip" or _is_ip_literal(host):
            try:
                connect_host = await self._policy.resolve_allowed(host, port or 0)
            except (OutboundTargetRejected, socket.gaierror) as error:
                self._log_outbound_skip(request, target, error)
                return PreflightResult(
                    status=PreflightStatus.UNREACHABLE,
                    error_code="outbound_target_rejected",
                    failed_stage=FailureStage.OUTBOUND_POLICY,
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
            if not request.ip_precheck_enabled:
                logger.debug(
                    "event=preflight_reachability_skipped task_id=%s target=%s kind=%s",
                    safe_log_value(request.task_id),
                    safe_log_value(target, max_length=255),
                    kind,
                )
            return PreflightResult(
                status=PreflightStatus.UNKNOWN,
                detail="outbound allowed; deferred to credential-aware probe",
                connect_host=connect_host,
            )

        if port is None:
            return PreflightResult(
                status=PreflightStatus.REACHABLE,
                connect_host=connect_host if not use_tls else "",
            )

        if not request.ip_precheck_enabled:
            logger.debug(
                "event=preflight_reachability_skipped task_id=%s target=%s kind=%s",
                safe_log_value(request.task_id),
                safe_log_value(target, max_length=255),
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
        if not request.ip_precheck_enabled:
            logger.debug(
                "event=preflight_reachability_skipped task_id=%s target=%s kind=remote",
                safe_log_value(request.task_id),
                safe_log_value(target, max_length=255),
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
                failed_stage=FailureStage.IP_PRECHECK,
            )
        except ConnectionRefusedError as error:
            return PreflightResult(
                status=PreflightStatus.UNREACHABLE,
                error_code="tcp_connection_refused",
                detail=type(error).__name__,
                failed_stage=FailureStage.IP_PRECHECK,
            )
        except socket.gaierror as error:
            return PreflightResult(
                status=PreflightStatus.UNREACHABLE,
                error_code="dns_resolution_failed",
                detail=type(error).__name__,
                failed_stage=FailureStage.IP_PRECHECK,
            )
        except OutboundTargetRejected as error:
            self._log_outbound_skip(request, target, error)
            return PreflightResult(
                status=PreflightStatus.UNREACHABLE,
                error_code="outbound_target_rejected",
                detail=type(error).__name__,
                failed_stage=FailureStage.OUTBOUND_POLICY,
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
                failed_stage=FailureStage.IP_PRECHECK,
            )
        finally:
            if writer is not None:
                writer.close()
                await writer.wait_closed()

    @staticmethod
    def _log_outbound_skip(request: CollectionRequest, target: str, error: BaseException) -> None:
        logger.info(
            "event=outbound_target_skipped task_id=%s target=%s " "failed_stage=outbound_policy error_type=%s",
            safe_log_value(request.task_id),
            safe_log_value(target, max_length=255),
            type(error).__name__,
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
