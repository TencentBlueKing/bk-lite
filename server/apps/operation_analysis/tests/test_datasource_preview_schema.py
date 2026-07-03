from apps.operation_analysis.services.datasource_preview.schema import infer_fields


def test_infer_fields_uses_first_non_empty_object_keys():
    rows = [
        {},
        {"date": "2026-06-01", "users": 120, "enabled": True},
        {"date": "2026-06-02", "users": "180", "enabled": False, "late_field": "ignored"},
    ]

    assert infer_fields(rows) == [
        {"key": "date", "title": "date", "value_type": "datetime"},
        {"key": "users", "title": "users", "value_type": "number"},
        {"key": "enabled", "title": "enabled", "value_type": "boolean"},
    ]


def test_infer_fields_downgrades_type_conflict_to_string():
    rows = [
        {"value": 1},
        {"value": "not-number"},
    ]

    assert infer_fields(rows) == [
        {"key": "value", "title": "value", "value_type": "string"},
    ]


def test_infer_fields_returns_empty_for_empty_rows():
    assert infer_fields([]) == []
    assert infer_fields([{}, None, "x"]) == []
