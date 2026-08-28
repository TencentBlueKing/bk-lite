"""压测 SNMP Engine 同步初始化对调度、超时和事件循环的影响。"""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import resource
import time
from dataclasses import asdict, dataclass

from core.collection.metrics import CollectionMetrics
from core.collection.scheduler import CollectionScheduler
from plugins.inputs.network import snmp_facts


@dataclass(frozen=True)
class BenchmarkResult:
    targets: int
    configured_concurrency: int
    dispatch_quantum: int
    cycle_deadline_seconds: float
    target_timeout_seconds: float
    wall_seconds: float
    cpu_seconds: float
    cpu_percent_of_one_core: float
    max_rss_bytes: int
    max_rss_delta_bytes: int
    peak_asyncio_tasks: int
    peak_live_snmp_engines: int
    completed_timeouts: int
    callback_errors: int
    scheduler_dispatch_total: int
    scheduler_yield_total: int
    target_schedule_wait_p95_seconds: float
    target_schedule_wait_p99_seconds: float
    dispatch_to_started_p99_seconds: float
    snmp_engine_init_p95_seconds: float
    snmp_engine_init_p99_seconds: float
    snmp_collect_to_first_io_p99_seconds: float
    timeout_overshoot_p95_seconds: float
    timeout_overshoot_p99_seconds: float
    timeout_overshoot_max_seconds: float
    event_loop_lag_p95_seconds: float
    event_loop_lag_p99_seconds: float
    event_loop_lag_max_seconds: float
    passed_latency_gates: bool
    milestone_wall_seconds: dict[str, float]
    milestone_timeout_overshoot_p99_seconds: dict[str, float]


class _MetricSink:
    def __init__(self) -> None:
        self.samples: dict[str, list[float]] = {}

    def observe(self, name: str, value: float) -> None:
        self.samples.setdefault(name, []).append(float(value))


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[int((len(ordered) - 1) * fraction)]


def _max_rss_bytes() -> int:
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return value if platform.system() == "Darwin" else value * 1024


async def run_benchmark(
    *,
    targets: int,
    concurrency: int,
    quantum: int,
    target_timeout_seconds: float,
    cycle_deadline_seconds: float,
    milestone_step: int = 0,
) -> BenchmarkResult:
    if targets <= 0 or concurrency <= 0 or target_timeout_seconds <= 0 or cycle_deadline_seconds <= 0:
        raise ValueError("benchmark arguments must be greater than zero")
    if quantum != 1:
        raise ValueError("production dispatch quantum is fixed to one")

    loop = asyncio.get_running_loop()
    callback_errors: list[dict] = []
    previous_exception_handler = loop.get_exception_handler()
    loop.set_exception_handler(lambda _loop, context: callback_errors.append(context))

    scheduler_metrics = CollectionMetrics(sample_capacity=targets)
    collector_metrics = _MetricSink()
    scheduler = CollectionScheduler(max_in_flight=concurrency, metrics=scheduler_metrics)

    real_engine = snmp_facts.SnmpEngine
    real_close = snmp_facts._close_snmp_engine
    real_get = snmp_facts.getCmd
    live_engines = 0
    peak_live_engines = 0
    engine_init_samples: list[float] = []

    def instrumented_engine():
        nonlocal live_engines, peak_live_engines
        started = time.monotonic()
        engine = real_engine()
        engine_init_samples.append(time.monotonic() - started)
        live_engines += 1
        peak_live_engines = max(peak_live_engines, live_engines)
        return engine

    def instrumented_close(engine) -> None:
        nonlocal live_engines
        try:
            real_close(engine)
        finally:
            live_engines = max(0, live_engines - 1)

    async def never_respond(*_args, **_kwargs):
        await asyncio.Future()

    snmp_facts.SnmpEngine = instrumented_engine
    snmp_facts._close_snmp_engine = instrumented_close
    snmp_facts.getCmd = never_respond

    timeout_overshoots: list[float] = []
    completed_timeouts = 0
    milestone_wall_seconds: dict[str, float] = {}
    milestone_timeout_overshoot_p99_seconds: dict[str, float] = {}
    event_loop_lags: list[float] = []
    peak_asyncio_tasks = 0
    stop_monitor = asyncio.Event()

    async def collect_one(_item: int) -> int:
        nonlocal completed_timeouts
        facts = snmp_facts.SnmpFacts(
            {
                "host": "127.0.0.1",
                "version": "v2c",
                "community": "benchmark-only",
                "snmp_port": 161,
                "_runtime_metrics": collector_metrics,
            }
        )
        started = time.monotonic()
        try:
            async with asyncio.timeout(target_timeout_seconds):
                await facts.collect()
        except TimeoutError:
            completed_timeouts += 1
            timeout_overshoots.append(max(0.0, time.monotonic() - started - target_timeout_seconds))
            if milestone_step > 0 and completed_timeouts % milestone_step == 0:
                milestone = str(completed_timeouts)
                milestone_wall_seconds[milestone] = round(time.monotonic() - wall_started, 6)
                milestone_timeout_overshoot_p99_seconds[milestone] = round(
                    _percentile(timeout_overshoots, 0.99),
                    6,
                )
        return _item

    async def monitor() -> None:
        nonlocal peak_asyncio_tasks
        interval = 0.01
        previous = time.monotonic()
        while not stop_monitor.is_set():
            await asyncio.sleep(interval)
            current = time.monotonic()
            event_loop_lags.append(max(0.0, current - previous - interval))
            previous = current
            peak_asyncio_tasks = max(peak_asyncio_tasks, len(asyncio.all_tasks()))

    monitor_task = asyncio.create_task(monitor(), name="snmp-benchmark-monitor")
    rss_before = _max_rss_bytes()
    cpu_started = time.process_time()
    wall_started = time.monotonic()
    try:
        async with asyncio.timeout(cycle_deadline_seconds):
            results = await scheduler.execute("snmp-benchmark", range(targets), collect_one)
        if len(results) != targets:
            raise RuntimeError("scheduler returned an incomplete result set")
    finally:
        wall_seconds = time.monotonic() - wall_started
        cpu_seconds = time.process_time() - cpu_started
        stop_monitor.set()
        try:
            await monitor_task
            await scheduler.shutdown()
        finally:
            loop.set_exception_handler(previous_exception_handler)
            snmp_facts.SnmpEngine = real_engine
            snmp_facts._close_snmp_engine = real_close
            snmp_facts.getCmd = real_get

    snapshot = scheduler_metrics.snapshot()
    first_io = collector_metrics.samples.get("snmp_collect_to_first_io_seconds", [])
    lag_p99 = _percentile(event_loop_lags, 0.99)
    overshoot_p99 = _percentile(timeout_overshoots, 0.99)
    passed_latency_gates = completed_timeouts == targets and not callback_errors and lag_p99 < 0.5 and overshoot_p99 < 1.0
    return BenchmarkResult(
        targets=targets,
        configured_concurrency=concurrency,
        dispatch_quantum=quantum,
        cycle_deadline_seconds=cycle_deadline_seconds,
        target_timeout_seconds=target_timeout_seconds,
        wall_seconds=round(wall_seconds, 6),
        cpu_seconds=round(cpu_seconds, 6),
        cpu_percent_of_one_core=round(cpu_seconds / wall_seconds * 100, 3),
        max_rss_bytes=_max_rss_bytes(),
        max_rss_delta_bytes=max(0, _max_rss_bytes() - rss_before),
        peak_asyncio_tasks=peak_asyncio_tasks,
        peak_live_snmp_engines=peak_live_engines,
        completed_timeouts=completed_timeouts,
        callback_errors=len(callback_errors),
        scheduler_dispatch_total=int(snapshot["scheduler_dispatch_total"]),
        scheduler_yield_total=int(snapshot["scheduler_yield_total"]),
        target_schedule_wait_p95_seconds=round(snapshot.get("target_schedule_wait_seconds_p95", 0.0), 6),
        target_schedule_wait_p99_seconds=round(snapshot.get("target_schedule_wait_seconds_p99", 0.0), 6),
        dispatch_to_started_p99_seconds=round(snapshot.get("target_dispatch_to_started_seconds_p99", 0.0), 6),
        snmp_engine_init_p95_seconds=round(_percentile(engine_init_samples, 0.95), 6),
        snmp_engine_init_p99_seconds=round(_percentile(engine_init_samples, 0.99), 6),
        snmp_collect_to_first_io_p99_seconds=round(_percentile(first_io, 0.99), 6),
        timeout_overshoot_p95_seconds=round(_percentile(timeout_overshoots, 0.95), 6),
        timeout_overshoot_p99_seconds=round(overshoot_p99, 6),
        timeout_overshoot_max_seconds=round(max(timeout_overshoots, default=0.0), 6),
        event_loop_lag_p95_seconds=round(_percentile(event_loop_lags, 0.95), 6),
        event_loop_lag_p99_seconds=round(lag_p99, 6),
        event_loop_lag_max_seconds=round(max(event_loop_lags, default=0.0), 6),
        passed_latency_gates=passed_latency_gates,
        milestone_wall_seconds=milestone_wall_seconds,
        milestone_timeout_overshoot_p99_seconds=milestone_timeout_overshoot_p99_seconds,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targets", type=int, required=True)
    parser.add_argument("--concurrency", type=int)
    parser.add_argument("--quantum", type=int, choices=(1,), default=1)
    parser.add_argument("--target-timeout-seconds", type=float, default=30.0)
    parser.add_argument("--cycle-deadline-seconds", type=float, default=1800.0)
    parser.add_argument("--milestone-step", type=int, default=0)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = asyncio.run(
        run_benchmark(
            targets=args.targets,
            concurrency=args.concurrency or args.targets,
            quantum=args.quantum,
            target_timeout_seconds=args.target_timeout_seconds,
            cycle_deadline_seconds=args.cycle_deadline_seconds,
            milestone_step=args.milestone_step,
        )
    )
    print("SNMP_SCHEDULER_BENCHMARK=" + json.dumps(asdict(result), sort_keys=True))


if __name__ == "__main__":
    main()
