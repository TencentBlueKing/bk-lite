from __future__ import annotations

import asyncio
import json
import socket
import ssl

from cryptography import x509

from core.collection.contracts import AccessProbeResult, AccessProbeStatus
from core.logger import logger

DEFAULT_PORT = 443
PROBE_TIMEOUT_SECONDS = 10


def parse_der_certificate(der: bytes) -> dict[str, str]:
    cert = x509.load_der_x509_certificate(der)
    return {
        "issuer": cert.issuer.rfc4514_string(),
        "create_time": cert.not_valid_before_utc.strftime("%Y-%m-%d %H:%M:%S"),
        "expired_time": cert.not_valid_after_utc.strftime("%Y-%m-%d %H:%M:%S"),
    }


def _load_targets(kwargs: dict) -> list[dict[str, str]]:
    raw = kwargs.get("ssl_cer_targets") or "[]"
    if isinstance(raw, list):
        items = raw
    else:
        try:
            items = json.loads(raw)
        except (TypeError, ValueError):
            items = []
    if not isinstance(items, list):
        return []
    rows = []
    for item in items:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "inst_name": str(item.get("inst_name") or "").strip(),
                "domain": str(item.get("domain") or "").strip(),
            }
        )
    return rows


class SslCerInfo:
    def __init__(self, kwargs: dict):
        self.host = str(kwargs.get("host") or "").strip()
        self.port = int(kwargs.get("port") or DEFAULT_PORT)
        self.timeout = PROBE_TIMEOUT_SECONDS
        self.collection_task_id = kwargs.get("collection_task_id")
        self.targets = _load_targets(kwargs)
        if not self.targets and self.host:
            self.targets = [{"inst_name": self.host, "domain": self.host}]

    async def probe(self) -> AccessProbeResult:
        if not self.host:
            return AccessProbeResult(status=AccessProbeStatus.TARGET_UNREACHABLE, error_code="domain_missing")
        return AccessProbeResult(status=AccessProbeStatus.READY)

    def _fetch_peer_der(self) -> bytes:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
            with context.wrap_socket(sock, server_hostname=self.host) as ssock:
                der = ssock.getpeercert(binary_form=True)
        if not der:
            raise ValueError("empty peer certificate")
        return der

    def _rows_for_host(self) -> list[dict[str, str]]:
        matched = [item for item in self.targets if item["domain"] == self.host]
        if matched:
            return matched
        empty = [item for item in self.targets if not item["domain"]]
        if empty:
            return empty
        if any(item["domain"] for item in self.targets):
            return []
        return [{"inst_name": self.host, "domain": self.host}]

    async def list_all_resources(self):
        rows = []
        for target in self._rows_for_host():
            if not target["domain"]:
                rows.append(
                    {
                        "inst_name": target["inst_name"],
                        "domain": "",
                        "collect_status": "failed",
                        "collect_error": "domain_missing",
                    }
                )
                continue
            try:
                der = await asyncio.to_thread(self._fetch_peer_der)
                parsed = parse_der_certificate(der)
                rows.append(
                    {
                        "inst_name": target["inst_name"] or target["domain"],
                        "domain": target["domain"],
                        "issuer": parsed["issuer"],
                        "create_time": parsed["create_time"],
                        "expired_time": parsed["expired_time"],
                    }
                )
            except Exception as err:
                logger.warning(
                    "event=ssl_cer_collect_failed host=%s task_id=%s failed_stage=handshake error_type=%s",
                    self.host,
                    self.collection_task_id,
                    type(err).__name__,
                )
                rows.append(
                    {
                        "inst_name": target["inst_name"] or target["domain"],
                        "domain": target["domain"],
                        "collect_status": "failed",
                        "collect_error": "tls_handshake_failed",
                    }
                )
        return {"result": {"ssl_cer": rows}, "success": True}
