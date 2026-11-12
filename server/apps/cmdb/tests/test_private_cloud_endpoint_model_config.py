"""私有云平台模型必须有必填的管理地址，采集下发才能带上 host。"""

from pathlib import Path

import pandas as pd

MODEL_CONFIG = Path("apps/cmdb/support-files/model_config.xlsx")
PLATFORM_MODELS = ("fusioncompute", "nutanixhci", "inspurincloudrail")
ENDPOINT_OPTION = '{"validation_type":"unrestricted","custom_regex":"","widget_type":"single_line"}'


def _attrs(model_id):
    frame = pd.read_excel(MODEL_CONFIG, sheet_name=f"attr-{model_id}", header=1).fillna("")
    return frame.set_index("attr_id")


def test_private_cloud_platforms_require_endpoint():
    for model_id in PLATFORM_MODELS:
        endpoint = _attrs(model_id).loc["endpoint"]
        assert endpoint["attr_name"] == "平台地址"
        assert endpoint["attr_type"] == "str"
        assert endpoint["option"] == ENDPOINT_OPTION
        assert endpoint["attr_group"] == "基本信息"
        assert bool(endpoint["is_only"]) is False
        assert bool(endpoint["editable"]) is True
        assert bool(endpoint["is_required"]) is True
