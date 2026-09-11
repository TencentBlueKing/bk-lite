#!/usr/bin/env python3
"""日志形状的有界发布压测；模拟采集结果与外部 ACK，真实执行发布/截止链路。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from collections import Counter
from dataclasses import replace
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get("STARGAZER_BENCHMARK_ROOT", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(PROJECT_ROOT))

from core.collection.contracts import CollectOutcome, CollectOutcomeStatus, PreflightResult, PreflightStatus, TargetExecutorSettings  # noqa: E402
from core.collection.executor import TargetCollectionExecutor  # noqa: E402
from core.collection.metrics import CollectionMetrics  # noqa: E402
from core.collection.result_delivery import ResultDeliveryCoordinator  # noqa: E402
from core.collection.result_publisher import BufferedResultPublisher, NatsResultPublisher  # noqa: E402
from core.collection.scheduler import CollectionScheduler  # noqa: E402
from core.infra import nats_utils  # noqa: E402
from core.infra.event_loop_monitor import EventLoopLagMonitor  # noqa: E402
from core.infra.jetstream_publish_window import JetStreamMessage, JetStreamPublishWindow, JetStreamPublishWindowSettings  # noqa: E402

from scripts.benchmark_jetstream_publisher import _peak_rss_mib, _request_and_lease, network_results  # noqa: E402


class DelayedJetStream:
    """只有服务边界是替身；不连接真实 broker，不代表磁盘/网络实测。"""

    def __init__(self, delay, *, fail_every=0, credit_pause_seconds=0):
        self.delay = delay
        self.fail_every = fail_every
        self.count = 0
        self.pending = 0
        self.peak = 0
        self.credit_pause_seconds = credit_pause_seconds

    async def publish_async(self, subject, payload, *, headers, **kwargs):
        assert headers["Nats-Msg-Id"]
        assert payload
        self.count += 1
        sequence = self.count
        self.pending += 1
        self.peak = max(self.peak, self.pending)
        future = asyncio.get_running_loop().create_future()

        def confirm():
            if not future.done():
                if self.fail_every and sequence % self.fail_every == 0:
                    future.set_exception(TimeoutError("injected PubAck timeout"))
                else:
                    future.set_result(None)

        delay = self.credit_pause_seconds if subject == "benchmark.credit-holder" else self.delay
        handle = asyncio.get_running_loop().call_later(delay, confirm)

        def finished(_future):
            handle.cancel()
            self.pending -= 1

        future.add_done_callback(finished)
        return future


async def run_scenario(args):
    if args.pipeline == "run":
        return await run_pipeline_scenario(args)
    os.environ["NATS_METRICS_JETSTREAM_ENABLED"] = "true"
    os.environ["NATS_JS_PUBLISH_MAX_PENDING"] = "256"
    os.environ["NATS_JS_PUBLISH_MAX_PENDING_PER_CALL"] = "64"
    os.environ["METRICS_ENCODE_WORKERS"] = "2"
    metrics = CollectionMetrics(sample_capacity=args.targets)
    jetstream = DelayedJetStream(args.ack_ms / 1000, fail_every=args.fail_every)
    window = JetStreamPublishWindow(lambda: jetstream, settings=JetStreamPublishWindowSettings(max_pending_messages_per_call=64))
    original_window = nats_utils._metrics_js_window
    nats_utils._metrics_js_window = window
    publisher = BufferedResultPublisher(NatsResultPublisher(metrics=metrics), capacity=args.concurrency, worker_count=4, metrics=metrics)
    deliveries = []
    for run in range(args.runs):
        request, lease = _request_and_lease(task_id=f"load-{run}", plugin_ref="network", targets=("synthetic",))
        deliveries.append(
            ResultDeliveryCoordinator(
                publisher=publisher,
                settings=TargetExecutorSettings(publish_total_timeout_seconds=args.deadline),
                metrics=metrics,
                request=request,
                lease=lease,
                log_identity=f"load-{run}",
                failure_log_limit=0,
            )
        )
    indices = iter(range(args.targets))
    results = Counter()
    small_latency = []
    large_latency = []
    first_send_wait = []
    peak_tasks = 0
    active = 0
    peak_active = 0
    started = time.monotonic()
    cpu_started = time.process_time()
    lag = EventLoopLagMonitor(interval_seconds=0.01)
    lag.start()

    async def collect_and_publish():
        nonlocal active, peak_active, peak_tasks
        for index in indices:
            # 与采集执行器相同：先取得 payload 额度才允许生成结果。
            permit = await publisher.reserve_payload()
            active += 1
            peak_active = max(peak_active, active)
            try:
                await asyncio.sleep(args.collection_ms / 1000)
                large = index < args.large_targets
                result = replace(
                    next(network_results(devices=1, lines_per_device=args.large_lines if large else args.small_lines)), target=f"synthetic-{index}"
                )
                delivery = deliveries[index % args.runs]
                pending = await delivery.enqueue(index, result, payload_permit=permit)
                del result
                pending = replace(pending, result=None)
                peak_tasks = max(peak_tasks, len(asyncio.all_tasks()))
                try:
                    _, status, _code = await delivery.finish(pending)
                except Exception as error:
                    status = f"exception:{type(error).__name__}"
                elapsed = time.monotonic() - pending.started_at
                (large_latency if large else small_latency).append(elapsed)
                first_send_wait.append(pending.receipt.queue_residence_seconds)
                results[status] += 1
            finally:
                active -= 1

    try:
        await asyncio.gather(*(collect_and_publish() for _ in range(args.concurrency)))
        await publisher.shutdown(grace_seconds=5)
    finally:
        await publisher.shutdown(grace_seconds=0.1)
        await lag.stop()
        nats_utils._metrics_js_window = original_window
    elapsed = time.monotonic() - started
    snapshot = window.snapshot()

    def percentile(values):
        return round(sorted(values)[int((len(values) - 1) * 0.99)], 4) if values else 0

    return {
        "warning": "synthetic collection and PubAck; NOT live SNMP/NATS/CMDB replay",
        "settings": vars(args),
        "elapsed_seconds": round(elapsed, 4),
        "cpu_seconds": round(time.process_time() - cpu_started, 4),
        "peak_rss_mib": _peak_rss_mib(),
        "terminal_counts": dict(results),
        "confirmed_lines": snapshot.confirmed_total,
        "expected_lines": args.large_targets * args.large_lines + (args.targets - args.large_targets) * args.small_lines,
        "small_p99_seconds": percentile(small_latency),
        "large_p99_seconds": percentile(large_latency),
        "first_send_wait_p99_seconds": percentile(first_send_wait),
        "event_loop_lag_p99_seconds": round(lag.p99_seconds, 4),
        "peak_active_targets": peak_active,
        "peak_payloads": publisher.peak_pending_payloads,
        "peak_pending_messages": snapshot.peak_pending_messages,
        "peak_async_tasks": peak_tasks,
        "remaining_payloads": publisher.pending_payloads,
        "remaining_messages": snapshot.pending_messages,
        "remaining_bytes": snapshot.pending_bytes,
        "remaining_sdk_futures": jetstream.pending,
        "deadline_expired": snapshot.deadline_expired_total,
        "retries": snapshot.retry_total,
    }


async def run_pipeline_scenario(args):
    """真实调度/执行/终态汇总；仅采集插件、网络探测、外部 SDK 为替身。"""
    os.environ["NATS_METRICS_JETSTREAM_ENABLED"] = "true"
    os.environ["NATS_JS_PUBLISH_MAX_PENDING"] = "256"
    os.environ["NATS_JS_PUBLISH_MAX_PENDING_PER_CALL"] = "64"
    os.environ["METRICS_ENCODE_WORKERS"] = "2"
    metrics = CollectionMetrics(sample_capacity=args.targets, sample_window_seconds=3600)
    jetstream = DelayedJetStream(args.ack_ms / 1000, fail_every=args.fail_every, credit_pause_seconds=args.credit_pause_seconds)
    window = JetStreamPublishWindow(
        lambda: jetstream,
        settings=JetStreamPublishWindowSettings(max_pending_messages_per_call=64, puback_timeout_seconds=max(30, args.credit_pause_seconds + 5)),
    )
    original_window = nats_utils._metrics_js_window
    nats_utils._metrics_js_window = window
    small_latency, large_latency, first_send_wait = [], [], []

    class MeasuredPublisher(BufferedResultPublisher):
        async def enqueue(self, request, result, lease, **options):
            index = int(result.target.rsplit("-", 1)[1])
            started = time.monotonic()
            receipt = await super().enqueue(request, result, lease, **options)

            def terminal(_completion):
                (large_latency if index < args.large_targets else small_latency).append(time.monotonic() - started)
                first_send_wait.append(receipt.queue_residence_seconds)

            receipt.add_done_callback(terminal)
            return receipt

    publisher = MeasuredPublisher(NatsResultPublisher(metrics=metrics), capacity=args.concurrency, worker_count=4, metrics=metrics)
    scheduler = CollectionScheduler(max_in_flight=args.concurrency)
    collected = 0
    first_wave = asyncio.Event()

    class Preflight:
        async def check(self, *positional, **options):
            return PreflightResult(status=PreflightStatus.REACHABLE)

    class Plugin:
        async def collect(self, target, credential, context):
            nonlocal collected
            collected += 1
            if collected >= min(args.concurrency, args.targets):
                first_wave.set()
            await first_wave.wait()
            await asyncio.sleep(args.collection_ms / 1000)
            index = int(target.rsplit("-", 1)[1])
            result = next(network_results(devices=1, lines_per_device=args.large_lines if index < args.large_targets else args.small_lines))
            return CollectOutcome(status=CollectOutcomeStatus.SUCCESS, value=result.value)

    executor = TargetCollectionExecutor(
        preflight=Preflight(),
        plugin=Plugin(),
        publisher=publisher,
        scheduler=scheduler,
        metrics=metrics,
        settings=TargetExecutorSettings(
            max_active_targets=args.concurrency, target_task_window=args.concurrency, publish_total_timeout_seconds=args.deadline
        ),
    )
    before = set(asyncio.all_tasks())
    peak_tasks = 0

    async def sample():
        nonlocal peak_tasks
        while True:
            peak_tasks = max(peak_tasks, len(asyncio.all_tasks()))
            await asyncio.sleep(0.05)  # 低频采样，避免长时间信贷等待的监测开销主导 CPU 指标。

    sampler = asyncio.create_task(sample())
    lag = EventLoopLagMonitor(interval_seconds=0.01)
    lag.start()
    holder = None
    holder_count = 256 if args.credit_pause_seconds else 0
    started, cpu_started = time.monotonic(), time.process_time()
    try:
        if holder_count:
            # 4 个窗口各占 64 条信贷，随后真实 Run 在同一全局窗口等待恢复。
            holder = asyncio.gather(
                *(
                    window.publish("benchmark.credit-holder", [JetStreamMessage(b"benchmark-holder", f"holder-{batch}-{i}") for i in range(64)])
                    for batch in range(4)
                )
            )
            while jetstream.pending < holder_count:
                await asyncio.sleep(0)
        runs = []
        for run in range(args.runs):
            request, lease = _request_and_lease(
                task_id=f"pipeline-{run}", plugin_ref="network", targets=tuple(f"synthetic-{i}" for i in range(run, args.targets, args.runs))
            )
            runs.append(executor.execute(request, lease))
        summaries = await asyncio.gather(*runs)
        if holder is not None:
            await holder
    finally:
        if holder is not None and not holder.done():
            holder.cancel()
            await asyncio.gather(holder, return_exceptions=True)
        await scheduler.shutdown()
        await publisher.shutdown(grace_seconds=5)
        sampler.cancel()
        await asyncio.gather(sampler, return_exceptions=True)
        await lag.stop()
        nats_utils._metrics_js_window = original_window
    await asyncio.sleep(0)
    snapshot = window.snapshot()
    counts = Counter()
    for summary in summaries:
        for status, attribute in (
            ("succeeded", "publish_succeeded"),
            ("failed", "publish_failed"),
            ("unknown", "publish_unknown"),
            ("permanent_failed", "publish_permanent_failed"),
            ("event_failed", "publish_event_failed"),
            ("not_applicable", "publish_not_applicable"),
        ):
            if getattr(summary, attribute):
                counts[status] += getattr(summary, attribute)

    def percentile(values):
        return round(sorted(values)[int((len(values) - 1) * 0.99)], 4) if values else 0

    return {
        "warning": "real run pipeline; synthetic SNMP/plugin and PubAck, NOT production NATS/CMDB replay",
        "pipeline": "Scheduler/Executor/RunResultSink/Publisher",
        "settings": vars(args),
        "elapsed_seconds": round(time.monotonic() - started, 4),
        "cpu_seconds": round(time.process_time() - cpu_started, 4),
        "peak_rss_mib": _peak_rss_mib(),
        "terminal_counts": dict(counts),
        "collection_succeeded": sum(s.collection_succeeded for s in summaries),
        "confirmed_lines": snapshot.confirmed_total - holder_count,
        "expected_lines": args.large_targets * args.large_lines + (args.targets - args.large_targets) * args.small_lines,
        "small_p99_seconds": percentile(small_latency),
        "large_p99_seconds": percentile(large_latency),
        "first_send_wait_p99_seconds": percentile(first_send_wait),
        "event_loop_lag_p99_seconds": round(lag.p99_seconds, 4),
        "peak_active_targets": scheduler.peak,
        "peak_payloads": publisher.peak_pending_payloads,
        "peak_pending_messages": snapshot.peak_pending_messages,
        "peak_async_tasks": peak_tasks,
        "remaining_payloads": publisher.pending_payloads,
        "remaining_messages": snapshot.pending_messages,
        "remaining_bytes": snapshot.pending_bytes,
        "remaining_sdk_futures": jetstream.pending,
        "remaining_tasks": len([t for t in asyncio.all_tasks() - before if not t.done()]),
        "deadline_expired": snapshot.deadline_expired_total,
        "retries": snapshot.retry_total,
        "stage_metrics": {k: v for k, v in metrics.snapshot().items() if k.startswith("publish_")},
    }


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--targets", type=int, default=3838)
    result.add_argument("--runs", type=int, default=7)
    result.add_argument("--concurrency", type=int, default=120)
    result.add_argument("--large-targets", type=int, default=8)
    result.add_argument("--large-lines", type=int, default=2048)
    result.add_argument("--small-lines", type=int, default=1)
    result.add_argument("--ack-ms", type=float, default=15)
    result.add_argument("--collection-ms", type=float, default=1)
    result.add_argument("--deadline", type=float, default=120)
    result.add_argument("--fail-every", type=int, default=0)
    result.add_argument("--pipeline", choices=("producer", "run"), default="producer")
    result.add_argument("--credit-pause-seconds", type=float, default=0)
    return result


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run_scenario(parser().parse_args())), ensure_ascii=False, indent=2))
