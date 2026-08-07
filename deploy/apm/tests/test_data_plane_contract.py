"""区域 Collector -> JetStream -> 系统 Collector -> VictoriaTraces 容器契约。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import http.client
import json
import os
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_APM_CONTAINER_CONTRACT") != "1",
    reason="set RUN_APM_CONTAINER_CONTRACT=1 to run real APM containers",
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
COMPOSE_FILE = REPOSITORY_ROOT / "deploy/apm/compose.yaml"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _request(url: str, *, data: bytes | None = None, headers: dict[str, str] | None = None):
    request = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()
    except (urllib.error.URLError, http.client.HTTPException, OSError) as error:
        return 0, str(error)


def _trace_payload(trace_id: str) -> bytes:
    started_at = time.time_ns()
    payload = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.namespace", "value": {"stringValue": "contract-app"}},
                        {"key": "service.name", "value": {"stringValue": "apm-nats-contract"}},
                        {"key": "service.instance.id", "value": {"stringValue": "contract-instance"}},
                        {"key": "service.version", "value": {"stringValue": "1.2.3"}},
                        {"key": "deployment.environment", "value": {"stringValue": "testing"}},
                        {"key": "bk.organization.id", "value": {"stringValue": "forged-resource"}},
                        {"key": "password", "value": {"stringValue": "resource-secret"}},
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {
                            "name": "bk-lite-apm-contract",
                            "attributes": [
                                {"key": "bk.forged.scope", "value": {"stringValue": "forged-scope"}}
                            ],
                        },
                        "spans": [
                            {
                                "traceId": trace_id,
                                "spanId": trace_id[-16:],
                                "name": "GET /orders/{order_id}",
                                "kind": 2,
                                "startTimeUnixNano": str(started_at),
                                "endTimeUnixNano": str(started_at + 20_000_000),
                                "attributes": [
                                    {"key": "http.request.method", "value": {"stringValue": "GET"}},
                                    {"key": "http.route", "value": {"stringValue": "/orders/{order_id}"}},
                                    {"key": "url.full", "value": {"stringValue": "https://example/orders/1?token=x"}},
                                    {"key": "http.request.body", "value": {"stringValue": "body-secret"}},
                                    {"key": "authorization", "value": {"stringValue": "bearer-secret"}},
                                    {"key": "bk.forged.span", "value": {"stringValue": "forged-span"}},
                                ],
                                "events": [
                                    {
                                        "timeUnixNano": str(started_at + 1_000_000),
                                        "name": "contract-event",
                                        "attributes": [
                                            {"key": "bk.forged.event", "value": {"stringValue": "forged-event"}}
                                        ],
                                    }
                                ],
                                "status": {"code": 1},
                            },
                            {
                                "traceId": trace_id,
                                "spanId": "cafebabecafebabe",
                                "parentSpanId": trace_id[-16:],
                                "name": "contract-downstream",
                                "kind": 3,
                                "startTimeUnixNano": str(started_at + 1_000_000),
                                "endTimeUnixNano": str(started_at + 13_000_000),
                                "attributes": [
                                    {"key": "server.address", "value": {"stringValue": "contract-downstream"}}
                                ],
                                "status": {"code": 1},
                            }
                        ],
                    }
                ],
            },
            {
                "resource": {
                    "attributes": [
                        {"key": "service.namespace", "value": {"stringValue": "contract-app"}},
                        {"key": "service.name", "value": {"stringValue": "contract-downstream"}},
                        {"key": "service.instance.id", "value": {"stringValue": "downstream-instance"}},
                        {"key": "service.version", "value": {"stringValue": "2.0.0"}},
                        {"key": "deployment.environment", "value": {"stringValue": "testing"}},
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "bk-lite-apm-contract"},
                        "spans": [
                            {
                                "traceId": trace_id,
                                "spanId": "fedcba9876543210",
                                "parentSpanId": "cafebabecafebabe",
                                "name": "GET /inventory/{item_id}",
                                "kind": 2,
                                "startTimeUnixNano": str(started_at + 2_000_000),
                                "endTimeUnixNano": str(started_at + 12_000_000),
                                "status": {"code": 1},
                            }
                        ],
                    }
                ],
            },
        ]
    }
    return json.dumps(payload, separators=(",", ":")).encode()


def _post_trace(port: int, payload: bytes):
    return _request(
        f"http://127.0.0.1:{port}/v1/traces",
        data=payload,
        headers={"Content-Type": "application/json"},
    )


def _post_empty_grpc_trace(port: int):
    # gRPC frame: uncompressed flag + uint32 message length + empty ExportTraceServiceRequest.
    with tempfile.NamedTemporaryFile() as payload:
        payload.write(b"\x00\x00\x00\x00\x00")
        payload.flush()
        completed = subprocess.run(
            [
                "curl",
                "--http2-prior-knowledge",
                "--silent",
                "--show-error",
                "--dump-header",
                "-",
                "--output",
                "/dev/null",
                "--header",
                "Content-Type: application/grpc",
                "--header",
                "TE: trailers",
                "--data-binary",
                f"@{payload.name}",
                f"http://127.0.0.1:{port}/opentelemetry.proto.collector.trace.v1.TraceService/Export",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    return completed


def _eventually(fetch, predicate, *, timeout: float = 60):
    deadline = time.monotonic() + timeout
    last_value = None
    while time.monotonic() < deadline:
        try:
            last_value = fetch()
        except (AssertionError, KeyError, ValueError) as error:
            last_value = error
            time.sleep(1)
            continue
        if predicate(last_value):
            return last_value
        time.sleep(1)
    raise AssertionError(f"condition not met before timeout; last value={last_value!r}")


def _jetstream_state(port: int):
    status, body = _request(f"http://127.0.0.1:{port}/jsz?streams=true&consumers=true")
    assert status == 200, body
    detail = json.loads(body)["account_details"][0]["stream_detail"][0]
    return detail["state"], detail["consumer_detail"][0]


def _compose_action(compose, environment, *arguments, timeout=120):
    completed = subprocess.run(
        [*compose, *arguments],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    assert completed.returncode == 0, f"{completed.stdout}\n{completed.stderr}"
    return completed


def _query(url: str, **params):
    return _request(f"{url}?{urllib.parse.urlencode(params)}")


def _vector_values(body: str):
    result = json.loads(body)["data"]["result"]
    return {item["metric"]["__name__"]: float(item["value"][1]) for item in result}


def test_trace_crosses_bounded_jetstream_and_reaches_victoria_traces_once():
    project = f"bk-lite-apm-contract-{os.getpid()}"
    http_port = _free_port()
    grpc_port = _free_port()
    traces_port = _free_port()
    nats_monitor_port = _free_port()
    regional_health_port = _free_port()
    regional_metrics_port = _free_port()
    system_health_port = _free_port()
    system_metrics_port = _free_port()
    trace_id = "0123456789abcdef0123456789abcdef"
    payload = _trace_payload(trace_id)

    environment = os.environ.copy()
    environment.update(
        {
            "APM_CLOUD_REGION_ID": "contract_region",
            "APM_OTLP_HTTP_BIND": "127.0.0.1",
            "APM_OTLP_HTTP_PORT": str(http_port),
            "APM_OTLP_GRPC_BIND": "127.0.0.1",
            "APM_OTLP_GRPC_PORT": str(grpc_port),
            "APM_VICTORIATRACES_QUERY_PORT": str(traces_port),
            "APM_NATS_MONITOR_PORT": str(nats_monitor_port),
            "APM_REGIONAL_HEALTH_PORT": str(regional_health_port),
            "APM_REGIONAL_METRICS_PORT": str(regional_metrics_port),
            "APM_SYSTEM_HEALTH_PORT": str(system_health_port),
            "APM_SYSTEM_METRICS_PORT": str(system_metrics_port),
            "APM_NATS_STREAM_MAX_BYTES": str(32 * 1024 * 1024),
            "APM_NATS_STREAM_MAX_AGE": "15m",
            "APM_NATS_MAX_DELIVER": "4",
            "APM_NATS_ACK_WAIT": "10s",
            "APM_NATS_MAX_ACK_PENDING": "16",
            "APM_REGIONAL_QUEUE_MAX_BYTES": str(8 * 1024 * 1024),
            "APM_TRACE_BATCH_SIZE": "1",
            "APM_TRACE_BATCH_MAX_SIZE": "1",
        }
    )
    compose = ["docker", "compose", "--project-name", project, "-f", str(COMPOSE_FILE)]

    try:
        _compose_action(compose, environment, "up", "-d", "--wait", "--wait-timeout", "120", timeout=180)

        assert _request(f"http://127.0.0.1:{regional_health_port}/")[0] == 200
        assert _request(f"http://127.0.0.1:{system_health_port}/")[0] == 200

        assert _post_trace(http_port, payload)[0] == 200
        grpc = _post_empty_grpc_trace(grpc_port)
        assert grpc.returncode == 0, grpc.stderr
        assert "grpc-status: 0" in grpc.stdout.lower(), grpc.stdout

        state, consumer = _eventually(
            lambda: _jetstream_state(nats_monitor_port),
            lambda value: value[0]["messages"] == 3
            and value[1]["ack_floor"]["stream_seq"] == 3
            and value[1]["num_ack_pending"] == 0,
        )
        assert state["bytes"] <= 32 * 1024 * 1024
        assert consumer["num_pending"] == 0

        trace_status, trace_body = _eventually(
            lambda: _request(f"http://127.0.0.1:{traces_port}/select/tempo/api/v2/traces/{trace_id}"),
            lambda value: value[0] == 200 and "apm-nats-contract" in value[1],
        )
        assert trace_status == 200
        assert "contract_region" in trace_body
        for forbidden in (
            "forged-resource",
            "forged-scope",
            "forged-span",
            "forged-event",
            "resource-secret",
            "body-secret",
            "bearer-secret",
            "https://example/orders/1?token=x",
        ):
            assert forbidden not in trace_body

        # 同一 OTLP 批次在去重窗口内重发时，消息 ID 相同且不会新增 Stream sequence。
        assert _post_trace(http_port, payload)[0] == 200
        time.sleep(3)
        duplicate_state, duplicate_consumer = _jetstream_state(nats_monitor_port)
        assert duplicate_state["last_seq"] == state["last_seq"] == 3
        assert duplicate_consumer["ack_floor"]["stream_seq"] == 3

        regional_metrics = _request(f"http://127.0.0.1:{regional_metrics_port}/metrics")
        system_metrics = _request(f"http://127.0.0.1:{system_metrics_port}/metrics")
        assert regional_metrics[0] == system_metrics[0] == 200
        assert "bklite_apm_nats_publish_acks" in regional_metrics[1]
        assert "bklite_apm_nats_last_publish_ack_unixtime" in regional_metrics[1]
        assert "bklite_apm_nats_delivery_acks" in system_metrics[1]
        assert "bklite_apm_nats_last_delivery_ack_unixtime" in system_metrics[1]

        # 区域到 NATS 断开时 OTLP 仍进入本地持久队列；Broker 恢复后补发并最终写入 VT。
        queued_trace_id = "1123456789abcdef0123456789abcdef"
        _compose_action(compose, environment, "stop", "apm-nats")
        assert _post_trace(http_port, _trace_payload(queued_trace_id))[0] == 200
        _compose_action(compose, environment, "start", "apm-nats")
        _eventually(
            lambda: _jetstream_state(nats_monitor_port),
            lambda value: value[0]["last_seq"] == 6
            and value[1]["ack_floor"]["stream_seq"] == 6,
        )
        _eventually(
            lambda: _request(f"http://127.0.0.1:{traces_port}/select/tempo/api/v2/traces/{queued_trace_id}"),
            lambda value: value[0] == 200,
        )

        # 中心消费者停止时 Stream 明确积压；恢复后 durable consumer 从原位置继续。
        pending_trace_id = "2123456789abcdef0123456789abcdef"
        _compose_action(compose, environment, "stop", "apm-system-collector")
        assert _post_trace(http_port, _trace_payload(pending_trace_id))[0] == 200
        _eventually(
            lambda: _jetstream_state(nats_monitor_port),
            lambda value: value[0]["last_seq"] == 9
            and value[1]["ack_floor"]["stream_seq"] == 6
            and value[1]["num_pending"] >= 1,
        )
        _compose_action(compose, environment, "start", "apm-system-collector")
        _eventually(
            lambda: _jetstream_state(nats_monitor_port),
            lambda value: value[1]["ack_floor"]["stream_seq"] == 9,
        )
        _eventually(
            lambda: _request(f"http://127.0.0.1:{traces_port}/select/tempo/api/v2/traces/{pending_trace_id}"),
            lambda value: value[0] == 200,
        )

        # VT 不可用时中心不得 ACK；恢复后同一消息重投并完成 ACK。
        retry_trace_id = "3123456789abcdef0123456789abcdef"
        _compose_action(compose, environment, "stop", "apm-victoria-traces")
        assert _post_trace(http_port, _trace_payload(retry_trace_id))[0] == 200
        _, retry_consumer = _eventually(
            lambda: _jetstream_state(nats_monitor_port),
            lambda value: value[0]["last_seq"] == 12
            and value[1]["ack_floor"]["stream_seq"] == 9,
        )
        assert retry_consumer["num_pending"] + retry_consumer["num_ack_pending"] >= 1
        _compose_action(compose, environment, "start", "apm-victoria-traces")
        _eventually(
            lambda: _jetstream_state(nats_monitor_port),
            lambda value: value[1]["ack_floor"]["stream_seq"] == 12,
            timeout=90,
        )
        _eventually(
            lambda: _request(f"http://127.0.0.1:{traces_port}/select/tempo/api/v2/traces/{retry_trace_id}"),
            lambda value: value[0] == 200,
        )

        # OTLP HTTP 与 NATS 单消息上限一致，超限请求不能占用 Stream。
        oversized = b"{" + b"x" * (8 * 1024 * 1024) + b"}"
        assert _post_trace(http_port, oversized)[0] in {400, 413}
        time.sleep(2)
        bounded_state, _ = _jetstream_state(nats_monitor_port)
        assert bounded_state["last_seq"] == 12

        # servicegraph 后台任务必须从真实跨服务 Span 关系生成 dependencies。
        dependency_status, dependency_body = _eventually(
            lambda: _query(
                f"http://127.0.0.1:{traces_port}/select/jaeger/api/dependencies",
                endTs=int(time.time() * 1000),
                lookback=3_600_000,
            ),
            lambda value: value[0] == 200
            and any(
                item.get("parent") == "apm-nats-contract"
                and item.get("child") == "contract-downstream"
                for item in json.loads(value[1]).get("data", [])
            ),
            timeout=90,
        )
        assert dependency_status == 200, dependency_body

        # 模拟 ACK 崩溃窗口导致 VT 物理重复；受控聚合先按 trace_id/span_id 去重，不能双计数。
        direct_vt_url = f"http://127.0.0.1:{traces_port}/insert/opentelemetry/v1/traces"
        assert _request(
            direct_vt_url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )[0] == 200
        assert _request(
            direct_vt_url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )[0] == 200
        time.sleep(2)
        stats_query = (
            '* `resource_attr:service.namespace`:="contract-app" '
            '`resource_attr:service.name`:="apm-nats-contract" '
            '`resource_attr:deployment.environment`:="testing" kind:in("2","5") '
            '| stats by (trace_id, span_id) max(duration) as duration, max(status_code) as status_code '
            '| stats count() as requests, count() if (status_code:="2") as errors, '
            'quantile(0.95, duration) as p95, quantile(0.99, duration) as p99'
        )
        stats_status, stats_body = _query(
            f"http://127.0.0.1:{traces_port}/select/logsql/stats_query",
            query=stats_query,
            start=(datetime.now(UTC) - timedelta(hours=1)).isoformat(),
            end=(datetime.now(UTC) + timedelta(minutes=1)).isoformat(),
        )
        assert stats_status == 200, stats_body
        values = _vector_values(stats_body)
        assert values == {
            "requests": 4,
            "errors": 0,
            "p95": 20_000_000,
            "p99": 20_000_000,
        }

        activity_query = (
            '`resource_attr:service.name`:* '
            '| stats by (`resource_attr:service.namespace`, `resource_attr:service.name`, '
            '`resource_attr:service.instance.id`, `resource_attr:deployment.environment`, '
            '`resource_attr:service.version`) max(end_time_unix_nano) as last_seen '
            '| sort by (last_seen) desc | limit 10000'
        )
        activity_status, activity_body = _query(
            f"http://127.0.0.1:{traces_port}/select/logsql/query",
            query=activity_query,
            start=(datetime.now(UTC) - timedelta(hours=1)).isoformat(),
            end=(datetime.now(UTC) + timedelta(minutes=1)).isoformat(),
            limit=10000,
        )
        assert activity_status == 200, activity_body
        activities = [json.loads(line) for line in activity_body.splitlines()]
        assert any(
            item.get("resource_attr:service.name") == "apm-nats-contract"
            and item.get("resource_attr:service.instance.id") == "contract-instance"
            and item.get("resource_attr:service.version") == "1.2.3"
            for item in activities
        )
    finally:
        subprocess.run(
            [*compose, "down", "--volumes", "--remove-orphans"],
            cwd=REPOSITORY_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
