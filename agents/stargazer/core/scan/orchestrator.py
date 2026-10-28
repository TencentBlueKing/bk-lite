from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Mapping, Sequence

from core.collection.enums import WorkloadClass
from core.scan.events import scan_event
from core.scan.ips import expand_scan_hosts
from core.scan.process_match import match_process_fingerprints
from core.scan.tcp_probe import probe_tcp

ListProcessesFn = Callable[[str], Awaitable[list[str]] | list[str]]
CollectFn = Callable[[dict[str, Any], Sequence[Mapping[str, Any]]], Awaitable[dict[str, Any]] | dict[str, Any]]
ProbeFn = Callable[..., Awaitable[bool]]


@dataclass
class ScanDiscoverRequest:
    execution_id: Any
    ip_ranges: list
    port_fingerprints: list[dict[str, Any]] = field(default_factory=list)
    process_fingerprints: list[dict[str, Any]] = field(default_factory=list)
    host_login: Mapping[str, Any] | None = None
    collect_credentials: Mapping[str, Any] | None = None
    credential_result_subject: str = "receive_scan_credential_result"
    access_point: list = field(default_factory=list)
    skip_hosts: list[str] = field(default_factory=list)
    workload_class: WorkloadClass = WorkloadClass.SCAN

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ScanDiscoverRequest:
        data = dict(payload or {})
        host_login = data.get("host_login")
        if host_login == {} or host_login is False:
            host_login = None
        skip_hosts = [str(item).strip() for item in (data.get("skip_hosts") or []) if str(item).strip()]
        return cls(
            execution_id=data.get("execution_id"),
            ip_ranges=list(data.get("ip_ranges") or []),
            port_fingerprints=[dict(item) for item in (data.get("port_fingerprints") or []) if isinstance(item, dict)],
            process_fingerprints=[dict(item) for item in (data.get("process_fingerprints") or []) if isinstance(item, dict)],
            host_login=host_login if isinstance(host_login, dict) else None,
            collect_credentials=data.get("collect_credentials") if isinstance(data.get("collect_credentials"), dict) else None,
            credential_result_subject=str(data.get("credential_result_subject") or "receive_scan_credential_result"),
            access_point=list(data.get("access_point") or []),
            skip_hosts=skip_hosts,
        )

    @property
    def hosts(self) -> list[str]:
        return expand_scan_hosts(self.ip_ranges)

    @property
    def ports(self) -> list[int]:
        ports = []
        seen = set()
        for item in self.port_fingerprints:
            try:
                port = int(item.get("port"))
            except (TypeError, ValueError):
                continue
            if port <= 0 or port in seen:
                continue
            seen.add(port)
            ports.append(port)
        return ports


class ScanOrchestrator:
    def __init__(
        self,
        scheduler,
        publisher,
        *,
        probe: ProbeFn = probe_tcp,
        list_processes: ListProcessesFn | None = None,
        collect_plugin: CollectFn | None = None,
    ) -> None:
        self._scheduler = scheduler
        self._publisher = publisher
        self._probe = probe
        self._list_processes = list_processes
        self._collect_plugin = collect_plugin

    async def run(self, request: ScanDiscoverRequest) -> dict[str, Any]:
        hosts = request.hosts
        hits: list[dict[str, Any]] = []

        async def probe_host(host: str) -> str:
            for port in request.ports:
                opened = await self._probe(host, port)
                if not opened:
                    continue
                for fingerprint in request.port_fingerprints:
                    try:
                        fingerprint_port = int(fingerprint.get("port"))
                    except (TypeError, ValueError):
                        continue
                    if fingerprint_port != port:
                        continue
                    target_type = str(fingerprint.get("target_type") or "").strip()
                    if not target_type:
                        continue
                    event = scan_event(
                        execution_id=request.execution_id,
                        host=host,
                        port=port,
                        target_type=target_type,
                        stage="port",
                    )
                    await self._publisher.publish(event)
                    hits.append({"host": host, "port": port, "target_type": target_type})
            return host

        if hosts and request.ports:
            await self._scheduler.execute(
                f"scan-port:{request.execution_id}",
                hosts,
                probe_host,
                workload=WorkloadClass.SCAN,
                capacity_group="scan",
            )

        logged_in_hosts: set[str] = set()
        if request.host_login and request.process_fingerprints and self._list_processes is not None:
            listed_hosts: set[str] = set()
            process_hosts = _process_hosts(hits, request.skip_hosts)

            async def match_host(host: str) -> str:
                if host in listed_hosts:
                    return host
                listed_hosts.add(host)
                command_lines = await _maybe_await(self._list_processes(host))
                if command_lines:
                    logged_in_hosts.add(host)
                matches = match_process_fingerprints(command_lines or [], request.process_fingerprints)
                for match in matches:
                    port = _port_for_type(request.port_fingerprints, match["target_type"], host, hits)
                    event = scan_event(
                        execution_id=request.execution_id,
                        host=host,
                        port=port,
                        target_type=match["target_type"],
                        stage="process",
                    )
                    await self._publisher.publish(event)
                    hits.append({"host": host, "port": port, "target_type": match["target_type"]})
                return host

            if process_hosts:
                await self._scheduler.execute(
                    f"scan-process:{request.execution_id}",
                    process_hosts,
                    match_host,
                    workload=WorkloadClass.SCAN,
                    capacity_group="scan_job",
                )

        collect_credentials = request.collect_credentials or {}
        if collect_credentials.get("host") and self._collect_plugin is not None:
            _append_host_collect_targets(hits, logged_in_hosts, request.skip_hosts)
        if collect_credentials and self._collect_plugin is not None:
            seen = set()
            unique_hits = []
            for hit in hits:
                key = (hit["host"], hit["port"], hit["target_type"])
                if key in seen:
                    continue
                seen.add(key)
                unique_hits.append(hit)

            async def collect_hit(hit: dict[str, Any]) -> dict[str, Any]:
                pool = collect_credentials.get(hit["target_type"]) or []
                if not pool:
                    return hit
                try:
                    result = await _maybe_await(self._collect_plugin(hit, pool))
                    status = "success" if (result or {}).get("success", True) else "failed"
                    error_code = str((result or {}).get("error_code") or "")
                except Exception:
                    status = "failed"
                    error_code = "collect_failed"
                    result = {}
                event = scan_event(
                    execution_id=request.execution_id,
                    host=hit["host"],
                    port=hit["port"],
                    target_type=hit["target_type"],
                    stage="collect",
                    status=status,
                    credential_id=str((pool[0] or {}).get("credential_id") or "") if pool else "",
                    error_code=error_code,
                    snapshot=(result or {}).get("snapshot") or {"host": hit["host"], "port": hit["port"]},
                )
                await self._publisher.publish(event)
                return hit

            await self._scheduler.execute(
                f"scan-collect:{request.execution_id}",
                unique_hits,
                collect_hit,
                workload=WorkloadClass.SCAN,
                capacity_group="scan",
            )

        return {"hosts": hosts, "hits": hits, "workload_class": request.workload_class}


def _skip_set(skip_hosts) -> set[str]:
    return {str(host).strip() for host in (skip_hosts or []) if str(host).strip()}


def _process_hosts(hits: list[dict[str, Any]], skip_hosts) -> list[str]:
    skip = _skip_set(skip_hosts)
    hosts: list[str] = []
    seen: set[str] = set()
    for hit in hits:
        host = str(hit.get("host") or "").strip()
        if not host or host in skip or host in seen:
            continue
        seen.add(host)
        hosts.append(host)
    return hosts


def _append_host_collect_targets(hits: list[dict[str, Any]], logged_in_hosts: set[str], skip_hosts) -> None:
    skip = _skip_set(skip_hosts)
    existing = {(str(hit.get("host") or ""), str(hit.get("target_type") or "")) for hit in hits}
    candidates = {str(hit.get("host") or "").strip() for hit in hits}
    candidates.update(str(host).strip() for host in logged_in_hosts)
    for host in sorted(host for host in candidates if host and host not in skip):
        if (host, "host") in existing:
            continue
        hits.append({"host": host, "port": 22, "target_type": "host"})
        existing.add((host, "host"))


def _port_for_type(port_fingerprints, target_type: str, host: str, hits: list[dict[str, Any]]) -> int:
    for hit in hits:
        if hit.get("host") == host and hit.get("target_type") == target_type:
            return int(hit.get("port") or 0)
    for fingerprint in port_fingerprints:
        if str(fingerprint.get("target_type") or "") == target_type:
            try:
                return int(fingerprint.get("port") or 0)
            except (TypeError, ValueError):
                return 0
    return 0


async def _maybe_await(value):
    if hasattr(value, "__await__"):
        return await value
    return value
