"""导入必须新增独立资源，重复导入不可覆盖。"""
import base64
import json
from io import BytesIO

import pytest
from openpyxl import Workbook

from apps.itsm.models import DataDictionary, DataDictionaryItem, DataTable, DataTableField, DataTableRow, Workflow, WorkflowVersion
from apps.itsm.tests.test_review_regressions import request
from apps.itsm.views.api import export_dictionaries, import_dictionaries
from apps.itsm.views.m2 import data_table_export, data_table_import, workflow_export, workflow_import

pytestmark = pytest.mark.django_db
PERMS = ["workflow-View", "workflow-Add", "workflow-Edit", "data-View", "data-Add", "data-Edit"]


def req(method="get", body=None, permissions=None):
    return request(method, body, "owner", permissions or PERMS)


def data(response):
    assert response.status_code == 200, response.content
    return json.loads(response.content)["data"]


def test_workflow_import_creates_distinct_drafts():
    original = Workflow.objects.create(key="flow", name="流程")
    version = WorkflowVersion.objects.create(workflow=original, version_no=1, design={"nodes": [{"id": "start", "type": "start"}], "edges": []})
    package = data(workflow_export(req(), original.id))
    copies = [data(workflow_import(req("post", package))) for _ in range(2)]
    assert len({item["id"] for item in copies} | {original.id}) == 3
    for item in copies:
        clone = Workflow.objects.get(pk=item["id"])
        assert clone.key.startswith("flow_") and len(clone.key) <= 64
        assert clone.current_version_id is None
        assert clone.versions.get().design == version.design
        assert not clone.versions.get().is_published
    assert original.versions.count() == 1


def test_dictionary_copy_preserves_tree_and_repeated_import():
    original = DataDictionary.objects.create(key="dict", name="字典")
    parent = DataDictionaryItem.objects.create(dictionary=original, key="p", label="父", order=3)
    DataDictionaryItem.objects.create(dictionary=original, key="c", label="子", parent=parent, is_enabled=False)
    package = json.loads(export_dictionaries(req()).content)
    for _ in range(2):
        result = data(import_dictionaries(req("post", package)))
        clone = DataDictionary.objects.get(pk=result["items"][0]["id"])
        assert clone.pk != original.pk and clone.key.startswith("dict_")
        child = clone.items.get(key="c")
        assert child.parent.dictionary_id == clone.pk and child.parent.key == "p"
        assert not child.is_enabled and child.parent.order == 3
    assert original.items.count() == 2
    count = DataDictionary.objects.count()
    assert import_dictionaries(req("post", [package[0], {"key": "bad", "name": ""}])).status_code == 400
    assert DataDictionary.objects.count() == count


def test_table_copy_preserves_columns_data_and_original():
    original = DataTable.objects.create(key="table", name="数据表")
    DataTableField.objects.create(table=original, key="text")
    DataTableField.objects.create(table=original, key="count", field_type="number")
    DataTableRow.objects.create(table=original, data={"text": "=1+1", "count": 3})
    package = data(data_table_export(req(), original.id))
    for _ in range(2):
        result = data(data_table_import(req("post", package)))
        clone = DataTable.objects.get(pk=result["id"])
        assert clone.pk != original.pk and clone.key.startswith("table_")
        assert clone.fields.get(key="count").field_type == "number"
        assert clone.rows.get().data == original.rows.get().data
    assert original.rows.count() == 1


def test_import_requires_add_permission_and_invalid_file_creates_nothing():
    Workflow.objects.create(key="flow", name="流程")
    DataTable.objects.create(key="table", name="数据表")
    assert workflow_import(req("post", {}, ["workflow-Edit"])).status_code == 403
    assert data_table_import(req("post", {}, ["data-Edit"])).status_code == 403
    assert workflow_import(req("post", {"design": "bad"})).status_code == 400
    assert data_table_import(req("post", {"content_base64": "bad"})).status_code == 400
    assert Workflow.objects.count() == 1 and DataTable.objects.count() == 1


def test_plain_excel_import_uses_header_order():
    table = DataTable.objects.create(key="x" * 64, name="长标识")
    DataTableField.objects.create(table=table, key="a")
    DataTableField.objects.create(table=table, key="b")
    book = Workbook()
    book.active.append(["b", "a"])
    book.active.append(["B", "A"])
    out = BytesIO()
    book.save(out)
    result = data(data_table_import(req("post", {"content_base64": base64.b64encode(out.getvalue()).decode()})))
    clone = DataTable.objects.get(pk=result["id"])
    assert len(clone.key) <= 64
    assert clone.rows.get().data == {"a": "A", "b": "B"}


def test_workflow_form_and_variables_are_independent():
    from apps.itsm.models import FormModel, FormVersion, WorkflowVariable

    form = FormModel.objects.create(key="f", name="表单")
    fv = FormVersion.objects.create(form=form, version_no=1, schema={"fields": [{"key": "title", "type": "input"}]})
    form.current_version = fv
    form.save()
    source = Workflow.objects.create(key="w", name="流程", form=form)
    WorkflowVersion.objects.create(workflow=source, version_no=1, design={"nodes": [], "edges": []})
    WorkflowVariable.objects.create(workflow=source, key="v", name="变量", default={"value": 2})
    package = data(workflow_export(req(), source.pk))
    clone = Workflow.objects.get(pk=data(workflow_import(req("post", package)))["id"])
    assert clone.form_id != form.pk
    assert clone.form.current_version.schema == fv.schema
    assert clone.variables.get().default == {"value": 2}
    other = data(workflow_import(request("post", package, "owner", PERMS, domain="other")))
    assert Workflow.objects.get(pk=other["id"]).domain == "other"


def test_dictionary_cycles_rollback():
    package = [
        {"key": "cycle", "name": "循环", "items": [{"key": "a", "label": "A", "parent_key": "b"}, {"key": "b", "label": "B", "parent_key": "a"}]}
    ]
    assert import_dictionaries(req("post", package)).status_code == 400
    assert not DataDictionary.objects.exists()


def test_table_export_roundtrip_empty_table_and_empty_values():
    table = DataTable.objects.create(key="empty", name="空表")
    package = data(data_table_export(req(), table.pk))
    clone = DataTable.objects.get(pk=data(data_table_import(req("post", package)))["id"])
    assert clone.fields.count() == 0 and clone.rows.count() == 0
    DataTableField.objects.create(table=table, key="value")
    DataTableRow.objects.create(table=table, data={"value": None})
    DataTableRow.objects.create(table=table, data={"value": ""})
    DataTableRow.objects.create(table=table, data={"value": {"nested": [1, 2]}})
    package = data(data_table_export(req(), table.pk))
    clone = DataTable.objects.get(pk=data(data_table_import(req("post", package)))["id"])
    assert list(clone.rows.order_by("id").values_list("data", flat=True)) == list(table.rows.order_by("id").values_list("data", flat=True))
