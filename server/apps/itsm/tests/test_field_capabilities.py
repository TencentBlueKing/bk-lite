from unittest.mock import patch

import pytest

from apps.itsm.services.form.capabilities import FIELD_CAPABILITIES, validate_binding, validate_result
from apps.itsm.services.form.schema import FIELD_TYPES


def test_every_field_has_explicit_capability():
    assert set(FIELD_CAPABILITIES) == FIELD_TYPES


@pytest.mark.parametrize("kind", sorted(FIELD_TYPES))
@pytest.mark.parametrize("source", ["api", "python", "dictionary", "table"])
def test_all_field_source_combinations(kind, source):
    cap = FIELD_CAPABILITIES[kind]
    cfg = {"source": "integration" if source in {"api", "python"} else source, "integration_kind": source, "mode": cap["mode"] or "value"}
    if cap["mode"] == "table":
        cfg["columns"] = {"name": "name"}
    field = {"key": "x", "type": kind, "fetch": cfg, "columns": [{"key": "name", "type": "input"}]}
    if source in cap["sources"]:
        validate_binding(field)
    else:
        with pytest.raises(ValueError):
            validate_binding(field)


@pytest.mark.parametrize(
    "kind,value", [("number", True), ("number", "12"), ("number", float("inf")), ("input", {}), ("textarea", []), ("table", [{}])]
)
def test_result_rejects_wrong_type(kind, value):
    field = {"key": "x", "type": kind, "fetch": {"mode": "table" if kind == "table" else "value", "columns": {"quantity": "quantity"}}}
    with pytest.raises(ValueError):
        validate_result(field, value)


def test_specialized_field_cannot_be_written_through_fill():
    from apps.itsm.services.form.fetch import freeze_schema

    field = {
        "key": "x",
        "type": "select",
        "fetch": {"source": "integration", "mode": "options", "integration_id": 1, "fill": {"who": "user"}},
    }
    with patch("apps.itsm.services.form.fetch.Integration.objects.get") as get:
        get.return_value.kind = "python"
        get.return_value.is_enabled = True
        get.return_value.config = {"script": ""}
        with pytest.raises(ValueError):
            freeze_schema({"fields": [field, {"key": "who", "type": "user"}]}, "domain.com")


@pytest.mark.parametrize(
    "cfg",
    [
        {"source": "dictionary", "mode": "options", "inputs": {"x": 1}},
        {"source": "dictionary", "mode": "options", "list_path": "items"},
        {"source": "integration", "integration_kind": "python", "mode": "options", "inputs": {"other": 1}},
        {"source": "integration", "integration_kind": "python", "mode": "options", "inputs": {"rows": "bad"}},
        {"source": "table", "mode": "options", "list_path": "items"},
    ],
)
def test_source_specific_invalid_parameters(cfg):
    with pytest.raises(ValueError):
        validate_binding({"key": "x", "type": "select", "fetch": cfg})


def test_tree_mapping_keeps_hierarchy_and_rejects_duplicate_values():
    from apps.itsm.services.form.fetch import flatten_options, map_options

    data = [{"value": "a", "label": "父级", "children": [{"value": "b", "label": "子级"}]}]
    options, _ = map_options(data, {}, tree=True)
    assert options == data
    assert list(flatten_options(options)) == [{"value": "a", "label": "父级"}, {"value": "b", "label": "子级"}]
    with pytest.raises(ValueError):
        map_options(data + data, {}, tree=True)


def test_valid_scalar_and_table_results():
    validate_result({"type": "number"}, 12.5)
    validate_result({"type": "input"}, "文本")
    validate_result({"type": "table", "props": {"columns": "数量:count:number"}, "fetch": {"columns": {"count": "n"}}}, [{"count": 3}])
    with pytest.raises(ValueError):
        validate_result({"type": "table", "props": {"columns": "数量:count:number"}, "fetch": {"columns": {"count": "n"}}}, [{"count": "3"}])
