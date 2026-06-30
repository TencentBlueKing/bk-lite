import json
from pathlib import Path

import pytest


PLUGIN_DIR = (
    Path(__file__).resolve().parents[1]
    / "support-files"
    / "plugins"
    / "unknown"
    / "k8s"
    / "k8s"
)


@pytest.fixture(scope="module")
def metrics():
    return json.loads((PLUGIN_DIR / "metrics.json").read_text(encoding="utf-8"))


@pytest.mark.unit
def test_k8s_display_fields_use_plugin_scoped_bindings(metrics):
    """K8s display fields use plugin scoped bindings; derived instances are handled by reported-plugin fallback."""
    for monitor_object in metrics["objects"]:
        for display_field in monitor_object.get("display_fields", []):
            for binding in display_field.get("metrics", []):
                assert binding["plugin"] == metrics["plugin"]
                assert binding["metric"]
