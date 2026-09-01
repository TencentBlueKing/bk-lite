#!/usr/bin/env python3
"""Stargazer 瞬时 Run/API 与目标调度突发压测。

默认执行不依赖 Redis/NATS 的目标调度矩阵，用于验证 1000/2500/5000
目标在 160 全局窗口下的 100/30/30 公平份额，以及 100/20/20 后追加
configuration 借满 160 的语义。

``--mode api`` 面向已部署的压测环境，在一次事件循环切片中创建全部 HTTP
提交并对 accepted/duplicate/busy/retryable/5xx/timeout 做终态对账。它会触发真实
采集，只应连接隔离的压测 Stargazer。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import resource
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.collection.enums import WorkloadClass  # noqa: E402
from core.collection.scheduler import CollectionScheduler  # noqa: E402

PRODUCTION_WEIGHTS = {
    WorkloadClass.CONFIGURATION: 100,
    WorkloadClass.MONITORING: 30,
    WorkloadClass.NETWORK_TOPOLOGY: 30,
}


def _percentile(values: Iterable[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    return ordered[round((len(ordered) - 1) * fraction)]


def _max_rss_bytes() -> int:
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return value if platform.system() == "Darwin" else value * 1024


@dataclass(frozen=True)
class SchedulerBurstResult:
    burst: int
    shape: str
    repeat: int
    completed: int
    peak_active: int
    first_phase_active: dict[str, int]
    borrowed_phase_active: dict[str, int]
    first_phase_idle_slots: int
    wall_seconds: float
    targets_per_second: float
    event_loop_lag_p99_seconds: float
    event_loop_lag_max_seconds: float
    peak_asyncio_tasks: int
    max_rss_delta_bytes: int
    passed: bool


async def _wait_for_active(scheduler: CollectionScheduler, expected: int, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while scheduler.active < expected and time.monotonic() < deadline:
        await asyncio.sleep(0)
    if scheduler.active != expected:
        raise RuntimeError(f"active target mismatch: expected={expected} actual={scheduler.active}")


def _active_snapshot(scheduler: CollectionScheduler) -> dict[str, int]:
    return {workload.value: int(scheduler.active_by_workload[workload]) for workload in WorkloadClass}


async def run_scheduler_burst(*, burst: int, shape: str, repeat: int) -> SchedulerBurstResult:
    if burst < 160:
        raise ValueError("burst must be at least 160")
    if shape not in {"100/30/30", "100/20/20"}:
        raise ValueError(f"unsupported shape: {shape}")

    scheduler = CollectionScheduler(
        max_in_flight=160,
        workload_weights=PRODUCTION_WEIGHTS,
    )
    release = asyncio.Event()
    stop_monitor = asyncio.Event()
    event_loop_lags: list[float] = []
    peak_asyncio_tasks = 0

    async def handle(item: int) -> int:
        await release.wait()
        # 强制经历一次公平调度，避免本地空函数把排空吞吐测成同步循环速度。
        await asyncio.sleep(0)
        return item

    async def monitor() -> None:
        nonlocal peak_asyncio_tasks
        interval = 0.005
        previous = time.monotonic()
        while not stop_monitor.is_set():
            await asyncio.sleep(interval)
            current = time.monotonic()
            event_loop_lags.append(max(0.0, current - previous - interval))
            previous = current
            peak_asyncio_tasks = max(peak_asyncio_tasks, len(asyncio.all_tasks()))

    monitor_task = asyncio.create_task(monitor(), name="collection-burst-monitor")
    rss_before = _max_rss_bytes()
    started = time.monotonic()
    runs: list[asyncio.Task] = []
    first_phase_active: dict[str, int] = {}
    borrowed_phase_active: dict[str, int] = {}
    first_phase_idle_slots = 0
    try:
        if shape == "100/30/30":
            monitoring_count = max(30, round(burst * 30 / 160))
            topology_count = max(30, round(burst * 30 / 160))
            configuration_count = burst - monitoring_count - topology_count
            runs = [
                asyncio.create_task(
                    scheduler.execute("configuration", range(configuration_count), handle),
                    name="burst-configuration",
                ),
                asyncio.create_task(
                    scheduler.execute(
                        "monitoring",
                        range(monitoring_count),
                        handle,
                        workload=WorkloadClass.MONITORING,
                    ),
                    name="burst-monitoring",
                ),
                asyncio.create_task(
                    scheduler.execute(
                        "topology",
                        range(topology_count),
                        handle,
                        workload=WorkloadClass.NETWORK_TOPOLOGY,
                    ),
                    name="burst-topology",
                ),
            ]
            await _wait_for_active(scheduler, 160)
            first_phase_active = _active_snapshot(scheduler)
            borrowed_phase_active = dict(first_phase_active)
        else:
            # 第一阶段严格只提供 100/20/20 个目标，20 个槽必须是真空闲。
            runs = [
                asyncio.create_task(
                    scheduler.execute("configuration", range(100), handle),
                    name="burst-configuration-initial",
                ),
                asyncio.create_task(
                    scheduler.execute(
                        "monitoring",
                        range(20),
                        handle,
                        workload=WorkloadClass.MONITORING,
                    ),
                    name="burst-monitoring",
                ),
                asyncio.create_task(
                    scheduler.execute(
                        "topology",
                        range(20),
                        handle,
                        workload=WorkloadClass.NETWORK_TOPOLOGY,
                    ),
                    name="burst-topology",
                ),
            ]
            await _wait_for_active(scheduler, 140)
            first_phase_active = _active_snapshot(scheduler)
            first_phase_idle_slots = 160 - scheduler.active
            runs.append(
                asyncio.create_task(
                    scheduler.execute("configuration-borrow", range(burst - 140), handle),
                    name="burst-configuration-borrow",
                )
            )
            await _wait_for_active(scheduler, 160)
            borrowed_phase_active = _active_snapshot(scheduler)

        # 给监控协程一个完整采样周期，记录第一波真实 Task/lag 峰值。
        await asyncio.sleep(0.01)
        release.set()
        results = await asyncio.gather(*runs)
        completed = sum(len(items) for items in results)
    finally:
        release.set()
        if runs:
            await asyncio.gather(*runs, return_exceptions=True)
        await scheduler.shutdown()
        stop_monitor.set()
        await monitor_task

    wall_seconds = time.monotonic() - started
    expected_first = (
        {"configuration": 100, "monitoring": 30, "network_topology": 30}
        if shape == "100/30/30"
        else {"configuration": 100, "monitoring": 20, "network_topology": 20}
    )
    expected_borrowed = expected_first if shape == "100/30/30" else {"configuration": 120, "monitoring": 20, "network_topology": 20}
    lag_p99 = _percentile(event_loop_lags, 0.99)
    passed = (
        completed == burst
        and scheduler.peak <= 160
        and first_phase_active == expected_first
        and borrowed_phase_active == expected_borrowed
        and first_phase_idle_slots == (20 if shape == "100/20/20" else 0)
        and lag_p99 < 1.0
    )
    return SchedulerBurstResult(
        burst=burst,
        shape=shape,
        repeat=repeat,
        completed=completed,
        peak_active=scheduler.peak,
        first_phase_active=first_phase_active,
        borrowed_phase_active=borrowed_phase_active,
        first_phase_idle_slots=first_phase_idle_slots,
        wall_seconds=round(wall_seconds, 6),
        targets_per_second=round(completed / wall_seconds, 2),
        event_loop_lag_p99_seconds=round(lag_p99, 6),
        event_loop_lag_max_seconds=round(max(event_loop_lags, default=0.0), 6),
        peak_asyncio_tasks=peak_asyncio_tasks,
        max_rss_delta_bytes=max(0, _max_rss_bytes() - rss_before),
        passed=passed,
    )


async def run_scheduler_matrix(args: argparse.Namespace) -> dict[str, object]:
    results = []
    for repeat in range(1, args.repeats + 1):
        for burst in args.bursts:
            for shape in ("100/30/30", "100/20/20"):
                result = await run_scheduler_burst(burst=burst, shape=shape, repeat=repeat)
                results.append(asdict(result))
    return {
        "mode": "scheduler",
        "global_concurrency": 160,
        "production_weights": {key.value: value for key, value in PRODUCTION_WEIGHTS.items()},
        "results": results,
        "passed": all(item["passed"] for item in results),
    }


async def run_api_burst(args: argparse.Namespace, burst: int, repeat: int) -> dict[str, object]:
    try:
        import httpx
    except ImportError as exc:  # pragma: no cover - only relevant in stripped runtime images
        raise RuntimeError("httpx is required for --mode api") from exc

    limits = httpx.Limits(max_connections=args.http_connections, max_keepalive_connections=args.http_connections)
    timeout = httpx.Timeout(args.http_timeout)
    latencies: list[float] = []
    categories = {name: 0 for name in ("accepted", "duplicate_active", "busy", "retryable", "5xx", "timeout", "other")}
    task_ids: list[str] = []

    async with httpx.AsyncClient(base_url=args.base_url, limits=limits, timeout=timeout) as client:

        async def submit(index: int) -> None:
            request_started = time.monotonic()
            try:
                response = await client.get(
                    args.api_path,
                    headers={
                        "cmdbmodel_id": args.model_id,
                        "cmdbplugin_name": args.plugin_name,
                        "cmdbhosts": f"{args.target_prefix}.{index // 256}.{index % 256}",
                        "cmdbexecutor_type": args.executor_type,
                        "cmdbcollect_task_id": f"burst-{repeat}-{index}",
                    },
                )
            except httpx.TimeoutException:
                categories["timeout"] += 1
                return
            except httpx.RequestError:
                categories["retryable"] += 1
                return
            finally:
                latencies.append(time.monotonic() - request_started)

            status = response.headers.get("x-task-status", "")
            if status in {"accepted", "duplicate_active", "busy"}:
                categories[status] += 1
            elif response.status_code in {429, 503}:
                categories["retryable"] += 1
            elif response.status_code >= 500:
                categories["5xx"] += 1
            else:
                categories["other"] += 1
            task_id = response.headers.get("x-task-id")
            if task_id:
                task_ids.append(task_id)

        started = time.monotonic()
        submissions = [asyncio.create_task(submit(index)) for index in range(burst)]
        task_creation_seconds = time.monotonic() - started
        await asyncio.gather(*submissions)
        wall_seconds = time.monotonic() - started

    classified = sum(categories.values())
    return {
        "burst": burst,
        "repeat": repeat,
        "task_creation_seconds": round(task_creation_seconds, 6),
        "wall_seconds": round(wall_seconds, 6),
        "requests_per_second": round(burst / wall_seconds, 2),
        "latency_p50_seconds": round(statistics.median(latencies), 6) if latencies else 0,
        "latency_p95_seconds": round(_percentile(latencies, 0.95), 6),
        "latency_p99_seconds": round(_percentile(latencies, 0.99), 6),
        "latency_max_seconds": round(max(latencies, default=0.0), 6),
        "categories": categories,
        "classified": classified,
        "unique_task_ids": len(set(task_ids)),
        "instant_submission_window_met": task_creation_seconds <= 1.0,
        "passed_accounting": classified == burst and categories["5xx"] == 0 and categories["timeout"] == 0,
    }


async def run_api_matrix(args: argparse.Namespace) -> dict[str, object]:
    results = []
    for repeat in range(1, args.repeats + 1):
        for burst in args.bursts:
            results.append(await run_api_burst(args, burst, repeat))
    return {
        "mode": "api",
        "base_url": args.base_url,
        "warning": "requests trigger real collection; use an isolated load-test Stargazer",
        "results": results,
        "passed": all(item["passed_accounting"] for item in results),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("scheduler", "api"), default="scheduler")
    parser.add_argument("--bursts", nargs="+", type=int, default=(1000, 2500, 5000))
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--base-url", default="http://127.0.0.1:8083")
    parser.add_argument("--api-path", default="/api/collect/collect_info")
    parser.add_argument("--http-connections", type=int, default=500)
    parser.add_argument("--http-timeout", type=float, default=10.0)
    parser.add_argument("--model-id", default="host")
    parser.add_argument("--plugin-name", default="host_info")
    parser.add_argument("--executor-type", default="job")
    parser.add_argument("--target-prefix", default="198.18")
    return parser


async def async_main(args: argparse.Namespace) -> int:
    if args.repeats <= 0 or any(burst <= 0 for burst in args.bursts):
        raise ValueError("bursts and repeats must be greater than zero")
    report = await (run_scheduler_matrix(args) if args.mode == "scheduler" else run_api_matrix(args))
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(async_main(build_parser().parse_args())))
