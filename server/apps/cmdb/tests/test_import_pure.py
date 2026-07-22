"""CMDB 资产导入解析逻辑覆盖测试（mock 图依赖）。

对照 specs/capabilities/legacy-prd-cmdb-资产.md：Excel 导入按字段类型(枚举/组织/用户/表格/标签/类型转换)解析与校验。
"""

import pytest


@pytest.fixture
def make_import(monkeypatch):
    """构造 Import 实例，mock 掉 get_model_asso_map（图依赖）。"""
    from apps.cmdb.utils.Import import Import

    monkeypatch.setattr(Import, "get_model_asso_map", lambda self: {})

    def _factory(attrs):
        return Import(model_id="host", attrs=attrs, exist_items=[], operator="admin")

    return _factory


# --------------------------------------------------------------------------
# _normalize_user_token (static)
# --------------------------------------------------------------------------


def test_normalize_user_token():
    from apps.cmdb.utils.Import import Import

    assert Import._normalize_user_token(None) is None
    assert Import._normalize_user_token("  ") == ""
    assert Import._normalize_user_token("admin") == "admin"
    assert Import._normalize_user_token("管理员(admin)") == "admin"
    assert Import._normalize_user_token("管理员（admin）") == "admin"


# --------------------------------------------------------------------------
# _build_field_maps
# --------------------------------------------------------------------------


def test_build_field_maps(make_import):
    attrs = [
        {"attr_id": "name", "attr_name": "名称", "attr_type": "str"},
        {"attr_id": "count", "attr_name": "数量", "attr_type": "int"},
        {"attr_id": "tags", "attr_name": "标签", "attr_type": "tag"},
        {"attr_id": "spec", "attr_name": "规格", "attr_type": "table"},
        {"attr_id": "status", "attr_name": "状态", "attr_type": "enum",
         "option": [{"id": "1", "name": "运行"}], "enum_select_mode": "single"},
        {"attr_id": "org", "attr_name": "组织", "attr_type": "organization", "option": []},
    ]
    imp = make_import(attrs)
    maps = imp._build_field_maps()
    assert maps["need_update_type"]["count"] == "int"
    assert "tags" in maps["tag_fields"]
    assert "spec" in maps["table_fields"]
    assert maps["need_val_to_id"]["status"] == {"运行": "1"}
    assert maps["org_user"]["org"] == "organization"


# --------------------------------------------------------------------------
# _process_type_conversion_field
# --------------------------------------------------------------------------


def test_process_type_conversion_ok(make_import):
    imp = make_import([{"attr_id": "count", "attr_name": "数量", "attr_type": "int"}])
    maps = imp._build_field_maps()
    value, err = imp._process_type_conversion_field("count", "42", 1, maps)
    assert value == 42 and err is None


def test_process_type_conversion_error(make_import):
    imp = make_import([{"attr_id": "count", "attr_name": "数量", "attr_type": "int"}])
    maps = imp._build_field_maps()
    value, err = imp._process_type_conversion_field("count", "abc", 1, maps)
    assert value is None and "格式错误" in err


# --------------------------------------------------------------------------
# _process_table_field
# --------------------------------------------------------------------------


def test_process_table_field_json(make_import):
    imp = make_import([{"attr_id": "spec", "attr_name": "规格", "attr_type": "table"}])
    maps = imp._build_field_maps()
    value, err = imp._process_table_field("spec", '[{"a": 1}]', 1, maps)
    assert value == [{"a": 1}] and err is None


def test_process_table_field_bad_json(make_import):
    imp = make_import([{"attr_id": "spec", "attr_name": "规格", "attr_type": "table"}])
    maps = imp._build_field_maps()
    value, err = imp._process_table_field("spec", "{bad", 1, maps)
    assert value is None and "JSON" in err


# --------------------------------------------------------------------------
# _process_enum_field
# --------------------------------------------------------------------------


def test_process_enum_single_ok(make_import):
    attrs = [{"attr_id": "status", "attr_name": "状态", "attr_type": "enum",
              "option": [{"id": "1", "name": "运行"}], "enum_select_mode": "single"}]
    imp = make_import(attrs)
    maps = imp._build_field_maps()
    value, err = imp._process_enum_field("status", "运行", 1, maps)
    assert value == ["1"] and err is None


def test_process_enum_single_invalid(make_import):
    attrs = [{"attr_id": "status", "attr_name": "状态", "attr_type": "enum",
              "option": [{"id": "1", "name": "运行"}], "enum_select_mode": "single"}]
    imp = make_import(attrs)
    maps = imp._build_field_maps()
    value, err = imp._process_enum_field("status", "未知", 1, maps)
    assert value is None and "无效" in err


def test_process_enum_multiple(make_import):
    attrs = [{"attr_id": "tags", "attr_name": "标签", "attr_type": "enum",
              "option": [{"id": "1", "name": "A"}, {"id": "2", "name": "B"}], "enum_select_mode": "multiple"}]
    imp = make_import(attrs)
    maps = imp._build_field_maps()
    value, err = imp._process_enum_field("tags", "A,B", 1, maps)
    assert value == ["1", "2"] and err is None


# --------------------------------------------------------------------------
# format_import_result_message
# --------------------------------------------------------------------------


def test_format_import_result_message(make_import):
    imp = make_import([])
    imp.format_import_result_message(
        add_results=[{"success": True, "data": {"inst_name": "h1"}},
                     {"success": False, "data": {"inst_name": "h2"}, "message": "重复"}],
        update_results=[{"success": True, "data": {"inst_name": "h3"}}],
        asso_result=[{"success": False, "message": "关联失败"}],
    )
    msg = imp.import_result_message
    assert msg["add"]["success"] == 1
    assert msg["add"]["error"] == 1
    assert msg["update"]["success"] == 1
    assert msg["asso"]["error"] == 1
