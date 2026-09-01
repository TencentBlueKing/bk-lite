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
async def test_snmp_probe_uses_fixed_timeout_10_retries_1(monkeypatch):
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
    assert captured["opts"] == {"timeout": 10, "retries": 1}


@pytest.mark.asyncio
async def test_snmp_probe_is_native_async(monkeypatch):
    facts = _make_facts()

    async def fake_get_cmd(*_args, **_kwargs):
        return (None, 0, 0, [("oid", "val")])

    monkeypatch.setattr("plugins.inputs.network.snmp_facts.getCmd", fake_get_cmd)
    result = await facts.probe()
    assert result.status == AccessProbeStatus.READY


@pytest.mark.asyncio
async def test_snmp_internal_exception_logs_target_and_sanitized_call_chain(monkeypatch):
    facts = _make_facts(
        model_id="network",
        plugin_name="snmp_facts",
        collection_task_id="snmp-task-7",
        collection_plugin_ref="network.config",
        _log_plugin_call_chain=True,
    )
    debug_logs = []
    error_logs = []

    async def broken_collect():
        raise RuntimeError("community=must-not-be-logged")

    def capture_error(message, *args):
        error_logs.append(message % args if args else message)

    monkeypatch.setattr(facts, "collect", broken_collect)
    monkeypatch.setattr(
        "plugins.inputs.network.snmp_facts.logger.debug",
        lambda message, *args: debug_logs.append(message % args if args else message),
    )
    monkeypatch.setattr("plugins.inputs.network.snmp_facts.logger.error", capture_error)

    result = await facts.list_all_resources()

    assert result["success"] is False
    assert len(debug_logs) == 1
    assert "event=snmp_facts_collection_started" in debug_logs[0]
    assert "target=127.0.0.1" in debug_logs[0]
    assert len(error_logs) == 1
    assert "event=plugin_exception" in error_logs[0]
    assert "task_id=snmp-task-7" in error_logs[0]
    assert "plugin_ref=network.config" in error_logs[0]
    assert "target=127.0.0.1" in error_logs[0]
    assert "error_type=RuntimeError" in error_logs[0]
    assert ":broken_collect" in error_logs[0]
    assert "community" not in error_logs[0]
    assert "must-not-be-logged" not in error_logs[0]
