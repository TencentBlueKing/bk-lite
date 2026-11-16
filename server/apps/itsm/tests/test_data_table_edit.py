import json

import pytest

from apps.itsm.models import DataTable, DataTableField, DataTableRow
from apps.itsm.tests.test_review_regressions import request
from apps.itsm.views import m2

pytestmark = pytest.mark.django_db


def body(response):
    assert response.status_code == 200, response.content
    return json.loads(response.content)["data"]


def test_table_fields_and_row_edit_validate_types_and_domain():
    result = body(
        m2.data_tables(
            request(
                "post",
                {
                    "name": "设备",
                    "key": "demo",
                    "fields": [{"key": "name", "label": "名称", "type": "string"}, {"key": "amount", "label": "金额", "type": "number"}],
                },
                permissions=["data-Add"],
            )
        )
    )
    table = DataTable.objects.get(pk=result["id"])
    assert table.fields.get(key="amount").label == "金额"
    row = body(m2.data_table_rows(request("post", {"data": {"name": "服务器", "amount": 12}}, permissions=["data-Edit"]), table.id))
    body(m2.data_table_row_detail(request("put", {"data": {"name": "更新", "amount": 20}}, permissions=["data-Edit"]), table.id, row["id"]))
    assert DataTableRow.objects.get(pk=row["id"]).data["amount"] == 20
    assert m2.data_table_row_detail(request("put", {"data": {"amount": "bad"}}, permissions=["data-Edit"]), table.id, row["id"]).status_code == 400
    assert m2.data_table_row_detail(request("put", {"data": {}}, permissions=["data-View"]), table.id, row["id"]).status_code == 403
    assert m2.data_table_row_detail(request("put", {"data": {}}, permissions=["data-Edit"], domain="other"), table.id, row["id"]).status_code == 404


def test_field_changes_preserve_data_and_reject_incompatible_types():
    table = DataTable.objects.create(name="表", key="demo")
    DataTableField.objects.create(table=table, key="name", label="名称", field_type="string")
    DataTableRow.objects.create(table=table, data={"name": "已有文本"})
    payload = {
        "name": "新表名",
        "fields": [{"key": "name", "label": "设备名称", "type": "string"}, {"key": "enabled", "label": "启用", "type": "boolean"}],
    }
    body(m2.data_table_detail(request("put", payload, permissions=["data-Edit"]), table.id))
    assert table.fields.get(key="name").label == "设备名称"
    payload["fields"][0]["type"] = "number"
    assert m2.data_table_detail(request("put", payload, permissions=["data-Edit"]), table.id).status_code == 400
    assert table.fields.get(key="name").field_type == "string"
    payload["fields"] = payload["fields"][1:]
    assert m2.data_table_detail(request("put", payload, permissions=["data-Edit"]), table.id).status_code == 400


def test_global_import_retains_field_names_and_creates_new_table():
    from apps.itsm.services.import_copy import export_table

    table = DataTable.objects.create(name="原表", key="original")
    DataTableField.objects.create(table=table, key="amount", label="金额", field_type="number")
    DataTableRow.objects.create(table=table, data={"amount": 10})
    result = body(m2.data_table_import(request("post", export_table(table), permissions=["data-Add"])))
    clone = DataTable.objects.get(pk=result["id"])
    assert clone.id != table.id and clone.key.startswith("original_")
    assert clone.fields.get(key="amount").label == "金额"
    assert clone.rows.get().data == {"amount": 10}


@pytest.mark.parametrize(
    "kind,value",
    [
        ("string", "text"),
        ("number", 12.5),
        ("boolean", True),
        ("date", "2026-11-16"),
        ("datetime", "2026-11-16T12:30"),
        ("object", {"x": 1}),
        ("array", [1, 2]),
    ],
)
def test_row_types(kind, value):
    from apps.itsm.services.data_tables import validate_row

    assert validate_row({"x": value}, [{"key": "x", "label": "字段", "type": kind}]) == {"x": value}


@pytest.mark.parametrize("kind,value", [("number", True), ("number", "12"), ("boolean", "true"), ("date", "bad"), ("object", []), ("array", {})])
def test_invalid_row_types(kind, value):
    from apps.itsm.services.data_tables import validate_row

    with pytest.raises(ValueError):
        validate_row({"x": value}, [{"key": "x", "label": "字段", "type": kind}])


def test_plain_excel_chinese_header_and_inferred_types():
    import base64
    from io import BytesIO

    from openpyxl import Workbook

    book = Workbook()
    book.active.append(["设备名称", "金额", "启用"])
    book.active.append(["示例", 25, True])
    stream = BytesIO()
    book.save(stream)
    result = body(
        m2.data_table_import(
            request("post", {"filename": "设备.xlsx", "content_base64": base64.b64encode(stream.getvalue()).decode()}, permissions=["data-Add"])
        )
    )
    table = DataTable.objects.get(pk=result["id"])
    assert list(table.fields.order_by("id").values_list("label", "field_type")) == [
        ("设备名称", "string"),
        ("金额", "number"),
        ("启用", "boolean"),
    ]
    assert table.rows.get().data == {"field_1": "示例", "field_2": 25, "field_3": True}
