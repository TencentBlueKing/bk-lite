# -- coding: utf-8 --
"""IP 模型不应再保留误加的主机表格字段。"""
import os

import openpyxl
import pytest

from apps.cmdb.services.ipam_model_cleanup import IP_HOST_TABLE_ATTR_ID, drop_ip_host_table_attr

pytestmark = pytest.mark.unit

XLSX = os.path.join(os.path.dirname(__file__), "..", "support-files", "model_config.xlsx")


def test_model_config_ip_sheet_has_no_host_table():
    wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
    rows = list(wb["attr-ip"].iter_rows(values_only=True))
    keys = rows[1]
    attr_ids = [dict(zip(keys, row)).get("attr_id") for row in rows[2:] if row[0]]
    assert IP_HOST_TABLE_ATTR_ID not in attr_ids
    assert "ip_table_display" not in attr_ids


def test_drop_ip_host_table_attr_deletes_when_present(monkeypatch):
    deleted = {}

    class ModelManage:
        @staticmethod
        def search_model_info(model_id):
            return {"_id": 1, "attrs": '[{"attr_id": "ip_table", "attr_type": "table"}]'}

        @staticmethod
        def parse_attrs(raw):
            return [{"attr_id": "ip_table", "attr_type": "table"}]

        @staticmethod
        def delete_model_attr(model_id, attr_id, username="admin"):
            deleted["args"] = (model_id, attr_id, username)
            return []

    class Group:
        def __init__(self):
            self.attr_orders = ["mac", "ip_table", "ip_status"]

        def save(self, update_fields=None):
            deleted["orders"] = list(self.attr_orders)

    class Query:
        def filter(self, **kwargs):
            return [Group()]

    monkeypatch.setattr("apps.cmdb.services.model.ModelManage", ModelManage)
    monkeypatch.setattr("apps.cmdb.models.field_group.FieldGroup.objects", Query())
    assert drop_ip_host_table_attr() is True
    assert deleted["args"] == ("ip", "ip_table", "admin")
    assert deleted["orders"] == ["mac", "ip_status"]


def test_drop_ip_host_table_attr_noop_when_missing(monkeypatch):
    class ModelManage:
        @staticmethod
        def search_model_info(model_id):
            return {"_id": 1, "attrs": '[{"attr_id": "mac"}]'}

        @staticmethod
        def parse_attrs(raw):
            return [{"attr_id": "mac"}]

        @staticmethod
        def delete_model_attr(*args, **kwargs):
            raise AssertionError("should not delete")

    monkeypatch.setattr("apps.cmdb.services.model.ModelManage", ModelManage)
    assert drop_ip_host_table_attr() is False
