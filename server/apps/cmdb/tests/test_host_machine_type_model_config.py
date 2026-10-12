# -*- coding: utf-8 -*-
"""host 模型机器类型字段，以及与物理服务器的 1:1 关联。不含自动关联规则。"""
import json

import pandas as pd
import pytest

MODEL_CONFIG = "apps/cmdb/support-files/model_config.xlsx"

pytestmark = pytest.mark.unit


def _records(sheet_name):
    frame = pd.read_excel(MODEL_CONFIG, sheet_name=sheet_name, header=1)
    return frame.fillna("").to_dict("records")


def test_host_machine_type_enum_defaults_to_unknown():
    rows = _records("attr-host")
    attr = next(row for row in rows if str(row.get("attr_id")).strip() == "machine_type")

    assert attr["attr_name"] == "机器类型"
    assert attr["attr_type"] == "enum"
    assert attr["attr_group"] == "基本信息"
    option = attr["option"]
    if isinstance(option, str):
        option = json.loads(option)
    assert option == [
        {"id": "unknown", "name": "未知"},
        {"id": "virtual", "name": "虚拟机"},
        {"id": "physical_server", "name": "物理服务器"},
    ]
    default_value = attr["default_value"]
    if isinstance(default_value, str):
        default_value = json.loads(default_value)
    assert default_value == ["unknown"]


def test_host_connects_physical_server_one_to_one_without_auto_rule():
    rows = _records("asso-host")
    matched = [
        row
        for row in rows
        if str(row.get("src_model_id")).strip() == "host"
        and str(row.get("dst_model_id")).strip() == "physcial_server"
        and str(row.get("asst_id")).strip() == "connect"
    ]

    assert len(matched) == 1
    assert str(matched[0]["mapping"]).strip() == "1:1"
    assert str(matched[0].get("auto_relation_rule") or "").strip() == ""


def test_host_mount_and_nic_are_tables():
    rows = _records("attr-host")
    by_id = {str(row.get("attr_id")).strip(): row for row in rows}

    mounts = json.loads(by_id["mounts"]["option"])
    nics = json.loads(by_id["nics"]["option"])

    assert by_id["mounts"]["attr_type"] == "table"
    assert by_id["mounts"]["attr_name"] == "挂载点"
    assert [item["column_id"] for item in mounts] == ["mount", "device", "fstype", "size_gb"]
    assert by_id["nics"]["attr_type"] == "table"
    assert by_id["nics"]["attr_name"] == "网卡"
    assert [item["column_id"] for item in nics] == ["name", "mac", "ip"]
