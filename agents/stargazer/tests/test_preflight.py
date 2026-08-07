import asyncio
import socket
import ssl

import pytest

from core.collection.runtime import CollectionRequest
from core.collection.preflight import AsyncProtocolPreflight
from core.infra.outbound_policy import OutboundTargetPolicy, OutboundTargetRejected
from core.collection.contracts import PreflightStatus


class FakeWriter:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True

    async def wait_closed(self):
        return None


@pytest.mark.asyncio
async def test_tcp_preflight_uses_protocol_port_and_closes_connection(monkeypatch):
    calls = []
    writer = FakeWriter()

    async def fake_open_connection(host, port, **kwargs):
        calls.append((host, port, kwargs))
        return object(), writer

    monkeypatch.setattr(asyncio, "open_connection", fake_open_connection)
    request = CollectionRequest(
        task_id="probe-mysql",
        plugin_ref="mysql.config",
        targets=("10.10.24.10",),
        params={"port": "3306", "preflight_kind": "tcp"},
    )

    result = await AsyncProtocolPreflight().check(
        "10.10.24.10", request, timeout_seconds=5
    )

    assert result.status == PreflightStatus.REACHABLE
    assert calls == [("10.10.24.10", 3306, {})]
    assert writer.closed is True


@pytest.mark.asyncio
async def test_http_preflight_uses_base_url_scheme_and_port(monkeypatch):
    calls = []
    writer = FakeWriter()

    class Policy:
        async def resolve_allowed(self, host, port=None):
            assert host == "api.example.test"
            assert port == 8080
            return host

    async def fake_open_connection(host, port, **kwargs):
        calls.append((host, port, kwargs))
        return object(), writer

    monkeypatch.setattr(asyncio, "open_connection", fake_open_connection)
    request = CollectionRequest(
        task_id="probe-http-base-url",
        plugin_ref="api.config",
        targets=("api.example.test",),
        params={
            "base_url": "http://api.example.test:8080/v1",
            "preflight_kind": "https",
        },
    )

    result = await AsyncProtocolPreflight(policy=Policy()).check(
        "api.example.test", request, timeout_seconds=5
    )

    assert result.status == PreflightStatus.REACHABLE
    assert calls == [("api.example.test", 8080, {})]


@pytest.mark.asyncio
async def test_https_certificate_failure_has_stable_error_code(monkeypatch):
    class Policy:
        async def resolve_allowed(self, host, port=None):
            return host

    async def certificate_rejected(*_args, **_kwargs):
        raise ssl.SSLCertVerificationError("certificate verify failed")

    monkeypatch.setattr(asyncio, "open_connection", certificate_rejected)
    request = CollectionRequest(
        task_id="probe-invalid-certificate",
        plugin_ref="api.config",
        targets=("api.example.test",),
        params={"preflight_kind": "https"},
    )

    result = await AsyncProtocolPreflight(policy=Policy()).check(
        "api.example.test", request, timeout_seconds=5
    )

    assert result.status == PreflightStatus.UNREACHABLE
    assert result.error_code == "tls_validation_failed"
    assert result.detail == "SSLCertVerificationError"


@pytest.mark.asyncio
async def test_cloud_and_udp_preflight_do_not_use_icmp_or_tcp(monkeypatch):
    async def unexpected_open_connection(*args, **kwargs):
        raise AssertionError("TCP must not be used")

    monkeypatch.setattr(asyncio, "open_connection", unexpected_open_connection)
    probe = AsyncProtocolPreflight()
    cloud = CollectionRequest(
        task_id="probe-cloud",
        plugin_ref="qcloud.monitor",
        targets=("qcloud-account",),
        params={"preflight_kind": "cloud"},
    )
    snmp = CollectionRequest(
        task_id="probe-snmp",
        plugin_ref="network.config",
        targets=("10.10.24.20",),
        params={"preflight_kind": "udp", "port": 161},
    )

    assert (
        await probe.check("qcloud-account", cloud, timeout_seconds=5)
    ).status == PreflightStatus.UNKNOWN
    assert (
        await probe.check("10.10.24.20", snmp, timeout_seconds=5)
    ).status == PreflightStatus.UNKNOWN


@pytest.mark.asyncio
async def test_tcp_preflight_returns_stable_unreachable_error(monkeypatch):
    async def refused(*args, **kwargs):
        raise ConnectionRefusedError

    monkeypatch.setattr(asyncio, "open_connection", refused)
    request = CollectionRequest(
        task_id="probe-refused",
        plugin_ref="mysql.config",
        targets=("10.10.24.30",),
        params={"port": 3306, "preflight_kind": "tcp"},
    )

    result = await AsyncProtocolPreflight().check(
        "10.10.24.30", request, timeout_seconds=5
    )

    assert result.status == PreflightStatus.UNREACHABLE
    assert result.error_code == "tcp_connection_refused"
    assert result.detail == "ConnectionRefusedError"


@pytest.mark.asyncio
async def test_outbound_rejected_target_is_logged(monkeypatch):
    logged = []

    def capture(message, *args):
        logged.append(message % args if args else message)

    monkeypatch.setattr(
        "core.collection.preflight.logger.info", capture
    )
    request = CollectionRequest(
        task_id="outbound-skip-log",
        plugin_ref="mysql.config",
        targets=("8.8.8.8",),
        params={"preflight_kind": "none", "port": 3306},
    )
    policy = OutboundTargetPolicy(allowed_cidrs=("10.0.0.0/8",))

    result = await AsyncProtocolPreflight(policy=policy).check(
        "8.8.8.8", request, timeout_seconds=1
    )

    assert result.status == PreflightStatus.UNREACHABLE
    assert result.error_code == "outbound_target_rejected"
    assert any("event=outbound_target_skipped" in item for item in logged)
    assert any("target=8.8.8.8" in item for item in logged)
    assert any("task_id=outbound-skip-log" in item for item in logged)


@pytest.mark.asyncio
async def test_allowed_domain_cannot_bypass_cidr_boundary_via_loopback_dns(
    monkeypatch,
):
    async def resolve(_host, _port, *, type):
        assert type == socket.SOCK_STREAM
        return [(socket.AF_INET, type, 6, "", ("127.0.0.1", 3306))]

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolve)
    policy = OutboundTargetPolicy(
        allowed_cidrs=("10.0.0.0/8",),
        allowed_domains=("trusted.example",),
    )

    with pytest.raises(OutboundTargetRejected):
        await policy.resolve_allowed("db.trusted.example", 3306)


@pytest.mark.asyncio
async def test_outbound_only_allows_after_cidr_without_tcp(monkeypatch):
    async def unexpected_open(*args, **kwargs):
        raise AssertionError("outbound_only must not dial")

    monkeypatch.setattr(asyncio, "open_connection", unexpected_open)
    request = CollectionRequest(
        task_id="outbound-only",
        plugin_ref="network.config",
        targets=("10.10.69.245",),
        params={"preflight_kind": "outbound_only", "port": 161},
    )
    result = await AsyncProtocolPreflight().check(
        "10.10.69.245", request, timeout_seconds=5
    )
    assert result.status == PreflightStatus.UNKNOWN


@pytest.mark.asyncio
async def test_remote_preflight_checks_cidr_then_responder():
    calls = []

    async def probe(node_id, *, timeout_seconds):
        calls.append((node_id, timeout_seconds))
        return False

    request = CollectionRequest(
        task_id="probe-remote",
        plugin_ref="host.monitor",
        targets=("10.10.24.10",),
        params={
            "preflight_kind": "remote",
            "ansible_node_id": "executor-region-a",
        },
    )

    result = await AsyncProtocolPreflight(remote_probe=probe).check(
        "10.10.24.10", request, timeout_seconds=5
    )

    assert calls == [("executor-region-a", 5)]
    assert result.status == PreflightStatus.UNREACHABLE
    assert result.error_code == "remote_responder_unavailable"
