from pathlib import Path

import pytest
import toml
import yaml

from apps.log.utils.plugin_controller import Controller, _build_log_template_env


PLUGIN_ROOT = Path(__file__).resolve().parents[1] / "support-files" / "plugins"


def render_plugin_template(plugin_path: str, template_name: str, context: dict) -> str:
    return Controller({}).render_template(str(PLUGIN_ROOT / plugin_path), template_name, context)


@pytest.mark.unit
def test_log_template_environment_has_no_default_globals(tmp_path):
    env = _build_log_template_env(str(tmp_path))

    assert {"lipsum", "cycler", "joiner", "namespace"}.isdisjoint(env.globals)


def test_vector_docker_template_renders_container_filter_lists():
    rendered = render_plugin_template(
        "Vector/docker",
        "docker.child.toml.j2",
        {
            "instance_id": "docker-1",
            "config_id": "CFG1",
            "endpoint": "unix:///var/run/docker.sock",
            "enable_container_filter": True,
            "container_name_contains": "nginx,api",
            "container_name_exclude": "vector,logspout",
            "enable_multiline": False,
            "NATS_PROTOCOL": "nats",
        },
    )

    assert 'include_containers = ["nginx", "api"]' in rendered
    assert 'exclude_containers = ["vector", "logspout"]' in rendered


def test_packetbeat_http_template_renders_string_ports_as_number_list():
    rendered = render_plugin_template(
        "Packetbeat/http",
        "http.child.yaml.j2",
        {
            "instance_id": "packetbeat-http-1",
            "ports": "80,8080,8000",
            "capture_body": False,
        },
    )

    data = yaml.safe_load(rendered)

    assert data[0]["type"] == "http"
    assert data[0]["ports"] == [80, 8080, 8000]


def test_auditbeat_file_integrity_template_renders_default_monitor_paths():
    rendered = render_plugin_template(
        "Auditbeat/file_integrity",
        "file_integrity.child.yaml.j2",
        {
            "instance_id": "auditbeat-file-integrity-1",
        },
    )

    data = yaml.safe_load(rendered)

    assert data[0]["module"] == "file_integrity"
    assert data[0]["paths"] == ["/etc/passwd", "/etc/shadow", "/etc/sudoers"]


def test_auditbeat_file_integrity_template_renders_exclude_path_string():
    rendered = render_plugin_template(
        "Auditbeat/file_integrity",
        "file_integrity.child.yaml.j2",
        {
            "instance_id": "auditbeat-file-integrity-1",
            "monitor_paths": "/var/log/app.log",
            "exclude_paths": "/tmp,/var/tmp",
        },
    )

    data = yaml.safe_load(rendered)

    assert data[0]["paths"] == ["/var/log/app.log"]
    assert data[0]["exclude_files"] == ["/tmp", "/var/tmp"]


KAFKA_SUBSCRIBE_HOST_METADATA = (
    "# bk-lite:vector-host-metadata:v1 begin\n"
    '.host_name = decode_base64!("${node.name_b64}")\n'
    '.host_ip = decode_base64!("${node.ip_b64}")\n'
    "# bk-lite:vector-host-metadata:v1 end"
)


def test_vector_kafka_subscribe_template_renders_plain_consumer():
    rendered = render_plugin_template(
        "Vector/kafka_subscribe",
        "kafka_subscribe.child.toml.j2",
        {
            "instance_id": "ks-1",
            "config_id": "CFG1",
            "topics": ["app-logs", "audit-logs"],
            "group_id": "",
            "bootstrap_servers": ["kafka.example:9092", "kafka-2.example:9092"],
            "auto_offset_reset": "latest",
            "sasl_enabled": False,
            "sasl_username": "log-user",
            "sasl_password": "should-not-render",
            "tls_enabled": False,
            "NATS_PROTOCOL": "nats",
        },
    )

    parsed = toml.loads(rendered)
    source = parsed["sources"]["kafka_subscribe_cfg1"]
    assert source["type"] == "kafka"
    assert source["bootstrap_servers"] == "kafka.example:9092,kafka-2.example:9092"
    assert source["group_id"] == "bk-lite-ks-1"
    assert source["topics"] == ["app-logs", "audit-logs"]
    assert source["auto_offset_reset"] == "latest"
    assert source["decoding"]["codec"] == "bytes"
    assert "sasl" not in source
    assert "tls" not in source
    assert "log-user" not in rendered
    assert "should-not-render" not in rendered

    enrich = parsed["transforms"]["kafka_subscribe_enrich_cfg1"]
    assert enrich["type"] == "remap"
    assert enrich["inputs"] == ["kafka_subscribe_cfg1"]
    assert '.collector = "Vector"' in enrich["source"]
    assert '.collect_type = "kafka_subscribe"' in enrich["source"]
    assert '.instance_id = "ks-1"' in enrich["source"]
    assert KAFKA_SUBSCRIBE_HOST_METADATA in enrich["source"]

    sink = parsed["sinks"]["vmlogs_cfg1"]
    assert sink["type"] == "nats"
    assert sink["subject"] == "vector"
    assert sink["inputs"] == ["kafka_subscribe_enrich_cfg1"]


def test_vector_kafka_subscribe_template_renders_sasl_and_tls():
    rendered = render_plugin_template(
        "Vector/kafka_subscribe",
        "kafka_subscribe.child.toml.j2",
        {
            "instance_id": "ks-2",
            "config_id": "CFG2",
            "topics": ["secure-logs"],
            "group_id": "ops-log-reader",
            "bootstrap_servers": "kafka.secure:9093",
            "auto_offset_reset": "earliest",
            "sasl_enabled": True,
            "sasl_mechanism": "SCRAM-SHA-256",
            "sasl_username": "log-user",
            "sasl_password": 'p@ss"word',
            "tls_enabled": True,
            "NATS_PROTOCOL": "tls",
            "operating_system": "linux",
        },
    )

    parsed = toml.loads(rendered)
    source = parsed["sources"]["kafka_subscribe_cfg2"]
    assert source["group_id"] == "ops-log-reader"
    assert source["auto_offset_reset"] == "earliest"
    assert source["sasl"]["enabled"] is True
    assert source["sasl"]["mechanism"] == "SCRAM-SHA-256"
    assert source["sasl"]["username"] == "log-user"
    assert source["sasl"]["password"] == 'p@ss"word'
    assert source["tls"]["enabled"] is True
    assert parsed["sinks"]["vmlogs_cfg2"]["tls"]["enabled"] is True
