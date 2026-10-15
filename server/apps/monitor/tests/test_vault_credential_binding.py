"""监控凭据绑定：存储/云 REST 应选 platform_api，而不是回落到 host+sql。"""

from types import SimpleNamespace

import pytest

from apps.monitor.services.vault_credential.binding import derive_credential_binding
from apps.system_mgmt.services.credential_builtin import BUILTIN_TYPES

pytestmark = pytest.mark.unit


def _usable(preferred_key, category):
    definition = BUILTIN_TYPES.get(preferred_key) or {}
    if category in (definition.get("categories") or []):
        return [preferred_key]
    return []


@pytest.fixture(autouse=True)
def _stub_usable_types(monkeypatch):
    monkeypatch.setattr(
        "apps.monitor.services.vault_credential.binding.usable_builtin_type_keys",
        _usable,
    )


def _plugin(*, object_name, type_id, type_name="", display_name=""):
    obj_type = SimpleNamespace(id=type_id, name=type_name)
    obj = SimpleNamespace(name=object_name, type=obj_type, display_name=display_name)
    return SimpleNamespace(id="plugin-1", monitor_object=SimpleNamespace(all=lambda: [obj]))


def _user_password_form(*, collect_type, password_name="password"):
    return {
        "collect_type": collect_type,
        "form_fields": [
            {"name": "username", "type": "input"},
            {"name": password_name, "type": "password"},
        ],
    }


def _snmp_form(*, collect_type):
    return {
        "collect_type": collect_type,
        "form_fields": [
            {"name": "community", "type": "input"},
            {"name": "sec_name", "type": "input"},
            {"name": "version", "type": "select"},
        ],
    }


def _variant(binding):
    variants = (binding or {}).get("variants") or []
    assert variants, binding
    return variants[0]


def test_storage_powerstore_like_form_uses_platform_api():
    plugin = _plugin(object_name="Storage", type_id="Hardware Device", display_name="存储设备")
    binding = derive_credential_binding(_user_password_form(collect_type="powerstore"), plugin)
    variant = _variant(binding)
    assert variant["category"] == "storage"
    assert variant["type_keys"] == ["platform_api"]
    assert variant["_preferred_keys"] == ["platform_api"]
    assert variant["_profile"] == "user_password"
    assert variant["managed_fields"] == ["username", "password"]
    assert variant["category"] != "network"


def test_sangforscp_like_form_uses_cloud_platform_api():
    plugin = _plugin(object_name="SangforSCP", type_id="Cloud")
    binding = derive_credential_binding(_user_password_form(collect_type="sangforscp"), plugin)
    variant = _variant(binding)
    assert variant["category"] == "cloud"
    assert variant["type_keys"] == ["platform_api"]
    assert variant["_preferred_keys"] == ["platform_api"]
    assert variant["_profile"] == "user_password"
    assert variant["category"] != "network"


def test_cnware_like_form_keeps_env_password_managed_field():
    plugin = _plugin(object_name="CNware", type_id="Cloud")
    binding = derive_credential_binding(
        _user_password_form(collect_type="cnware", password_name="ENV_PASSWORD"),
        plugin,
    )
    variant = _variant(binding)
    assert variant["category"] == "cloud"
    assert variant["type_keys"] == ["platform_api"]
    assert variant["_profile"] == "user_password"
    assert variant["managed_fields"] == ["username", "ENV_PASSWORD"]
    assert variant["category"] != "network"


def test_storage_snmp_keeps_snmp_type():
    plugin = _plugin(object_name="Storage", type_id="Hardware Device", display_name="存储设备")
    binding = derive_credential_binding(_snmp_form(collect_type="snmp_storage_sangfor_eds"), plugin)
    variant = _variant(binding)
    assert variant["category"] == "storage"
    assert variant["type_keys"] == ["snmp"]
    assert variant["_profile"] in {"snmp_v2", "snmp_v3"}


def test_mysql_like_form_still_sql_database():
    plugin = _plugin(object_name="Mysql", type_id="Database", type_name="数据库")
    binding = derive_credential_binding(
        _user_password_form(collect_type="database", password_name="ENV_PASSWORD"),
        plugin,
    )
    variant = _variant(binding)
    assert variant["category"] == "database"
    assert variant["type_keys"] == ["sql"]
    assert variant["_profile"] == "user_password"
    assert variant["managed_fields"] == ["username", "ENV_PASSWORD"]


def test_hardware_server_ipmi_stays_host():
    plugin = _plugin(object_name="Hardware Server", type_id="Hardware Device")
    binding = derive_credential_binding(
        {
            "collect_type": "ipmi",
            "form_fields": [
                {"name": "username", "type": "input"},
                {"name": "ENV_PASSWORD", "type": "password"},
            ],
        },
        plugin,
    )
    variant = _variant(binding)
    assert variant["category"] == "host"
    assert variant["type_keys"] == ["ipmi"]
    assert variant["_profile"] == "ipmi"


def test_hardware_server_snmp_stays_network_not_storage():
    plugin = _plugin(object_name="Hardware Server", type_id="Hardware Device")
    binding = derive_credential_binding(_snmp_form(collect_type="snmp"), plugin)
    variant = _variant(binding)
    assert variant["category"] == "network"
    assert variant["type_keys"] == ["snmp"]
