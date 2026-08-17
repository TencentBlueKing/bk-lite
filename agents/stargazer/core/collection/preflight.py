"""采集协议级异步预检；ICMP 不作为采集准入条件。"""

from __future__ import annotations

import asyncio
import os
import socket
import ssl
from urllib.parse import urlsplit

from core.collection.contracts import PreflightResult, PreflightStatus
from core.collection.runtime import CollectionRequest
from core.infra.outbound_policy import OutboundTargetPolicy, OutboundTargetRejected
from core.logger import logger

_REACHABILITY_OFF = {"", "0", "off", "false", "no"}


def reachability_enabled_from_env() -> bool:
    raw = str(os.getenv("PREFLIGHT_REACHABILITY", "off")).strip().lower()
    return raw not in _REACHABILITY_OFF


class AsyncProtocolPreflight:
    def __init__(
        self,
        policy: OutboundTargetPolicy | None = None,
        remote_probe=None,
        reachability_enabled: bool | None = None,
    ) -> None:
        self._policy = policy or OutboundTargetPolicy()
        self._remote_probe = remote_probe
        self._reachability_enabled = (
            reachability_enabled_from_env()
            if reachability_enabled is None
            else bool(reachability_enabled)
        )

    async def check(  # noqa: C901
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
            if (
                request.params.get("target_policy_mode") == "cloud_endpoint"
                and request.params.get("_yaml_target_policy_verified") is True
            ):
                trusted_cloud_domains = (
                    request.params.get("trusted_endpoint_domains") or ()
                )
            try:
                trusted_cloud_domains = self._policy.validate_trusted_domains(
                    trusted_cloud_domains
                )
            except OutboundTargetRejected as error:
                self._log_outbound_skip(request, target, error)
                return PreflightResult(
                    status=PreflightStatus.UNREACHABLE,
                    error_code="outbound_target_rejected",
                )
        else:
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
            if not self._reachability_enabled:
                logger.info(
                    "event=preflight_reachability_skipped task_id=%s "
                    "target=%s kind=remote",
                    request.task_id,
                    target,
                )
                return PreflightResult(
                    status=PreflightStatus.UNKNOWN,
                    detail="outbound allowed; remote probe disabled",
                    connect_host=connect_host if not use_tls else "",
                )
            node_id = str(
                request.params.get("ansible_node_id")
                or request.params.get("node_id")
                or ""
            ).strip()
            if self._remote_probe is not None and node_id:
                available = await self._remote_probe(
                    node_id, timeout_seconds=timeout_seconds
                )
                return PreflightResult(
                    status=(
                        PreflightStatus.UNKNOWN
                        if available
                        else PreflightStatus.UNREACHABLE
                    ),
                    error_code=("" if available else "remote_responder_unavailable"),
                )
            try:
                from core.infra.nats import get_nats

                connected = bool(get_nats().is_connected)
            except Exception:
                connected = False
            return PreflightResult(
                status=(
                    PreflightStatus.UNKNOWN
                    if connected
                    else PreflightStatus.UNREACHABLE
                ),
                error_code="" if connected else "remote_responder_unavailable",
            )
        if kind == "none":
            return PreflightResult(
                status=PreflightStatus.REACHABLE,
                connect_host=connect_host if not use_tls else "",
            )
        if kind in {"udp", "snmp"}:
            return PreflightResult(
                status=PreflightStatus.UNKNOWN,
                detail="UDP reachability requires a credential-aware probe",
                connect_host=connect_host,
            )

        if port is None:
            return PreflightResult(
                status=PreflightStatus.REACHABLE,
                connect_host=connect_host if not use_tls else "",
            )

        writer = None
        try:
            if not self._reachability_enabled:
                logger.info(
                    "event=preflight_reachability_skipped task_id=%s "
                    "target=%s kind=%s",
                    request.task_id,
                    target,
                    kind,
                )
                return PreflightResult(
                    status=PreflightStatus.UNKNOWN,
                    detail="outbound allowed; tcp reachability disabled",
                    connect_host=connect_host if not use_tls else "",
                )
            connect_options = {}
            if use_tls:
                connect_options = {
                    "ssl": ssl.create_default_context(),
                    "server_hostname": host,
                }
            async with asyncio.timeout(timeout_seconds):
                _reader, writer = await asyncio.open_connection(
                    connect_host, port, **connect_options
                )
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
            return PreflightResult(
                status=PreflightStatus.UNREACHABLE,
                error_code="tls_validation_failed",
                detail=type(error).__name__,
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

    @staticmethod
    def _log_outbound_skip(
        request: CollectionRequest, target: str, error: BaseException
    ) -> None:
        reason = str(error).strip() or type(error).__name__
        logger.info(
            "🚫 event=outbound_target_skipped task_id=%s target=%s reason=%s",
            request.task_id,
            target,
            reason,
        )

    @staticmethod
    def _endpoint(
        target: str, request: CollectionRequest, kind: str
    ) -> tuple[str, int | None, bool]:
        if (
            kind in {"http", "https"}
            or "://" in target
            or request.params.get("base_url")
        ):
            base_url = str(request.params.get("base_url") or "").strip()
            endpoint = target if "://" in target else base_url or f"{kind}://{target}"
            parsed = urlsplit(endpoint)
            use_tls = parsed.scheme == "https"
            port = parsed.port or (443 if use_tls else 80)
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
