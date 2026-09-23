"""NetworkService SNMP 健康状态 Enum 必须带可展示选项。"""

import json
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1] / "support-files" / "plugins" / "Telegraf" / "snmp"
PLUGIN_FILES = (
    PLUGIN_ROOT / "network_service_efficientip" / "metrics.json",
    PLUGIN_ROOT / "network_service_endace" / "metrics.json",
    PLUGIN_ROOT / "network_service_meinberg" / "metrics.json",
    PLUGIN_ROOT / "network_service_servertech" / "metrics.json",
    PLUGIN_ROOT / "network_service_spectracom" / "metrics.json",
)


def _enum_metrics(path: Path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [item for item in payload["metrics"] if item.get("data_type") == "Enum"]


def test_network_service_status_enums_have_options():
    total = 0
    for path in PLUGIN_FILES:
        metrics = _enum_metrics(path)
        assert metrics, path
        for metric in metrics:
            options = json.loads(metric["unit"])
            by_id = {item["id"]: item["name"] for item in options}
            assert by_id[1] == "healthy", metric["name"]
            assert by_id[2] == "fault", metric["name"]
            assert len({item["id"] for item in options}) == len(options)
            total += 1
    assert total == 11
