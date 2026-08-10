import pytest

from core.collection.contracts import AccessProbeStatus
from plugins.inputs.network.snmp_facts import SnmpFacts


def test_snmp_probe_maps_timeout_indication_to_no_response(monkeypatch):
    facts = SnmpFacts(
        {
            "host": "127.0.0.1",
            "version": "v2",
            "community": "public",
            "snmp_port": 161,
            "timeout": 1,
            "retries": 0,
        }
    )

    class FakeCmdGen:
        def getCmd(self, *_args, **_kwargs):
            return ("No SNMP response received before timeout", 0, 0, ())

    monkeypatch.setattr(
        "plugins.inputs.network.snmp_facts.cmdgen.CommandGenerator",
        FakeCmdGen,
    )
    result = facts._probe_sync()
    assert result.status == AccessProbeStatus.NO_RESPONSE
    assert result.error_code == "protocol_no_response"


def test_snmp_probe_ready_on_successful_get(monkeypatch):
    facts = SnmpFacts(
        {
            "host": "127.0.0.1",
            "version": "v2",
            "community": "public",
            "snmp_port": 161,
            "timeout": 1,
            "retries": 0,
        }
    )

    class FakeOid:
        def prettyPrint(self):
            return "1.3.6.1.2.1.1.5.0"

    class FakeVal:
        def prettyPrint(self):
            return "switch-a"

    class FakeCmdGen:
        def getCmd(self, *_args, **_kwargs):
            return (None, 0, 0, [(FakeOid(), FakeVal())])

    monkeypatch.setattr(
        "plugins.inputs.network.snmp_facts.cmdgen.CommandGenerator",
        FakeCmdGen,
    )
    result = facts._probe_sync()
    assert result.status == AccessProbeStatus.READY


@pytest.mark.asyncio
async def test_snmp_probe_uses_to_thread(monkeypatch):
    facts = SnmpFacts(
        {
            "host": "127.0.0.1",
            "version": "v2",
            "community": "public",
            "snmp_port": 161,
        }
    )
    called = {"sync": False}

    def fake_sync():
        called["sync"] = True
        from core.collection.contracts import (
            AccessProbeResult,
            AccessProbeStatus,
        )

        return AccessProbeResult(status=AccessProbeStatus.READY)

    monkeypatch.setattr(facts, "_probe_sync", fake_sync)
    result = await facts.probe()
    assert called["sync"] is True
    assert result.status == AccessProbeStatus.READY
