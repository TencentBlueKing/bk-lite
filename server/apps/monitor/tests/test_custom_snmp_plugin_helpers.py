"""CustomSnmpPluginService 纯辅助函数规格测试。"""

import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.services import custom_snmp_plugin as csp
from apps.monitor.services.custom_snmp_plugin import CustomSnmpPluginService as S


class TestGetSnmpSectionBounds:
    def test_finds_field_section(self):
        content = "[[outputs.x]]\n\n[[inputs.snmp.field]]\noid='.1'"
        start, end = S._get_snmp_section_bounds(content)
        assert "[[inputs.snmp.field]]" in content[start:]
        assert content[start:].lstrip().startswith("[[inputs.snmp.field]]")
        assert end == len(content)

    def test_missing_section_raises(self):
        with pytest.raises(BaseAppException):
            S._get_snmp_section_bounds("no snmp here")


class TestInjectAndExtractMarkers:
    def test_inject_wraps_snippet(self):
        content = "[[inputs.snmp]]\nagents=[]\n\n[[inputs.snmp.field]]\noid='.1'\n"
        out = S._inject_collect_markers(content)
        assert csp.SNMP_COLLECT_MARKER_START in out
        assert csp.SNMP_COLLECT_MARKER_END in out

    def test_inject_idempotent(self):
        content = "[[inputs.snmp.field]]\noid='.1'\n"
        once = S._inject_collect_markers(content)
        twice = S._inject_collect_markers(once)
        assert once == twice

    def test_extract_collect_snippet(self):
        content = "[[inputs.snmp.field]]\noid='.1'\n"
        wrapped = S._inject_collect_markers(content)
        snippet = S._extract_collect_snippet(wrapped)
        assert "[[inputs.snmp.field]]" in snippet

    def test_extract_without_markers_raises(self):
        with pytest.raises(BaseAppException):
            S._extract_collect_snippet("no markers")

    def test_replace_collect_snippet(self):
        content = "[[inputs.snmp.field]]\noid='.1'\n"
        wrapped = S._inject_collect_markers(content)
        replaced = S._replace_collect_snippet(wrapped, "[[inputs.snmp.field]]\noid='.99'")
        assert "oid='.99'" in S._extract_collect_snippet(replaced)

    def test_replace_without_markers_raises(self):
        with pytest.raises(BaseAppException):
            S._replace_collect_snippet("no markers", "x")


class TestNormalizeDuration:
    def test_strips_trailing_s(self):
        assert S._normalize_duration("30s") == "30"

    def test_non_string_passthrough(self):
        assert S._normalize_duration(30) == 30

    def test_string_without_s(self):
        assert S._normalize_duration("30") == "30"


class TestParseIpPort:
    def test_empty_raises(self):
        with pytest.raises(BaseAppException):
            S._parse_ip_port(None)

    def test_valid(self):
        host, port = S._parse_ip_port("udp://10.0.0.1:161")
        assert host == "10.0.0.1" and port == 161

    def test_invalid_format_raises(self):
        with pytest.raises(BaseAppException):
            S._parse_ip_port("10.0.0.1")
