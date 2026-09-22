"""控制台设备汇总电源状态必须带可展示的枚举选项。"""

import json
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1] / "support-files" / "plugins" / "Telegraf" / "snmp"
PLUGIN_FILES = (
    PLUGIN_ROOT / "console_server_lantronix" / "metrics.json",
    PLUGIN_ROOT / "console_server_wti" / "metrics.json",
)


def _device_psu_state(path: Path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    return next(item for item in payload["metrics"] if item["name"] == "device_psu_state")


def test_console_server_device_psu_state_has_enum_options():
    for path in PLUGIN_FILES:
        metric = _device_psu_state(path)
        assert metric["data_type"] == "Enum"
        options = json.loads(metric["unit"])
        by_id = {item["id"]: item["name"] for item in options}
        assert by_id[1] == "healthy"
        assert by_id[2] == "fault"
        assert len({item["id"] for item in options}) == len(options)
