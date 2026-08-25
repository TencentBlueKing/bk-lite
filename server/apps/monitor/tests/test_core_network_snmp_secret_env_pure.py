"""Generic switch/router/firewall/loadbalance SNMP plugins must not inline SNMPv3 secrets."""

import json
from pathlib import Path

import pytest

from apps.monitor.utils.plugin_controller import Controller


SERVER_ROOT = Path(__file__).resolve().parents[3]
SNMP_ROOT = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf" / "snmp"
CORE_PLUGINS = ("switch", "router", "firewall", "loadbalance")
CANARY = "P@ssw0rd12#-canary"


def _plugin_files(name: str):
    plugin_dir = SNMP_ROOT / name
    ui = json.loads((plugin_dir / "UI.json").read_text(encoding="utf-8"))
    toml_path = next(plugin_dir.glob("*.child.toml.j2"))
    return ui, toml_path.read_text(encoding="utf-8")


@pytest.mark.unit
@pytest.mark.parametrize("plugin", CORE_PLUGINS)
def test_core_network_plugins_keep_v3_passwords_in_sidecar_env(plugin):
    ui, toml_text = _plugin_files(plugin)
    fields = {field["name"]: field for field in ui["form_fields"]}

    assert "ENV_AUTH_PASSWORD" in fields
    assert "ENV_PRIV_PASSWORD" in fields
    assert "auth_password" not in fields
    assert "priv_password" not in fields
    assert fields["ENV_AUTH_PASSWORD"].get("encrypted") is True
    assert fields["ENV_PRIV_PASSWORD"].get("encrypted") is True
    assert fields["ENV_AUTH_PASSWORD"]["transform_on_edit"]["origin_path"] == (
        "child.env_config.AUTH_PASSWORD__{{config_id}}"
    )
    assert fields["ENV_PRIV_PASSWORD"]["transform_on_edit"]["origin_path"] == (
        "child.env_config.PRIV_PASSWORD__{{config_id}}"
    )
    assert 'auth_password = "${AUTH_PASSWORD__{{ config_id }}}"' in toml_text
    assert 'priv_password = "${PRIV_PASSWORD__{{ config_id }}}"' in toml_text
    assert "{{ auth_password }}" not in toml_text
    assert "{{ priv_password }}" not in toml_text


@pytest.mark.unit
@pytest.mark.parametrize("plugin", CORE_PLUGINS)
def test_core_network_plugin_render_does_not_inline_v3_passwords(plugin):
    _, toml_text = _plugin_files(plugin)
    rendered = Controller({}).render_template(
        toml_text,
        {
            "interval": 30,
            "version": 3,
            "ip": "172.24.191.104",
            "port": 161,
            "community": "should-not-matter",
            "timeout": 20,
            "sec_name": "canway_monitor",
            "sec_level": "authPriv",
            "auth_protocol": "SHA",
            "priv_protocol": "AES",
            "auth_password": CANARY,
            "priv_password": CANARY,
            "ENV_AUTH_PASSWORD": CANARY,
            "ENV_PRIV_PASSWORD": CANARY,
            "config_id": "ABC123DEF",
            "logical_instance_value": "YWE1ZWYwMjQ3MDIx",
            "instance_type": plugin,
            "ifmib_capable": False,
        },
        escape_toml_strings=True,
    )

    assert CANARY not in rendered
    assert 'auth_password = "${AUTH_PASSWORD__ABC123DEF}"' in rendered
    assert 'priv_password = "${PRIV_PASSWORD__ABC123DEF}"' in rendered
    assert f'config_type = "{plugin}"' in rendered
