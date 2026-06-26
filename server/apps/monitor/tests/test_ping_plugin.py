import json
import re
from pathlib import Path

import pytest


PLUGIN_DIR = (
    Path(__file__).resolve().parents[1]
    / "support-files"
    / "plugins"
    / "Telegraf"
    / "ping"
    / "ping"
)


@pytest.fixture(scope="module")
def ui():
    return json.loads((PLUGIN_DIR / "UI.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def toml_text():
    return (PLUGIN_DIR / "ping.child.toml.j2").read_text(encoding="utf-8")


def _rule_pattern(ui_config, field_name):
    field = {field["name"]: field for field in ui_config["table_columns"]}[field_name]
    return field["rules"][0]["pattern"]


@pytest.mark.unit
def test_ping_url_rule_accepts_domain_ipv4_and_ipv6(ui):
    pattern = _rule_pattern(ui, "url")

    assert re.fullmatch(pattern, "example.com")
    assert re.fullmatch(pattern, "192.168.1.1")
    assert re.fullmatch(pattern, "2001:db8::1")
    assert re.fullmatch(pattern, "::1")


@pytest.mark.unit
def test_ping_exposes_ipv4_default_and_ipv6_option(ui):
    fields = {field["name"]: field for field in ui["table_columns"]}
    form_fields = {field["name"]: field for field in ui["form_fields"]}
    ip_version = fields["ip_version"]

    assert ip_version["type"] == "select"
    assert ip_version["default_value"] == "ipv4"
    assert ip_version["options"] == [
        {"label": "IPv4", "value": "ipv4"},
        {"label": "IPv6", "value": "ipv6"},
    ]
    assert form_fields["ip_version"]["default_value"] == "ipv4"
    assert form_fields["ip_version"]["transform_on_edit"]["origin_path"] == "child.content.config.ip_version"


@pytest.mark.unit
def test_ping_template_enables_ipv6_only_when_selected(toml_text):
    assert 'ipv6 = {{ ((ip_version | default("ipv4", true)) == "ipv6") | lower }}' in toml_text
