"""Consul 内置模型种子：采集已有入口，模型必须能接住落库字段。"""

import pandas as pd
import pytest

MODEL_CONFIG = "apps/cmdb/support-files/model_config.xlsx"

CONSUL_ATTRS = {
    "inst_name",
    "organization",
    "ip_addr",
    "port",
    "tag",
    "version",
    "install_path",
    "conf_path",
    "data_dir",
    "role",
    "operator",
    "bak_operator",
    "auto_collect",
    "collect_time",
    "collect_task",
}


@pytest.mark.unit
def test_consul_model_exists_as_middleware():
    models = pd.read_excel(MODEL_CONFIG, sheet_name="models", header=1)
    row = models[models["model_id"].astype(str) == "consul"]
    assert len(row) == 1
    assert row.iloc[0]["classification_id"] == "middleware"
    assert row.iloc[0]["app_topo_layer"] == "appService"
    assert "consul" in str(row.iloc[0]["icn"]).lower()


@pytest.mark.unit
def test_consul_attr_sheet_covers_collect_fields():
    xl = pd.ExcelFile(MODEL_CONFIG)
    assert "attr-consul" in xl.sheet_names
    attrs = pd.read_excel(MODEL_CONFIG, sheet_name="attr-consul", header=1)
    present = {str(value) for value in attrs["attr_id"].dropna()}
    assert CONSUL_ATTRS <= present
    required = set(attrs.loc[attrs["is_required"] == True, "attr_id"].astype(str))  # noqa: E712
    assert required >= {"inst_name", "organization"}
    tag = attrs[attrs["attr_id"].astype(str) == "tag"].iloc[0]
    assert str(tag["attr_type"]) == "tag"
