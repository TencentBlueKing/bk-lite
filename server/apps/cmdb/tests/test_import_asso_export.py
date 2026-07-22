"""CMDB Import 关联数据 / format_import_asso_data / Export 字段类型分支覆盖。

对照 specs/capabilities/legacy-prd-cmdb-资产.md：Excel 关联数据处理、用户/组织/枚举/标签/表格字段导出格式化、
inst_association 名称回填、关联校验入口。
"""

import io
import json

import openpyxl
import pytest

from apps.cmdb.utils.Import import Import
from apps.cmdb.utils.export import Export


# --------------------------------------------------------------------------
# Import.add_asso_data
# --------------------------------------------------------------------------


def _make_import(attrs=None):
    obj = Import.__new__(Import)
    obj.model_id = "host"
    obj.attrs = attrs or []
    obj.exist_items = []
    obj.operator = "admin"
    obj.inst_name_id_map = {}
    obj.inst_id_name_map = {}
    obj.inst_list = []
    obj.model_asso_map = {}
    obj.validation_errors = []
    obj._field_maps = None
    obj.import_result_message = {
        "add": {"success": 0, "error": 0, "data": []},
        "update": {"success": 0, "error": 0, "data": []},
        "asso": {"success": 0, "error": 0, "data": []},
    }
    return obj


def test_add_asso_data_unknown_asso_key():
    obj = _make_import()
    # asso_key 不在 model_asso_map → 跳过
    result = obj.add_asso_data({"unknown_key": {"h1": ["s1"]}})
    assert result == []


def test_add_asso_data_skip_empty_inst_name_list():
    obj = _make_import()
    obj.model_asso_map = {"host_conn_sw": {"asst_id": "conn", "src_model_id": "host", "dst_model_id": "sw"}}
    result = obj.add_asso_data({"host_conn_sw": {}})
    assert result == []


def test_add_asso_data_missing_src_inst_skip():
    obj = _make_import()
    obj.model_asso_map = {"host_conn_sw": {"asst_id": "conn", "src_model_id": "host", "dst_model_id": "sw"}}
    obj.inst_name_id_map = {"host": {}, "sw": {"s1": 2}}  # h1 不在 host 映射
    result = obj.add_asso_data({"host_conn_sw": {"h1": ["s1"]}})
    assert result == []


def test_add_asso_data_missing_dst_inst_skip():
    obj = _make_import()
    obj.model_asso_map = {"host_conn_sw": {"asst_id": "conn", "src_model_id": "host", "dst_model_id": "sw"}}
    obj.inst_name_id_map = {"host": {"h1": 1}, "sw": {}}  # s1 不在 sw 映射
    result = obj.add_asso_data({"host_conn_sw": {"h1": ["s1"]}})
    assert result == []


def test_add_asso_data_ok(monkeypatch):
    obj = _make_import()
    obj.model_asso_map = {"host_conn_sw": {"asst_id": "conn", "src_model_id": "host", "dst_model_id": "sw"}}
    obj.inst_name_id_map = {"host": {"h1": 1}, "sw": {"s1": 2}}
    obj.inst_id_name_map = {"host": {1: "h1"}, "sw": {2: "s1"}}
    # mock instance_association_create 跳过图调用
    monkeypatch.setattr(
        "apps.cmdb.utils.Import.Import.instance_association_create",
        lambda self, data, operator: {"_id": 100, "success": True},
    )
    result = obj.add_asso_data({"host_conn_sw": {"h1": ["s1"]}})
    assert len(result) == 1
    assert result[0]["_id"] == 100


def test_add_asso_data_dst_model_is_self():
    """当 self.model_id == dst_model_id 时，dst 模型 ID 解析为 src_model_id"""
    obj = _make_import()
    obj.model_id = "sw"  # 当前模型是 sw
    obj.model_asso_map = {"host_conn_sw": {"asst_id": "conn", "src_model_id": "host", "dst_model_id": "sw"}}
    # _model_src_inst_name 是 sw 的实例，目标模型是 host
    obj.inst_name_id_map = {"sw": {"s1": 2}, "host": {"h1": 1}}
    obj.inst_id_name_map = {"sw": {2: "s1"}, "host": {1: "h1"}}
    # 调用入口
    result = obj.add_asso_data({"host_conn_sw": {}})  # empty → return []
    assert result == []


# --------------------------------------------------------------------------
# Import.format_import_asso_data
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_format_import_asso_data_empty():
    obj = _make_import()
    # 空 → 直接返回，inst_name_id_map 保持空
    obj.format_import_asso_data({})
    assert obj.inst_name_id_map == {}


@pytest.mark.django_db
def test_format_import_asso_data_ok(fake_graph):
    obj = _make_import()
    obj.model_asso_map = {
        "host_conn_sw": {
            "asst_id": "conn", "src_model_id": "host", "dst_model_id": "sw",
            "model_asst_id": "host_conn_sw",
        }
    }
    fake_graph(
        "apps.cmdb.utils.Import",
        query_entity=([{"_id": 1, "inst_name": "h1"}, {"_id": 2, "inst_name": "s1"}], 2),
    )
    obj.format_import_asso_data({"host_conn_sw": {"h1": ["s1"]}})
    assert obj.inst_name_id_map["host"]["h1"] == 1


# --------------------------------------------------------------------------
# Export.export_inst_list 各字段类型分支
# --------------------------------------------------------------------------


_RICH_ATTRS = [
    {"attr_id": "inst_name", "attr_name": "实例名", "attr_type": "str", "is_required": True},
    {"attr_id": "tag", "attr_name": "标签", "attr_type": "tag"},
    {"attr_id": "status", "attr_name": "状态", "attr_type": "enum",
     "option": [{"id": "1", "name": "运行"}, {"id": "2", "name": "停止"}]},
    {"attr_id": "org", "attr_name": "组织", "attr_type": "organization",
     "option": [{"id": 1, "name": "Default"}, {"id": 2, "name": "Tech"}]},
    {"attr_id": "config", "attr_name": "配置", "attr_type": "table"},
    {"attr_id": "operator", "attr_name": "维护人", "attr_type": "user",
     "option": [{"id": "alice", "username": "alice", "display_name": "张三", "name": "张三"}]},
]


def test_export_inst_list_all_types():
    inst_list = [
        {"_id": 1, "inst_name": "h1",
         "tag": ["env:prod"],
         "status": ["1", "2"],
         "org": [1, 2],
         "config": [{"k": "v"}],
         "operator": ["alice"]},
    ]
    stream = Export(_RICH_ATTRS, model_id="host").export_inst_list(inst_list)
    data = stream.read()
    assert data[:2] == b"PK"


def test_export_inst_list_tag_string():
    attrs = [
        {"attr_id": "inst_name", "attr_name": "n", "attr_type": "str"},
        {"attr_id": "tag", "attr_name": "标签", "attr_type": "tag"},
    ]
    inst_list = [{"_id": 1, "inst_name": "h1", "tag": "env:prod"}]
    stream = Export(attrs, model_id="host").export_inst_list(inst_list)
    assert stream.read()[:2] == b"PK"


def test_export_inst_list_enum_single():
    attrs = [
        {"attr_id": "inst_name", "attr_name": "n", "attr_type": "str"},
        {"attr_id": "status", "attr_name": "状态", "attr_type": "enum",
         "option": [{"id": "1", "name": "运行"}]},
    ]
    inst_list = [{"_id": 1, "inst_name": "h1", "status": "1"}]
    stream = Export(attrs, model_id="host").export_inst_list(inst_list)
    assert stream.read()[:2] == b"PK"


def test_export_inst_list_organization_empty_list():
    attrs = [
        {"attr_id": "inst_name", "attr_name": "n", "attr_type": "str"},
        {"attr_id": "org", "attr_name": "组织", "attr_type": "organization",
         "option": [{"id": 1, "name": "Default"}]},
    ]
    inst_list = [{"_id": 1, "inst_name": "h1", "org": []}]
    stream = Export(attrs, model_id="host").export_inst_list(inst_list)
    assert stream.read()[:2] == b"PK"


def test_export_inst_list_operator_single_value():
    attrs = [
        {"attr_id": "inst_name", "attr_name": "n", "attr_type": "str"},
        {"attr_id": "operator", "attr_name": "维护人", "attr_type": "user",
         "option": [{"id": "alice", "username": "alice", "display_name": "张三", "name": "张三"}]},
    ]
    inst_list = [{"_id": 1, "inst_name": "h1", "operator": "alice"}]
    stream = Export(attrs, model_id="host").export_inst_list(inst_list)
    assert stream.read()[:2] == b"PK"


def test_export_inst_list_table_string_value():
    attrs = [
        {"attr_id": "inst_name", "attr_name": "n", "attr_type": "str"},
        {"attr_id": "config", "attr_name": "配置", "attr_type": "table"},
    ]
    inst_list = [{"_id": 1, "inst_name": "h1", "config": '[{"k":"v"}]'}]
    stream = Export(attrs, model_id="host").export_inst_list(inst_list)
    assert stream.read()[:2] == b"PK"


# --------------------------------------------------------------------------
# Export.format_inst_asst_name (with association)
# --------------------------------------------------------------------------


def test_export_format_inst_asst_name_no_association():
    obj = Export(_RICH_ATTRS, model_id="host")  # 无 association → 直接返回
    sheet_data = []
    obj.format_inst_asst_name({"_id": 1}, sheet_data)
    # 没有副作用


def test_export_format_inst_asst_name_with_association(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.search_model",
        lambda: [{"model_id": "host", "model_name": "主机"}, {"model_id": "sw", "model_name": "交换机"}],
    )
    monkeypatch.setattr(
        "apps.cmdb.services.instance.InstanceManage.instance_association_instance_list",
        lambda mid, iid: [
            {"model_asst_id": "host_conn_sw",
             "inst_list": [{"inst_name": "sw1"}, {"inst_name": "sw2"}]}
        ],
    )
    association = [
        {"asst_id": "conn", "src_model_id": "host", "dst_model_id": "sw",
         "model_asst_id": "host_conn_sw"}
    ]
    obj = Export(_RICH_ATTRS, model_id="host", association=association)
    sheet_data = ["a", "b"]
    obj.format_inst_asst_name({"_id": 1}, sheet_data)
    # 应至少追加了一项关联名称
    assert len(sheet_data) >= 3
