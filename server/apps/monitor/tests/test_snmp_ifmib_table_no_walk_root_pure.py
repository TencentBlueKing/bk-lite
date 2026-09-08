"""公共 IF-MIB 混采表不得带表级 oid，否则 Telegraf 会 MIB 整表展开。"""

from __future__ import annotations

import pytest

from apps.monitor.utils.snmp_interface_template import (
    _load_common_ifmib_table,
    ensure_core_network_ifmib_jinja,
    get_common_ifmib_table,
    get_common_ifmib_table_block,
    is_public_ifmib_table,
    is_public_ifmib_table_block,
)


@pytest.mark.unit
class TestCommonIfmibTableHasNoWalkRoot:
    def setup_method(self):
        _load_common_ifmib_table.cache_clear()

    def test_common_table_uses_explicit_fields_and_index_tag(self):
        table = get_common_ifmib_table()
        assert "oid" not in table
        assert table["name"] == "interface"
        assert table.get("index_as_tag") is True
        assert is_public_ifmib_table(table) is True

    def test_common_table_block_has_no_iftable_walk_root(self):
        block = get_common_ifmib_table_block()
        assert 'oid = "1.3.6.1.2.1.2.2"' not in block
        assert "index_as_tag = true" in block
        assert is_public_ifmib_table_block(block) is True

    def test_render_replaces_legacy_iftable_oid_with_index_as_tag(self):
        template = """
[[inputs.snmp]]
    [[inputs.snmp.table]]
        oid = "1.3.6.1.2.1.2.2"
        name = "interface"
        inherit_tags = ["source"]
    [[inputs.snmp.table.field]]
        oid = "1.3.6.1.2.1.2.2.1.2"
        name = "ifDescr"
        is_tag = true
"""
        rendered = ensure_core_network_ifmib_jinja(template, {"ifmib_capable": True})
        assert 'oid = "1.3.6.1.2.1.2.2"' not in rendered
        assert "index_as_tag = true" in rendered
        assert 'oid = "1.3.6.1.2.1.31.1.1.1.6"' in rendered
