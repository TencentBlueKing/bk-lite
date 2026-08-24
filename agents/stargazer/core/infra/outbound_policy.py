"""采集目标的统一出站地址边界。"""

from __future__ import annotations

import asyncio
import ipaddress
import os
import re
import socket


class OutboundTargetRejected(ValueError):
    pass


class OutboundTargetPolicy:
    DEFAULT_CIDRS = (
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "fc00::/7",
    )

    def __init__(
        self,
        *,
        allowed_cidrs: tuple[str, ...] | None = None,
        allowed_domains: tuple[str, ...] | None = None,
    ) -> None:
        if allowed_cidrs is None:
            allowed_cidrs = self._env_values("OUTBOUND_ALLOWED_CIDRS", self.DEFAULT_CIDRS)
        if allowed_domains is None:
            allowed_domains = self._env_values("OUTBOUND_ALLOWED_DOMAINS", ())
        self._networks = tuple(ipaddress.ip_network(value, strict=False) for value in allowed_cidrs)
        self._domains = tuple(value.lower().lstrip(".") for value in allowed_domains)

    async def resolve_allowed(self, host: str, port: int = 0) -> str:
        normalized = str(host or "").strip().rstrip(".")
        if not normalized:
            raise OutboundTargetRejected("empty outbound target")
        try:
            address = ipaddress.ip_address(normalized)
        except ValueError:
            address = None
        if address is not None:
            if self._address_allowed(address):
                return str(address)
            raise OutboundTargetRejected("outbound address is outside allowed ranges")

        infos = await asyncio.get_running_loop().getaddrinfo(
            normalized,
            port,
            type=socket.SOCK_STREAM,
        )
        domain_allowed = self._domain_allowed(normalized)
        if self._domains and not domain_allowed:
            raise OutboundTargetRejected("outbound domain is not allowed")
        resolved_addresses = tuple(dict.fromkeys(ipaddress.ip_address(sockaddr[0]) for _family, _type, _proto, _canonname, sockaddr in infos))
        if not resolved_addresses or any(not self._address_allowed(address) for address in resolved_addresses):
            raise OutboundTargetRejected("resolved address is outside allowed ranges")
        return str(resolved_addresses[0])

    @staticmethod
    def validate_trusted_domains(domains) -> tuple[str, ...]:
        """校验由受版本控制 plugin YAML 声明的云 SDK 固定域名后缀。"""
        normalized = tuple(str(value or "").strip().lower().lstrip(".") for value in domains)
        if not normalized or any(
            not value or len(value) > 253 or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", value) or "." not in value for value in normalized
        ):
            raise OutboundTargetRejected("trusted cloud endpoint domains are invalid")
        return normalized

    def _address_allowed(self, address) -> bool:
        return any(address in network for network in self._networks)

    def _domain_allowed(self, host: str) -> bool:
        normalized = host.lower()
        return any(normalized == suffix or normalized.endswith(f".{suffix}") for suffix in self._domains)

    @staticmethod
    def _env_values(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
        raw = os.getenv(name)
        if raw is None:
            return default
        return tuple(item.strip() for item in raw.split(",") if item.strip())
