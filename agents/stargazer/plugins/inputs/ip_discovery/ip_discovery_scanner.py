# -- coding: utf-8 --
"""IP 发现 collector：按子网范围 ICMP/TCP 探活，返回活跃 IP（含 best-effort MAC）。"""
import asyncio
import ipaddress
import json

DEFAULT_PORTS = [22, 80, 443, 3389]
CONCURRENCY = 50


class IPDiscoveryScanner:
    def __init__(self, kwargs: dict):
        self.model_id = kwargs.get("model_id", "ip")
        self.scan_method = (kwargs.get("scan_method") or "icmp").lower()
        self.ports = self._normalize_ports(kwargs.get("ports") or DEFAULT_PORTS)
        self.subnets = self._normalize_json_list(kwargs.get("subnets") or [])
        self.targets = self._build_targets(kwargs.get("targets") or [])
        self.timeout = float(kwargs.get("timeout", 2))

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
            try:
                normalized.append(int(port))
            except (TypeError, ValueError):
                continue
        return normalized or DEFAULT_PORTS

    def _build_targets(self, explicit_targets) -> list[dict]:
        targets = []
        for ip in self._normalize_json_list(explicit_targets) if isinstance(explicit_targets, str) else explicit_targets:
            targets.append({"ip": str(ip), "subnet_id": "", "subnet_cidr": ""})

        for subnet in self.subnets:
            if not isinstance(subnet, dict):
                continue
            cidr = str(subnet.get("cidr") or "").strip()
            try:
                network = ipaddress.ip_network(cidr, strict=False)
            except ValueError:
                continue
            reserved = {
                str(item).strip()
                for item in subnet.get("reserved_addresses", [])
                if str(item).strip()
            }
            gateway = str(subnet.get("gateway") or "").strip()
            if gateway:
                reserved.add(gateway)
            for ip in network.hosts():
                ip_text = str(ip)
                if ip_text in reserved:
                    continue
                targets.append(
                    {
                        "ip": ip_text,
                        "subnet_id": str(subnet.get("subnet_id") or ""),
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

    def _read_mac(self, ip: str) -> str:
        """best-effort：仅同二层可得（读 ARP 表）。跨三层返回空。规格 §13.3。"""
        try:
            import subprocess
            out = subprocess.run(["arp", "-n", ip], capture_output=True, text=True, timeout=2).stdout
            for tok in out.split():
                if ":" in tok and len(tok) == 17:
                    return tok
        except Exception:
            pass
        return ""

    async def _probe_one(self, target: dict, sem: asyncio.Semaphore):
        ip = target["ip"]
        async with sem:
            alive = (await self._tcp_alive(ip)) if self.scan_method == "tcp" else (await self._icmp_probe(ip, self.timeout))
        if not alive:
            return None
        if not target.get("subnet_id"):
            return {"ip": ip, "mac": self._read_mac(ip)}
        return {
            "ip_addr": ip,
            "ip_status": "online",
            "subnet_id": target["subnet_id"],
            "subnet_cidr": target["subnet_cidr"],
            "scan_method": self.scan_method,
            "auto_collect": "true",
            "mac": self._read_mac(ip),
        }

    async def list_all_resources(self) -> dict:
        sem = asyncio.Semaphore(CONCURRENCY)
        results = await asyncio.gather(*[self._probe_one(target, sem) for target in self.targets])
        alive = [r for r in results if r]
        return {"success": True, "result": {self.model_id: alive}}
