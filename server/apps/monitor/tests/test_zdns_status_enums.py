"""ZDNS 服务状态 Enum 必须带可展示选项。"""

import json
from pathlib import Path

PLUGIN_FILE = (
    Path(__file__).resolve().parents[1]
    / "support-files"
    / "plugins"
    / "Telegraf"
    / "snmp"
    / "network_service_zdns"
    / "metrics.json"
)


def test_zdns_status_enums_have_options():
    payload = json.loads(PLUGIN_FILE.read_text(encoding="utf-8"))
    enums = [item for item in payload["metrics"] if item.get("data_type") == "Enum"]
    assert len(enums) == 9
    for metric in enums:
        options = json.loads(metric["unit"])
        by_id = {item["id"]: item["name"] for item in options}
        assert by_id[1] == "healthy", metric["name"]
        assert by_id[2] == "fault", metric["name"]
        assert len({item["id"] for item in options}) == len(options)
