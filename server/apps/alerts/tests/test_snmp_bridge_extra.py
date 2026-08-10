"""SNMP Trap bridge 解析/投递补充覆盖测试。

对照 specs/capabilities/legacy-prd-告警中心-集成.md：SNMP trap 经 bridge 归一化为标准事件并投递到接收器。
"""

import pytest

from apps.alerts.service import snmp_trap_bridge as bridge


# --------------------------------------------------------------------------
# varbinds / trap_oid / title
# --------------------------------------------------------------------------


def test_extract_varbinds_basic():
    vb = bridge._extract_varbinds("ifName=Gi0/1 ifIndex=3, IF-MIB::ifOperStatus=down")
    assert vb["ifname"] == "Gi0/1"
    assert vb["ifindex"] == "3"
    assert vb["ifoperstatus"] == "down"


def test_extract_varbinds_empty():
    assert bridge._extract_varbinds("") == {}
    assert bridge._extract_varbinds("no key value pairs here") == {}


def test_extract_trap_oid_from_varbind():
    oid = bridge._extract_trap_oid("snmpTrapOID.0=1.3.6.1.6.3.1.1.5.3")
    assert oid == "1.3.6.1.6.3.1.1.5.3"


def test_extract_trap_oid_token_scan():
    oid = bridge._extract_trap_oid("trap fired 1.3.6.1.4.1.9 details")
    assert oid == "1.3.6.1.4.1.9"


def test_extract_trap_oid_none():
    assert bridge._extract_trap_oid("") is None
    assert bridge._extract_trap_oid("no oid here") is None


def test_build_title_with_instance():
    rule = {"normalized_key": "link_down"}
    resource = {"resource_name": "sw1", "resource_id": "sw1"}
    title = bridge._build_title(rule, resource, {"instance_key": "Gi0/1"})
    assert "link_down" in title
    assert "Gi0/1" in title


def test_build_title_without_instance():
    rule = {"normalized_key": "link_down"}
    resource = {"resource_name": "sw1", "resource_id": "sw1"}
    title = bridge._build_title(rule, resource, {})
    assert "Gi0/1" not in title
    assert "sw1" in title


# --------------------------------------------------------------------------
# resolve_rule / resolve_resource_identity
# --------------------------------------------------------------------------


def test_resolve_rule_known():
    rule = bridge.resolve_rule({"normalized_key": "linkdown"})
    assert rule["normalized_key"] == "link_down"


def test_resolve_rule_unknown_default():
    assert bridge.resolve_rule({})["normalized_key"] == "unknown_trap"


def test_resolve_resource_identity_falls_back_to_node_ip():
    rule = bridge.RULES["linkdown"]
    resource = bridge.resolve_resource_identity({"node_ip": "10.0.0.1"}, {}, rule)
    assert resource["resource_id"] == "10.0.0.1"
    assert resource["resource_type"] == "network_device"


def test_resolve_resource_identity_unknown():
    rule = bridge.RULES["linkdown"]
    resource = bridge.resolve_resource_identity({}, {}, rule)
    assert resource["resource_id"] == "unknown"


# --------------------------------------------------------------------------
# send_to_alerts retry behavior
# --------------------------------------------------------------------------


def test_send_to_alerts_success(monkeypatch):
    calls = {"n": 0}

    class FakeResp:
        def raise_for_status(self):
            return None

    def fake_post(*a, **k):
        calls["n"] += 1
        return FakeResp()

    monkeypatch.setattr(bridge.requests, "post", fake_post)
    bridge.send_to_alerts({"events": []}, {"webhook_url": "http://x", "secret": "s", "max_retries": 3, "timeout": 5})
    assert calls["n"] == 1


def test_send_to_alerts_retries_then_raises(monkeypatch):
    calls = {"n": 0}

    def fake_post(*a, **k):
        calls["n"] += 1
        raise bridge.requests.RequestException("boom")

    monkeypatch.setattr(bridge.requests, "post", fake_post)
    with pytest.raises(bridge.requests.RequestException):
        bridge.send_to_alerts({"events": []}, {"webhook_url": "http://x", "secret": "s", "max_retries": 3, "timeout": 5})
    assert calls["n"] == 3


# --------------------------------------------------------------------------
# handle_vector_message
# --------------------------------------------------------------------------


def test_handle_vector_message_non_snmp_returns_false():
    assert bridge.handle_vector_message({"collect_type": "log"}, {}) is False


def test_handle_vector_message_success(monkeypatch):
    sent = {}

    def fake_send(payload, config):
        sent["payload"] = payload

    monkeypatch.setattr(bridge, "send_to_alerts", fake_send)
    payload = {"collect_type": "snmp_trap", "trap_message": "linkDown ifName=Gi0/1", "node_ip": "10.0.0.1"}
    result = bridge.handle_vector_message(payload, {"push_source_id": "x"})
    assert result is True
    assert "events" in sent["payload"]
