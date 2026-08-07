"""Shared protocol-visibility contract for every Telegraf SNMP form."""

import json
from pathlib import Path

import pytest


SERVER_ROOT = Path(__file__).resolve().parents[3]
SNMP_ROOT = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf" / "snmp"

V2_DEPENDENCY = {"field": "version", "value": 2}
V3_DEPENDENCY = {"field": "version", "value": 3}
AUTH_DEPENDENCY = {
    "field": ["version", "sec_level"],
    "conditions": [[{"equals": 3}], [{"in": ["authNoPriv", "authPriv"]}]],
}
PRIV_DEPENDENCY = {
    "field": ["version", "sec_level"],
    "conditions": [[{"equals": 3}], [{"equals": "authPriv"}]],
}
AUTH_FIELDS = ("auth_protocol", "auth_password", "ENV_AUTH_PASSWORD")
PRIV_FIELDS = ("priv_protocol", "priv_password", "ENV_PRIV_PASSWORD")


def _ui_files():
    return sorted(SNMP_ROOT.glob("**/UI.json"))


def _fields_by_name(path):
    ui = json.loads(path.read_text(encoding="utf-8"))
    fields = ui["form_fields"]
    names = [field["name"] for field in fields]
    assert len(names) == len(set(names)), f"{path}: duplicate form field name"
    return {field["name"]: field for field in fields}


@pytest.mark.unit
def test_all_snmp_forms_follow_the_protocol_visibility_contract():
    ui_files = _ui_files()
    assert len(ui_files) == 250

    for path in ui_files:
        fields = _fields_by_name(path)
        version = fields["version"]
        assert {option["value"] for option in version["options"]} == {2, 3}, path

        assert fields["community"].get("dependency") == V2_DEPENDENCY, path
        assert fields["sec_name"].get("dependency") == V3_DEPENDENCY, path
        assert fields["sec_level"].get("dependency") == V3_DEPENDENCY, path

        for name in AUTH_FIELDS:
            if name in fields:
                assert fields[name].get("dependency") == AUTH_DEPENDENCY, f"{path}: {name}"
        for name in PRIV_FIELDS:
            if name in fields:
                assert fields[name].get("dependency") == PRIV_DEPENDENCY, f"{path}: {name}"
