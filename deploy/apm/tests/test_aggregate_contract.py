"""系统 Collector 入口聚合的容器契约。

使用独立 Compose project 和随机宿主端口，不碰本机已经在跑的 APM 栈。
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_APM_CONTAINER_CONTRACT") != "1",
    reason="set RUN_APM_CONTAINER_CONTRACT=1 to run real APM containers",
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
COMPOSE_FILE = REPOSITORY_ROOT / "deploy/apm/compose.yaml"
RESERVED_HOST_PORTS = {4317, 4318, 8428, 9428, 10428, 13133, 18222, 18888, 18889, 18890, 23133, 33133, 18428}
ALLOWED_LABELS = {
    "__name__",
    "job",
    "shard",
    "service_name",
    "service_namespace",
    "deployment_environment",
    "span_name",
    "status_code",
    "le",
    "otel_metric_overflow",
}
FORBIDDEN_LABELS = {
    "instance",
    "collector_instance_id",
    "span_kind",
    "otel_scope_name",
    "otel_scope_version",
    "service_instance_id",
    "service_version",
    "pod_name",
    "trace_id",
    "span_id",
    "db_statement",
}
EXPECTED_BUCKETS = ["5", "10", "25", "50", "100", "200", "300", "500", "800", "1000", "2000", "3000", "5000", "10000", "+Inf"]
COLLECTOR_IMAGE = os.environ.get("APM_AGG_VERIFY_IMAGE", "bklite/apm-otel-collector:0.153.0-bklite.3")


def _free_port() -> int:
    while True:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        if port not in RESERVED_HOST_PORTS:
            return port


def _request(url: str, *, data: bytes | None = None, headers: dict[str, str] | None = None, timeout: float = 10):
    request = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return 0, str(error)


def _eventually(fetch, predicate, *, timeout: float = 45):
    deadline = time.monotonic() + timeout
    last_value = None
    while time.monotonic() < deadline:
        try:
            last_value = fetch()
        except (AssertionError, KeyError, ValueError, IndexError) as error:
            last_value = error
            time.sleep(1)
            continue
        if predicate(last_value):
            return last_value
        time.sleep(1)
    raise AssertionError(f"condition not met before timeout; last value={last_value!r}")


def _span(trace_id: str, span_id: str, name: str, kind: int, start: int, end: int, *, status: int = 1):
    return {
        "traceId": trace_id,
        "spanId": span_id,
        "name": name,
        "kind": kind,
        "startTimeUnixNano": str(start),
        "endTimeUnixNano": str(end),
        "status": {"code": status},
        "attributes": [
            {"key": "db.statement", "value": {"stringValue": "select secret from accounts"}},
            {"key": "url.full", "value": {"stringValue": "https://shop.example/pay?token=secret"}},
        ],
    }


def _resource(namespace: str, name: str, instance: str, spans: list, *, environment: str = "prod"):
    attributes = [
        ("service.namespace", namespace),
        ("service.name", name),
        ("service.instance.id", instance),
        ("service.version", "9.9.9"),
        ("pod.name", instance),
        ("deployment.environment", environment),
    ]
    return {
        "resource": {
            "attributes": [{"key": key, "value": {"stringValue": value}} for key, value in attributes],
        },
        "scopeSpans": [{"scope": {"name": "agg-contract", "version": "0.0.0"}, "spans": spans}],
    }


def _payload(resources: list) -> bytes:
    return json.dumps({"resourceSpans": resources}, separators=(",", ":")).encode()


def _le(value: str) -> str:
    if value == "+Inf":
        return value
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return format(number, "g")


class AggregateStack:
    def __init__(self, suffix: str, **overrides: str):
        self.project = f"apm-agg-verify-{os.getpid()}-{suffix}"
        self.http_port = _free_port()
        self.grpc_port = _free_port()
        self.traces_port = _free_port()
        self.nats_port = _free_port()
        self.regional_health_port = _free_port()
        self.regional_metrics_port = _free_port()
        self.system_health_port = _free_port()
        self.system_metrics_port = _free_port()
        self.aggregate_health_port = _free_port()
        self.aggregate_metrics_port = _free_port()
        self.aggregate_port = _free_port()
        self.environment = os.environ.copy()
        self.environment.pop("COMPOSE_FILE", None)
        self.environment.pop("AGG_VICTORIAMETRICS_WRITE_URL", None)
        self.environment["COMPOSE_PROJECT_NAME"] = self.project
        self.environment.update(
            {
                "APM_CLOUD_REGION_ID": "agg_contract",
                "APM_OTLP_HTTP_BIND": "127.0.0.1",
                "APM_OTLP_HTTP_PORT": str(self.http_port),
                "APM_OTLP_GRPC_BIND": "127.0.0.1",
                "APM_OTLP_GRPC_PORT": str(self.grpc_port),
                "APM_VICTORIATRACES_QUERY_BIND": "127.0.0.1",
                "APM_VICTORIATRACES_QUERY_PORT": str(self.traces_port),
                "APM_NATS_MONITOR_BIND": "127.0.0.1",
                "APM_NATS_MONITOR_PORT": str(self.nats_port),
                "APM_REGIONAL_HEALTH_BIND": "127.0.0.1",
                "APM_REGIONAL_HEALTH_PORT": str(self.regional_health_port),
                "APM_REGIONAL_METRICS_BIND": "127.0.0.1",
                "APM_REGIONAL_METRICS_PORT": str(self.regional_metrics_port),
                "APM_SYSTEM_HEALTH_BIND": "127.0.0.1",
                "APM_SYSTEM_HEALTH_PORT": str(self.system_health_port),
                "APM_SYSTEM_METRICS_BIND": "127.0.0.1",
                "APM_SYSTEM_METRICS_PORT": str(self.system_metrics_port),
                "APM_AGG_COLLECTOR_HEALTH_BIND": "127.0.0.1",
                "APM_AGG_COLLECTOR_HEALTH_PORT": str(self.aggregate_health_port),
                "APM_AGG_COLLECTOR_METRICS_BIND": "127.0.0.1",
                "APM_AGG_COLLECTOR_METRICS_PORT": str(self.aggregate_metrics_port),
                "APM_AGG_METRICS_BIND": "127.0.0.1",
                "APM_AGG_METRICS_PORT": str(self.aggregate_port),
                "APM_COLLECTOR_IMAGE": COLLECTOR_IMAGE,
                "APM_AGG_SHARD": f"agg-{suffix}",
                "APM_AGG_FLUSH_INTERVAL": "1s",
                "APM_TRACE_BATCH_SIZE": "1",
                "APM_TRACE_BATCH_MAX_SIZE": "1",
                "APM_NATS_STREAM_MAX_BYTES": str(32 * 1024 * 1024),
                "APM_NATS_STREAM_MAX_AGE": "15m",
                "APM_NATS_ACK_WAIT": "30s",
                "APM_NATS_MAX_ACK_PENDING": "32",
            }
        )
        self.environment.update(overrides)
        self.compose = ["docker", "compose", "--project-name", self.project, "-f", str(COMPOSE_FILE)]

    def up(self):
        self._run("up", "-d", "--wait", "--wait-timeout", "180", timeout=240)
        assert _request(f"http://127.0.0.1:{self.system_health_port}/")[0] == 200
        assert _request(f"http://127.0.0.1:{self.aggregate_health_port}/")[0] == 200

    def down(self):
        subprocess.run(
            [*self.compose, "down", "--volumes", "--remove-orphans"],
            cwd=REPOSITORY_ROOT,
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

    def restart_aggregate(self):
        self._run("restart", "apm-aggregate-collector", timeout=90)
        _eventually(lambda: _request(f"http://127.0.0.1:{self.aggregate_health_port}/")[0], lambda status: status == 200)

    def stop(self, service: str):
        self._run("stop", service, timeout=60)

    def start(self, service: str):
        self._run("start", service, timeout=90)

    def post(self, resources: list):
        status, body = _request(
            f"http://127.0.0.1:{self.http_port}/v1/traces",
            data=_payload(resources),
            headers={"Content-Type": "application/json"},
        )
        assert status == 200, body

    def vm_query(self, query: str):
        status, body = _request(f"http://127.0.0.1:{self.aggregate_port}/api/v1/query?{urllib.parse.urlencode({'query': query})}")
        assert status == 200, body
        payload = json.loads(body)
        assert payload.get("status") == "success", body
        return payload["data"]["result"]

    def vt_copies(self, service_name: str):
        query = (
            f'* `resource_attr:service.name`:="{service_name}" '
            "| stats by (trace_id, span_id) count() as copies "
            "| stats count() as spans, sum(copies) as rows"
        )
        status, body = _request(
            "http://127.0.0.1:"
            f"{self.traces_port}/select/logsql/stats_query?"
            + urllib.parse.urlencode(
                {
                    "query": query,
                    "start": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
                    "end": (datetime.now(UTC) + timedelta(minutes=1)).isoformat(),
                }
            )
        )
        assert status == 200, body
        result = json.loads(body)["data"]["result"]
        return {item["metric"]["__name__"]: float(item["value"][1]) for item in result}

    def jetstream(self):
        status, body = _request(f"http://127.0.0.1:{self.nats_port}/jsz?streams=true&consumers=true")
        assert status == 200, body
        detail = json.loads(body)["account_details"][0]["stream_detail"][0]
        consumers = {item["name"]: item for item in detail["consumer_detail"]}
        return detail["state"], consumers

    def logs(self) -> str:
        completed = subprocess.run(
            [*self.compose, "logs", "--tail=160", "apm-aggregate-collector", "apm-system-collector"],
            cwd=REPOSITORY_ROOT,
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return (completed.stdout + completed.stderr)[-4000:]

    def _run(self, *arguments: str, timeout: int):
        completed = subprocess.run(
            [*self.compose, *arguments],
            cwd=REPOSITORY_ROOT,
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        assert completed.returncode == 0, f"{completed.stdout}\n{completed.stderr}"


def _series(rows, name: str, service: str | None = None):
    selected = []
    for row in rows:
        metric = row["metric"]
        if metric.get("__name__") != name:
            continue
        if service is not None and metric.get("service_name") != service:
            continue
        selected.append(row)
    return selected


def _assert_labels(rows):
    for row in rows:
        keys = set(row["metric"])
        assert keys <= ALLOWED_LABELS, row["metric"]
        assert keys.isdisjoint(FORBIDDEN_LABELS), row["metric"]
        rendered = json.dumps(row["metric"], ensure_ascii=False)
        assert "select secret" not in rendered
        assert "pod-" not in rendered
        assert "9.9.9" not in rendered


def _calls(stack: AggregateStack, service: str):
    return _series(stack.vm_query("apm_calls_total"), "apm_calls_total", service)


def test_entry_aggregate_merges_instances_buckets_late_spans_and_restart_increase():
    now = time.time_ns()
    fresh_end = now
    fresh_start = now - 12_000_000
    late_end = now - 10 * 60 * 1_000_000_000
    stack = AggregateStack("merge", APM_AGG_SHARD="agg-merge")
    try:
        stack.up()
        stack.post(
            [
                _resource(
                    "shop",
                    "checkout",
                    "pod-a",
                    [_span("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "1111111111111111", "GET /pay", 2, fresh_start, fresh_end)],
                ),
                _resource(
                    "shop",
                    "checkout",
                    "pod-b",
                    [_span("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "2222222222222222", "GET /pay", 2, fresh_start, fresh_end)],
                ),
                _resource(
                    "shop",
                    "checkout",
                    "pod-a",
                    [_span("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "3333333333333333", "GET /pay", 3, fresh_start, fresh_end)],
                ),
                _resource(
                    "shop",
                    "worker",
                    "pod-w",
                    [_span("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "4444444444444444", "consume-order", 5, fresh_start, fresh_end)],
                ),
            ]
        )
        checkout = _eventually(lambda: _calls(stack, "checkout"), lambda rows: len(rows) == 1 and float(rows[0]["value"][1]) == 2.0)
        assert checkout[0]["metric"]["job"] == "shop/checkout"
        assert checkout[0]["metric"]["shard"] == "agg-merge"
        assert checkout[0]["metric"]["service_namespace"] == "shop"
        assert checkout[0]["metric"]["deployment_environment"] == "prod"
        assert checkout[0]["metric"]["span_name"] == "GET /pay"
        assert checkout[0]["metric"]["status_code"] == "STATUS_CODE_OK"
        assert "instance" not in checkout[0]["metric"]
        worker = _calls(stack, "worker")
        assert len(worker) == 1 and float(worker[0]["value"][1]) == 1.0

        buckets = _series(
            stack.vm_query('apm_duration_milliseconds_bucket{service_name="checkout",status_code="STATUS_CODE_OK"}'),
            "apm_duration_milliseconds_bucket",
            "checkout",
        )
        by_le = {_le(row["metric"]["le"]): float(row["value"][1]) for row in buckets}
        assert sorted(by_le, key=lambda item: float("inf") if item == "+Inf" else float(item)) == EXPECTED_BUCKETS
        assert by_le["10"] == 0.0
        assert by_le["25"] == 2.0
        assert by_le["10000"] == 2.0
        assert by_le["+Inf"] == 2.0

        stack.post(
            [
                _resource(
                    "shop",
                    "late-svc",
                    "pod-late",
                    [_span("cccccccccccccccccccccccccccccccc", "5555555555555555", "GET /old", 2, late_end - 12_000_000, late_end)],
                )
            ]
        )
        late = _eventually(
            lambda: stack.vm_query("apm_aggregate_late_spans_total"),
            lambda rows: rows and sum(float(row["value"][1]) for row in rows) >= 1,
        )
        assert _calls(stack, "late-svc") == []
        _assert_labels(late)
        names = {row["metric"]["__name__"] for row in stack.vm_query('{__name__=~"apm_.*|target_info|trace_.*"}')}
        assert names <= {
            "apm_calls_total",
            "apm_duration_milliseconds_bucket",
            "apm_duration_milliseconds_count",
            "apm_duration_milliseconds_sum",
            "apm_aggregate_late_spans_total",
        }
        assert "target_info" not in names
        _assert_labels(stack.vm_query("apm_calls_total"))

        restart_start = time.time_ns()
        stack.post(
            [
                _resource(
                    "shop",
                    "restart-svc",
                    "pod-r",
                    [
                        _span("dddddddddddddddddddddddddddddddd", "6666666666666666", "GET /restart", 2, restart_start - 12_000_000, restart_start),
                        _span("dddddddddddddddddddddddddddddddd", "7777777777777777", "GET /restart", 2, restart_start - 12_000_000, restart_start),
                        _span(
                            "dddddddddddddddddddddddddddddddd",
                            "8888888888888888",
                            "GET /restart",
                            2,
                            restart_start - 12_000_000,
                            restart_start,
                            status=2,
                        ),
                    ],
                )
            ]
        )

        def _increase():
            rows = stack.vm_query('sum(increase(apm_calls_total{service_name="restart-svc"}[5m]))')
            return float(rows[0]["value"][1]) if rows else 0.0

        assert _eventually(_increase, lambda value: value == 3.0) == 3.0
        stack.restart_aggregate()
        again = time.time_ns()
        stack.post(
            [
                _resource(
                    "shop",
                    "restart-svc",
                    "pod-r2",
                    [_span("eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee", "9999999999999999", "GET /restart", 2, again - 12_000_000, again)],
                )
            ]
        )
        assert _eventually(_increase, lambda value: value == 4.0, timeout=60) == 4.0
        time.sleep(3)
        assert _increase() == 4.0
        restarted = _calls(stack, "restart-svc")
        _assert_labels(restarted)
        assert all("instance" not in row["metric"] for row in restarted)
    except AssertionError as error:
        raise AssertionError(f"{error}\n{stack.logs()}") from error
    finally:
        stack.down()


def test_remote_write_failure_does_not_duplicate_victoria_traces():
    now = time.time_ns()
    late_end = now - 10 * 60 * 1_000_000_000
    stack = AggregateStack(
        "isolate",
        APM_AGG_SHARD="agg-isolate",
        AGG_VICTORIAMETRICS_WRITE_URL="http://127.0.0.1:1/api/v1/write",
    )
    try:
        stack.up()
        stack.post(
            [
                _resource(
                    "shop",
                    "iso-svc",
                    "pod-iso",
                    [
                        _span("ffffffffffffffffffffffffffffffff", "abcdabcdabcdabcd", "GET /iso", 2, now - 12_000_000, now),
                        _span("ffffffffffffffffffffffffffffffff", "bcdebcdebcdebcde", "GET /iso-late", 2, late_end - 12_000_000, late_end),
                        _span("ffffffffffffffffffffffffffffffff", "cdefcdefcdefcdef", "GET /iso-client", 3, now - 12_000_000, now),
                    ],
                )
            ]
        )

        # 区域 Collector 的 batch size 是 1，三条 Span 会变成三条消息。
        # 明细消费者和聚合消费者都要 ACK，且没有重投。验收的不是消息条数本身。
        def _acked(consumer: dict) -> bool:
            return (
                consumer["ack_floor"]["stream_seq"] == 3
                and consumer["num_ack_pending"] == 0
                and consumer["num_pending"] == 0
                and consumer.get("num_redelivered", 0) == 0
            )

        _eventually(
            stack.jetstream,
            lambda value: value[0]["last_seq"] == 3 and _acked(value[1]["BKLITE_APM_SYSTEM"]) and _acked(value[1]["BKLITE_APM_AGGREGATE"]),
            timeout=40,
        )
        time.sleep(8)
        state, consumers = stack.jetstream()
        assert state["last_seq"] == 3, consumers
        assert _acked(consumers["BKLITE_APM_SYSTEM"])
        assert _acked(consumers["BKLITE_APM_AGGREGATE"])
        copies = _eventually(lambda: stack.vt_copies("iso-svc"), lambda value: value.get("spans") == 3 and value.get("rows") == 3)
        assert copies == {"spans": 3.0, "rows": 3.0}
    except AssertionError as error:
        raise AssertionError(f"{error}\n{stack.logs()}") from error
    finally:
        stack.down()


def test_cardinality_limit_collapses_overflow_into_one_series():
    now = time.time_ns()
    stack = AggregateStack("overflow", APM_AGG_SHARD="agg-overflow", APM_AGG_CARDINALITY_LIMIT="2")
    try:
        stack.up()
        spans = [_span(f"{index:032x}", f"{index:016x}", f"/op-{index}", 2, now - 12_000_000, now) for index in range(1, 6)]
        stack.post([_resource("shop", "overflow-svc", f"pod-{index}", [span]) for index, span in enumerate(spans, start=1)])
        # 溢出点只带 otel.metric.overflow，不再带 service.name 等维度。
        # job 仍来自资源上的命名空间和服务名。
        rows = _eventually(
            lambda: stack.vm_query('apm_calls_total{job="shop/overflow-svc"}'),
            lambda selected: len(selected) == 3 and sum(float(row["value"][1]) for row in selected) == 5.0,
        )
        overflow = [row for row in rows if row["metric"].get("otel_metric_overflow") == "true"]
        kept = [row for row in rows if "otel_metric_overflow" not in row["metric"]]
        assert len(overflow) == 1, rows
        assert float(overflow[0]["value"][1]) == 3.0
        assert "service_name" not in overflow[0]["metric"]
        assert "deployment_environment" not in overflow[0]["metric"]
        assert "span_name" not in overflow[0]["metric"]
        assert len(kept) == 2, rows
        assert sum(float(row["value"][1]) for row in kept) == 2.0
        assert {row["metric"]["service_name"] for row in kept} == {"overflow-svc"}
        _assert_labels(rows)
        assert all("instance" not in row["metric"] for row in rows)
    except AssertionError as error:
        raise AssertionError(f"{error}\n{stack.logs()}") from error
    finally:
        stack.down()


def test_expired_series_restarts_from_zero_and_increase_includes_both_sides():
    now = time.time_ns()
    stack = AggregateStack("expire", APM_AGG_SHARD="agg-expire", APM_AGG_SERIES_EXPIRATION="3s")
    try:
        stack.up()
        stack.post(
            [
                _resource(
                    "shop",
                    "expire-svc",
                    "pod-e",
                    [
                        _span("12121212121212121212121212121212", "1212121212121212", "GET /expire", 2, now - 12_000_000, now),
                        _span("23232323232323232323232323232323", "2323232323232323", "GET /expire", 2, now - 12_000_000, now),
                        _span("34343434343434343434343434343434", "3434343434343434", "GET /expire", 2, now - 12_000_000, now),
                    ],
                )
            ]
        )

        def _value() -> float:
            rows = _calls(stack, "expire-svc")
            return sum(float(row["value"][1]) for row in rows)

        def _increase() -> float:
            rows = stack.vm_query('sum(increase(apm_calls_total{service_name="expire-svc"}[5m]))')
            return float(rows[0]["value"][1]) if rows else 0.0

        assert _eventually(_value, lambda value: value == 3.0, timeout=45) == 3.0
        # 3s 过期加上 1s 刷出。等到下一次刷出把序列从内存删掉，再写入才会从 0 开始。
        time.sleep(8)
        again = time.time_ns()
        stack.post(
            [
                _resource(
                    "shop",
                    "expire-svc",
                    "pod-e2",
                    [_span("45454545454545454545454545454545", "4545454545454545", "GET /expire", 2, again - 12_000_000, again)],
                )
            ]
        )
        assert _eventually(_value, lambda value: value == 1.0, timeout=45) == 1.0
        assert _eventually(_increase, lambda value: value == 4.0, timeout=60) == 4.0
        time.sleep(3)
        assert _value() == 1.0
        assert _increase() == 4.0
    except AssertionError as error:
        raise AssertionError(f"{error}\n{stack.logs()}") from error
    finally:
        stack.down()


def test_victoria_traces_outage_counts_each_entry_span_once():
    now = time.time_ns()
    stack = AggregateStack("vt-outage", APM_AGG_SHARD="agg-vt-outage")
    spans = [_span(f"{index:032x}", f"{index:016x}", "GET /checkout", 2, now - 12_000_000, now) for index in range(1, 5)]
    try:
        stack.up()
        stack.stop("apm-victoria-traces")
        stack.post([_resource("shop", "vt-outage-svc", "pod-vt", spans)])

        def _calls_value() -> float:
            return sum(float(row["value"][1]) for row in _calls(stack, "vt-outage-svc"))

        assert _eventually(_calls_value, lambda value: value == 4.0, timeout=45) == 4.0
        state, consumers = stack.jetstream()
        system_seq = consumers["BKLITE_APM_SYSTEM"].get("ack_floor", {}).get("stream_seq", 0)
        aggregate_seq = consumers["BKLITE_APM_AGGREGATE"]["ack_floor"]["stream_seq"]
        assert state["last_seq"] > 0
        assert system_seq < state["last_seq"]
        assert aggregate_seq == state["last_seq"]
        time.sleep(6)
        assert _calls_value() == 4.0
        stack.start("apm-victoria-traces")
        _eventually(
            lambda: stack.jetstream()[1]["BKLITE_APM_SYSTEM"]["ack_floor"]["stream_seq"],
            lambda seq: seq == state["last_seq"],
            timeout=90,
        )
        copies = _eventually(
            lambda: stack.vt_copies("vt-outage-svc"),
            lambda value: value.get("spans") == 4 and value.get("rows") == 4,
            timeout=90,
        )
        assert copies == {"spans": 4.0, "rows": 4.0}
        time.sleep(6)
        assert _calls_value() == 4.0
    except AssertionError as error:
        raise AssertionError(f"{error}\n{stack.logs()}") from error
    finally:
        stack.down()
