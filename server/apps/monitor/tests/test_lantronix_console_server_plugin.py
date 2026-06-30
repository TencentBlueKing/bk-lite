from __future__ import annotations

import json
import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = ROOT.parent
PLUGIN_DIR = (
    ROOT
    / "apps"
    / "monitor"
    / "support-files"
    / "plugins"
    / "Telegraf"
    / "snmp"
    / "console_server_lantronix"
)
WEB_ROOT = REPO_ROOT / "web" / "src" / "app" / "monitor"
ICON_PATH = REPO_ROOT / "web" / "public" / "assets" / "icons" / "mm-lantronix_lantronix.svg"
FORBIDDEN_SOURCE_WORDS = re.compile(
    "|".join(
        [
            "Data" + "dog",
            "Libre" + "NMS",
            "Zab" + "bix",
            "Check" + "mk",
            "Open" + "NMS",
            "snmp_" + "exporter",
        ]
    ),
    re.IGNORECASE,
)


def _json(name: str):
    return json.loads((PLUGIN_DIR / name).read_text(encoding="utf-8"))


def _yaml(name: str):
    return yaml.safe_load((ROOT / "apps" / "monitor" / "language" / name).read_text(encoding="utf-8"))


def test_lantronix_snmpv3_passwords_use_sidecar_env():
    ui = _json("UI.json")
    field_names = {field["name"] for field in ui["form_fields"]}
    assert "ENV_AUTH_PASSWORD" in field_names
    assert "ENV_PRIV_PASSWORD" in field_names

    toml = (PLUGIN_DIR / "lantronix.child.toml.j2").read_text(encoding="utf-8")
    assert '${AUTH_PASSWORD__{{ config_id }}}' in toml
    assert '${PRIV_PASSWORD__{{ config_id }}}' in toml
    assert "{{ auth_password }}" not in toml
    assert "{{ priv_password }}" not in toml


def test_lantronix_metrics_are_vendor_delta_only_and_policy_subset():
    metrics = _json("metrics.json")
    policy = _json("policy.json")
    metric_names = {metric["name"] for metric in metrics["metrics"]}

    assert metrics["collect_type"] == "snmp_lantronix"
    assert metrics["name"] == "ConsoleServer"
    assert metrics["plugin"] == "ConsoleServer Lantronix SLC SNMP"
    assert metrics["metrics"] == []
    assert not {"snmp_uptime", "interface_ifHCInOctets", "interface_ifHCOutOctets"} & metric_names
    assert not {name for name in metric_names if name.startswith("device_total_")}

    policy_metrics = {template["metric_name"] for template in policy["templates"]}
    assert policy_metrics <= metric_names


def test_lantronix_toml_uses_64bit_ifxtable_without_32bit_octets():
    toml = (PLUGIN_DIR / "lantronix.child.toml.j2").read_text(encoding="utf-8")
    assert "ifHCInOctets" in toml
    assert "ifHCOutOctets" in toml
    assert "1.3.6.1.2.1.31.1.1.1.6" in toml
    assert "1.3.6.1.2.1.31.1.1.1.10" in toml
    assert "ifDescr" in toml
    assert "ifInOctets" not in toml
    assert "ifOutOctets" not in toml
    assert "1.3.6.1.2.1.2.2.1.10" not in toml
    assert "1.3.6.1.2.1.2.2.1.16" not in toml


def test_lantronix_i18n_and_frontend_wiring_are_present():
    zh = _yaml("zh-Hans.yaml")
    en = _yaml("en.yaml")
    plugin_key = "ConsoleServer Lantronix SLC SNMP"

    assert plugin_key in zh["monitor_object_plugin"]
    assert plugin_key in en["monitor_object_plugin"]
    assert "Lantronix" in zh["monitor_object_plugin"][plugin_key]["name"]
    assert "Lantronix" in en["monitor_object_plugin"][plugin_key]["name"]
    assert ": " not in en["monitor_object_plugin"][plugin_key]["desc"]

    console_server_tsx = (
        WEB_ROOT / "hooks" / "integration" / "objects" / "networkDevice" / "consoleServer.tsx"
    ).read_text(encoding="utf-8")
    common_tsx = (WEB_ROOT / "utils" / "common.tsx").read_text(encoding="utf-8")
    assert "'ConsoleServer Lantronix SLC SNMP': 'snmp_lantronix'" in console_server_tsx
    assert "label: 'Lantronix SLC'" in common_tsx
    assert "icon: 'mm-lantronix_lantronix'" in common_tsx
    assert ICON_PATH.exists()


def test_lantronix_brand_regex_avoids_generic_console_terms():
    common_tsx = (WEB_ROOT / "utils" / "common.tsx").read_text(encoding="utf-8")
    lantronix_line = next(line for line in common_tsx.splitlines() if "Lantronix SLC" in line)
    assert "lantronix" in lantronix_line.lower()
    assert "slc" in lantronix_line.lower()
    assert "emg" in lantronix_line.lower()
    assert "console" not in lantronix_line.lower()
    assert "server" not in lantronix_line.lower()


def test_lantronix_files_do_not_leak_external_source_names():
    for path in [
        *PLUGIN_DIR.iterdir(),
        Path(__file__),
        WEB_ROOT / "hooks" / "integration" / "objects" / "networkDevice" / "consoleServer.tsx",
        WEB_ROOT / "utils" / "common.tsx",
        ICON_PATH,
    ]:
        text = path.read_text(encoding="utf-8")
        assert not FORBIDDEN_SOURCE_WORDS.search(text), path
