from pathlib import Path

import yaml

from apps.log.utils.plugin_controller import Controller


PLUGIN_ROOT = Path(__file__).resolve().parents[1] / "support-files" / "plugins"


def render_plugin_template(plugin_path: str, template_name: str, context: dict) -> str:
    return Controller({}).render_template(str(PLUGIN_ROOT / plugin_path), template_name, context)


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
