from apps.itsm.services.form.validator import FormValidator

SCHEMA = {
    "version": 1,
    "fields": [
        {"key": "title", "type": "input", "label": "标题", "required": True, "props": {"maxLength": 8}},
        {
            "key": "priority",
            "type": "select",
            "label": "优先级",
            "source": {"type": "static", "options": [{"label": "P1", "value": "P1"}, {"label": "P3", "value": "P3"}]},
        },
        {"key": "host", "type": "cmdb", "label": "主机", "required": True},
        {"key": "qty", "type": "number", "label": "数量", "props": {"min": 1, "max": 10}},
        {"key": "secret", "type": "input", "label": "内部备注"},
        {"key": "total", "type": "number", "label": "合计"},
        {"key": "items", "type": "table", "label": "明细"},
        {"key": "note", "type": "description", "label": "说明"},
    ],
    "rules": [
        {"type": "visible", "field": "host", "when": {"field": "priority", "op": "in", "value": ["P1"]}},
        {"type": "compute", "field": "total", "expr": "sum(items.qty)"},
    ],
}


def test_required_and_type_errors():
    errors = FormValidator(SCHEMA).validate({"priority": "P3", "qty": "x"})
    assert errors["title"] == "必填"
    assert errors["qty"] == "必须是数字"


def test_field_permission_drops_readonly_input():
    validator = FormValidator(SCHEMA, {"secret": "readonly", "*": "editable"})
    errors = validator.validate({"title": "服务器", "priority": "P3", "secret": "不要写入", "qty": 2, "items": []})
    assert errors == {}
    assert "secret" not in validator.cleaned
    assert validator.cleaned["title"] == "服务器"


def test_hidden_field_skips_required_and_compute_runs():
    validator = FormValidator(SCHEMA)
    errors = validator.validate({"title": "服务器", "priority": "P3", "qty": 2, "items": [{"qty": 2}, {"qty": 3}]})
    assert "host" not in errors
    assert validator.cleaned["total"] == 5


def test_string_bounds_group_children_and_multi_options():
    schema = {
        "version": 1,
        "fields": [
            {"key": "amount", "type": "number", "props": {"min": "1", "max": "9"}},
            {"key": "tags", "type": "checkbox", "source": {"type": "static", "options": [{"label": "甲", "value": "a"}]}},
            {"key": "group", "type": "section", "children": [{"key": "inner", "type": "input", "required": True}]},
        ],
    }
    errors = FormValidator(schema).validate({"amount": 0, "tags": ["nope"]})
    assert errors["amount"] == "小于最小值"
    assert errors["tags"] == "选项不存在"
    assert errors["inner"] == "必填"
    cleaned = FormValidator(schema)
    assert cleaned.validate({"amount": 2, "tags": ["a"], "inner": "组内"}) == {}
    assert cleaned.cleaned["inner"] == "组内"


def test_visible_cmdb_still_required():
    errors = FormValidator(SCHEMA).validate({"title": "服务器", "priority": "P1", "qty": 2, "items": []})
    assert errors["host"] == "必填"


def test_readonly_group_protects_children():
    schema = {"fields": [{"key": "group", "type": "section", "children": [{"key": "private", "type": "input"}]}]}
    validator = FormValidator(schema, {"group": "readonly"})
    cleaned, errors = validator.apply({"private": "attack"})
    assert errors == {}
    assert "private" not in cleaned


def test_nested_visibility_and_conditional_required_follow_group():
    schema = {
        "fields": [
            {"key": "kind", "type": "input"},
            {
                "key": "section",
                "type": "section",
                "visibleWhen": {"field": "kind", "op": "=", "value": "show"},
                "children": [
                    {"key": "notes", "type": "input", "visibleWhen": {"field": "kind", "op": "not_empty"}},
                ],
            },
        ],
        "rules": [{"field": "notes", "type": "required", "when": {"field": "kind", "op": "!=", "value": "other"}}],
    }
    assert FormValidator(schema).validate({"kind": "hide"}) == {}
    assert FormValidator(schema).validate({"kind": "show"}) == {"notes": "必填"}


def test_table_columns_are_validated_per_row_and_optional_placeholder_is_empty():
    field = {"key": "machines", "type": "table", "children": [{"key": "qty", "label": "数量", "type": "number", "required": True}]}
    validator = FormValidator({"fields": [field]})
    assert validator.validate({"machines": [{"qty": 0}]}) == {}
    assert validator.cleaned == {"machines": [{"qty": 0}]}
    assert validator.validate({"machines": [{"qty": 1}, {}]}) == {"machines": "请填写第 2 行的数量"}
    assert validator.validate({"machines": [{}]}) == {}
    assert validator.cleaned == {"machines": []}
    assert FormValidator({"fields": [{**field, "required": True}]}).validate({"machines": [{}]}) == {"machines": "必填"}
    assert FormValidator({"fields": [field]}, {"qty": "hidden"}).validate({"machines": [{}]}) == {}


def test_basic_subform_types_round_trip_and_invalid_cells_identify_their_row():
    leaf = {"label": "业务组", "value": "ops", "children": [{"label": "一线", "value": "l1"}]}
    row = {
        "input": "A",
        "number": 3,
        "textarea": "多行\n备注",
        "richtext": "<p>详情</p>",
        "radio": "ops",
        "checkbox": ["ops"],
        "select": "ops",
        "multiselect": ["ops"],
        "date": "2026-10-05",
        "datetime": "2026-10-05 09:00:00",
        "time": "09:00:00",
        "dateRange": ["2026-10-05", "2026-10-06"],
        "cascade": "l1",
        "multiCascade": ["l1"],
        "user": ["admin"],
        "multiUser": ["admin", "ops"],
    }
    columns = [{"key": kind, "type": kind, "label": kind, "source": {"type": "static", "options": [leaf]}} for kind in row]
    validator = FormValidator({"fields": [{"type": "table", "key": "items", "children": columns}]})
    cleaned, errors = validator.apply({"items": [row, {**row, "number": "3"}]})
    assert not errors
    assert cleaned["items"] == [row, row]
    for key, bad in [("checkbox", "ops"), ("number", "abc"), ("user", "admin"), ("cascade", "unknown"), ("multiselect", [{}])]:
        errors = validator.validate({"items": [row, {**row, key: bad}]})
        assert "第 2 行" in errors["items"] and key in errors["items"]


def test_subform_readonly_cells_preserve_originals_while_reordering_rows():
    from apps.itsm.services.form.table_columns import merge_table_rows, visible_table_rows

    field = {
        "key": "items",
        "type": "table",
        "children": [{"key": key, "type": "input"} for key in ["name", "serial", "secret"]],
    }
    original = [{"name": "a", "serial": "s1", "secret": "x"}, {"name": "b", "serial": "s2", "secret": "y"}]
    permissions = {"serial": "readonly", "secret": "hidden"}
    view = visible_table_rows(original, field["children"][:2], "ticket:1", "items", preserve_hidden=True)
    rows = [{**row, "name": "改名", "serial": "edited", "secret": "edited"} for row in reversed(view)]
    assert merge_table_rows(field, original, rows, permissions, "ticket:1") == [{**row, "name": "改名"} for row in reversed(original)]


def test_static_numeric_select_in_each_table_row():
    schema = {
        "fields": [
            {
                "key": "items",
                "type": "table",
                "children": [
                    {
                        "key": "capacity",
                        "type": "select",
                        "required": True,
                        "source": {"type": "static", "options": [{"value": 20, "label": "20 GiB"}, {"value": 80, "label": "80 GiB"}]},
                    }
                ],
            }
        ]
    }
    validator = FormValidator(schema)

    assert validator.validate({"items": [{"capacity": 20}, {"capacity": 80}]}) == {}
    assert validator.validate({"items": [{"capacity": 20}, {"capacity": 40}]}) == {"items": "第 2 行的capacity：选项不存在"}


def test_conditional_subform_cells_are_checked_against_their_own_row_and_preserve_previous_values():
    from apps.itsm.services.form.table_columns import merge_table_rows, visible_table_rows

    details = {"key": "details", "label": "详情", "type": "input", "required": True, "visibleWhen": {"field": "show", "op": "=", "value": "yes"}}
    field = {"key": "items", "type": "table", "children": [{"key": "show", "type": "input"}, details]}
    validator = FormValidator({"fields": [field]})
    assert validator.validate({"items": [{"show": "no"}, {"show": "yes"}]}) == {"items": "请填写第 2 行的详情"}
    original = [{"show": "no", "details": "previous"}, {"show": "yes", "details": "visible"}]
    view = visible_table_rows(original, field["children"], "ticket:1", "items", preserve_hidden=True)
    assert "details" not in view[0]
    assert view[1]["details"] == "visible"
    rows = [{**view[0], "details": "forged"}, {**view[1], "details": "updated"}, {"show": "no", "details": "forged"}]
    assert merge_table_rows(field, original, rows, {}, "ticket:1") == [original[0], {"show": "yes", "details": "updated"}, {"show": "no"}]
