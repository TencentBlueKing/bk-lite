import json
from pathlib import Path

import pytest


PLUGIN_DIR = (
    Path(__file__).resolve().parents[1]
    / "support-files"
    / "plugins"
    / "Telegraf"
    / "docker"
    / "docker"
)


@pytest.fixture(scope="module")
def ui():
    return json.loads((PLUGIN_DIR / "UI.json").read_text(encoding="utf-8"))


@pytest.mark.unit
def test_docker_instance_id_includes_node_ip(ui):
    assert ui["instance_id"] == "{{cloud_region}}_docker_{{ip}}_{{endpoint}}"
    assert "{{ip}}" in ui["instance_id"]
    assert "{{endpoint}}" in ui["instance_id"]
    assert "_docker_" in ui["instance_id"]


@pytest.mark.unit
def test_docker_identity_does_not_come_from_display_name_or_form_ip(ui):
    table_fields = {field["name"] for field in ui["table_columns"]}
    form_fields = {field["name"] for field in ui["form_fields"]}

    assert "ip" not in table_fields
    assert "ip" not in form_fields
    assert "instance_name" in table_fields
    assert "{{instance_name}}" not in ui["instance_id"]


@pytest.mark.unit
def test_docker_default_endpoint_stays_local_socket(ui):
    endpoint = {field["name"]: field for field in ui["table_columns"]}["endpoint"]

    assert endpoint["default_value"] == "unix:///var/run/docker.sock"
