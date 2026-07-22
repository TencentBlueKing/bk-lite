import pytest
import yaml

from apps.operation_analysis.constants.import_export import ImportExportErrorCode, YAML_SCHEMA_VERSION
from apps.operation_analysis.services.import_export.precheck_service import PrecheckService


DATE_RANGE_QUICK_TYPES = (
    "today",
    "yesterday",
    "this_week",
    "last_week",
    "this_month",
    "last_month",
    "last_7_days",
    "last_30_days",
    "last_90_days",
)


@pytest.fixture(autouse=True)
def _skip_database_conflict_lookup(monkeypatch):
    monkeypatch.setattr(PrecheckService, "identify_conflicts", lambda *_args, **_kwargs: [])


_UNSET = object()


def _precheck(value, params=_UNSET):
    if params is _UNSET:
        params = [
            {
                "name": "period",
                "alias_name": "Period",
                "type": "dateRange",
                "filterType": "filter",
                "value": value,
            }
        ]
    document = {
        "meta": {
            "schema_version": YAML_SCHEMA_VERSION,
            "object_counts": {"datasources": 1},
        },
        "datasources": [
            {
                "key": "cost::cloud_cost/query",
                "name": "cost",
                "rest_api": "cloud_cost/query",
                "params": params,
            }
        ],
    }
    return PrecheckService.precheck(yaml.safe_dump(document))


@pytest.mark.parametrize(
    "value",
    [
        *(pytest.param({"rangeType": range_type}, id=range_type) for range_type in DATE_RANGE_QUICK_TYPES),
        pytest.param(
            {"rangeType": "custom", "startDate": "2026-07-01", "endDate": "2026-07-17"},
            id="custom",
        ),
        pytest.param(None, id="null"),
    ],
)
def test_import_precheck_accepts_valid_date_range_values(value):
    assert _precheck(value)["valid"] is True


@pytest.mark.parametrize(
    "value",
    [
        pytest.param({"rangeType": "last30days"}, id="unknown-range-type"),
        pytest.param({"rangeType": "custom", "endDate": "2026-07-17"}, id="custom-missing-start"),
        pytest.param({"rangeType": "custom", "startDate": "2026-07-01"}, id="custom-missing-end"),
        pytest.param(
            {"rangeType": "custom", "startDate": "2026-02-30", "endDate": "2026-03-01"},
            id="invalid-calendar-date",
        ),
        pytest.param(
            {"rangeType": "custom", "startDate": "2026-07-01T00:00:00Z", "endDate": "2026-07-17"},
            id="datetime-not-date",
        ),
        pytest.param(
            {"rangeType": "custom", "startDate": "2026-07-17", "endDate": "2026-07-01"},
            id="reversed-custom-range",
        ),
        pytest.param(
            {"rangeType": "last_7_days", "startDate": "2026-07-01", "endDate": "2026-07-17"},
            id="quick-rule-with-custom-fields",
        ),
        pytest.param(["2026-07-01", "2026-07-17"], id="resolved-array"),
        pytest.param({}, id="missing-range-type"),
    ],
)
def test_import_precheck_rejects_invalid_date_range_values(value):
    result = _precheck(value)

    assert result["valid"] is False
    assert any("dateRange" in error["message"] for error in result["errors"])


@pytest.mark.parametrize(
    "params",
    [
        pytest.param(
            {
                "name": "period",
                "type": "dateRange",
                "value": {"rangeType": "today"},
            },
            id="single-param-dict",
        ),
        pytest.param(
            {
                "period": {
                    "name": "period",
                    "type": "dateRange",
                    "value": {"rangeType": "last_7_days"},
                },
                "keyword": {"name": "keyword", "type": "string", "value": "ok"},
            },
            id="param-mapping-with-ordinary-param",
        ),
        pytest.param(None, id="null-params"),
        pytest.param(
            [
                {"name": "keyword", "type": "string", "value": "ok"},
                {"name": "period", "type": "dateRange", "value": None},
            ],
            id="mixed-list",
        ),
    ],
)
def test_import_precheck_accepts_supported_params_shapes(params):
    assert _precheck(None, params=params)["valid"] is True


def test_import_precheck_reports_date_range_error_contract():
    result = _precheck({"rangeType": "unknown"})

    error = next(error for error in result["errors"] if "dateRange" in error["message"])
    assert error["code"] == ImportExportErrorCode.YAML_SCHEMA_INVALID
    assert error["details"] == {
        "path": "datasources[0].params[0].value",
        "message": "dateRange value must be null or a canonical persisted date-range rule",
    }
