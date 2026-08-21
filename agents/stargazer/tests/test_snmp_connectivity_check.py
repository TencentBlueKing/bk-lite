import argparse

import pytest

from scripts import snmp_connectivity_check as check


def test_expand_targets_supports_cidr_range_and_deduplicates():
    targets = check.expand_targets(
        ["192.0.2.0/30,192.0.2.2", "192.0.2.5-192.0.2.6"],
        max_hosts=10,
    )

    assert targets == ["192.0.2.1", "192.0.2.2", "192.0.2.5", "192.0.2.6"]


def test_expand_targets_rejects_oversized_input_before_scanning():
    with pytest.raises(ValueError, match="超过安全上限 4"):
        check.expand_targets(["192.0.2.0/29"], max_hosts=4)


def test_build_credential_reads_secret_from_environment(monkeypatch):
    monkeypatch.setenv("TEST_SNMP_COMMUNITY", "not-logged-secret")
    args = argparse.Namespace(
        version="v2c",
        community=None,
        community_env="TEST_SNMP_COMMUNITY",
        username=None,
        username_env=None,
        level="authNoPriv",
        integrity="sha",
        privacy="aes",
        auth_key=None,
        auth_key_env=None,
        priv_key=None,
        priv_key_env=None,
    )

    assert check.build_credential(args) == {
        "version": "v2c",
        "community": "not-logged-secret",
    }


def test_build_credential_rejects_missing_v2c_community():
    args = argparse.Namespace(
        version="v2c",
        community=None,
        community_env=None,
        username=None,
        username_env=None,
        level="authNoPriv",
        integrity="sha",
        privacy="aes",
        auth_key=None,
        auth_key_env=None,
        priv_key=None,
        priv_key_env=None,
    )

    with pytest.raises(ValueError, match="community"):
        check.build_credential(args)


@pytest.mark.asyncio
async def test_probe_host_reports_success_without_exposing_credential():
    async def fake_snmp_get(_host, _port, _timeout, _retries, _credential):
        return None, 0, 0, [("oid", "switch-a")]

    result = await check.probe_host(
        "192.0.2.10",
        port=161,
        timeout=1,
        retries=0,
        credential={"version": "v2c", "community": "secret"},
        snmp_get=fake_snmp_get,
        route_probe=lambda _host, _port: (True, "route_ok"),
    )

    assert result.status == "success"
    assert result.sys_name == "switch-a"
    assert "secret" not in str(result)


@pytest.mark.asyncio
async def test_probe_host_does_not_mislabel_snmp_timeout_as_network_failure():
    async def fake_snmp_get(_host, _port, _timeout, _retries, _credential):
        return "No SNMP response received before timeout", 0, 0, []

    result = await check.probe_host(
        "192.0.2.10",
        port=161,
        timeout=1,
        retries=0,
        credential={"version": "v2c", "community": "secret"},
        snmp_get=fake_snmp_get,
        route_probe=lambda _host, _port: (True, "route_ok"),
    )

    assert result.status == "snmp_timeout"
    assert "网络/ACL" in result.detail
    assert "community" in result.detail


@pytest.mark.asyncio
async def test_probe_host_reports_local_route_failure_without_snmp_request():
    called = False

    async def fake_snmp_get(*_args):
        nonlocal called
        called = True
        raise AssertionError("不应发起 SNMP 请求")

    result = await check.probe_host(
        "192.0.2.10",
        port=161,
        timeout=1,
        retries=0,
        credential={"version": "v2c", "community": "secret"},
        snmp_get=fake_snmp_get,
        route_probe=lambda _host, _port: (False, "Network is unreachable"),
    )

    assert result.status == "network_unreachable"
    assert called is False


@pytest.mark.asyncio
async def test_probe_host_redacts_credential_from_sdk_exception():
    async def fake_snmp_get(_host, _port, _timeout, _retries, _credential):
        raise RuntimeError("SDK rejected community secret-value")

    result = await check.probe_host(
        "192.0.2.10",
        port=161,
        timeout=1,
        retries=0,
        credential={"version": "v2c", "community": "secret-value"},
        snmp_get=fake_snmp_get,
        route_probe=lambda _host, _port: (True, "route_ok"),
    )

    assert "secret-value" not in result.detail
    assert "[REDACTED]" in result.detail
