import pytest

from apps.operation_analysis.services.datasource_preview.base import ConnectorError
from apps.operation_analysis.services.datasource_preview.rest_api import RestApiConnectorExecutor, extract_response_path, normalize_rest_items


def test_extract_response_path_reads_nested_list():
    payload = {"data": {"items": [{"name": "a"}]}}
    assert extract_response_path(payload, "data.items") == [{"name": "a"}]


def test_normalize_rest_items_accepts_list_and_items_dict():
    assert normalize_rest_items([{"a": 1}]) == ([{"a": 1}], 1)
    assert normalize_rest_items({"items": [{"a": 1}], "count": 5}) == ([{"a": 1}], 5)


def test_normalize_rest_items_rejects_scalar():
    with pytest.raises(ConnectorError) as exc:
        normalize_rest_items({"ok": True})

    assert exc.value.code == "rest_response_not_list"


def test_rest_preview_uses_http_client_and_infers_fields():
    calls = []

    class FakeResponse:
        headers = {"content-length": "64"}

        def raise_for_status(self):
            return None

        def json(self):
            return {"data": {"items": [{"date": "2026-06-01", "users": 120}], "count": 1}}

    class FakeClient:
        def request(self, **kwargs):
            calls.append(kwargs)
            return FakeResponse()

    executor = RestApiConnectorExecutor(http_client=FakeClient())
    result = executor.preview(
        {
            "url": "https://example.com/orders",
            "method": "GET",
            "headers": {"Authorization": "Bearer x"},
            "timeout": 3,
        },
        {"response_path": "data", "limit": 100},
        limit=100,
    )

    assert calls[0]["method"] == "GET"
    assert calls[0]["url"] == "https://example.com/orders"
    assert result.as_dict() == {
        "items": [{"date": "2026-06-01", "users": 120}],
        "count": 1,
        "fields": [
            {"key": "date", "title": "date", "value_type": "datetime"},
            {"key": "users", "title": "users", "value_type": "number"},
        ],
    }
