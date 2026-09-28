import io

import openpyxl

from apps.cmdb.utils.Import import Import


def test_transfer_rows_preserve_zero_and_row_number_without_echoing_bad_values(monkeypatch):
    monkeypatch.setattr("apps.cmdb.services.model.ModelManage.model_association_search", lambda *a, **k: [])
    importer = Import(
        "host",
        [{"attr_id": "inst_name", "attr_name": "实例名", "attr_type": "str"}, {"attr_id": "count", "attr_name": "数量", "attr_type": "int"}],
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
        [None, "two", "PRIVATE-CELL-SENTINEL"],
    ):
        sheet.append(row)
    stream = io.BytesIO()
    book.save(stream)
    stream.seek(0)
    rows = list(importer.iter_transfer_rows(stream, [1]))
    assert rows[0] == (4, {"model_id": "host", "inst_name": "one", "count": 0}, {}, "")
    assert rows[1][0] == 5
    assert rows[1][3] == "字段类型或取值不合法，请检查模板要求"
    assert "PRIVATE-CELL-SENTINEL" not in rows[1][3]
