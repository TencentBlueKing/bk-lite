"""同步 Excel 导入必须保留 0、0.0 和 False，空白单元格和空容器仍然省略。"""

import io

import openpyxl

from apps.cmdb.utils.Import import Import


def _attrs():
    return [
        {"attr_id": "inst_name", "attr_name": "实例名", "attr_type": "str"},
        {"attr_id": "count", "attr_name": "数量", "attr_type": "int"},
        {"attr_id": "enabled", "attr_name": "启用", "attr_type": "bool"},
        {"attr_id": "remark", "attr_name": "备注", "attr_type": "str"},
        {"attr_id": "ratio", "attr_name": "比率", "attr_type": "float"},
        {"attr_id": "payload", "attr_name": "载荷", "attr_type": "list"},
        {"attr_id": "blank_note", "attr_name": "说明", "attr_type": "str"},
    ]


def _workbook():
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "host"
    rows = [
        ["实例名", "数量", "启用", "备注", "比率", "载荷", "说明", "关联"],
        ["字符串", "整数", "布尔", "字符串", "浮点", "列表", "字符串", "关联"],
        ["inst_name", "count", "enabled", "remark", "ratio", "payload", "blank_note", "host_connect_host"],
        ["native", 0, False, None, 0.0, None, None, None],
        ["text", "0", "False", "   ", "0.0", "[]", "None", 0],
        ["containers", 3, True, "{}", 1.25, "()", "kept", False],
        ["linked", 2, True, "note", "1.5", "[1]", "ok", "peer-a,peer-b"],
    ]
    for row in rows:
        sheet.append(row)
    stream = io.BytesIO()
    book.save(stream)
    stream.seek(0)
    return stream


def test_sync_import_keeps_zero_and_false_for_update(monkeypatch):
    monkeypatch.setattr("apps.cmdb.services.model.ModelManage.model_association_search", lambda *args, **kwargs: [])
    parsed = {}
    original = Import.format_excel_data

    def spy(self, excel_meta, allowed_org_ids=None):
        rows, asso = original(self, excel_meta, allowed_org_ids=allowed_org_ids)
        parsed["rows"] = rows
        parsed["asso"] = asso
        return rows, asso

    captured = {}

    def capture_update(self, inst_list):
        captured["inst_list"] = inst_list
        return [], []

    monkeypatch.setattr(Import, "format_excel_data", spy)
    monkeypatch.setattr(Import, "_load_import_exist_items", lambda self, inst_list: None)
    monkeypatch.setattr(Import, "inst_list_update", capture_update)

    importer = Import("host", _attrs(), [], "admin")
    importer.import_inst_list_support_edit(_workbook())

    handed = {row["inst_name"]: row for row in captured["inst_list"]}
    native = handed["native"]
    text = handed["text"]
    containers = handed["containers"]
    linked = handed["linked"]

    assert native["count"] == 0 and type(native["count"]) is int
    assert native["enabled"] is False
    assert native["ratio"] == 0.0 and type(native["ratio"]) is float
    assert "remark" not in native
    assert "payload" not in native
    assert "blank_note" not in native

    assert text["count"] == 0 and type(text["count"]) is int
    assert text["enabled"] is False
    assert text["ratio"] == 0.0 and type(text["ratio"]) is float
    assert "remark" not in text
    assert "payload" not in text
    assert "blank_note" not in text

    assert containers["count"] == 3
    assert containers["enabled"] is True
    assert containers["blank_note"] == "kept"
    assert containers["ratio"] == 1.25
    assert "remark" not in containers
    assert "payload" not in containers

    assert linked["remark"] == "note"
    assert linked["payload"] == [1]
    assert linked["blank_note"] == "ok"

    associations = parsed["asso"]["host_connect_host"]
    assert "native" not in associations
    assert "text" not in associations
    assert "containers" not in associations
    assert associations["linked"] == ["peer-a", "peer-b"]
    assert [row["inst_name"] for row in captured["inst_list"]] == ["native", "text", "containers", "linked"]
    assert [row["inst_name"] for row in parsed["rows"]] == ["native", "text", "containers", "linked"]


def test_async_transfer_rows_still_keep_numeric_zero(monkeypatch):
    monkeypatch.setattr("apps.cmdb.services.model.ModelManage.model_association_search", lambda *args, **kwargs: [])
    importer = Import(
        "host",
        [
            {"attr_id": "inst_name", "attr_name": "实例名", "attr_type": "str"},
            {"attr_id": "count", "attr_name": "数量", "attr_type": "int"},
        ],
        [],
        "admin",
    )
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "host"
    for row in (
        ["提示", "实例名", "数量"],
        ["类型", "str", "int"],
        ["字段标识(请勿编辑)", "inst_name", "count"],
        [None, "one", 0],
    ):
        sheet.append(row)
    stream = io.BytesIO()
    book.save(stream)
    stream.seek(0)
    rows = list(importer.iter_transfer_rows(stream, [1]))
    assert rows == [(4, {"model_id": "host", "inst_name": "one", "count": 0}, {}, [])]
