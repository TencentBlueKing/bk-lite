import pytest

from core.collection.contracts import AccessProbeStatus
from plugins.inputs.network.snmp_facts import SnmpFacts


def _make_facts(**overrides):
    params = {
        "host": "127.0.0.1",
        "version": "v2",
        "community": "public",
        "snmp_port": 161,
        "timeout": 1,
        "retries": 0,
    }
    params.update(overrides)
    return SnmpFacts(params)


@pytest.mark.asyncio
async def test_snmp_probe_maps_timeout_indication_to_no_response(monkeypatch):
    facts = _make_facts()

    async def fake_get_cmd(*_args, **_kwargs):
        return ("No SNMP response received before timeout", 0, 0, [])

    monkeypatch.setattr("plugins.inputs.network.snmp_facts.getCmd", fake_get_cmd)
    result = await facts.probe()
    assert result.status == AccessProbeStatus.NO_RESPONSE
    assert result.error_code == "protocol_no_response"


@pytest.mark.asyncio
async def test_snmp_probe_ready_on_successful_get(monkeypatch):
    facts = _make_facts()

    class FakeOid:
        def prettyPrint(self):
            return "1.3.6.1.2.1.1.5.0"

    class FakeVal:
        def prettyPrint(self):
            return "switch-a"

    async def fake_get_cmd(*_args, **_kwargs):
        return (None, 0, 0, [(FakeOid(), FakeVal())])

    monkeypatch.setattr("plugins.inputs.network.snmp_facts.getCmd", fake_get_cmd)
    result = await facts.probe()
    assert result.status == AccessProbeStatus.READY


@pytest.mark.asyncio
async def test_snmp_probe_uses_fixed_timeout_5_retries_2(monkeypatch):
    facts = _make_facts(timeout=1, retries=0)
    captured = {}

    async def fake_get_cmd(_engine, _auth, target, *_args, **_kwargs):
        captured["target"] = target
        return ("No SNMP response received before timeout", 0, 0, [])

    def fake_udp(address, **kwargs):
        captured["opts"] = kwargs
        return ("udp", address, kwargs)

    monkeypatch.setattr("plugins.inputs.network.snmp_facts.getCmd", fake_get_cmd)
    monkeypatch.setattr(
        "plugins.inputs.network.snmp_facts.UdpTransportTarget",
        fake_udp,
    )
    await facts.probe()
    assert captured["opts"] == {"timeout": 5, "retries": 2}


@pytest.mark.asyncio
async def test_snmp_probe_is_native_async(monkeypatch):
    facts = _make_facts()

    async def fake_get_cmd(*_args, **_kwargs):
        return (None, 0, 0, [("oid", "val")])

    monkeypatch.setattr("plugins.inputs.network.snmp_facts.getCmd", fake_get_cmd)
    result = await facts.probe()
    assert result.status == AccessProbeStatus.READY
