# -- coding: utf-8 --
"""IP 发现 collector：按 scan_method 对 targets 并发探活，返回活跃 IP（含 best-effort MAC）。规格 §13.2/§13.3。"""
import asyncio

DEFAULT_PORTS = [22, 80, 443, 3389]
CONCURRENCY = 50


class IPDiscoveryScanner:
    def __init__(self, kwargs: dict):
        self.model_id = kwargs.get("model_id", "ip")
        self.scan_method = (kwargs.get("scan_method") or "icmp").lower()
        self.ports = kwargs.get("ports") or DEFAULT_PORTS
        self.targets = kwargs.get("targets") or []
        self.timeout = float(kwargs.get("timeout", 2))

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

    async def _probe_one(self, ip: str, sem: asyncio.Semaphore):
        async with sem:
            alive = (await self._tcp_alive(ip)) if self.scan_method == "tcp" else (await self._icmp_probe(ip, self.timeout))
        if not alive:
            return None
        return {"ip": ip, "mac": self._read_mac(ip)}

    async def list_all_resources(self) -> dict:
        sem = asyncio.Semaphore(CONCURRENCY)
        results = await asyncio.gather(*[self._probe_one(ip, sem) for ip in self.targets])
        alive = [r for r in results if r]
        return {"success": True, "result": {self.model_id: alive}}
