import json
from pathlib import Path


PLUGIN_FILE = (
    Path(__file__).resolve().parents[1]
    / "support-files"
    / "plugins"
    / "unknown"
    / "k8s"
    / "k8s"
    / "metrics.json"
)


def test_k8s_base_object_defaults_to_thirty_minute_cleanup():
    plugin = json.loads(PLUGIN_FILE.read_text(encoding="utf-8"))
    base_object = next(item for item in plugin["objects"] if item["level"] == "base")

    assert base_object["cleanup_policy"] == "timeout"
    assert base_object["cleanup_timeout_days"] == 30
    assert base_object["cleanup_timeout_unit"] == "minute"
