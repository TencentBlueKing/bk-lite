#!/usr/bin/env python3
"""方案 B 生产发布链路基准：5000 网络设备与深信服 HCI。"""

from __future__ import annotations

import argparse
import asyncio
import gc
import json
import os
import resource
import sys
import time
from collections.abc import Iterable
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.collection.contracts import PublishStatus, StructuredMetricsPayload, TargetCollectionResult  # noqa: E402
from core.collection.metrics import CollectionMetrics  # noqa: E402
from core.collection.result_publisher import BufferedResultPublisher, NatsResultPublisher  # noqa: E402
from core.collection.runtime import CollectionRequest, RunLease  # noqa: E402
from core.infra import nats_utils  # noqa: E402
from core.infra.event_loop_monitor import EventLoopLagMonitor  # noqa: E402
from core.infra.jetstream_publish_window import JetStreamPublishWindow, JetStreamPublishWindowSettings  # noqa: E402


class SimulatedJetStream:
    """只模拟可控 PubAck 延迟；不模拟 broker 存储、磁盘和网络吞吐。"""

    def __init__(self, ack_delay_seconds: float) -> None:
        self.ack_delay_seconds = max(0.0, ack_delay_seconds)
        self.published = 0
        self.in_flight = 0
        self.peak_in_flight = 0

    async def publish_async(self, _subject, _payload=b"", *, headers=None, stream=None, **_kwargs):
        assert headers and headers.get("Nats-Msg-Id")
        assert stream
        self.published += 1
        sequence = self.published
        self.in_flight += 1
        self.peak_in_flight = max(self.peak_in_flight, self.in_flight)
        future = asyncio.get_running_loop().create_future()

        async def confirm() -> None:
            try:
                if self.ack_delay_seconds:
                    await asyncio.sleep(self.ack_delay_seconds)
                future.set_result(SimpleNamespace(stream=stream, seq=sequence))
            finally:
                self.in_flight -= 1

        asyncio.create_task(confirm())
        return future


def _network_address(index: int) -> str:
    return f"10.{index // 65536}.{(index // 256) % 256}.{index % 256}"


def network_results(*, devices: int, lines_per_device: int) -> Iterable[TargetCollectionResult]:
    for device_index in range(devices):
        address = _network_address(device_index)
        rows = tuple(
            {
                "ip": address,
                "metric": f"metric_{line_index}",
                "value": device_index + line_index,
            }
            for line_index in range(lines_per_device)
        )
        yield TargetCollectionResult(
            target=address,
            status="success",
            attempts=1,
            value=StructuredMetricsPayload(data={"network_device": rows}),
            publish_timestamp_ms=1_700_000_000_000,
        )


def sangfor_result(*, hosts: int, vms: int, description_bytes: int) -> TargetCollectionResult:
    description = "x" * max(0, description_bytes)
    host_rows = tuple(
        {
            "resource_id": f"host-{index}",
            "name": f"HCI-HOST-{index}",
            "ip": f"10.233.{index // 255}.{index % 255}",
            "description": description,
        }
        for index in range(hosts)
    )
    vm_rows = tuple(
        {
            "resource_id": f"vm-{index}",
            "name": f"HCI-VM-{index}",
            "host_id": f"host-{index % max(1, hosts)}",
            "description": description,
        }
        for index in range(vms)
    )
    return TargetCollectionResult(
        target="10.233.1.171",
        status="success",
        attempts=1,
        value=StructuredMetricsPayload(
            data={
                "sangforscp_host": host_rows,
                "sangforscp_vm": vm_rows,
            }
        ),
        publish_timestamp_ms=1_700_000_000_000,
    )


def _peak_rss_mib() -> float:
    max_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    divisor = 1024 * 1024 if sys.platform == "darwin" else 1024
    return round(max_rss / divisor, 2)


def _request_and_lease(*, task_id: str, plugin_ref: str, targets: tuple[str, ...]) -> tuple[CollectionRequest, RunLease]:
    request = CollectionRequest(
        task_id=task_id,
        plugin_ref=plugin_ref,
        targets=targets,
        params={"model_id": plugin_ref, "monitor_type": plugin_ref},
    )
    lease = RunLease(
        task_id=request.task_id,
        request_digest=request.digest,
        owner_id="benchmark",
        fence=1,
        expires_at=time.time() + 3600,
        attempt_id="attempt-1",
    )
    return request, lease


async def run_pipeline_scenario(args, *, name: str, include_network: bool, include_sangfor: bool) -> dict[str, object]:
    run_suffix = f"{time.time_ns()}-{name}"
    metrics = CollectionMetrics(sample_capacity=5000)
    publisher = BufferedResultPublisher(
        NatsResultPublisher(metrics=metrics),
        capacity=args.queue_capacity,
        batch_size=args.batch_size,
        flush_interval_seconds=args.flush_interval,
        worker_count=args.publish_workers,
        metrics=metrics,
    )
    network_request = network_lease = None
    network_items = []
    if include_network:
        network_items = list(
            network_results(
                devices=args.network_devices,
                lines_per_device=args.network_lines_per_device,
            )
        )
        network_request, network_lease = _request_and_lease(
            task_id=f"benchmark-network-{run_suffix}",
            plugin_ref="network",
            targets=tuple(item.target for item in network_items),
        )
    sangfor_item = sangfor_request = sangfor_lease = None
    if include_sangfor:
        sangfor_item = sangfor_result(
            hosts=args.sangfor_hosts,
            vms=args.sangfor_vms,
            description_bytes=args.sangfor_description_bytes,
        )
        sangfor_request, sangfor_lease = _request_and_lease(
            task_id=f"benchmark-sangfor-{run_suffix}",
            plugin_ref="sangforscp",
            targets=(sangfor_item.target,),
        )

    gc.collect()
    lag_monitor = EventLoopLagMonitor(interval_seconds=0.01)
    completion_seconds: dict[str, list[float]] = {"network": [], "sangfor": []}
    waiters: list[asyncio.Task] = []
    started = time.perf_counter()

    async def enqueue(request, result, lease, group: str) -> None:
        receipt = await publisher.enqueue(request, result, lease)
        waiter = asyncio.create_task(receipt.wait())
        waiter.add_done_callback(lambda _future, key=group: completion_seconds[key].append(time.perf_counter() - started))
        waiters.append(waiter)

    lag_monitor.start()
    try:
        if sangfor_item is not None:
            await enqueue(sangfor_request, sangfor_item, sangfor_lease, "sangfor")
        if network_request is not None:
            for item in network_items:
                await enqueue(network_request, item, network_lease, "network")
        outcomes = await asyncio.gather(*waiters, return_exceptions=True)
    finally:
        await publisher.shutdown(grace_seconds=args.shutdown_grace)
        await lag_monitor.stop()

    elapsed = time.perf_counter() - started
    snapshot = metrics.snapshot()
    failures = sum(1 for outcome in outcomes if isinstance(outcome, BaseException) or getattr(outcome, "status", None) != PublishStatus.CONFIRMED)
    expected_lines = (args.network_devices * args.network_lines_per_device if include_network else 0) + (
        args.sangfor_hosts + args.sangfor_vms if include_sangfor else 0
    )
    return {
        "scenario": name,
        "targets": len(waiters),
        "expected_lines": expected_lines,
        "confirmed_lines": int(snapshot.get("publish_lines_total", 0)),
        "published_bytes": int(snapshot.get("publish_bytes_total", 0)),
        "failed_targets": failures,
        "elapsed_seconds": round(elapsed, 6),
        "messages_per_second": round(snapshot.get("publish_lines_total", 0) / elapsed, 2) if elapsed else 0,
        "network_complete_seconds": round(max(completion_seconds["network"]), 6) if completion_seconds["network"] else None,
        "sangfor_complete_seconds": round(max(completion_seconds["sangfor"]), 6) if completion_seconds["sangfor"] else None,
        "peak_result_queue_depth": publisher.peak_queue_depth,
        "event_loop_lag_p99_seconds": round(lag_monitor.p99_seconds, 6),
        "peak_rss_mib": _peak_rss_mib(),
        "publish_queue_wait_p99_seconds": round(snapshot.get("publish_queue_wait_seconds_p99", 0), 6),
        "publish_encode_p99_seconds": round(snapshot.get("publish_encode_duration_seconds_p99", 0), 6),
        "publish_flush_p99_seconds": round(snapshot.get("publish_flush_duration_seconds_p99", 0), 6),
    }


async def async_main(args) -> int:
    os.environ["NATS_METRICS_JETSTREAM_ENABLED"] = "true"
    os.environ["NATS_JS_PUBLISH_MAX_PENDING"] = str(args.max_pending_messages)
    os.environ["NATS_JS_PUBLISH_MAX_PENDING_BYTES"] = str(args.max_pending_bytes)
    os.environ["NATS_JS_PUBACK_TIMEOUT"] = str(args.puback_timeout)
    os.environ["NATS_JS_PUBLISH_MAX_ATTEMPTS"] = str(args.max_attempts)
    os.environ["NATS_JS_STREAM_NAME"] = args.stream
    simulated = None
    if args.transport == "simulated":
        simulated = SimulatedJetStream(args.simulated_ack_ms / 1000)
        nats_utils._metrics_js_window = JetStreamPublishWindow(
            lambda: simulated,
            settings=JetStreamPublishWindowSettings(
                max_pending_messages=args.max_pending_messages,
                max_pending_bytes=args.max_pending_bytes,
                puback_timeout_seconds=args.puback_timeout,
                max_attempts=args.max_attempts,
                expected_stream=args.stream,
            ),
        )
    else:
        nats_utils._metrics_js_window = None

    scenarios = []
    try:
        if args.scenario in {"network", "all"}:
            scenarios.append(
                await run_pipeline_scenario(
                    args,
                    name="network",
                    include_network=True,
                    include_sangfor=False,
                )
            )
        if args.scenario in {"sangfor", "all"}:
            scenarios.append(
                await run_pipeline_scenario(
                    args,
                    name="sangfor_hci",
                    include_network=False,
                    include_sangfor=True,
                )
            )
        if args.scenario in {"mixed", "all"}:
            scenarios.append(
                await run_pipeline_scenario(
                    args,
                    name="mixed",
                    include_network=True,
                    include_sangfor=True,
                )
            )
    finally:
        window_snapshot = nats_utils.nats_metrics_connection_stats()
        await nats_utils.close_shared_nats()

    report = {
        "transport": args.transport,
        "pipeline": "BufferedResultPublisher -> NatsResultPublisher -> encoder/validator -> JetStream PubAck",
        "warning": (
            "simulated PubAck only; elapsed time is not a real NATS result"
            if args.transport == "simulated"
            else "real producer PubAck; excludes Telegraf/VictoriaMetrics ingestion"
        ),
        "settings": vars(args),
        "simulated_peak_in_flight": simulated.peak_in_flight if simulated else None,
        "jetstream": window_snapshot,
        "results": scenarios,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(any(item["failed_targets"] or item["confirmed_lines"] != item["expected_lines"] for item in scenarios))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transport", choices=("simulated", "jetstream"), default="simulated")
    parser.add_argument("--scenario", choices=("network", "sangfor", "mixed", "all"), default="all")
    parser.add_argument("--network-devices", type=int, default=5000)
    parser.add_argument("--network-lines-per-device", type=int, default=20)
    parser.add_argument("--sangfor-hosts", type=int, default=92)
    parser.add_argument("--sangfor-vms", type=int, default=1437)
    parser.add_argument("--sangfor-description-bytes", type=int, default=3500)
    parser.add_argument("--queue-capacity", type=int, default=160)
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--publish-workers", type=int, default=4)
    parser.add_argument("--flush-interval", type=float, default=0.02)
    parser.add_argument("--max-pending-messages", type=int, default=256)
    parser.add_argument("--max-pending-bytes", type=int, default=32 * 1024 * 1024)
    parser.add_argument("--puback-timeout", type=float, default=30.0)
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--stream", default="CMDB_METRICS")
    parser.add_argument("--simulated-ack-ms", type=float, default=1.0)
    parser.add_argument("--shutdown-grace", type=float, default=120.0)
    return parser


if __name__ == "__main__":
    raise SystemExit(asyncio.run(async_main(build_parser().parse_args())))
