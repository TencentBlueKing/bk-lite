"""Collection Run 级 Job 节点信息批量加载。"""

from __future__ import annotations

import asyncio
import ipaddress
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextlib import suppress
from typing import Any

from core.logger import logger

NodeInfoLoader = Callable[..., Awaitable[Sequence[Mapping[str, Any]]]]


class RunNodeInfoLookup:
    """在一个 Collection Run 内合并节点信息查询并缓存最终结果。"""

    def __init__(
        self,
        *,
        task_id: str,
        targets: Sequence[str],
        loader: NodeInfoLoader,
        metrics=None,
        collect_task_id: Any = None,
        cloud_region_id: Any = None,
        batch_size: int = 500,
        batch_timeout_seconds: float = 10.0,
        total_timeout_seconds: float = 15.0,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than zero")
        if batch_timeout_seconds <= 0 or total_timeout_seconds <= 0:
            raise ValueError("node info lookup timeouts must be greater than zero")
        self._task_id = str(task_id)
        self._targets = tuple(targets)
        self._initial_ips = tuple(dict.fromkeys(filter(None, (_normalized_ip(item) for item in targets))))
        self._loader = loader
        self._metrics = metrics
        self._collect_task_id = collect_task_id
        self._cloud_region_id = cloud_region_id
        self._batch_size = batch_size
        self._batch_timeout_seconds = batch_timeout_seconds
        self._total_timeout_seconds = total_timeout_seconds
        self._lock = asyncio.Lock()
        self._rpc_lock = asyncio.Lock()
        self._load_task: asyncio.Task[dict[str, dict[str, Any]]] | None = None
        self._extra_tasks: dict[str, asyncio.Task[dict[str, Any] | None]] = {}
        self._results: dict[str, dict[str, Any]] = {}
        self._statuses: dict[str, str] = {}
        self._started_at: float | None = None
        self._deadline: float | None = None
        self._finished_at: float | None = None
        self._cancelled = False
        self._rpc_calls = 0
        self._summary_emitted = False

    async def get(
        self,
        target: str,
        *,
        connect_host: str = "",
    ) -> Mapping[str, Any] | None:
        lookup_ip = _normalized_ip(connect_host) or _normalized_ip(target)
        if not lookup_ip:
            return None
        self._start_budget()

        if self._initial_ips:
            task = self._load_task
            if task is None:
                async with self._lock:
                    if self._load_task is None:
                        self._load_task = asyncio.create_task(
                            self._load_all(),
                            name=f"job-node-info:{self._task_id}",
                        )
                    task = self._load_task
            node_map = await asyncio.shield(task)
            if lookup_ip in self._initial_ips:
                return node_map.get(lookup_ip)

        extra_task = self._extra_tasks.get(lookup_ip)
        if extra_task is None:
            async with self._lock:
                if lookup_ip not in self._extra_tasks:
                    self._extra_tasks[lookup_ip] = asyncio.create_task(
                        self._load_resolved_ip(lookup_ip),
                        name=f"job-node-info-resolved:{self._task_id}",
                    )
                extra_task = self._extra_tasks[lookup_ip]
        return await asyncio.shield(extra_task)

    async def close(self) -> None:
        tasks = [task for task in (self._load_task, *self._extra_tasks.values()) if task is not None]
        for task in tasks:
            if not task.done():
                self._cancelled = True
                task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task
        self._emit_summary()

    async def _load_all(self) -> dict[str, dict[str, Any]]:
        try:
            ips = self._initial_ips
            for offset in range(0, len(ips), self._batch_size):
                batch = ips[offset : offset + self._batch_size]
                remaining = self._remaining_budget()
                if remaining <= 0:
                    self._record_failed(ips[offset:])
                    logger.warning(
                        "event=job_node_info_budget_exhausted task_id=%s remaining_targets=%s",
                        self._task_id,
                        len(ips) - offset,
                    )
                    break
                await self._load_batch(
                    batch,
                    timeout_seconds=min(self._batch_timeout_seconds, remaining),
                    batch_index=str(offset // self._batch_size + 1),
                )
            return dict(self._results)
        finally:
            self._finished_at = time.monotonic()

    async def _load_resolved_ip(self, ip: str) -> dict[str, Any] | None:
        try:
            async with self._rpc_lock:
                if ip in self._statuses:
                    return self._results.get(ip)
                remaining = self._remaining_budget()
                if remaining <= 0:
                    self._record_failed((ip,))
                    logger.warning(
                        "event=job_node_info_budget_exhausted task_id=%s remaining_targets=1",
                        self._task_id,
                    )
                    return None
                await self._load_batch(
                    (ip,),
                    timeout_seconds=min(self._batch_timeout_seconds, remaining),
                    batch_index="resolved",
                )
                return self._results.get(ip)
        finally:
            self._finished_at = time.monotonic()

    async def _load_batch(
        self,
        ips: Sequence[str],
        *,
        timeout_seconds: float,
        batch_index: str,
    ) -> None:
        self._rpc_calls += 1
        self._increment_metric("job_node_info_lookup_rpc_total")
        try:
            async with asyncio.timeout(timeout_seconds):
                nodes = await self._loader(
                    ips,
                    collect_task_id=self._collect_task_id,
                    cloud_region_id=self._cloud_region_id,
                    timeout_seconds=timeout_seconds,
                )
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001 - 查询失败按批次回退 SSH
            self._record_failed(ips)
            logger.warning(
                "event=job_node_info_batch_failed task_id=%s batch_size=%s " "batch_index=%s error_type=%s detail=%s",
                self._task_id,
                len(ips),
                batch_index,
                type(error).__name__,
                str(error)[:200] or "-",
                exc_info=True,
            )
            return

        nodes_by_ip: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for node in nodes:
            if not isinstance(node, Mapping):
                continue
            node_ip = _normalized_ip(node.get("ip"))
            if node_ip in ips:
                nodes_by_ip[node_ip].append(dict(node))
        for ip in ips:
            matching = nodes_by_ip.get(ip, [])
            if len(matching) == 1:
                self._results[ip] = matching[0]
                self._statuses[ip] = "found"
                self._increment_metric("job_node_info_lookup_found_total")
            elif len(matching) > 1:
                self._statuses[ip] = "ambiguous"
                self._increment_metric("job_node_info_lookup_ambiguous_total")
            else:
                self._statuses[ip] = "missing"
                self._increment_metric("job_node_info_lookup_missing_total")
            self._increment_metric("job_node_info_lookup_target_total")

    def _record_failed(self, ips: Sequence[str]) -> None:
        new_failures = 0
        for ip in ips:
            if ip not in self._statuses:
                self._statuses[ip] = "failed"
                new_failures += 1
        if new_failures:
            self._increment_metric("job_node_info_lookup_target_total", new_failures)
            self._increment_metric("job_node_info_lookup_failure_total", new_failures)

    def _start_budget(self) -> None:
        if self._started_at is None:
            self._started_at = time.monotonic()
            self._deadline = self._started_at + self._total_timeout_seconds

    def _remaining_budget(self) -> float:
        if self._deadline is None:
            return 0.0
        return max(0.0, self._deadline - time.monotonic())

    def _emit_summary(self) -> None:
        if self._summary_emitted or self._started_at is None:
            return
        self._summary_emitted = True
        counts = {status: list(self._statuses.values()).count(status) for status in ("found", "missing", "ambiguous", "failed")}
        finished_at = self._finished_at or time.monotonic()
        duration = max(0.0, finished_at - self._started_at)
        self._increment_metric("job_node_info_lookup_total")
        if self._metrics is not None:
            self._metrics.observe("job_node_info_lookup_duration_seconds", duration)
        logger.info(
            "event=job_node_info_lookup task_id=%s targets=%s unique_ips=%s "
            "found=%s missing=%s ambiguous=%s failed_targets=%s rpc_calls=%s "
            "duration_ms=%s status=%s",
            self._task_id,
            len(self._targets),
            len(self._statuses),
            counts["found"],
            counts["missing"],
            counts["ambiguous"],
            counts["failed"],
            self._rpc_calls,
            round(duration * 1000, 2),
            ("cancelled" if self._cancelled else "completed" if counts["failed"] == 0 else "completed_with_errors"),
        )

    def _increment_metric(self, name: str, value: float = 1) -> None:
        if self._metrics is not None:
            self._metrics.increment(name, value)


def _normalized_ip(value: Any) -> str:
    try:
        return str(ipaddress.ip_address(str(value).strip()))
    except ValueError:
        return ""
