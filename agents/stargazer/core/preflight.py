"""采集协议级异步预检；ICMP 不作为采集准入条件。"""

from __future__ import annotations

import asyncio
import socket
import ssl
from urllib.parse import urlsplit

from core.collection_runtime import CollectionRequest
from core.outbound_policy import OutboundTargetPolicy, OutboundTargetRejected
from core.target_collection_executor import PreflightResult, PreflightStatus


class AsyncProtocolPreflight:
    def __init__(
        self,
        policy: OutboundTargetPolicy | None = None,
        remote_probe=None,
    ) -> None:
        self._policy = policy or OutboundTargetPolicy()
        self._remote_probe = remote_probe

    async def check(
        self,
        target: str,
        request: CollectionRequest,
        *,
        timeout_seconds: float,
    ) -> PreflightResult:
        kind = str(request.params.get("preflight_kind") or "").lower()
        if kind == "cloud":
            return PreflightResult(
                status=PreflightStatus.UNKNOWN,
                detail="cloud endpoint validation is credential-aware",
            )
        if kind == "remote":
            node_id = str(request.params.get("ansible_node_id") or "").strip()
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
                    error_code=(
                        "" if available else "remote_responder_unavailable"
                    ),
                )
            try:
                from core.nats import get_nats

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
            if request.params.get("target_is_logical"):
                return PreflightResult(status=PreflightStatus.REACHABLE)
            try:
                await self._policy.resolve_allowed(target)
            except (OutboundTargetRejected, socket.gaierror):
                return PreflightResult(
                    status=PreflightStatus.UNREACHABLE,
                    error_code="outbound_target_rejected",
                )
            return PreflightResult(status=PreflightStatus.REACHABLE)
        if kind in {"udp", "snmp"}:
            return PreflightResult(
                status=PreflightStatus.UNKNOWN,
                detail="UDP reachability requires a credential-aware probe",
            )

        host, port, use_tls = self._endpoint(target, request, kind)
        if port is None:
            return PreflightResult(status=PreflightStatus.REACHABLE)

        writer = None
        try:
            connect_host = await self._policy.resolve_allowed(host, port)
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
            return PreflightResult(status=PreflightStatus.REACHABLE)
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
            return PreflightResult(
                status=PreflightStatus.UNREACHABLE,
                error_code="outbound_target_rejected",
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
    def _endpoint(
        target: str, request: CollectionRequest, kind: str
    ) -> tuple[str, int | None, bool]:
        if kind in {"http", "https"} or "://" in target:
            parsed = urlsplit(
                target if "://" in target else f"{kind}://{target}"
            )
            use_tls = parsed.scheme == "https"
            port = parsed.port or (443 if use_tls else 80)
            return parsed.hostname or target, port, use_tls

        raw_port = request.params.get("port")
        if raw_port in (None, ""):
            return target, None, False
        port = int(raw_port)
        if not 1 <= port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        return target, port, False
