import asyncio
import socket
import ssl

import pytest
from core.collection.contracts import PreflightStatus
from core.collection.preflight import AsyncProtocolPreflight
from core.collection.runtime import CollectionRequest
from core.infra.outbound_policy import OutboundTargetPolicy, OutboundTargetRejected


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

    result = await AsyncProtocolPreflight(reachability_enabled=True).check(
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

    result = await AsyncProtocolPreflight(
        policy=Policy(), reachability_enabled=True
    ).check("api.example.test", request, timeout_seconds=5)

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

    result = await AsyncProtocolPreflight(
        policy=Policy(), reachability_enabled=True
    ).check("api.example.test", request, timeout_seconds=5)

    assert result.status == PreflightStatus.UNREACHABLE
    assert result.error_code == "tls_validation_failed"
    assert result.detail == "SSLCertVerificationError"


@pytest.mark.asyncio
async def test_cloud_and_udp_preflight_do_not_use_icmp_or_tcp(monkeypatch):
    async def unexpected_open_connection(*args, **kwargs):
        raise AssertionError("TCP must not be used")

    monkeypatch.setattr(asyncio, "open_connection", unexpected_open_connection)

    class Policy:
        async def resolve_allowed(self, host, port=0):
            assert host == "10.10.24.20"
            return host

        def validate_trusted_domains(self, domains):
            assert domains == ("tencentcloudapi.com",)
            return domains

    probe = AsyncProtocolPreflight(policy=Policy())
    cloud = CollectionRequest(
        task_id="probe-cloud",
        plugin_ref="qcloud.monitor",
        targets=("qcloud-account",),
        params={
            "preflight_kind": "cloud",
            "target_is_logical": True,
            "target_policy_mode": "cloud_endpoint",
            "trusted_endpoint_domains": ("tencentcloudapi.com",),
            "_yaml_target_policy_verified": True,
        },
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
async def test_logical_instance_id_is_not_resolved_as_https_hostname():
    calls = []

    class Policy:
        async def resolve_allowed(self, host, port=0):
            calls.append((host, port))
            raise AssertionError("logical instance id must not enter DNS policy")

    request = CollectionRequest(
        task_id="vmware-missing-host",
        plugin_ref="vmware_vc.config",
        targets=("cmdb_6",),
        params={
            "model_id": "vmware_vc",
            "preflight_kind": "https",
            "target_is_logical": True,
            "port": 443,
        },
    )

    result = await AsyncProtocolPreflight(policy=Policy()).check(
        "cmdb_6", request, timeout_seconds=1
    )

    assert result.status == PreflightStatus.UNREACHABLE
    assert result.error_code == "network_target_missing"
    assert result.detail == "logical target is not a network endpoint"
    assert calls == []


@pytest.mark.asyncio
async def test_untrusted_logical_flag_cannot_bypass_outbound_policy():
    request = CollectionRequest(
        task_id="logical-bypass",
        plugin_ref="network.config",
        targets=("8.8.8.8",),
        params={"preflight_kind": "skip", "target_is_logical": True},
    )
    policy = OutboundTargetPolicy(allowed_cidrs=("10.0.0.0/8",))

    result = await AsyncProtocolPreflight(policy=policy).check(
        "8.8.8.8", request, timeout_seconds=1
    )

    assert result.status == PreflightStatus.UNREACHABLE
    assert result.error_code == "outbound_target_rejected"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ("skip", "cloud", "snmp", "udp"))
async def test_non_dial_preflight_modes_still_enforce_outbound_policy(kind):
    request = CollectionRequest(
        task_id=f"outbound-{kind}",
        plugin_ref="network.config",
        targets=("8.8.8.8",),
        params={"preflight_kind": kind, "port": 161},
    )
    policy = OutboundTargetPolicy(allowed_cidrs=("10.0.0.0/8",))

    result = await AsyncProtocolPreflight(
        policy=policy, reachability_enabled=False
    ).check("8.8.8.8", request, timeout_seconds=1)

    assert result.status == PreflightStatus.UNREACHABLE
    assert result.error_code == "outbound_target_rejected"


@pytest.mark.asyncio
async def test_cloud_endpoint_policy_validates_url_hostname_without_dial(monkeypatch):
    calls = []

    class Policy:
        async def resolve_allowed(self, host, port=0):
            calls.append((host, port))
            return host

    async def unexpected_open(*_args, **_kwargs):
        raise AssertionError("cloud endpoint validation must not dial")

    monkeypatch.setattr(asyncio, "open_connection", unexpected_open)
    request = CollectionRequest(
        task_id="cloud-endpoint-policy",
        plugin_ref="qcloud.config",
        targets=("cloud.example.test",),
        params={
            "preflight_kind": "cloud",
            "base_url": "https://cloud.example.test:8443/v1",
        },
    )

    result = await AsyncProtocolPreflight(policy=Policy()).check(
        "cloud.example.test", request, timeout_seconds=1
    )

    assert result.status == PreflightStatus.UNKNOWN
    assert calls == [("cloud.example.test", 8443)]


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

    result = await AsyncProtocolPreflight(reachability_enabled=True).check(
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

    monkeypatch.setattr("core.collection.preflight.logger.info", capture)
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
async def test_mixed_allowed_and_rejected_dns_answers_fail_closed(monkeypatch):
    async def resolve(_host, _port, *, type):
        return [
            (socket.AF_INET, type, 6, "", ("10.0.0.8", 3306)),
            (socket.AF_INET, type, 6, "", ("127.0.0.1", 3306)),
        ]

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

    assert result.connect_host == "10.10.69.245"
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

    result = await AsyncProtocolPreflight(
        remote_probe=probe, reachability_enabled=True
    ).check("10.10.24.10", request, timeout_seconds=5)

    assert calls == [("executor-region-a", 5)]
    assert result.status == PreflightStatus.UNREACHABLE
    assert result.error_code == "remote_responder_unavailable"


@pytest.mark.asyncio
async def test_tcp_reachability_off_skips_dial_after_cidr(monkeypatch):
    async def unexpected_open(*args, **kwargs):
        raise AssertionError("tcp reachability must not dial when disabled")

    monkeypatch.setattr(asyncio, "open_connection", unexpected_open)
    request = CollectionRequest(
        task_id="probe-mysql-no-dial",
        plugin_ref="mysql.config",
        targets=("10.10.24.10",),
        params={"port": 3306, "preflight_kind": "tcp"},
    )

    result = await AsyncProtocolPreflight(reachability_enabled=False).check(
        "10.10.24.10", request, timeout_seconds=5
    )

    assert result.status == PreflightStatus.UNKNOWN
    assert "tcp reachability disabled" in (result.detail or "")


@pytest.mark.asyncio
async def test_tcp_reachability_off_still_rejects_cidr():
    request = CollectionRequest(
        task_id="probe-mysql-cidr",
        plugin_ref="mysql.config",
        targets=("8.8.8.8",),
        params={"port": 3306, "preflight_kind": "tcp"},
    )
    policy = OutboundTargetPolicy(allowed_cidrs=("10.0.0.0/8",))

    result = await AsyncProtocolPreflight(
        policy=policy, reachability_enabled=False
    ).check("8.8.8.8", request, timeout_seconds=1)

    assert result.status == PreflightStatus.UNREACHABLE
    assert result.error_code == "outbound_target_rejected"


@pytest.mark.asyncio
async def test_remote_skips_responder_but_keeps_outbound_policy_when_reachability_off():
    calls = []

    async def probe(node_id, *, timeout_seconds):
        calls.append((node_id, timeout_seconds))
        return False

    request = CollectionRequest(
        task_id="probe-remote-no-tcp",
        plugin_ref="host.monitor",
        targets=("10.10.24.10",),
        params={
            "preflight_kind": "remote",
            "ansible_node_id": "executor-region-a",
        },
    )

    result = await AsyncProtocolPreflight(
        remote_probe=probe, reachability_enabled=False
    ).check("10.10.24.10", request, timeout_seconds=5)

    assert calls == []
    assert result.status == PreflightStatus.UNKNOWN
    assert result.error_code == ""


def test_reachability_defaults_off(monkeypatch):
    monkeypatch.delenv("PREFLIGHT_REACHABILITY", raising=False)
    from core.collection.preflight import reachability_enabled_from_env

    assert reachability_enabled_from_env() is False
    monkeypatch.setenv("PREFLIGHT_REACHABILITY", "on")
    assert reachability_enabled_from_env() is True
