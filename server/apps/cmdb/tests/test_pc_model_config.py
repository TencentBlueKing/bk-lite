"""PC 与安装软件模型配置合同测试。

锁定 model_config.xlsx 中：
- `pc_software` 模型存在且归属固定资产分类；
- `pc` 补充的自动采集字段类型；
- `pc_software` 字段全集与类型；
- 人工资产字段（如 user）保持可编辑、不被采集对账抢占；
- `pc_software --install_on--> pc` 关联方向与约束。
"""

import os

import openpyxl

XLSX = os.path.join(os.path.dirname(__file__), "..", "support-files", "model_config.xlsx")

PC_COLLECTED = {
    "host_name": "str",
    "ip_addr": "str",
    "os_type": "str",
    "os_name": "str",
    "os_version": "str",
    "os_build": "str",
    "architecture": "str",
    "hardware_uuid": "str",
    "serial_number": "str",
    "brand": "str",
    "device_model": "str",
    "cpu": "str",
    "men": "str",
    "disk": "str",
    "logged_in_user": "str",
    "last_collect_time": "time",
}

SOFTWARE_FIELDS = {
    "inst_name": "str",
    "organization": "organization",
    "name": "str",
    "version": "str",
    "publisher": "str",
    "software_key": "str",
    "product_id": "str",
    "install_location": "str",
    "install_date": "str",
    "architecture": "str",
    "source": "str",
    "last_collect_time": "time",
}


def _rows(sheet):
    rows = list(sheet.iter_rows(values_only=True))
    keys = rows[1]
    return [dict(zip(keys, row)) for row in rows[2:] if row[0]]


def test_pc_and_software_schema_contract():
    wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
    models = {row["model_id"]: row for row in _rows(wb["models"])}
    assert models["pc_software"]["classification_id"] == "fixed_asset"

    pc_attrs = {row["attr_id"]: row for row in _rows(wb["attr-pc"])}
    sw_attrs = {row["attr_id"]: row for row in _rows(wb["attr-pc_software"])}
    assert {key: pc_attrs[key]["attr_type"] for key in PC_COLLECTED} == PC_COLLECTED
    assert {key: sw_attrs[key]["attr_type"] for key in SOFTWARE_FIELDS} == SOFTWARE_FIELDS

    # 人工资产字段保持可编辑，自动采集不得抢占
    assert pc_attrs["user"]["editable"] is True

    # 软件身份字段约束：inst_name 唯一且必填，organization 必填
    assert sw_attrs["inst_name"]["is_only"] is True
    assert sw_attrs["inst_name"]["is_required"] is True
    assert sw_attrs["organization"]["is_required"] is True

    association = _rows(wb["asso-pc_software"])[0]
    assert association == {
        "src_model_id": "pc_software",
        "dst_model_id": "pc",
        "asst_id": "install_on",
        "mapping": "n:1",
    }
