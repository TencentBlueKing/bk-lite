"""CMDB Import 工具纯逻辑覆盖测试（绕开 __init__ 中的 GraphClient 调用）。

对照 specs/capabilities/legacy-prd-cmdb-资产.md·实例导入：Excel 字段类型转换、表格/标签/枚举/组织/用户字段解析、
用户显示名解析、字段映射构建、行处理校验错误聚合。
"""

import pytest

from apps.cmdb.utils.Import import Import


def _make(attrs):
    """构造 Import 实例但绕开 __init__（避免 get_model_asso_map 调图库）。"""
    obj = Import.__new__(Import)
    obj.model_id = "host"
    obj.attrs = attrs
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
# _normalize_user_token（静态方法）
# --------------------------------------------------------------------------


def test_normalize_user_token_none():
    assert Import._normalize_user_token(None) is None


def test_normalize_user_token_empty():
    assert Import._normalize_user_token("  ") == ""


def test_normalize_user_token_plain():
    assert Import._normalize_user_token("alice") == "alice"


def test_normalize_user_token_en_parens():
    assert Import._normalize_user_token("张三(alice)") == "alice"


def test_normalize_user_token_cn_parens():
    assert Import._normalize_user_token("张三（alice）") == "alice"


# --------------------------------------------------------------------------
# _build_field_maps
# --------------------------------------------------------------------------


def test_build_field_maps_categorizes():
    attrs = [
        {"attr_id": "name", "attr_name": "名称", "attr_type": "str"},
        {"attr_id": "tab", "attr_name": "表", "attr_type": "table"},
        {"attr_id": "tag", "attr_name": "标签", "attr_type": "tag"},
        {"attr_id": "org", "attr_name": "组织", "attr_type": "organization", "option": [{"id": 1, "name": "Default"}]},
        {"attr_id": "user", "attr_name": "用户", "attr_type": "user", "option": [{"id": "alice", "name": "张三"}]},
        {"attr_id": "status", "attr_name": "状态", "attr_type": "enum",
         "option": [{"id": "1", "name": "运行"}, {"id": "2", "name": "停止"}], "enum_select_mode": "single"},
    ]
    fm = _make(attrs)._build_field_maps()
    assert "tab" in fm["table_fields"]
    assert "tag" in fm["tag_fields"]
    assert "org" in fm["org_user"] and fm["org_user"]["org"] == "organization"
    assert fm["need_val_to_id"]["user"] == {"张三": "alice"}
    assert fm["enum_select_mode"]["status"] == "single"
    assert fm["attr_name_map"]["name"] == "名称"


# --------------------------------------------------------------------------
# _process_table_field
# --------------------------------------------------------------------------


def test_process_table_field_json_string():
    obj = _make([])
    fm = {"attr_name_map": {"t": "表"}}
    out, err = obj._process_table_field("t", '[{"a":1}]', 1, fm)
    assert out == [{"a": 1}] and err is None


def test_process_table_field_bad_json():
    obj = _make([])
    fm = {"attr_name_map": {"t": "表"}}
    out, err = obj._process_table_field("t", "{bad", 2, fm)
    assert out is None and "格式错误" in err


def test_process_table_field_non_string_passthrough():
    obj = _make([])
    fm = {"attr_name_map": {"t": "表"}}
    out, err = obj._process_table_field("t", [{"a": 1}], 3, fm)
    assert out == [{"a": 1}] and err is None


# --------------------------------------------------------------------------
# _process_tag_field
# --------------------------------------------------------------------------


def test_process_tag_field_valid():
    obj = _make([])
    fm = {"attr_name_map": {"tag": "标签"}}
    out, err = obj._process_tag_field("tag", "env:prod,app:web", 1, fm)
    assert err is None
    assert "env:prod" in out


def test_process_tag_field_list():
    obj = _make([])
    fm = {"attr_name_map": {"tag": "标签"}}
    out, err = obj._process_tag_field("tag", ["env:prod"], 1, fm)
    assert err is None
    assert out == ["env:prod"]


# --------------------------------------------------------------------------
# _process_enum_field
# --------------------------------------------------------------------------


def test_process_enum_field_single_ok():
    obj = _make([])
    fm = {
        "enum_select_mode": {"s": "single"},
        "need_val_to_id": {"s": {"运行": "1", "停止": "2"}},
        "attr_name_map": {"s": "状态"},
    }
    out, err = obj._process_enum_field("s", "运行", 1, fm)
    assert out == ["1"] and err is None


def test_process_enum_field_single_invalid():
    obj = _make([])
    fm = {
        "enum_select_mode": {"s": "single"},
        "need_val_to_id": {"s": {"运行": "1"}},
        "attr_name_map": {"s": "状态"},
    }
    out, err = obj._process_enum_field("s", "未知", 1, fm)
    assert out is None and "无效" in err


def test_process_enum_field_multi_comma():
    obj = _make([])
    fm = {
        "enum_select_mode": {"s": "multiple"},
        "need_val_to_id": {"s": {"运行": "1", "停止": "2"}},
        "attr_name_map": {"s": "状态"},
    }
    out, err = obj._process_enum_field("s", "运行,停止", 1, fm)
    assert err is None
    assert set(out) == {"1", "2"}


def test_process_enum_field_multi_invalid():
    obj = _make([])
    fm = {
        "enum_select_mode": {"s": "multiple"},
        "need_val_to_id": {"s": {"运行": "1"}},
        "attr_name_map": {"s": "状态"},
    }
    out, err = obj._process_enum_field("s", "未知", 1, fm)
    assert out is None and "无效" in err


def test_process_enum_field_multi_list():
    obj = _make([])
    fm = {
        "enum_select_mode": {"s": "multiple"},
        "need_val_to_id": {"s": {"a": "1", "b": "2"}},
        "attr_name_map": {"s": "S"},
    }
    out, err = obj._process_enum_field("s", ["a", "b"], 1, fm)
    assert err is None and set(out) == {"1", "2"}


# --------------------------------------------------------------------------
# _process_type_conversion_field
# --------------------------------------------------------------------------


def test_process_type_conversion_int_ok():
    obj = _make([])
    fm = {"need_update_type": {"n": "int"}, "attr_name_map": {"n": "数"}}
    out, err = obj._process_type_conversion_field("n", "123", 1, fm)
    assert out == 123 and err is None


def test_process_type_conversion_int_bad():
    obj = _make([])
    fm = {"need_update_type": {"n": "int"}, "attr_name_map": {"n": "数"}}
    out, err = obj._process_type_conversion_field("n", "notnumber", 1, fm)
    assert out is None and "格式错误" in err


# --------------------------------------------------------------------------
# _process_org_user_field（用户分支，无 DB）
# --------------------------------------------------------------------------


def test_process_user_field_ok():
    obj = _make([])
    fm = {
        "org_user": {"u": "user"},
        "need_val_to_id": {"u": {"alice": 1, "bob": 2}},
        "attr_name_map": {"u": "用户"},
    }
    out, err, _ = obj._process_org_user_field("u", "alice,bob", 1, fm, allowed_org_set=set())
    assert out == [1, 2] and err is None


def test_process_user_field_invalid():
    obj = _make([])
    fm = {
        "org_user": {"u": "user"},
        "need_val_to_id": {"u": {"alice": 1}},
        "attr_name_map": {"u": "用户"},
    }
    out, err, _ = obj._process_org_user_field("u", "carol", 1, fm, allowed_org_set=set())
    assert out is None and "无效" in err


def test_process_user_field_with_display_name():
    obj = _make([])
    fm = {
        "org_user": {"u": "user"},
        "need_val_to_id": {"u": {"alice": 1}},
        "attr_name_map": {"u": "用户"},
    }
    out, err, _ = obj._process_org_user_field("u", "张三(alice)", 1, fm, allowed_org_set=set())
    assert out == [1] and err is None


# --------------------------------------------------------------------------
# format_import_result_message
# --------------------------------------------------------------------------


def test_format_import_result_message():
    obj = _make([])
    add_results = [
        {"data": {"inst_name": "h1"}, "success": True},
        {"data": {"inst_name": "h2"}, "success": False, "message": "重复"},
    ]
    update_results = [{"data": {"inst_name": "h3"}, "success": True}]
    asso_result = [{"success": False, "message": "关联缺失"}]
    obj.format_import_result_message(add_results, update_results, asso_result)
    assert obj.import_result_message["add"]["success"] == 1
    assert obj.import_result_message["add"]["error"] == 1
    assert obj.import_result_message["update"]["success"] == 1
    assert obj.import_result_message["asso"]["error"] == 1


# --------------------------------------------------------------------------
# _normalize_and_merge_tag_records
# --------------------------------------------------------------------------


def test_normalize_tag_records_no_tag_attr():
    obj = _make([{"attr_id": "name", "attr_type": "str", "attr_name": "名称"}])
    out = obj._normalize_and_merge_tag_records([{"inst_name": "h", "tag": ["a:1"]}])
    # 没有 tag 属性 → 原样返回
    assert out == [{"inst_name": "h", "tag": ["a:1"]}]


def test_normalize_tag_records_valid(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.merge_tag_options_from_values",
        lambda mid, vals: None,
    )
    obj = _make([{"attr_id": "tag", "attr_type": "tag", "attr_name": "标签",
                  "option": {"mode": "free"}}])
    out = obj._normalize_and_merge_tag_records([{"inst_name": "h", "tag": ["env:prod"]}])
    assert out[0]["tag"] == ["env:prod"]


def test_normalize_tag_records_invalid_collects_error():
    obj = _make([{"attr_id": "tag", "attr_type": "tag", "attr_name": "标签",
                  "option": {"mode": "strict", "options": [{"key": "env", "value": "prod"}]}}])
    obj._normalize_and_merge_tag_records([{"inst_name": "h", "tag": ["env:dev"]}])
    # strict 模式 dev 不在候选 → validation_errors 增加
    assert len(obj.validation_errors) > 0


# --------------------------------------------------------------------------
# inst_list_save / inst_list_update（fake_graph）
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_inst_list_save(fake_graph, monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.display_field.DisplayFieldHandler.build_display_fields",
        lambda mid, info, attrs: info,
    )
    monkeypatch.setattr(
        "apps.cmdb.validators.FieldValidator.validate_instance_data",
        lambda data, attrs: [],
    )
    obj = _make([{"attr_id": "inst_name", "attr_type": "str", "attr_name": "名称", "is_required": True}])
    # 用上下文管理器 patch GraphClient
    fake_graph("apps.cmdb.utils.Import", batch_create_entity=[{"data": {"inst_name": "h1"}, "success": True}])
    # get_check_attr_map 依赖 build_unique_rule_context → mock 之
    monkeypatch.setattr(
        "apps.cmdb.utils.Import.build_unique_rule_context",
        lambda mid: type("Ctx", (), {"unique_rules": [], "attrs_by_id": {}})(),
    )
    result = obj.inst_list_save([{"inst_name": "h1"}])
    assert result[0]["success"] is True


@pytest.mark.django_db
def test_inst_list_update(fake_graph, monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.display_field.DisplayFieldHandler.build_display_fields",
        lambda mid, info, attrs: info,
    )
    monkeypatch.setattr(
        "apps.cmdb.validators.FieldValidator.validate_instance_data",
        lambda data, attrs: [],
    )
    monkeypatch.setattr(
        "apps.cmdb.utils.Import.build_unique_rule_context",
        lambda mid: type("Ctx", (), {"unique_rules": [], "attrs_by_id": {}})(),
    )
    obj = _make([{"attr_id": "inst_name", "attr_type": "str", "attr_name": "名称", "is_required": True}])
    fake_graph(
        "apps.cmdb.utils.Import",
        batch_save_entity=([{"data": {"inst_name": "h1"}, "success": True}], []),
    )
    add_r, update_r = obj.inst_list_update([{"inst_name": "h1"}])
    assert add_r[0]["success"] is True


# --------------------------------------------------------------------------
# get_model_asso_map / add_asso_data 输入空
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_get_model_asso_map_empty(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.model_association_search",
        lambda mid: [],
    )
    obj = _make([])
    assert obj.get_model_asso_map() == {}


def test_add_asso_data_empty():
    obj = _make([])
    assert obj.add_asso_data({}) == []
    assert obj.add_asso_data(None) == []


# --------------------------------------------------------------------------
# format_excel_data（构造 in-memory Excel）
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_format_excel_data():
    import io
    import openpyxl

    obj = _make([
        {"attr_id": "inst_name", "attr_type": "str", "attr_name": "名称", "is_required": True},
        {"attr_id": "ip", "attr_type": "str", "attr_name": "IP"},
    ])
    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.title = "host"  # model_id
    sheet.append(["实例名(必填)", "IP"])  # row 1: attr_name
    sheet.append(["字符串", "字符串"])  # row 2: type
    sheet.append(["inst_name", "ip"])  # row 3: attr_id
    sheet.append(["h1", "1.1.1.1"])
    sheet.append(["h2", "2.2.2.2"])

    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)

    result, asso_key_map = obj.format_excel_data(stream)
    assert len(result) == 2
    assert result[0]["inst_name"] == "h1"


@pytest.mark.django_db
def test_format_excel_data_wrong_sheet_name():
    import io
    import openpyxl

    obj = _make([{"attr_id": "inst_name", "attr_type": "str", "attr_name": "名称"}])
    wb = openpyxl.Workbook()
    wb.active.title = "wrong_model"
    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    with pytest.raises(ValueError):
        obj.format_excel_data(stream)
