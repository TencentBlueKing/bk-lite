from io import BytesIO

import openpyxl
import pytest

from apps.operation_analysis.services.datasource_preview.base import ConnectorError
from apps.operation_analysis.services.datasource_preview.excel import ExcelConnectorExecutor


def _build_excel_file() -> BytesIO:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "orders"
    sheet.append(["date", "channel", "users"])
    sheet.append(["2026-06-01", "官网", 120])
    sheet.append(["2026-06-02", "广告", 96])

    stream = BytesIO()
    workbook.save(stream)
    stream.seek(0)
    stream.name = "orders.xlsx"
    return stream


def test_excel_preview_parses_uploaded_file_and_infers_fields():
    result = ExcelConnectorExecutor().preview({"file": _build_excel_file()}, {}, limit=10)

    assert result.as_dict() == {
        "items": [
            {"date": "2026-06-01", "channel": "官网", "users": 120},
            {"date": "2026-06-02", "channel": "广告", "users": 96},
        ],
        "count": 2,
        "fields": [
            {"key": "date", "title": "date", "value_type": "datetime"},
            {"key": "channel", "title": "channel", "value_type": "string"},
            {"key": "users", "title": "users", "value_type": "number"},
        ],
    }


def test_excel_preview_reads_saved_imported_items():
    result = ExcelConnectorExecutor().preview(
        {},
        {
            "imported_items": [
                {"name": "官网", "value": 120},
                {"name": "广告", "value": 96},
            ],
            "imported_fields": [
                {"key": "name", "title": "name", "value_type": "string"},
                {"key": "value", "title": "value", "value_type": "number"},
            ],
        },
        limit=1,
    )

    assert result.as_dict() == {
        "items": [{"name": "官网", "value": 120}],
        "count": 2,
        "fields": [
            {"key": "name", "title": "name", "value_type": "string"},
            {"key": "value", "title": "value", "value_type": "number"},
        ],
    }


def test_excel_preview_rejects_missing_file_or_saved_rows():
    with pytest.raises(Exception):
        ExcelConnectorExecutor().preview({}, {}, limit=10)


def test_excel_preview_rejects_legacy_xls_extension():
    stream = _build_excel_file()
    stream.name = "orders.xls"

    with pytest.raises(ConnectorError) as exc:
        ExcelConnectorExecutor().preview({"file": stream}, {}, limit=10)

    assert exc.value.code == "excel_file_type_invalid"
