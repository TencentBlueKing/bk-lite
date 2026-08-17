import pytest

from service.debug import snmp_debug


@pytest.mark.asyncio
async def test_connection_probes_sys_name_oid(monkeypatch):
    captured = {}

    def fake_snmpget(target, port, timeout, credential, oid):
        captured["oid"] = oid
        return {
            "success": True,
            "stage": None,
            "summary": None,
            "raw_log": "device-name",
            "duration_ms": 1,
        }

    monkeypatch.setattr(snmp_debug, "_run_snmpget_sync", fake_snmpget)

    result = await snmp_debug.run_snmp_test_connection(
        {
            "target": "192.0.2.10",
            "port": 161,
            "timeout": 10,
            "credential": {"version": "v2c", "community": "test-community"},
        }
    )

    assert result["success"] is True
    assert captured["oid"] == "1.3.6.1.2.1.1.5.0"
