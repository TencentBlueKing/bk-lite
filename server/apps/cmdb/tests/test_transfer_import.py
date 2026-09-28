import io

import openpyxl

from apps.cmdb.utils.Import import Import


def test_transfer_rows_preserve_zero_and_name_the_failing_column(monkeypatch):
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
    assert rows[0] == (4, {"model_id": "host", "inst_name": "one", "count": 0}, {}, [])
    assert rows[1][0] == 5
    column, field_id, reason = rows[1][3][0]
    assert column == "C 数量"
    assert field_id == "count"
    assert reason == "第5行，字段'数量'的值'PRIVATE-CELL-SENTINEL'格式错误"


def test_user_and_organization_none_is_skipped_and_user_matches_username(monkeypatch):
    monkeypatch.setattr("apps.cmdb.services.model.ModelManage.model_association_search", lambda *a, **k: [])
    importer = Import(
        "system",
        [
            {"attr_id": "inst_name", "attr_name": "系统名称", "attr_type": "str"},
            {
                "attr_id": "operator",
                "attr_name": "运维人员",
                "attr_type": "user",
                "option": [{"id": 7, "name": "alice", "username": "alice", "display_name": "张三"}],
            },
            {
                "attr_id": "developer",
                "attr_name": "开发人员",
                "attr_type": "user",
                "option": [{"id": 7, "name": "alice", "username": "alice", "display_name": "张三"}],
            },
            {
                "attr_id": "organization",
                "attr_name": "组织",
                "attr_type": "organization",
                "option": [{"id": 1, "name": "Default"}],
            },
        ],
        [],
        "admin",
    )
    book = openpyxl.Workbook()
    sheet = book.active
    for row in (
        ["提示", "系统名称", "运维人员", "开发人员", "组织"],
        ["类型", "字符串", "用户", "用户", "组织"],
        ["字段标识(请勿编辑)", "inst_name", "operator", "developer", "organization"],
        [None, "sys-empty", "None", "None", "None"],
        [None, "sys-user", "张三(alice)", None, None],
        [None, "sys-id", "7", None, None],
    ):
        sheet.append(row)
    stream = io.BytesIO()
    book.save(stream)
    stream.seek(0)
    rows = list(importer.iter_transfer_rows(stream, [1]))
    assert rows[0][1] == {"model_id": "system", "inst_name": "sys-empty"}
    assert rows[0][3] == []
    assert rows[1][1]["operator"] == [7]
    assert rows[1][3] == []
    column, field_id, reason = rows[2][3][0]
    assert field_id == "operator"
    assert column.endswith("运维人员")
    assert "7" in reason


def test_credential_reason_omits_submitted_value():
    from apps.cmdb.services.transfer_execution import TransferExecution
    from apps.cmdb.services.transfer_import import TransferImport

    reason = TransferImport._public_reason("password", "第4行，字段'密码'的值'SECRET-CELL'格式错误")
    assert reason == "凭据字段格式不正确"
    assert "SECRET-CELL" not in reason
    assert TransferExecution._excel_text("=1+1") == "'=1+1"
    assert TransferExecution._excel_text("数量") == "数量"
