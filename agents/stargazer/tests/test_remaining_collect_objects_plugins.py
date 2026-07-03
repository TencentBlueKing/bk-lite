import importlib
import re
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
REPO_ROOT = ROOT.parents[1]
DESC_PATH = REPO_ROOT / "server/apps/cmdb_enterprise/collect/new_collect_object_definitions.py"


def _remaining_objects():
    spec = spec_from_file_location("remaining_collect_objects", DESC_PATH)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.REMAINING_COLLECT_OBJECTS


def _load_plugin(model_id):
    return yaml.safe_load((ROOT / "enterprise" / "plugins" / "inputs" / model_id / "plugin.yml").read_text())


def _collector_class_name(model_id):
    return "".join(part.capitalize() for part in model_id.split("_")) + "Info"


def test_remaining_plugin_manifests_exist_and_point_to_collectors():
    for collect_object in _remaining_objects():
        model_id = collect_object["model_id"]
        plugin = _load_plugin(model_id)

        assert plugin["name"] == model_id
        assert plugin["metadata"]["model_id"] == model_id
        assert plugin["default_executor"] == collect_object["driver_type"]

        executor = plugin["executors"][collect_object["driver_type"]]
        if collect_object["driver_type"] == "job":
            assert executor["collector"] == {"module": "plugins.script_executor", "class": "SSHPlugin"}
            script = executor["scripts"]["linux"]
            assert script == f"enterprise/plugins/inputs/{model_id}/{model_id}_default_discover.sh"
            body = (ROOT / script).read_text()
            assert "object_type" in body
            assert "uname" in body or "ps " in body
            assert not re.search(r"\b(rm|kill|shutdown|reboot|mkfs|dd|start|stop|delete|reset)\b", body, re.IGNORECASE)
        else:
            collector = executor["collector"]
            assert collector["module"] == f"enterprise.plugins.inputs.{model_id}.{model_id}_info"
            assert collector["class"] == _collector_class_name(model_id)
            module = importlib.import_module(collector["module"])
            assert hasattr(module, collector["class"])


def test_remaining_protocol_collector_returns_model_metric():
    from enterprise.plugins.inputs.xsky.xsky_info import XskyInfo

    collector = XskyInfo({"model_id": "xsky", "host": "10.0.0.1", "port": "443"})
    result = collector.list_all_resources()

    assert result["success"] is True
    assert result["result"]["xsky"][0]["ip_addr"] == "10.0.0.1"
    assert result["result"]["xsky"][0]["port"] == 443
