# -- coding: utf-8 --
"""IP 模型配置不应再带主机表格字段。"""
import os

import openpyxl
import pytest

pytestmark = pytest.mark.unit

XLSX = os.path.join(os.path.dirname(__file__), "..", "support-files", "model_config.xlsx")


def test_model_config_ip_sheet_has_no_host_table():
    wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
    rows = list(wb["attr-ip"].iter_rows(values_only=True))
    keys = rows[1]
    attr_ids = [dict(zip(keys, row)).get("attr_id") for row in rows[2:] if row[0]]
    assert "ip_table" not in attr_ids
    assert "ip_table_display" not in attr_ids
