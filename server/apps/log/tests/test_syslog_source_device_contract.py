import json
from pathlib import Path

import pytest

SERVER_ROOT = Path(__file__).resolve().parents[3]
VECTOR_PATH = SERVER_ROOT / "apps/node_mgmt/support-files/collectors/Vector.json"
COLLECT_TYPE_PATH = SERVER_ROOT / "apps/log/support-files/plugins/Vector/syslog/collect_type.json"
LOG_MENU_PATH = SERVER_ROOT / "support-files/system_mgmt/menus/log.json"

SYSLOG_VRL = """.collector = "Vector"
.collect_type = "syslog"
.instance_id = "base"
.cloud_region_id = "${node.cloud_region}"
.received_at = now()
if !exists(.timestamp) {
  .timestamp = now()
}

raw_hostname = ""
if exists(.hostname) && is_string(.hostname) {
  raw_hostname = strip_whitespace(string!(.hostname))
}
if raw_hostname == "" {
  .hostname = ""
} else {
  .hostname = raw_hostname
}
"""


def test_linux_vector_templates_write_cloud_region_and_trimmed_hostname():
    templates = json.loads(VECTOR_PATH.read_text())
    linux = [item for item in templates if item["node_operating_system"] == "linux"]
    windows = [item for item in templates if item["id"] == "Vector_windows"]

    assert [item["cpu_architecture"] for item in linux] == ["x86_64", "arm64"]
    assert len(windows) == 1
    assert windows[0]["default_config"]["add_config"] == ""

    for item in linux:
        add_config = item["default_config"]["add_config"]
        assert SYSLOG_VRL in add_config
        assert "${node.cloud_region_id}" not in add_config
        assert "transforms.default_enrich" in item["default_config"]["nats"]
        snmp_prefix = add_config.split("# ====================================\n# syslog", 1)[0]
        assert '.collect_type = "snmp_trap"' in snmp_prefix
        assert '.cloud_region_id = "${node.cloud_region}"' in snmp_prefix
        assert "${node.cloud_region_id}" not in snmp_prefix
        assert "raw_hostname" not in snmp_prefix


def test_syslog_collect_type_attrs_include_cloud_region_without_changing_default_query():
    payload = json.loads(COLLECT_TYPE_PATH.read_text())
    assert payload["default_query"] == "collect_type: syslog | last 1 by (_time) partition by (instance_id)"
    assert payload["attrs"][payload["attrs"].index("instance_id") + 1] == "cloud_region_id"


def test_source_device_menu_is_a_view_only_integration_page_granted_to_normal_role():
    from apps.log.views.syslog_source_device import SOURCE_DEVICE_VIEW_PERMISSION

    payload = json.loads(LOG_MENU_PATH.read_text(encoding="utf-8"))
    integration = next(menu for menu in payload["menus"] if menu["name"] == "Integration")
    source_device = next(child for child in integration["children"] if child["id"] == "source_device")
    normal_role = next(role for role in payload["roles"] if role["name"] == "normal")

    assert source_device["operation"] == ["View"]
    assert SOURCE_DEVICE_VIEW_PERMISSION == "source_device-View"
    assert SOURCE_DEVICE_VIEW_PERMISSION in normal_role["menus"]


def test_syslog_source_discovery_is_a_five_minute_beat_task():
    from apps.log.config import CELERY_BEAT_SCHEDULE
    from apps.log.tasks.syslog_source_device import discover_syslog_source_devices

    entry = CELERY_BEAT_SCHEDULE["discover_syslog_source_devices"]
    assert entry["task"] == "apps.log.tasks.syslog_source_device.discover_syslog_source_devices"
    assert entry["schedule"].minute == CELERY_BEAT_SCHEDULE["compensate_log_notice"]["schedule"].minute
    assert discover_syslog_source_devices.name == entry["task"]


def test_discovery_is_not_started_from_init_or_repair():
    for relative in (
        "apps/core/management/commands/batch_init.py",
        "apps/node_mgmt/management/services/node_init/collector_init.py",
    ):
        assert "discover_syslog_source_devices" not in (SERVER_ROOT / relative).read_text()
    for relative in (
        "apps/log/services/syslog_source_device.py",
        "apps/log/tasks/syslog_source_device.py",
        "apps/log/views/syslog_source_device.py",
    ):
        text = (SERVER_ROOT / relative).read_text()
        assert "repair_node_config" not in text
        assert "CollectInstance" not in text
        assert "openapi_expose" not in text


@pytest.mark.django_db
def test_celery_task_returns_discovery_summary(monkeypatch):
    summary = {"region_count": 0, "written_rows": 0, "truncated_regions": 0, "failed": False}
    monkeypatch.setattr("apps.log.tasks.syslog_source_device.run_syslog_source_device_discovery", lambda: summary)
    from apps.log.tasks.syslog_source_device import discover_syslog_source_devices

    assert discover_syslog_source_devices() == summary
