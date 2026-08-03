"""真实容器契约测试。

显式设置 RUN_APM_CONTAINER_CONTRACT=1 后运行；测试只创建独立 Compose project，
并在结束时删除由该 project 创建的容器、网络和卷。
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_APM_CONTAINER_CONTRACT") != "1",
    reason="set RUN_APM_CONTAINER_CONTRACT=1 to run real APM containers",
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
COMPOSE_FILE = REPOSITORY_ROOT / "deploy/apm/compose.yaml"
VALID_TOKEN = "bkapm_contract_token"
TRUSTED_SOURCE_ID = "11111111-2222-4333-8444-555555555555"


class _AuthHandler(BaseHTTPRequestHandler):
    enabled = True
    unavailable = False
    calls = 0

    def do_GET(self):  # noqa: N802 - http.server contract
        type(self).calls += 1
        if self.path != "/api/v1/apm/machine-auth/":
            self.send_response(404)
        elif type(self).unavailable:
            self.send_response(503)
        elif type(self).enabled and self.headers.get("Authorization") == f"Bearer {VALID_TOKEN}":
            self.send_response(204)
            self.send_header("X-BK-Ingest-Source-Id", TRUSTED_SOURCE_ID)
            self.send_header("Cache-Control", "private, max-age=8")
        else:
            self.send_response(401)
        self.end_headers()

    def log_message(self, _format, *_args):
        return


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


def _trace_payload(trace_id: str, service_name: str, *, is_error: bool) -> bytes:
    started_at = time.time_ns()
    payload = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.namespace", "value": {"stringValue": "contract"}},
                        {"key": "service.name", "value": {"stringValue": service_name}},
                        {"key": "service.instance.id", "value": {"stringValue": "contract-instance"}},
                        {"key": "deployment.environment", "value": {"stringValue": "testing"}},
                        {"key": "bk.ingest_source.id", "value": {"stringValue": "forged-resource"}},
                        {"key": "bk.organization.id", "value": {"stringValue": "forged-organization"}},
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {
                            "name": "bk-lite-apm-contract",
                            "attributes": [
                                {"key": "bk.ingest_source.id", "value": {"stringValue": "forged-scope"}}
                            ],
                        },
                        "spans": [
                            {
                                "traceId": trace_id,
                                "spanId": trace_id[-16:],
                                "name": "GET /orders/12345?token=secret",
                                "kind": 2,
                                "startTimeUnixNano": str(started_at),
                                "endTimeUnixNano": str(started_at + 20_000_000),
                                "attributes": [
                                    {"key": "http.request.method", "value": {"stringValue": "GET"}},
                                    {"key": "http.route", "value": {"stringValue": "/orders/{order_id}"}},
                                    {"key": "bk.ingest_source.id", "value": {"stringValue": "forged-span"}},
                                    {"key": "user.id", "value": {"stringValue": "unbounded-user"}},
                                ],
                                "events": [
                                    {
                                        "timeUnixNano": str(started_at + 1_000_000),
                                        "name": "contract-event",
                                        "attributes": [
                                            {
                                                "key": "bk.ingest_source.id",
                                                "value": {"stringValue": "forged-event"},
                                            }
                                        ],
                                    }
                                ],
                                "status": {"code": 2 if is_error else 1},
                            }
                        ],
                    }
                ],
            }
        ]
    }
    return json.dumps(payload).encode()


def _post_trace(edge_port: int, trace_id: str, service_name: str, *, token: str | None, is_error: bool):
    headers = {
        "Content-Type": "application/json",
        "X-BK-Ingest-Source-Id": "forged-header",
    }
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return _request(
        f"http://127.0.0.1:{edge_port}/v1/traces",
        data=_trace_payload(trace_id, service_name, is_error=is_error),
        headers=headers,
    )


def _post_empty_grpc_trace(edge_port: int, *, token: str | None):
    # gRPC frame: uncompressed flag + uint32 message length + empty ExportTraceServiceRequest.
    with tempfile.NamedTemporaryFile() as payload:
        payload.write(b"\x00\x00\x00\x00\x00")
        payload.flush()
        command = [
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
        ]
        if token is not None:
            command.extend(("--header", f"Authorization: Bearer {token}"))
        command.append(
            f"http://127.0.0.1:{edge_port}/opentelemetry.proto.collector.trace.v1.TraceService/Export"
        )
        completed = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
    status_line = next((line for line in completed.stdout.splitlines() if line.startswith("HTTP/")), "")
    return completed.returncode, status_line, completed.stdout, completed.stderr


def _eventually(fetch, predicate, *, timeout: float = 45):
    deadline = time.monotonic() + timeout
    last_value = None
    while time.monotonic() < deadline:
        last_value = fetch()
        if predicate(last_value):
            return last_value
        time.sleep(1)
    raise AssertionError(f"condition not met before timeout; last value={last_value!r}")


def test_otlp_reaches_trace_and_metric_stores_with_trusted_identity():
    _AuthHandler.enabled = True
    _AuthHandler.unavailable = False
    _AuthHandler.calls = 0
    project = f"bk-lite-apm-contract-{os.getpid()}"
    edge_port = _free_port()
    grpc_port = _free_port()
    traces_port = _free_port()
    metrics_port = _free_port()
    auth_server = ThreadingHTTPServer(("0.0.0.0", 0), _AuthHandler)
    auth_thread = threading.Thread(target=auth_server.serve_forever, daemon=True)
    auth_thread.start()

    environment = os.environ.copy()
    environment.update(
        {
            "APM_SERVER_UPSTREAM": f"http://host.docker.internal:{auth_server.server_port}",
            "APM_OTLP_HTTP_BIND": "127.0.0.1",
            "APM_OTLP_HTTP_PORT": str(edge_port),
            "APM_OTLP_GRPC_BIND": "127.0.0.1",
            "APM_OTLP_GRPC_PORT": str(grpc_port),
            "APM_VICTORIATRACES_QUERY_PORT": str(traces_port),
            "APM_VICTORIAMETRICS_QUERY_PORT": str(metrics_port),
            "APM_VICTORIAMETRICS_WRITE_ENDPOINT": "http://apm-victoriametrics:8428/api/v1/write",
            "APM_NORMAL_TRACE_SAMPLE_PERCENT": "0",
            "APM_TAIL_DECISION_WAIT": "1s",
        }
    )
    compose = [
        "docker",
        "compose",
        "--project-name",
        project,
        "-f",
        str(COMPOSE_FILE),
        "--profile",
        "standalone-metrics",
    ]

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

        assert _post_trace(edge_port, "0" * 31 + "1", "unauthorized", token=None, is_error=True)[0] == 401
        assert _post_trace(edge_port, "0" * 31 + "2", "wrong-token", token="wrong", is_error=True)[0] == 401
        grpc_missing = _post_empty_grpc_trace(grpc_port, token=None)
        grpc_valid = _post_empty_grpc_trace(grpc_port, token=VALID_TOKEN)
        assert " 401 " in grpc_missing[1], grpc_missing
        assert grpc_valid[0] == 0 and " 200 " in grpc_valid[1], grpc_valid
        assert "grpc-status: 0" in grpc_valid[2].lower(), grpc_valid

        error_trace_id = "0123456789abcdef0123456789abcdef"
        unsampled_trace_id = "fedcba9876543210fedcba9876543210"
        assert _post_trace(
            edge_port,
            error_trace_id,
            "apm-contract-error",
            token=VALID_TOKEN,
            is_error=True,
        )[0] == 200
        assert _post_trace(
            edge_port,
            unsampled_trace_id,
            "apm-contract-unsampled",
            token=VALID_TOKEN,
            is_error=False,
        )[0] == 200

        # 正向结果应由边缘缓存；禁用后的撤销窗口不超过 10 秒。
        _AuthHandler.enabled = False
        assert _post_trace(
            edge_port,
            "0" * 31 + "3",
            "cached-auth",
            token=VALID_TOKEN,
            is_error=True,
        )[0] == 200
        time.sleep(9.5)
        assert _post_trace(
            edge_port,
            "0" * 31 + "4",
            "revoked-auth",
            token=VALID_TOKEN,
            is_error=True,
        )[0] == 401
        _AuthHandler.enabled = True
        _AuthHandler.unavailable = True
        assert _post_trace(
            edge_port,
            "0" * 31 + "5",
            "unavailable-auth",
            token="uncached-token",
            is_error=True,
        )[0] == 503
        _AuthHandler.unavailable = False

        trace_url = f"http://127.0.0.1:{traces_port}/select/tempo/api/v2/traces/{error_trace_id}"
        trace_status, trace_body = _eventually(
            lambda: _request(trace_url),
            lambda value: value[0] == 200 and TRUSTED_SOURCE_ID in value[1],
        )
        assert trace_status == 200
        assert "forged-header" not in trace_body
        assert "forged-resource" not in trace_body
        assert "forged-span" not in trace_body
        assert "forged-scope" not in trace_body
        assert "forged-event" not in trace_body
        assert "forged-organization" not in trace_body

        unsampled_url = f"http://127.0.0.1:{traces_port}/select/tempo/api/v2/traces/{unsampled_trace_id}"
        unsampled_status, unsampled_body = _request(unsampled_url)
        assert unsampled_status != 200 or "apm-contract-unsampled" not in unsampled_body

        metric_url = (
            f"http://127.0.0.1:{metrics_port}/api/v1/series?"
            + urllib.parse.urlencode({"match[]": '{__name__=~"bklite_apm_.*"}'})
        )
        _, metric_body = _eventually(
            lambda: _request(metric_url),
            lambda value: value[0] == 200 and "apm-contract-unsampled" in value[1],
        )
        assert TRUSTED_SOURCE_ID in metric_body
        assert "unbounded-user" not in metric_body
    finally:
        auth_server.shutdown()
        auth_server.server_close()
        subprocess.run(
            [*compose, "down", "--volumes", "--remove-orphans"],
            cwd=REPOSITORY_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
