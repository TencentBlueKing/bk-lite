import json
from pathlib import Path


VECTOR_COLLECTOR_DEFINITION = (
    Path(__file__).resolve().parents[1] / "support-files" / "collectors" / "Vector.json"
)
FUSION_COLLECTOR_AGENT = (
    Path(__file__).resolve().parents[4] / "agents" / "fusion-collector" / "agent"
)
SNMP_TRAP_SOCKET_PATH = "/tmp/snmp_trap.sock"


def test_vector_nats_tls_configs_use_verify_certificate_field():
    collectors = json.loads(VECTOR_COLLECTOR_DEFINITION.read_text())

    for collector in collectors:
        default_config = collector["default_config"]
        config_text = "\n".join(
            value for value in default_config.values() if isinstance(value, str)
        )

        assert "skip_cert_verify" not in config_text
        assert "verify_certificate = true" in config_text


def test_linux_vector_snmp_trap_source_uses_unix_datagram_socket():
    collectors = json.loads(VECTOR_COLLECTOR_DEFINITION.read_text())
    linux_collectors = [
        collector
        for collector in collectors
        if collector["node_operating_system"] == "linux"
    ]
    assert linux_collectors
    for collector in linux_collectors:
        add_config = collector["default_config"]["add_config"]
        assert '[sources.snmp_trap]' in add_config
        assert 'mode = "unix_datagram"' in add_config
        assert f'path = "{SNMP_TRAP_SOCKET_PATH}"' in add_config


def test_container_vector_startup_unlinks_stale_snmp_trap_socket():
    startup = (FUSION_COLLECTOR_AGENT / "startup.sh").read_text()
    wrapper = (FUSION_COLLECTOR_AGENT / "vector-wrapper").read_text()
    dockerfile = (FUSION_COLLECTOR_AGENT / "Dockerfile").read_text()

    assert f"rm -f {SNMP_TRAP_SOCKET_PATH}" in startup
    assert f"rm -f {SNMP_TRAP_SOCKET_PATH}" in wrapper
    assert 'exec /opt/fusion-collectors/bin/vector-real "$@"' in wrapper
    assert "ADD ./vector ./bin/vector-real" in dockerfile
    assert "ADD ./vector-wrapper ./bin/vector" in dockerfile
