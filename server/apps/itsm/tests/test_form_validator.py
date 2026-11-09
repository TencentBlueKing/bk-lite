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


def test_visible_cmdb_still_required():
    errors = FormValidator(SCHEMA).validate({"title": "服务器", "priority": "P1", "qty": 2, "items": []})
    assert errors["host"] == "必填"
