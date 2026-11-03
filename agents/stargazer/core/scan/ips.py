from __future__ import annotations

import ipaddress
from typing import Iterable, Mapping

from plugins.base_utils import expand_ip_range


def expand_scan_hosts(ip_ranges: Iterable[Mapping[str, str] | str] | None) -> list[str]:
    hosts: list[str] = []
    seen: set[str] = set()
    for item in ip_ranges or []:
        begin = end = ""
        if isinstance(item, str):
            raw = item.strip()
            if "-" in raw:
                begin, end = [part.strip() for part in raw.split("-", 1)]
            else:
                begin = end = raw
        elif isinstance(item, dict):
            begin = str(item.get("begin") or item.get("start") or "").strip()
            end = str(item.get("end") or begin).strip()
        if not begin:
            continue
        try:
            if end and end != begin:
                expanded = expand_ip_range(f"{begin}-{end}")
            else:
                ipaddress.IPv4Address(begin)
                expanded = [begin]
        except Exception:
            continue
        for host in expanded:
            if host in seen:
                continue
            seen.add(host)
            hosts.append(host)
    return hosts
