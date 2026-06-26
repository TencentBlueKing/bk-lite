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
def test_ping_does_not_require_manual_ip_version_selection(ui):
    fields = {field["name"]: field for field in ui["table_columns"]}
    form_fields = {field["name"]: field for field in ui["form_fields"]}

    assert "ip_version" not in fields
    assert "ip_version" not in form_fields


@pytest.mark.unit
def test_ping_auto_access_columns_have_compact_layout(ui):
    fields = {field["name"]: field for field in ui["table_columns"]}

    assert fields["url"]["label"] == "目标地址"
    assert fields["url"]["widget_props"]["placeholder"] == "example.com / 192.168.1.1 / 2001:db8::1"
    assert fields["node_ids"]["widget_props"]["width"] == 220
    assert fields["url"]["widget_props"]["width"] == 340
    assert fields["instance_name"]["widget_props"]["width"] == 220
    assert fields["group_ids"]["widget_props"]["width"] == 220


@pytest.mark.unit
def test_ping_template_does_not_force_address_family(toml_text):
    assert "ipv4" not in toml_text
    assert "ipv6" not in toml_text
