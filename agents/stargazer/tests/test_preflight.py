import asyncio
import socket
import ssl

import pytest
from core.collection.contracts import PreflightStatus
from core.collection.enums import FailureStage
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
        params={"port": "3306", "preflight_kind": "tcp", "ip_precheck": True},
    )

    result = await AsyncProtocolPreflight().check("10.10.24.10", request, timeout_seconds=5)

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
            "ip_precheck": True,
        },
    )

    result = await AsyncProtocolPreflight(policy=Policy()).check("api.example.test", request, timeout_seconds=5)

    assert result.status == PreflightStatus.REACHABLE
    assert calls == [("api.example.test", 8080, {})]


@pytest.mark.asyncio
async def test_https_preflight_uses_configured_port_for_bare_target(monkeypatch):
    calls = []
    writer = FakeWriter()

    class Policy:
        async def resolve_allowed(self, host, port=None):
            calls.append(("policy", host, port))
            return host

    async def fake_open_connection(host, port, **kwargs):
        calls.append(("connect", host, port))
        return object(), writer

    monkeypatch.setattr(asyncio, "open_connection", fake_open_connection)
    request = CollectionRequest(
        task_id="probe-hci-custom-port",
        plugin_ref="sangforhci.config",
        targets=("192.0.2.17",),
        params={"port": 8443, "preflight_kind": "https", "ip_precheck": True},
    )

    result = await AsyncProtocolPreflight(policy=Policy()).check("192.0.2.17", request, timeout_seconds=5)

    assert result.status == PreflightStatus.REACHABLE
    assert calls[0] == ("policy", "192.0.2.17", 8443)
    assert calls[1] == ("connect", "192.0.2.17", 8443)


@pytest.mark.asyncio
async def test_https_certificate_failure_still_reachable(monkeypatch):
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
        params={"preflight_kind": "https", "ip_precheck": True},
    )

    result = await AsyncProtocolPreflight(policy=Policy()).check("api.example.test", request, timeout_seconds=5)

    assert result.status == PreflightStatus.REACHABLE
    assert result.detail == "tls certificate deferred: SSLCertVerificationError"


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

    assert (await probe.check("qcloud-account", cloud, timeout_seconds=5)).status == PreflightStatus.UNKNOWN
    assert (await probe.check("10.10.24.20", snmp, timeout_seconds=5)).status == PreflightStatus.UNKNOWN


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

    result = await AsyncProtocolPreflight(policy=Policy()).check("cmdb_6", request, timeout_seconds=1)

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

    result = await AsyncProtocolPreflight(policy=policy).check("8.8.8.8", request, timeout_seconds=1)

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

    result = await AsyncProtocolPreflight(policy=policy).check("8.8.8.8", request, timeout_seconds=1)

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

    result = await AsyncProtocolPreflight(policy=Policy()).check("cloud.example.test", request, timeout_seconds=1)

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
        params={"port": 3306, "preflight_kind": "tcp", "ip_precheck": True},
    )

    result = await AsyncProtocolPreflight().check("10.10.24.30", request, timeout_seconds=5)

    assert result.status == PreflightStatus.UNREACHABLE
    assert result.error_code == "tcp_connection_refused"
    assert result.detail == "ConnectionRefusedError"
    assert result.failed_stage == FailureStage.IP_PRECHECK


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

    result = await AsyncProtocolPreflight(policy=policy).check("8.8.8.8", request, timeout_seconds=1)

    assert result.status == PreflightStatus.UNREACHABLE
    assert result.error_code == "outbound_target_rejected"
    assert result.failed_stage == FailureStage.OUTBOUND_POLICY
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
    result = await AsyncProtocolPreflight().check("10.10.69.245", request, timeout_seconds=5)

    assert result.connect_host == "10.10.69.245"
    assert result.status == PreflightStatus.UNKNOWN


@pytest.mark.asyncio
async def test_remote_preflight_dials_ssh_port_when_reachability_enabled(monkeypatch):
    connected = []

    async def fake_open_connection(host, port, **kwargs):
        connected.append((host, port))
        raise ConnectionRefusedError("refused")

    monkeypatch.setattr("core.collection.preflight.asyncio.open_connection", fake_open_connection)
    request = CollectionRequest(
        task_id="probe-remote",
        plugin_ref="host.monitor",
        targets=("10.10.24.10",),
        params={
            "preflight_kind": "remote",
            "ansible_node_id": "executor-region-a",
            "port": 22,
            "executor_node_ip": "10.0.0.1",
            "ip_precheck": True,
        },
    )

    result = await AsyncProtocolPreflight().check("10.10.24.10", request, timeout_seconds=5)

    assert connected == [("10.10.24.10", 22)]
    assert result.status == PreflightStatus.UNREACHABLE
    assert result.error_code == "tcp_connection_refused"


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

    result = await AsyncProtocolPreflight().check("10.10.24.10", request, timeout_seconds=5)

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

    result = await AsyncProtocolPreflight(policy=policy).check("8.8.8.8", request, timeout_seconds=1)

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

    result = await AsyncProtocolPreflight(remote_probe=probe).check("10.10.24.10", request, timeout_seconds=5)

    assert calls == []
    assert result.status == PreflightStatus.UNKNOWN
    assert result.error_code == ""


@pytest.mark.asyncio
async def test_environment_cannot_override_request_ip_precheck_off(monkeypatch):
    monkeypatch.setenv("PREFLIGHT_REACHABILITY", "on")
    calls = []

    async def fake_open_connection(*args, **kwargs):
        calls.append((args, kwargs))
        return object(), FakeWriter()

    monkeypatch.setattr("core.collection.preflight.asyncio.open_connection", fake_open_connection)
    request = CollectionRequest(
        task_id="request-precheck-off",
        plugin_ref="mysql.info",
        targets=("10.10.24.10",),
        params={"port": 3306, "preflight_kind": "tcp", "ip_precheck": False},
    )

    result = await AsyncProtocolPreflight().check("10.10.24.10", request, timeout_seconds=5)

    assert result.status == PreflightStatus.UNKNOWN
    assert calls == []


@pytest.mark.asyncio
async def test_ip_precheck_enables_tcp_dial_for_current_request(monkeypatch):
    connected = []

    async def fake_open_connection(host, port, **kwargs):
        connected.append((host, port))

        class _Writer:
            def close(self):
                return None

            async def wait_closed(self):
                return None

        return object(), _Writer()

    monkeypatch.setattr("core.collection.preflight.asyncio.open_connection", fake_open_connection)
    request = CollectionRequest(
        task_id="ip-precheck-on",
        plugin_ref="mysql.info",
        targets=("10.10.24.10",),
        params={"port": 3306, "preflight_kind": "tcp", "ip_precheck": True},
    )
    result = await AsyncProtocolPreflight().check("10.10.24.10", request, timeout_seconds=5)
    assert result.status == PreflightStatus.REACHABLE
    assert connected == [("10.10.24.10", 3306)]


@pytest.mark.asyncio
async def test_ip_precheck_off_skips_tcp_dial(monkeypatch):
    async def fail_open_connection(*args, **kwargs):
        raise AssertionError("should not dial")

    monkeypatch.setattr("core.collection.preflight.asyncio.open_connection", fail_open_connection)
    request = CollectionRequest(
        task_id="ip-precheck-off",
        plugin_ref="mysql.info",
        targets=("10.10.24.10",),
        params={"port": 3306, "preflight_kind": "tcp", "ip_precheck": False},
    )
    result = await AsyncProtocolPreflight().check("10.10.24.10", request, timeout_seconds=5)
    assert result.status == PreflightStatus.UNKNOWN


@pytest.mark.asyncio
async def test_remote_ip_precheck_skips_when_target_is_executor_node(monkeypatch):
    async def fail_open_connection(*args, **kwargs):
        raise AssertionError("local target should skip dial")

    monkeypatch.setattr("core.collection.preflight.asyncio.open_connection", fail_open_connection)
    request = CollectionRequest(
        task_id="remote-local-skip",
        plugin_ref="host.info",
        targets=("10.0.0.8",),
        params={
            "preflight_kind": "remote",
            "ip_precheck": True,
            "executor_node_ip": "10.0.0.8",
            "port": 22,
        },
    )
    result = await AsyncProtocolPreflight().check("10.0.0.8", request, timeout_seconds=5)
    assert result.status == PreflightStatus.REACHABLE


@pytest.mark.asyncio
async def test_remote_ip_precheck_dials_ssh_port(monkeypatch):
    connected = []

    async def fake_open_connection(host, port, **kwargs):
        connected.append((host, port))

        class _Writer:
            def close(self):
                return None

            async def wait_closed(self):
                return None

        return object(), _Writer()

    monkeypatch.setattr("core.collection.preflight.asyncio.open_connection", fake_open_connection)
    request = CollectionRequest(
        task_id="remote-ssh-dial",
        plugin_ref="host.info",
        targets=("10.10.24.20",),
        params={
            "preflight_kind": "remote",
            "ip_precheck": "true",
            "executor_node_ip": "10.0.0.8",
            "port": 22,
        },
    )
    result = await AsyncProtocolPreflight().check("10.10.24.20", request, timeout_seconds=5)
    assert result.status == PreflightStatus.REACHABLE
    assert connected == [("10.10.24.20", 22)]


@pytest.mark.asyncio
async def test_snmp_ip_precheck_off_still_skips_udp_probe(monkeypatch):
    async def fail_sendall(*args, **kwargs):
        raise AssertionError("snmp must not udp probe when ip_precheck off")

    monkeypatch.setattr("asyncio.BaseEventLoop.sock_sendall", fail_sendall)
    request = CollectionRequest(
        task_id="snmp-pass",
        plugin_ref="network.config",
        targets=("10.10.24.1",),
        params={"preflight_kind": "snmp", "ip_precheck": False, "port": 161},
    )
    result = await AsyncProtocolPreflight().check("10.10.24.1", request, timeout_seconds=5)
    assert result.status == PreflightStatus.UNKNOWN


@pytest.mark.asyncio
async def test_snmp_ip_precheck_on_defers_to_credential_probe_without_raw_udp(monkeypatch):
    async def fail_sendall(*args, **kwargs):
        raise AssertionError("SNMP target policy must not send a credential-free UDP probe")

    monkeypatch.setattr(asyncio.get_running_loop(), "sock_sendall", fail_sendall)
    request = CollectionRequest(
        task_id="snmp-precheck-on",
        plugin_ref="network.config",
        targets=("10.10.24.1",),
        params={"preflight_kind": "snmp", "ip_precheck": True, "port": 161},
    )
    result = await AsyncProtocolPreflight().check("10.10.24.1", request, timeout_seconds=1)
    assert result.status == PreflightStatus.UNKNOWN
    assert "credential-aware probe" in (result.detail or "")


@pytest.mark.asyncio
async def test_preflight_component_failure_passes(monkeypatch):
    secret = "preflight-" + "component-secret-sentinel"
    warning_calls = []

    async def boom(*args, **kwargs):
        raise RuntimeError("password=" + secret)

    monkeypatch.setattr("core.collection.preflight.asyncio.open_connection", boom)
    monkeypatch.setattr(
        "core.collection.preflight.logger.warning",
        lambda message, *args: warning_calls.append((message, args)),
    )
    request = CollectionRequest(
        task_id="preflight-crash",
        plugin_ref="mysql.info",
        targets=("10.10.24.10",),
        params={"port": 3306, "preflight_kind": "tcp", "ip_precheck": True},
    )
    result = await AsyncProtocolPreflight().check("10.10.24.10", request, timeout_seconds=5)
    assert result.status == PreflightStatus.UNKNOWN
    assert "preflight component failed" in (result.detail or "")
    rendered = [template % args for template, args in warning_calls]
    assert len(rendered) == 1
    assert "error_type=RuntimeError" in rendered[0]
    assert secret not in rendered[0]
