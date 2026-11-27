import pytest

from apps.operation_analysis.services.datasource_params.binding import (
    apply_json_template,
    apply_sql_bindings,
    filter_excel_rows,
    validate_declared_params,
)
from apps.operation_analysis.services.datasource_preview.base import ConnectorError

pytestmark = pytest.mark.unit


def test_sql_binds_scalar_and_shifts_date_range_end_to_next_day():
    sql = "select sum(amount) as total from bills where status = :status and bill_date >= :bill_start and bill_date < :bill_end"
    specs = [
        {"name": "status", "type": "string"},
        {"name": "bill", "type": "dateRange"},
    ]
    bound_sql, binds = apply_sql_bindings(
        sql,
        specs,
        {"status": "paid", "bill": ["2026-07-01", "2026-07-17"]},
    )

    assert bound_sql == sql
    assert binds == {"status": "paid", "bill_start": "2026-07-01", "bill_end": "2026-07-18"}


def test_sql_keeps_time_range_endpoints():
    sql = "select 1 where created_at >= :window_start and created_at < :window_end"
    _, binds = apply_sql_bindings(
        sql,
        [{"name": "window", "type": "timeRange"}],
        {"window": ["2026-07-17T02:08:00Z", "2026-07-17T03:08:00Z"]},
    )

    assert binds == {
        "window_start": "2026-07-17T02:08:00Z",
        "window_end": "2026-07-17T03:08:00Z",
    }


def test_sql_value_is_not_concatenated_into_the_statement():
    sql = "select id from hosts where name = :name"
    bound_sql, binds = apply_sql_bindings(sql, [{"name": "name", "type": "string"}], {"name": "'; drop table hosts"})

    assert bound_sql == sql
    assert binds["name"] == "'; drop table hosts"


def test_sql_missing_placeholder_is_rejected():
    with pytest.raises(ConnectorError) as caught:
        apply_sql_bindings("select 1", [{"name": "status", "type": "string"}], {"status": "paid"})

    assert caught.value.code == "param_placeholder_missing"


def test_sql_placeholder_without_a_value_is_rejected():
    with pytest.raises(ConnectorError) as caught:
        apply_sql_bindings("select 1 where status = :status", [{"name": "status", "type": "string"}], {})

    assert caught.value.code == "param_value_missing"


def test_sql_braces_are_rejected_without_a_value():
    with pytest.raises(ConnectorError) as caught:
        apply_sql_bindings("select 1 where status = '{{status}}'", [{"name": "status", "type": "string"}], {})

    assert caught.value.code == "param_placeholder_missing"


def test_sql_keeps_braces_when_the_colon_placeholder_is_present():
    sql = "select 1 where status = :status and note = '{{status}}'"
    bound_sql, binds = apply_sql_bindings(sql, [{"name": "status", "type": "string"}], {"status": "paid"})

    assert bound_sql == sql
    assert binds == {"status": "paid"}


def test_sql_range_braces_are_rejected_without_a_value():
    with pytest.raises(ConnectorError) as caught:
        apply_sql_bindings(
            "select 1 where created_at >= {{window_start}}",
            [{"name": "window", "type": "timeRange"}],
            {},
        )

    assert caught.value.code == "param_placeholder_missing"


def test_sql_without_declared_values_stays_unbound():
    sql = "select 1"
    assert apply_sql_bindings(sql, [], {}) == (sql, {})


def test_array_string_is_rejected():
    with pytest.raises(ConnectorError) as caught:
        apply_sql_bindings("select 1 where id = :ids", [{"name": "ids", "type": "string"}], {"ids": ["a", "b"]})

    assert caught.value.code == "param_multiple_unsupported"


def test_json_template_replaces_whole_placeholder_only():
    payload = apply_json_template(
        {
            "params": {"status": "{{status}}", "note": "status {{status}}"},
            "body": {"start": "{{bill_start}}", "end": "{{bill_end}}"},
        },
        [{"name": "status", "type": "string"}, {"name": "bill", "type": "dateRange"}],
        {"status": "paid", "bill": ["2026-07-01", "2026-07-17"]},
    )

    assert payload["params"]["status"] == "paid"
    assert payload["params"]["note"] == "status {{status}}"
    assert payload["body"]["start"] == "2026-07-01"
    assert payload["body"]["end"] == "2026-07-18"


def test_json_colon_placeholder_is_rejected_without_a_value():
    with pytest.raises(ConnectorError) as caught:
        apply_json_template(
            {"params": {"status": ":status"}},
            [{"name": "status", "type": "string"}],
            {},
        )

    assert caught.value.code == "param_placeholder_missing"


def test_json_colon_inside_a_longer_string_stays():
    payload = {"params": {"note": "status :status"}}

    assert apply_json_template(payload, [{"name": "status", "type": "string"}], {}) == payload


def test_excel_filters_by_column_name_and_keeps_last_calendar_day():
    rows = [
        {"账单日期": "2026-07-17 15:00:00", "状态": "paid"},
        {"账单日期": "2026-07-18 00:00:00", "状态": "paid"},
        {"账单日期": "2026-07-01", "状态": "open"},
    ]
    filtered = filter_excel_rows(
        rows,
        [{"name": "账单日期", "type": "dateRange"}, {"name": "状态", "type": "string"}],
        {"账单日期": ["2026-07-01", "2026-07-17"], "状态": "paid"},
    )

    assert filtered == [{"账单日期": "2026-07-17 15:00:00", "状态": "paid"}]


def test_excel_missing_column_is_rejected():
    with pytest.raises(ConnectorError) as caught:
        filter_excel_rows(
            [{"city": "shanghai", "created_at": "2026-07-17 15:00:00"}],
            [{"name": "window", "type": "timeRange"}],
            {"window": ["2026-07-17T00:00:00Z", "2026-07-17T06:00:00Z"]},
        )

    assert caught.value.code == "param_placeholder_missing"


def test_excel_blank_cell_drops_only_that_row():
    filtered = filter_excel_rows(
        [{"city": "shanghai", "amount": 30}, {"city": None, "amount": 5}],
        [{"name": "city", "type": "string"}],
        {"city": "shanghai"},
    )

    assert filtered == [{"city": "shanghai", "amount": 30}]


def test_excel_param_without_a_value_is_skipped():
    rows = [{"city": "beijing"}]

    assert filter_excel_rows(rows, [{"name": "city", "type": "string"}], {}) == rows


def test_validate_declared_params_rejects_second_range_and_condition_filter():
    with pytest.raises(ConnectorError) as caught:
        validate_declared_params(
            "mysql",
            [{"name": "a", "type": "timeRange"}, {"name": "b", "type": "dateRange"}],
        )
    assert caught.value.code == "param_single_range"

    with pytest.raises(ConnectorError) as caught:
        validate_declared_params("excel", [{"name": "列", "type": "conditionFilter"}])
    assert caught.value.code == "param_condition_unsupported"


def test_validate_declared_params_allows_excel_column_names_and_rejects_sql_names():
    validate_declared_params("excel", [{"name": "账单日期", "type": "dateRange"}])

    with pytest.raises(ConnectorError) as caught:
        validate_declared_params("postgresql", [{"name": "账单日期", "type": "string"}])
    assert caught.value.code == "param_name_invalid"


def test_nats_params_are_not_restricted():
    validate_declared_params(
        "nats",
        [{"name": "过滤", "type": "conditionFilter"}, {"name": "a", "type": "timeRange"}, {"name": "b", "type": "dateRange"}],
    )
