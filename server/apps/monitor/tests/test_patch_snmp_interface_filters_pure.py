"""patch_snmp_interface_filters 选型契约。

须覆盖 snmp_* 厂商 collect_type；仅 Network Device / IF-MIB 能力插件参与补齐，
避免 hardware_server 等非 capable 存量被写入默认 tagdrop。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from apps.monitor.constants.snmp_interface import DEFAULT_IFTYPE_EXCLUDE
from apps.monitor.management.commands.patch_snmp_interface_filters import (
    is_patchable_snmp_child_config,
    patch_child_content_dict,
)


@pytest.mark.unit
class TestPatchSnmpInterfaceFilterSelection:
    def test_vendor_and_generic_snmp_collect_types_are_patchable_when_capable(self):
        assert is_patchable_snmp_child_config(
            SimpleNamespace(collect_type="snmp_cisco", monitor_plugin=object()),
            capable=True,
        )
        assert is_patchable_snmp_child_config(
            SimpleNamespace(collect_type="snmp", monitor_plugin=object()),
            capable=True,
        )

    def test_non_snmp_or_non_capable_not_patchable(self):
        assert not is_patchable_snmp_child_config(
            SimpleNamespace(collect_type="snmp_cisco", monitor_plugin=None),
            capable=False,
        )
        assert not is_patchable_snmp_child_config(
            SimpleNamespace(collect_type="http", monitor_plugin=object()),
            capable=True,
        )

    def test_capable_override_avoids_recomputing_plugin_capability(self):
        """Command 应按 plugin_id 缓存后传入 capable=，避免对每行再查 M2M。"""
        config = SimpleNamespace(collect_type="snmp_h3c", monitor_plugin=object())
        assert is_patchable_snmp_child_config(config, capable=True) is True
        assert is_patchable_snmp_child_config(config, capable=False) is False

    def test_patch_child_content_adds_default_tagdrop_for_ifdescr_tables(self):
        content = {
            "config": {
                "table": [
                    {
                        "name": "interface",
                        "field": [{"name": "ifDescr", "oid": "IF-MIB::ifDescr", "is_tag": True}],
                    }
                ]
            }
        }
        assert patch_child_content_dict(content) is True
        assert content["config"]["tagexclude"] == ["ifType"]
        assert content["config"]["tagdrop"]["ifType"] == list(DEFAULT_IFTYPE_EXCLUDE)
        assert any(f.get("name") == "ifType" for f in content["config"]["table"][0]["field"])
