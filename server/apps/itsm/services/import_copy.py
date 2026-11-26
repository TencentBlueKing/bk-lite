"""导入只创建新资源，不修改源对象或发布运行中的流程。"""

import base64
import binascii
import json
import re
from copy import deepcopy
from io import BytesIO
from uuid import uuid4
from zipfile import BadZipFile, ZipFile

from django.db import transaction
from openpyxl import Workbook, load_workbook

from apps.itsm.models import (
    DataDictionary,
    DataDictionaryItem,
    DataTable,
    DataTableField,
    DataTableRow,
    FormModel,
    FormVersion,
    Workflow,
    WorkflowVariable,
    WorkflowVersion,
)


def identity(key, name, suffix_label="导入副本"):
    if not isinstance(key, str) or not key.strip() or not isinstance(name, str) or not name.strip():
        raise ValueError("名称和标识不能为空")
    suffix = uuid4().hex[:12]
    return {"key": f"{key.strip()[:51]}_{suffix}", "name": f"{name.strip()[:110]}（{suffix_label}）"}


def actor(request):
    return {"domain": request.user.domain, "created_by": request.user.username, "updated_by": request.user.username}


def result(item):
    return {"id": item.pk, "key": item.key, "name": item.name}


@transaction.atomic
def copy_dictionaries(request, rows):
    if not isinstance(rows, list) or not 1 <= len(rows) <= 500:
        raise ValueError("字典文件需包含1至500个字典")
    created = []
    for row in rows:
        item = DataDictionary.objects.create(**identity(row["key"], row["name"]), **actor(request))
        children = row.get("items", [])
        if not isinstance(children, list) or len(children) > 10000:
            raise ValueError("字典项格式或数量无效")
        mapping = {}
        for child in children:
            key, label = child.get("key"), child.get("label")
            if not isinstance(key, str) or not 1 <= len(key) <= 64 or key in mapping or not isinstance(label, str) or len(label) > 128:
                raise ValueError("字典项标识重复或格式无效")
            order = child.get("order", 0)
            if type(order) is not int or order < 0 or type(child.get("is_enabled", True)) is not bool:
                raise ValueError("字典项排序或状态无效")
            mapping[key] = DataDictionaryItem.objects.create(
                dictionary=item, key=key, label=label, order=order, is_enabled=child.get("is_enabled", True), **actor(request)
            )
        for child in children:
            parent = child.get("parent_key")
            if parent is not None:
                if parent not in mapping or parent == child["key"]:
                    raise ValueError("字典父项无效")
                mapping[child["key"]].parent = mapping[parent]
        for child in mapping.values():
            seen = {child.key}
            parent = child.parent
            while parent:
                if parent.key in seen:
                    raise ValueError("字典层级存在循环")
                seen.add(parent.key)
                parent = parent.parent
        DataDictionaryItem.objects.bulk_update(mapping.values(), ["parent"])
        created.append(result(item))
    return {"created": len(created), "items": created}


@transaction.atomic
def copy_workflow(request, payload, *, suffix_label="导入副本"):
    if not isinstance(payload, dict):
        raise ValueError("流程文件必须是 JSON 对象")
    design = payload.get("design")
    if not isinstance(design, dict) or not isinstance(design.get("nodes"), list) or not isinstance(design.get("edges", []), list):
        raise ValueError("流程设计格式无效")
    clone = Workflow.objects.create(
        **identity(payload.get("key", "imported_flow"), payload.get("name", "导入流程"), suffix_label),
        description=str(payload.get("description", ""))[:500],
        **actor(request),
    )
    form = payload.get("form")
    if form:
        schema = form.get("schema")
        if not isinstance(schema, dict) or not isinstance(schema.get("fields"), list):
            raise ValueError("流程表单格式无效")
        copied_form = FormModel.objects.create(**identity(form["key"], form["name"], suffix_label), **actor(request))
        fv = FormVersion.objects.create(form=copied_form, version_no=1, schema=schema, **actor(request))
        copied_form.current_version = fv
        copied_form.save(update_fields=["current_version"])
        clone.form = copied_form
        clone.save(update_fields=["form"])
    version = WorkflowVersion.objects.create(workflow=clone, version_no=1, design=deepcopy(design), **actor(request))
    variables = payload.get("variables", [])
    if not isinstance(variables, list):
        raise ValueError("流程变量格式无效")
    keys = set()
    for variable in variables:
        key = variable.get("key")
        if not isinstance(key, str) or not 1 <= len(key) <= 64 or key in keys:
            raise ValueError("流程变量标识无效或重复")
        keys.add(key)
        WorkflowVariable.objects.create(
            workflow=clone,
            **{field: variable[field] for field in ("key", "name", "value_type", "source", "default") if field in variable},
            **actor(request),
        )
    return {**result(clone), "version_id": version.pk, "version_no": 1}


def export_table(table):
    fields = list(table.fields.order_by("id").values("key", "label", "field_type"))
    keys = [field["key"] for field in fields]
    rows = list(table.rows.order_by("id").values_list("data", flat=True))
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
                fields.append({"key": key, "field_type": "string"})
    book = Workbook()
    sheet = book.active
    sheet.title = "data"
    sheet.append(keys)
    json_cells = []
    for row_index, row in enumerate(rows, 2):
        for col, key in enumerate(keys, 1):
            value = row.get(key)
            if isinstance(value, (dict, list)) or (key in row and value in (None, "")):
                value = json.dumps(value, ensure_ascii=False)
                json_cells.append(f"{row_index}:{col}")
            if isinstance(value, str) and len(value.encode("utf-16-le")) > 65534:
                raise ValueError("数据超过 Excel 单元格容量，请缩短内容后导出")
            cell = sheet.cell(row_index, col, value)
            if isinstance(value, str):
                cell.data_type = "s"
    meta = book.create_sheet("_itsm")
    meta.append(["format", "itsm-table-v2"])
    metadata = json.dumps({"key": table.key, "name": table.name, "fields": fields, "json_cells": json_cells}, separators=(",", ":"))
    for row_index, start in enumerate(range(0, len(metadata), 16000), 2):
        meta.cell(row_index, 1, "metadata")
        meta.cell(row_index, 2, metadata[start : start + 16000]).data_type = "s"
    meta.sheet_state = "hidden"
    out = BytesIO()
    book.save(out)
    return {"filename": f"{table.key}.xlsx", "content_base64": base64.b64encode(out.getvalue()).decode()}


def infer_imported_field_types(table, created):
    for field in table.fields.all():
        values = [row.data[field.key] for row in created if row.data.get(field.key) is not None]
        kind = (
            "boolean"
            if values and all(type(v) is bool for v in values)
            else "number"
            if values and all(type(v) in (int, float) for v in values)
            else "string"
        )
        field.field_type = kind
        field.save(update_fields=["field_type"])
        if kind == "string":
            for row in created:
                if row.data.get(field.key) is not None:
                    row.data[field.key] = str(row.data[field.key])


@transaction.atomic
def copy_table(request, payload):
    content = payload.get("content_base64")
    if not isinstance(content, str) or len(content) > 28 * 1024 * 1024:
        raise ValueError("文件无效或超过20MB")
    try:
        raw = base64.b64decode(content, validate=True)
        with ZipFile(BytesIO(raw)) as archive:
            if sum(entry.file_size for entry in archive.infolist()) > 100 * 1024 * 1024:
                raise ValueError("解压后文件过大")
        book = load_workbook(BytesIO(raw), read_only=True, data_only=False)
    except (binascii.Error, BadZipFile, OSError, KeyError) as exc:
        raise ValueError("无效的xlsx文件") from exc
    try:
        meta = {}
        if "_itsm" in book:
            chunks = book["_itsm"].iter_rows(min_col=2, max_col=2, values_only=True)
            if next(chunks, (None,))[0] not in ("itsm-table-v1", "itsm-table-v2"):
                raise ValueError("不支持的数据表格式")
            meta = json.loads("".join(chunk for (chunk,) in chunks))
        sheet = book["data"] if "data" in book else book.active
        iterator = sheet.iter_rows(values_only=True)
        header = list(next(iterator, []))
        if meta.get("fields") == [] and not any(header):
            header = []
        if (
            (not header and meta.get("fields") != [])
            or len(header) > 200
            or any(not isinstance(key, str) or not 1 <= len(key) <= 64 for key in header)
            or len(set(header)) != len(header)
        ):
            raise ValueError("表头不能为空、重复或超过200列")
        if not meta:
            header_labels = list(header)
            used = set(header)
            for index, key in enumerate(header):
                if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", key):
                    replacement = f"field_{index + 1}"
                    while replacement in used:
                        replacement += "_"
                    header[index] = replacement
                    used.add(replacement)
        table = DataTable.objects.create(
            **identity(meta.get("key", "imported_table"), meta.get("name", str(payload.get("filename") or "导入数据表").removesuffix(".xlsx"))),
            **actor(request),
        )
        field_types = {field["key"]: field["field_type"] for field in meta.get("fields", [])}
        field_labels = {field["key"]: field.get("label") or field["key"] for field in meta.get("fields", [])}
        if not meta:
            field_labels = dict(zip(header, header_labels))
        for key in header:
            field_type = field_types.get(key, "string")
            if not isinstance(field_type, str) or len(field_type) > 32:
                raise ValueError("字段类型无效")
            DataTableField.objects.create(table=table, key=key, label=field_labels.get(key, key), field_type=field_type, **actor(request))
        json_cells = set(meta.get("json_cells", []))
        created = []
        for index, values in enumerate(iterator, 2):
            if index > 10001:
                raise ValueError("导入最多10000行")
            row = {}
            for col, (key, value) in enumerate(zip(header, values), 1):
                if value is not None:
                    if f"{index}:{col}" in json_cells:
                        value = json.loads(value)
                    elif hasattr(value, "isoformat"):
                        value = value.isoformat()
                    row[key] = value
            if row:
                created.append(DataTableRow(table=table, data=row, **actor(request)))
        if not meta:
            infer_imported_field_types(table, created)
        DataTableRow.objects.bulk_create(created, batch_size=500)
        return {**result(table), "created": len(created)}
    finally:
        book.close()
