"""patch_snmp_interface_filters 选型契约。

须覆盖 snmp_* 厂商 collect_type；仅 Network Device / IF-MIB 能力插件参与补齐，
避免 hardware_server 等非 capable 存量被写入默认 tagdrop。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from django.core.management.base import CommandError

from apps.monitor.constants.snmp_interface import DEFAULT_IFTYPE_EXCLUDE
from apps.monitor.management.commands.patch_snmp_interface_filters import (
    CHECKPOINT_VERSION,
    _load_checkpoint,
    _reconcile_common_ifmib_fields,
    is_patchable_snmp_child_config,
    patch_child_content_dict,
)
from apps.monitor.utils.snmp_interface_template import _load_common_ifmib_table


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
        table = content["config"]["table"][0]
        assert content["config"]["tagexclude"] == ["ifType"]
        assert content["config"]["tagdrop"]["ifType"] == list(DEFAULT_IFTYPE_EXCLUDE)
        assert any(f.get("name") == "ifType" for f in table["field"])
        assert "oid" not in table
        assert table.get("index_as_tag") is True


@pytest.mark.unit
class TestReconcilePublicIfmibWalkRoot:
    """v8：存量公共表必须去掉表级 oid，并带上 index_as_tag。"""

    def setup_method(self):
        _load_common_ifmib_table.cache_clear()

    def test_strips_iftable_walk_root_and_sets_index_as_tag(self):
        config = {
            "table": [
                {
                    "oid": "1.3.6.1.2.1.2.2",
                    "name": "interface",
                    "inherit_tags": ["source"],
                    "field": [
                        {
                            "oid": "1.3.6.1.2.1.2.2.1.2",
                            "name": "ifDescr",
                            "is_tag": True,
                        }
                    ],
                }
            ]
        }

        assert _reconcile_common_ifmib_fields(config) is True
        table = config["table"][0]
        assert "oid" not in table
        assert table.get("index_as_tag") is True
        assert table["name"] == "interface"

    def test_strips_stock_ifxtable_walk_root_kept_by_v7(self):
        config = {
            "table": [
                {
                    "oid": "1.3.6.1.2.1.31.1.1",
                    "name": "interface",
                    "inherit_tags": ["source"],
                    "field": [
                        {"oid": "1.3.6.1.2.1.31.1.1.1.6", "name": "ifHCInOctets"},
                        {"oid": "1.3.6.1.2.1.31.1.1.1.10", "name": "ifHCOutOctets"},
                    ],
                }
            ]
        }

        assert _reconcile_common_ifmib_fields(config) is True
        table = config["table"][0]
        names = {field.get("name") for field in table["field"]}
        assert "oid" not in table
        assert table.get("index_as_tag") is True
        assert "ifHCInOctets" in names
        assert "ifDescr" in names

    def test_patch_child_content_strips_ifxtable_oid(self):
        content = {
            "config": {
                "table": [
                    {
                        "oid": "1.3.6.1.2.1.31.1.1",
                        "name": "interface",
                        "field": [
                            {"oid": "1.3.6.1.2.1.2.2.1.2", "name": "ifDescr", "is_tag": True},
                            {"oid": "1.3.6.1.2.1.31.1.1.1.6", "name": "ifHCInOctets"},
                        ],
                    }
                ]
            }
        }

        assert patch_child_content_dict(content) is True
        table = content["config"]["table"][0]
        assert "oid" not in table
        assert table.get("index_as_tag") is True

    def test_v7_checkpoint_is_rejected(self, tmp_path):
        checkpoint = tmp_path / "checkpoint.json"
        checkpoint.write_text(
            json.dumps(
                {
                    "version": 7,
                    "cursor": {"created_at": "2026-01-01T00:00:00+00:00", "id": "cfg-1"},
                    "overwrite_default": False,
                }
            ),
            encoding="utf-8",
        )

        with pytest.raises(CommandError, match="Unsupported checkpoint version"):
            _load_checkpoint(checkpoint, overwrite_default=False)

    def test_v8_checkpoint_loads(self, tmp_path):
        checkpoint = tmp_path / "checkpoint.json"
        checkpoint.write_text(
            json.dumps(
                {
                    "version": CHECKPOINT_VERSION,
                    "cursor": {"created_at": "2026-01-01T00:00:00+00:00", "id": "cfg-1"},
                    "overwrite_default": False,
                }
            ),
            encoding="utf-8",
        )

        cursor = _load_checkpoint(checkpoint, overwrite_default=False)
        assert cursor is not None
        assert cursor[1] == "cfg-1"
