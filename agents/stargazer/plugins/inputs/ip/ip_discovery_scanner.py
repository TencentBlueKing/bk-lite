# -- coding: utf-8 --
"""IP 发现 collector：按子网范围 ICMP/TCP 探活，返回活跃 IP（含 best-effort MAC）。"""

import asyncio
import ipaddress
import json
import os
import re

from core.collection.contracts import AccessProbeResult, AccessProbeStatus

DEFAULT_PORTS = [22, 80, 443, 3389]
CONCURRENCY = 50
MAX_PORTS = 64
PROBE_TIMEOUT_SECONDS = 5


class IPDiscoveryScanner:
    def __init__(self, kwargs: dict):
        self.model_id = kwargs.get("model_id", "ip")
        self.scan_method = (kwargs.get("scan_method") or "icmp").lower()
        self.ports = self._normalize_ports(kwargs.get("ports") or DEFAULT_PORTS)
        if len(self.ports) > MAX_PORTS:
            raise ValueError(f"port count exceeds {MAX_PORTS}")
        self.subnets = self._normalize_json_list(kwargs.get("subnets") or [])
        self.max_targets = int(os.getenv("MAX_TARGETS_PER_RUN", "10000"))
        if self.max_targets <= 0:
            raise ValueError("MAX_TARGETS_PER_RUN must be greater than zero")
        self.concurrency = CONCURRENCY
        self.targets = self._build_targets(kwargs.get("targets") or [])
        # 表单 timeout 是整次子网正式采集的框架预算；单 IP 探测使用独立固定上限。
        self.timeout = PROBE_TIMEOUT_SECONDS

    async def probe(self) -> AccessProbeResult:
        """扫描器自身执行有界探测，不在正式扫描前重复扫描目标。"""
        return AccessProbeResult(status=AccessProbeStatus.READY)

    @staticmethod
    def _normalize_json_list(value):
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except (TypeError, ValueError):
                return []
            return parsed if isinstance(parsed, list) else []
        return value if isinstance(value, list) else []

    @classmethod
    def _normalize_ports(cls, value):
        ports = cls._normalize_json_list(value) if isinstance(value, str) else value
        if not isinstance(ports, list):
            return DEFAULT_PORTS
        normalized = []
        for port in ports:
            if isinstance(port, bool):
                raise ValueError("port must be between 1 and 65535")
            if isinstance(port, str):
                port_text = port.strip()
                if not re.fullmatch(r"[+-]?\d+", port_text):
                    raise ValueError("port must be between 1 and 65535")
                port = int(port_text)
            elif not isinstance(port, int):
                raise ValueError("port must be between 1 and 65535")
            if not 1 <= port <= 65535:
                raise ValueError("port must be between 1 and 65535")
            normalized.append(port)
        return normalized or DEFAULT_PORTS

    def _build_targets(self, explicit_targets) -> list[dict]:
        targets = []

        def append(target: dict) -> None:
            if len(targets) >= self.max_targets:
                raise ValueError(f"target count exceeds MAX_TARGETS_PER_RUN={self.max_targets}")
            targets.append(target)

        for ip in self._normalize_json_list(explicit_targets) if isinstance(explicit_targets, str) else explicit_targets:
            append({"ip": str(ip), "subnet_uuid": "", "subnet_cidr": ""})

        for subnet in self.subnets:
            if not isinstance(subnet, dict):
                continue
            cidr = str(subnet.get("cidr") or "").strip()
            try:
                network = ipaddress.ip_network(cidr, strict=False)
            except ValueError:
                continue
            reserved = {str(item).strip() for item in subnet.get("reserved_addresses", []) if str(item).strip()}
            gateway = str(subnet.get("gateway") or "").strip()
            if gateway:
                reserved.add(gateway)
            for ip in network.hosts():
                ip_text = str(ip)
                if ip_text in reserved:
                    continue
                append(
                    {
                        "ip": ip_text,
                        "subnet_uuid": str(subnet.get("subnet_uuid") or ""),
                        "subnet_cidr": str(network),
                    }
                )
        return targets

    async def _tcp_probe(self, ip: str, port: int, timeout: float) -> bool:
        try:
            fut = asyncio.open_connection(ip, port)
            reader, writer = await asyncio.wait_for(fut, timeout=timeout)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            return True
        except Exception:
            return False

    async def _tcp_alive(self, ip: str) -> bool:
        for port in self.ports:
            if await self._tcp_probe(ip, port, self.timeout):
                return True
        return False

    async def _icmp_probe(self, ip: str, timeout: float) -> bool:
        from icmplib import async_ping

        try:
            host = await async_ping(ip, count=1, timeout=timeout, privileged=True)
            return host.is_alive
        except Exception:
            return False

    async def _read_mac(self, ip: str) -> str:
        """best-effort：仅同二层可得（读 ARP 表）。跨三层返回空。规格 §13.3。"""
        process = None
        try:
            process = await asyncio.create_subprocess_exec(
                "arp",
                "-n",
                ip,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _stderr = await asyncio.wait_for(process.communicate(), timeout=2)
            if process.returncode not in (None, 0):
                return ""
            match = re.search(rb"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", stdout)
            return match.group(0).decode("ascii") if match else ""
        except TimeoutError:
            if process is not None:
                process.kill()
                await process.communicate()
        except Exception:
            return ""
        return ""

    async def _probe_one(self, target: dict, sem: asyncio.Semaphore):
        ip = target["ip"]
        async with sem:
            alive = (await self._tcp_alive(ip)) if self.scan_method == "tcp" else (await self._icmp_probe(ip, self.timeout))
            if not alive:
                return None
            mac = await self._read_mac(ip)
        if not target.get("subnet_uuid"):
            return {"ip": ip, "mac": mac}
        return {
            "ip_addr": ip,
            "ip_status": "online",
            "subnet_uuid": target["subnet_uuid"],
            "subnet_cidr": target["subnet_cidr"],
            "scan_method": self.scan_method,
            "auto_collect": "true",
            "mac": mac,
        }

    async def list_all_resources(self) -> dict:
        if not self.targets:
            return {"success": True, "result": {self.model_id: []}}
        sem = asyncio.Semaphore(self.concurrency)
        results = [None] * len(self.targets)
        next_index = 0
        index_lock = asyncio.Lock()

        async def worker() -> None:
            nonlocal next_index
            while True:
                async with index_lock:
                    if next_index >= len(self.targets):
                        return
                    index = next_index
                    next_index += 1
                results[index] = await self._probe_one(self.targets[index], sem)

        workers = [asyncio.create_task(worker()) for _ in range(min(self.concurrency, len(self.targets)))]
        await asyncio.gather(*workers)
        alive = [r for r in results if r]
        return {"success": True, "result": {self.model_id: alive}}
