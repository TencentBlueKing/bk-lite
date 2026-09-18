"""未确认认证契约的入口必须明确失败，不能伪造采集成功。"""
import importlib.util
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[3] / "enterprise/agents/stargazer/enterprise/plugins/inputs"


@pytest.mark.parametrize("model_id", ["zstack", "ibm_ds", "xsky"])
def test_unconfirmed_collector_reports_missing_contract(model_id):
    path = SOURCE / model_id / (model_id + "_info.py")
    spec = importlib.util.spec_from_file_location("pending_" + model_id, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cls = getattr(module, "".join(part.capitalize() for part in model_id.split("_")) + "Info")
    collector = cls({"model_id": model_id, "host": "192.0.2.10", "port": 443})
    with pytest.raises(NotImplementedError, match="authentication contract"):
        collector.list_all_resources()
