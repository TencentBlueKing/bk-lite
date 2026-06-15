import pytest

from apps.alerts.models.alert_source import AlertSource
from apps.alerts.constants.constants import EventAction
from apps.alerts.service.snmp_trap_bridge import (
    build_event,
    build_external_id,
    build_webhook_payload,
    handle_vector_message,
    is_snmp_trap_message,
    load_bridge_config,
    parse_trap_message,
    resolve_rule,
)


def test_is_snmp_trap_message_true_by_collect_type():
    assert is_snmp_trap_message({"collect_type": "snmp_trap"}) is True


def test_is_snmp_trap_message_false():
    assert is_snmp_trap_message({"collect_type": "syslog", "event_type": "log"}) is False


def test_parse_trap_message_linkdown():
    parsed = parse_trap_message(
        {
            "trap_message": "SNMPv2-MIB::snmpTrapOID.0=SNMPv2-MIB::linkDown ifIndex=3 ifName=GE1/0/3",
            "node_ip": "10.0.0.8",
        }
    )
    assert parsed["normalized_key"] == "linkdown"
    assert parsed["instance_key"] == "GE1/0/3"


def test_parse_trap_message_extracts_numeric_trap_oid_from_varbind():
    parsed = parse_trap_message(
        {
            "trap_message": "SNMPv2-MIB::snmpTrapOID.0=1.3.6.1.6.3.1.1.5.3 linkDown ifIndex=3 ifName=GE1/0/3",
            "node_ip": "10.0.0.8",
        }
    )
    assert parsed["trap_oid"] == "1.3.6.1.6.3.1.1.5.3"


def test_resolve_rule_unknown():
    rule = resolve_rule({"normalized_key": None})
    assert rule["item"] == "snmp_trap:unknown_trap"
    assert rule["action"] == EventAction.CREATED


def test_build_external_id_stable():
    rule = {"normalized_key": "link_down"}
    resource = {"resource_id": "10.0.0.8"}
    parsed = {"trap_oid": "1.3.6.1.6.3.1.1.5.3", "instance_key": "ifIndex=3"}
    assert build_external_id(rule, resource, parsed) == build_external_id(rule, resource, parsed)


def test_build_external_id_same_for_linkdown_and_linkup_same_instance():
    resource = {"resource_id": "10.0.0.8"}
    down_rule = {"normalized_key": "link_down"}
    up_rule = {"normalized_key": "link_down"}
    down_parsed = {"trap_oid": "1.3.6.1.6.3.1.1.5.3", "instance_key": "GE1/0/3"}
    up_parsed = {"trap_oid": "1.3.6.1.6.3.1.1.5.4", "instance_key": "GE1/0/3"}

    assert build_external_id(down_rule, resource, down_parsed) == build_external_id(up_rule, resource, up_parsed)


def test_build_event_success():
    event = build_event(
        {
            "collect_type": "snmp_trap",
            "event_type": "snmp_trap",
            "trap_message": "SNMPv2-MIB::snmpTrapOID.0=SNMPv2-MIB::linkDown ifIndex=3 ifName=GE1/0/3",
            "timestamp": "1719912000",
            "received_at": "1719912001",
            "node_ip": "10.0.0.8",
            "collector": "Snmptrapd",
        }
    )

    assert event is not None
    assert event["item"] == "snmp_trap:link_down"
    assert event["action"] == EventAction.CREATED
    assert event["resource_id"] == "10.0.0.8"
    assert event["external_id"]


@pytest.mark.django_db
def test_load_bridge_config_uses_snmp_trap_source_secret_when_env_missing(monkeypatch):
    monkeypatch.delenv("SNMP_TRAP_ALERTS_SECRET", raising=False)
    AlertSource.objects.create(
        name="SNMP Trap",
        source_id="snmp_trap",
        source_type="restful",
        secret="source-secret",
        config={},
    )

    config = load_bridge_config()

    assert config["secret"] == "source-secret"


@pytest.mark.django_db
def test_load_bridge_config_prefers_env_secret(monkeypatch):
    monkeypatch.setenv("SNMP_TRAP_ALERTS_SECRET", "env-secret")
    AlertSource.objects.create(
        name="SNMP Trap",
        source_id="snmp_trap",
        source_type="restful",
        secret="source-secret",
        config={},
    )

    config = load_bridge_config()

    assert config["secret"] == "env-secret"


def test_build_event_non_snmp_returns_none():
    assert build_event({"collect_type": "syslog"}) is None


def test_build_webhook_payload():
    payload = build_webhook_payload({"title": "x"})
    assert payload == {"events": [{"title": "x"}]}


def test_handle_vector_message_ignored_non_snmp(monkeypatch):
    called = {"sent": False}

    def fake_send(*args, **kwargs):
        called["sent"] = True

    monkeypatch.setattr(
        "apps.alerts.service.snmp_trap_bridge.send_to_alerts",
        fake_send,
    )

    ok = handle_vector_message(
        {"collect_type": "syslog"},
        {"webhook_url": "http://x", "secret": "y", "push_source_id": "snmp_trap_bridge"},
    )

    assert ok is False
    assert called["sent"] is False


def test_handle_vector_message_success(monkeypatch):
    called = {"sent": False}

    def fake_send(payload, config):
        called["sent"] = True

    monkeypatch.setattr(
        "apps.alerts.service.snmp_trap_bridge.send_to_alerts",
        fake_send,
    )

    ok = handle_vector_message(
        {
            "collect_type": "snmp_trap",
            "event_type": "snmp_trap",
            "trap_message": "SNMPv2-MIB::snmpTrapOID.0=SNMPv2-MIB::linkDown ifIndex=3 ifName=GE1/0/3",
            "timestamp": "1719912000",
            "node_ip": "10.0.0.8",
        },
        {"webhook_url": "http://x", "secret": "y", "push_source_id": "snmp_trap_bridge"},
    )

    assert ok is True
    assert called["sent"] is True
