from types import SimpleNamespace

from apps.itsm.flowable.client import _variables
from apps.itsm.services.ticket.service import _form_variables


def test_flowable_table_variables_preserve_typed_rows():
    rows = [{"size": 0, "name": "第一行", "enabled": False}, {"size": 64, "name": "第二行", "enabled": True}]
    version = SimpleNamespace(
        design={"form_schema": {"fields": [{"key": "items", "type": "table", "children": [{"key": key} for key in ("size", "name", "enabled")]}]}}
    )
    data = {"items": [dict(row, _itsm_row_ref="internal") for row in rows], "_field_labels": {}, "unknown": rows}
    assert _variables(_form_variables(data, version)) == [{"name": "form_items", "type": "json", "value": rows}]
    assert _form_variables({"items": [], "title": "测试"}, version) == {"form_items": [], "form_title": "测试"}
