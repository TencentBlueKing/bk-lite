"""区域 Collector -> JetStream -> 系统 Collector -> VictoriaTraces 容器契约。"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import tempfile
import time
import urllib.error
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
    except urllib.error.URLError as error:
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
                            }
                        ],
                    }
                ],
            }
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
        last_value = fetch()
        if predicate(last_value):
            return last_value
        time.sleep(1)
    raise AssertionError(f"condition not met before timeout; last value={last_value!r}")


def _jetstream_state(port: int):
    status, body = _request(f"http://127.0.0.1:{port}/jsz?streams=true&consumers=true")
    assert status == 200, body
    detail = json.loads(body)["account_details"][0]["stream_detail"][0]
    return detail["state"], detail["consumer_detail"][0]


def test_trace_crosses_bounded_jetstream_and_reaches_victoria_traces_once():
    project = f"bk-lite-apm-contract-{os.getpid()}"
    http_port = _free_port()
    grpc_port = _free_port()
    traces_port = _free_port()
    nats_monitor_port = _free_port()
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
        started = subprocess.run(
            [*compose, "up", "-d", "--wait", "--wait-timeout", "120"],
            cwd=REPOSITORY_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert started.returncode == 0, f"{started.stdout}\n{started.stderr}"

        assert _post_trace(http_port, payload)[0] == 200
        grpc = _post_empty_grpc_trace(grpc_port)
        assert grpc.returncode == 0, grpc.stderr
        assert "grpc-status: 0" in grpc.stdout.lower(), grpc.stdout

        state, consumer = _eventually(
            lambda: _jetstream_state(nats_monitor_port),
            lambda value: value[0]["messages"] == 1
            and value[1]["ack_floor"]["stream_seq"] == 1
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
        assert duplicate_state["last_seq"] == state["last_seq"] == 1
        assert duplicate_consumer["ack_floor"]["stream_seq"] == 1
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
