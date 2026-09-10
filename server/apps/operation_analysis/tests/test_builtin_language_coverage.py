"""内置画布语言包必须覆盖 init 使用的 YAML 种子。"""

from pathlib import Path

import pytest
import yaml

from apps.core.utils.loader import LanguageLoader, clear_language_cache

pytestmark = pytest.mark.unit

SUPPORT = Path(__file__).resolve().parents[1] / "support-files"
SOURCES = [
    SUPPORT / "builtin_canvases.yaml",
    SUPPORT / "flow_dashboard.yaml",
    SUPPORT / "weopsx_platform_usage_dashboard.yaml",
    SUPPORT / "builtin_network_topology_screen.yaml",
    SUPPORT / "zombie_host_report.yaml",
]
REQUIRED_DASHBOARDS = {
    "dashboard::CMDB仪表盘_内置",
    "dashboard::统一告警中心仪表盘_内置",
    "dashboard::监控中心仪表盘_内置",
    "dashboard::Flow网络流量分析仪表盘",
    "dashboard::WeOpsX平台使用_内置",
}
REQUIRED_SCREENS = {
    "screen::告警运营大屏_内置",
    "screen::3D机房大屏_内置",
    "screen::3D应用大屏_内置",
    "screen::网络状态拓扑大屏_内置",
}
REQUIRED_REPORTS = {
    "report::僵尸机报表",
}


def _collect_keys():
    dashboards = set()
    screens = set()
    reports = set()
    datasources = set()
    for path in SOURCES:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for item in data.get("dashboards") or []:
            if item.get("key"):
                dashboards.add(item["key"])
        for item in data.get("screens") or []:
            if item.get("key"):
                screens.add(item["key"])
        for item in data.get("reports") or []:
            if item.get("key"):
                reports.add(item["key"])
        for item in data.get("datasources") or []:
            if item.get("key"):
                datasources.add(item["key"])
    return dashboards, screens, reports, datasources


def test_language_pack_covers_builtin_canvas_keys():
    clear_language_cache("operation_analysis")
    dashboards, screens, reports, datasources = _collect_keys()
    en = LanguageLoader("operation_analysis", "en").translations
    zh = LanguageLoader("operation_analysis", "zh-Hans").translations

    missing_en = sorted(key for key in dashboards if key not in (en.get("dashboards") or {}))
    missing_zh = sorted(key for key in dashboards if key not in (zh.get("dashboards") or {}))
    missing_screen_en = sorted(key for key in screens if key not in (en.get("screens") or {}))
    missing_report_en = sorted(key for key in reports if key not in (en.get("reports") or {}))
    missing_report_zh = sorted(key for key in reports if key not in (zh.get("reports") or {}))
    missing_ds = sorted(key for key in datasources if key not in (en.get("datasources") or {}) or key not in (zh.get("datasources") or {}))

    assert dashboards >= REQUIRED_DASHBOARDS
    assert screens >= REQUIRED_SCREENS
    assert reports >= REQUIRED_REPORTS
    assert missing_en == []
    assert missing_zh == []
    assert missing_screen_en == []
    assert missing_report_en == []
    assert missing_report_zh == []
    assert missing_ds == []
    assert en["directories"]["__builtin__"]["name"] == "Built-in"
    assert zh["directories"]["__builtin__"]["name"] == "内置目录"
    assert en["dashboards"]["dashboard::CMDB仪表盘_内置"]["name"] == "CMDB Dashboard"
    assert en["reports"]["report::僵尸机报表"]["name"] == "Zombie Host Report"
