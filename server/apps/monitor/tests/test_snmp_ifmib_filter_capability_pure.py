"""IF-MIB 过滤注入须与 Network Device 能力对齐。

hardware_server 等非 Network Device SNMP 模板含 ifDescr，但不能静默套用
默认 ifType 排除；只有 ifmib_capable 插件才注入过滤 Jinja / 默认排除集。
"""

from __future__ import annotations

import pytest

from apps.monitor.constants.snmp_interface import DEFAULT_IFTYPE_EXCLUDE
from apps.monitor.utils.plugin_controller import Controller
from apps.monitor.utils.snmp_interface_template import FILTER_MARKER_BEGIN


HARDWARE_LIKE_CHILD = """
[[inputs.snmp]]
  agents = ["udp://{{ ip }}:161"]
  [[inputs.snmp.table]]
    name = "interface"
    oid = "IF-MIB::ifTable"
    [[inputs.snmp.table.field]]
      name = "ifDescr"
      oid = "IF-MIB::ifDescr"
      is_tag = true
"""


@pytest.mark.unit
class TestSnmpInterfaceFilterCapabilityGate:
    def test_non_capable_hardware_like_template_keeps_interfaces_without_silent_tagdrop(self):
        rendered = Controller({}).render_template(
            HARDWARE_LIKE_CHILD,
            {
                "ifmib_capable": False,
                "ip": "10.0.0.1",
                "instance_id": "('hw-1',)",
            },
        )

        assert 'name = "interface"' in rendered
        assert 'name = "ifDescr"' in rendered
        assert FILTER_MARKER_BEGIN not in rendered
        assert "tagdrop" not in rendered
        assert "tagpass" not in rendered

    def test_capable_plugin_with_default_exclude_renders_tagdrop_when_enabled(self):
        rendered = Controller({}).render_template(
            HARDWARE_LIKE_CHILD,
            {
                "ifmib_capable": True,
                "enable_ifmib": True,
                "iftype_exclude": list(DEFAULT_IFTYPE_EXCLUDE),
                "ip": "10.0.0.2",
                "instance_id": "('sw-1',)",
            },
        )

        assert FILTER_MARKER_BEGIN in rendered
        assert "tagdrop" in rendered
        for value in DEFAULT_IFTYPE_EXCLUDE:
            assert f'"{value}"' in rendered

    def test_capable_plugin_disabled_ifmib_omits_interface_table_and_filters(self):
        rendered = Controller({}).render_template(
            HARDWARE_LIKE_CHILD,
            {
                "ifmib_capable": True,
                "enable_ifmib": False,
                "iftype_exclude": list(DEFAULT_IFTYPE_EXCLUDE),
                "ip": "10.0.0.3",
                "instance_id": "('sw-2',)",
            },
        )

        assert 'name = "interface"' not in rendered
        assert FILTER_MARKER_BEGIN not in rendered
        assert "tagdrop" not in rendered
