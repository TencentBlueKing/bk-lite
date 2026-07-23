"""CMDB Import _resolve_organization_ids + _process_cell_value + format_excel_data 关联分支。

对照 specs/capabilities/legacy-prd-cmdb-资产.md·实例导入：组织字段（名称/路径）解析与范围校验、单元格值统一路由、
导入流程中关联字段的 sheet 解析。
"""

import io
import json

import openpyxl
import pytest

from apps.cmdb.utils.Import import Import
from apps.system_mgmt.models import Group


def _make(attrs=None):
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


# --------------------------------------------------------------------------
# _resolve_organization_ids
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_resolve_org_ids_empty():
    obj = _make()
    out, err, provided = obj._resolve_organization_ids([], allowed_org_set={1}, row_index=1, field_display_name="组织")
    assert out == [] and err is None and provided is False


@pytest.mark.django_db
def test_resolve_org_ids_by_name():
    g = Group.objects.create(name="__test_org_default")
    obj = _make()
    out, err, provided = obj._resolve_organization_ids(
        ["__test_org_default"], allowed_org_set={g.id}, row_index=1, field_display_name="组织",
    )
    assert out == [g.id]
    assert err is None
    assert provided is True


@pytest.mark.django_db
def test_resolve_org_ids_invalid_name():
    obj = _make()
    out, err, _ = obj._resolve_organization_ids(
        ["NoSuch"], allowed_org_set={1}, row_index=1, field_display_name="组织",
    )
    assert out == [] and "无效" in err


@pytest.mark.django_db
def test_resolve_org_ids_out_of_scope():
    g = Group.objects.create(name="__test_org_default")
    obj = _make()
    out, err, _ = obj._resolve_organization_ids(
        ["__test_org_default"], allowed_org_set=set(), row_index=1, field_display_name="组织",
    )
    assert out == [] and "范围" in err


@pytest.mark.django_db
def test_resolve_org_ids_by_path():
    parent = Group.objects.create(name="__test_org_default")
    child = Group.objects.create(name="__test_org_tech", parent_id=parent.id)
    obj = _make()
    out, err, _ = obj._resolve_organization_ids(
        ["__test_org_default/__test_org_tech"], allowed_org_set={child.id}, row_index=1, field_display_name="组织",
    )
    assert out == [child.id]


@pytest.mark.django_db
def test_resolve_org_ids_path_invalid():
    obj = _make()
    out, err, _ = obj._resolve_organization_ids(
        ["/"], allowed_org_set={1}, row_index=1, field_display_name="组织",
    )
    assert out == [] and "无效" in err


@pytest.mark.django_db
def test_resolve_org_ids_no_allowed_set_returns_context_error():
    g = Group.objects.create(name="__test_org_default")
    child = Group.objects.create(name="__test_org_tech", parent_id=g.id)
    obj = _make()
    out, err, _ = obj._resolve_organization_ids(
        ["__test_org_default/__test_org_tech"], allowed_org_set=None, row_index=1, field_display_name="组织",
    )
    assert out == [] and ("范围上下文" in err or "组织范围" in err)


@pytest.mark.django_db
def test_resolve_org_ids_no_allowed_set_unique_name_ok():
    g = Group.objects.create(name="UniqueOrg")
    obj = _make()
    out, err, _ = obj._resolve_organization_ids(
        ["UniqueOrg"], allowed_org_set=None, row_index=1, field_display_name="组织",
    )
    assert out == [g.id] and err is None


# --------------------------------------------------------------------------
# _process_cell_value 路由
# --------------------------------------------------------------------------


def test_process_cell_value_type_conversion():
    obj = _make()
    item = {}
    fm = {
        "need_update_type": {"n": "int"},
        "table_fields": set(),
        "tag_fields": set(),
        "need_val_to_id": {},
        "org_user": {},
        "attr_name_map": {"n": "数"},
    }
    handled, err, _ = obj._process_cell_value("n", "5", 1, fm, set(), item)
    assert handled is True and item["n"] == 5


def test_process_cell_value_table():
    obj = _make()
    item = {}
    fm = {
        "need_update_type": {},
        "table_fields": {"t"},
        "tag_fields": set(),
        "need_val_to_id": {},
        "org_user": {},
        "attr_name_map": {"t": "T"},
    }
    handled, err, _ = obj._process_cell_value("t", '[{"k":1}]', 1, fm, set(), item)
    assert handled is True and item["t"] == [{"k": 1}]


def test_process_cell_value_tag():
    obj = _make()
    item = {}
    fm = {
        "need_update_type": {},
        "table_fields": set(),
        "tag_fields": {"tag"},
        "need_val_to_id": {},
        "org_user": {},
        "attr_name_map": {"tag": "标签"},
    }
    handled, err, _ = obj._process_cell_value("tag", "env:prod", 1, fm, set(), item)
    assert handled is True and item["tag"] == ["env:prod"]


def test_process_cell_value_enum():
    obj = _make()
    item = {}
    fm = {
        "need_update_type": {},
        "table_fields": set(),
        "tag_fields": set(),
        "need_val_to_id": {"s": {"运行": "1"}},
        "org_user": {},
        "enum_select_mode": {"s": "single"},
        "attr_name_map": {"s": "状态"},
    }
    handled, err, _ = obj._process_cell_value("s", "运行", 1, fm, set(), item)
    assert handled is True and item["s"] == ["1"]


def test_process_cell_value_unknown_returns_unhandled():
    obj = _make()
    item = {}
    fm = {
        "need_update_type": {}, "table_fields": set(), "tag_fields": set(),
        "need_val_to_id": {}, "org_user": {}, "attr_name_map": {},
    }
    handled, err, _ = obj._process_cell_value("x", "v", 1, fm, set(), item)
    assert handled is False and err is None


# --------------------------------------------------------------------------
# format_excel_data 含关联列
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_format_excel_data_with_asso_column():
    obj = _make([
        {"attr_id": "inst_name", "attr_type": "str", "attr_name": "名称"},
    ])
    # 模拟当前模型有一条关联，sheet 第 2 行将列类型标记为"关联"
    obj.model_asso_map = {"host_conn_sw": {"asst_id": "conn", "src_model_id": "host", "dst_model_id": "sw"}}

    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.title = "host"
    sheet.append(["实例名", "关联"])
    sheet.append(["字符串", "关联"])  # 关联列
    sheet.append(["inst_name", "host_conn_sw"])  # asso_key 含 model_id
    sheet.append(["h1", "sw1,sw2"])
    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)

    result, asso_key_map = obj.format_excel_data(stream)
    assert len(result) == 1
    assert asso_key_map["host_conn_sw"] == {"h1": ["sw1", "sw2"]}


# --------------------------------------------------------------------------
# get_check_attr_map
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_get_check_attr_map(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.utils.Import.build_unique_rule_context",
        lambda mid: type("Ctx", (), {"unique_rules": [], "attrs_by_id": {}})(),
    )
    obj = _make([
        {"attr_id": "name", "attr_name": "名称", "attr_type": "str",
         "is_only": True, "is_required": True, "editable": True},
    ])
    out = obj.get_check_attr_map()
    assert "name" in out["is_only"]
    assert "name" in out["is_required"]
    assert "name" in out["editable"]


# --------------------------------------------------------------------------
# import_inst_list_support_edit（覆盖入口分流）
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_import_inst_list_support_edit(monkeypatch):
    obj = _make([{"attr_id": "inst_name", "attr_type": "str", "attr_name": "名称"}])
    monkeypatch.setattr(
        "apps.cmdb.utils.Import.Import.inst_list_update",
        lambda self, lst: ([], []),
    )
    monkeypatch.setattr(
        "apps.cmdb.utils.Import.Import.format_excel_data",
        lambda self, fs, allowed_org_ids=None: ([{"inst_name": "h1"}], {}),
    )
    monkeypatch.setattr(
        "apps.cmdb.utils.Import.Import.format_import_asso_data",
        lambda self, asso_map: None,
    )
    monkeypatch.setattr(
        "apps.cmdb.utils.Import.Import.add_asso_data", lambda self, asso_map: []
    )
    add_r, update_r, asso_r = obj.import_inst_list_support_edit(b"data")
    assert add_r == [] and update_r == [] and asso_r == []
