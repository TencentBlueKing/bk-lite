"""数据源预览接口测试。"""

from io import BytesIO
from types import SimpleNamespace

import openpyxl
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import Http404
from rest_framework import status

from apps.operation_analysis.models.datasource_models import DataSourceAPIModel
from apps.operation_analysis.services.datasource_preview import PreviewResult
from apps.operation_analysis.views import datasource_view

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _build_excel_upload() -> SimpleUploadedFile:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["date", "channel", "users"])
    sheet.append(["2026-06-01", "官网", 120])

    stream = BytesIO()
    workbook.save(stream)
    return SimpleUploadedFile(
        "orders.xlsx",
        stream.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


class FakePreviewExecutor:
    def __init__(self):
        self.calls = []

    def preview(self, connection_config, query_config, limit=100):
        self.calls.append(
            {
                "connection_config": connection_config,
                "query_config": query_config,
                "limit": limit,
            }
        )
        return PreviewResult(
            items=[{"date": "2026-06-01", "channel": "官网", "users": 120}],
            count=1,
            fields=[
                {"key": "date", "title": "date", "value_type": "datetime"},
                {"key": "channel", "title": "channel", "value_type": "string"},
                {"key": "users", "title": "users", "value_type": "number"},
            ],
        )


@pytest.mark.parametrize(
    ("permission", "expected_status"),
    [
        ("data_source-View", status.HTTP_403_FORBIDDEN),
        ("data_source-Add", status.HTTP_200_OK),
        ("data_source-Edit", status.HTTP_200_OK),
    ],
)
def test_preview_unsaved_datasource_requires_add_or_edit_permission(
    api_client,
    authenticated_user,
    monkeypatch,
    permission,
    expected_status,
):
    authenticated_user.is_superuser = False
    authenticated_user.permission = {"ops-analysis": {permission}}
    executor = FakePreviewExecutor()
    monkeypatch.setattr(datasource_view, "get_preview_executor", lambda source_type: executor)
    api_client.cookies["current_team"] = "1"

    response = api_client.post(
        "/api/v1/operation_analysis/api/data_source/preview/",
        {
            "source_type": DataSourceAPIModel.SOURCE_TYPE_REST_API,
            "connection_config": {"url": "https://example.com/api"},
            "query_config": {"response_path": "data"},
        },
        format="json",
    )

    assert response.status_code == expected_status
    assert len(executor.calls) == (1 if expected_status == status.HTTP_200_OK else 0)


@pytest.mark.parametrize(
    ("permission", "expected_status"),
    [
        ("data_source-View", status.HTTP_403_FORBIDDEN),
        ("data_source-Add", status.HTTP_403_FORBIDDEN),
        ("data_source-Edit", status.HTTP_200_OK),
    ],
)
def test_preview_saved_datasource_requires_edit_permission(
    api_client,
    authenticated_user,
    monkeypatch,
    permission,
    expected_status,
):
    authenticated_user.is_superuser = False
    authenticated_user.permission = {"ops-analysis": {permission}}
    executor = FakePreviewExecutor()
    monkeypatch.setattr(datasource_view, "get_preview_executor", lambda source_type: executor)
    monkeypatch.setattr(
        datasource_view.DataSourceAPIModelViewSet,
        "get_object",
        lambda self: SimpleNamespace(
            id=1,
            name="rest-demo",
            groups=[1],
            source_type=DataSourceAPIModel.SOURCE_TYPE_REST_API,
            connection_config={"url": "https://example.com/api"},
            query_config={"response_path": "data"},
        ),
    )
    api_client.cookies["current_team"] = "1"

    response = api_client.post("/api/v1/operation_analysis/api/data_source/1/preview/", {}, format="json")

    assert response.status_code == expected_status
    assert len(executor.calls) == (1 if expected_status == status.HTTP_200_OK else 0)


def test_preview_saved_datasource_rejects_team_outside_user_groups(api_client, authenticated_user, monkeypatch):
    authenticated_user.is_superuser = False
    authenticated_user.permission = {"ops-analysis": {"data_source-Edit"}}
    authenticated_user.group_list = [{"id": 1}]
    executor = FakePreviewExecutor()
    monkeypatch.setattr(datasource_view, "get_preview_executor", lambda source_type: executor)
    monkeypatch.setattr(
        datasource_view.DataSourceAPIModelViewSet,
        "get_object",
        lambda self: SimpleNamespace(
            id=1,
            name="rest-demo",
            groups=[2],
            source_type=DataSourceAPIModel.SOURCE_TYPE_REST_API,
            connection_config={"url": "https://example.com/api"},
            query_config={"response_path": "data"},
        ),
    )
    api_client.cookies["current_team"] = "2"

    response = api_client.post("/api/v1/operation_analysis/api/data_source/1/preview/", {}, format="json")

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert executor.calls == []


def test_preview_unsaved_datasource_executes_inline_config(api_client, authenticated_user, monkeypatch):
    authenticated_user.is_superuser = True
    executor = FakePreviewExecutor()
    monkeypatch.setattr(datasource_view, "get_preview_executor", lambda source_type: executor)
    api_client.cookies["current_team"] = "1"

    response = api_client.post(
        "/api/v1/operation_analysis/api/data_source/preview/",
        {
            "source_type": DataSourceAPIModel.SOURCE_TYPE_REST_API,
            "connection_config": {"url": "https://example.com/api", "method": "GET"},
            "query_config": {"response_path": "data"},
            "limit": 10,
        },
        format="json",
    )
    payload = response.json()

    assert response.status_code == status.HTTP_200_OK
    assert payload["result"] is True
    assert payload["data"]["count"] == 1
    assert payload["data"]["fields"][2]["value_type"] == "number"
    assert executor.calls[0]["connection_config"]["url"] == "https://example.com/api"
    assert executor.calls[0]["query_config"]["response_path"] == "data"
    assert executor.calls[0]["limit"] == 10


def test_preview_unsaved_excel_datasource_accepts_upload(api_client, authenticated_user):
    authenticated_user.is_superuser = True
    api_client.cookies["current_team"] = "1"

    response = api_client.post(
        "/api/v1/operation_analysis/api/data_source/preview/",
        {
            "source_type": DataSourceAPIModel.SOURCE_TYPE_EXCEL,
            "file": _build_excel_upload(),
            "limit": "10",
        },
        format="multipart",
    )
    payload = response.json()

    assert response.status_code == status.HTTP_200_OK
    assert payload["result"] is True
    assert payload["data"]["items"] == [{"date": "2026-06-01", "channel": "官网", "users": 120}]
    assert payload["data"]["fields"][2]["key"] == "users"


def test_preview_saved_datasource_checks_group(api_client, authenticated_user, monkeypatch):
    authenticated_user.is_superuser = False
    authenticated_user.permission = {"ops-analysis": {"data_source-Edit"}}
    api_client.cookies["current_team"] = "1"

    monkeypatch.setattr(
        datasource_view.DataSourceAPIModelViewSet,
        "get_object",
        lambda self: SimpleNamespace(
            id=1,
            name="rest-demo",
            groups=[2],
            source_type=DataSourceAPIModel.SOURCE_TYPE_REST_API,
            connection_config={"url": "https://example.com/api"},
            query_config={},
        ),
    )

    response = api_client.post("/api/v1/operation_analysis/api/data_source/1/preview/", {}, format="json")
    payload = response.json()

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert payload["result"] is False
    assert payload["message"] == "无权访问当前数据源"


def test_preview_saved_datasource_uses_persisted_config(api_client, authenticated_user, monkeypatch):
    authenticated_user.is_superuser = True
    executor = FakePreviewExecutor()
    monkeypatch.setattr(datasource_view, "get_preview_executor", lambda source_type: executor)
    monkeypatch.setattr(
        datasource_view.DataSourceAPIModelViewSet,
        "get_object",
        lambda self: SimpleNamespace(
            id=1,
            name="rest-demo",
            groups=[1],
            source_type=DataSourceAPIModel.SOURCE_TYPE_REST_API,
            connection_config={"url": "https://example.com/api"},
            query_config={"response_path": "data.items"},
        ),
    )
    api_client.cookies["current_team"] = "1"

    response = api_client.post(
        "/api/v1/operation_analysis/api/data_source/1/preview/",
        {"limit": 5},
        format="json",
    )
    payload = response.json()

    assert response.status_code == status.HTTP_200_OK
    assert payload["result"] is True
    assert executor.calls[0]["connection_config"]["url"] == "https://example.com/api"
    assert executor.calls[0]["query_config"]["response_path"] == "data.items"
    assert executor.calls[0]["limit"] == 5


def test_preview_returns_not_found_for_deleted_datasource(api_client, authenticated_user, monkeypatch):
    authenticated_user.is_superuser = True
    api_client.cookies["current_team"] = "1"
    monkeypatch.setattr(
        datasource_view.DataSourceAPIModelViewSet,
        "get_object",
        lambda self: (_ for _ in ()).throw(Http404()),
    )

    response = api_client.post("/api/v1/operation_analysis/api/data_source/1/preview/", {}, format="json")
    payload = response.json()

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert payload["result"] is False
    assert payload["message"] == "数据源不存在或已删除"


def test_get_source_data_executes_inline_datasource(api_client, authenticated_user, monkeypatch):
    authenticated_user.is_superuser = False
    authenticated_user.permission = {"ops-analysis": {"data_source-View"}}
    api_client.cookies["current_team"] = "1"
    executor = FakePreviewExecutor()
    monkeypatch.setattr(datasource_view, "get_preview_executor", lambda source_type: executor)
    monkeypatch.setattr(
        datasource_view.DataSourceAPIModelViewSet,
        "get_object",
        lambda self: SimpleNamespace(
            id=1,
            name="rest-demo",
            groups=[1],
            source_type=DataSourceAPIModel.SOURCE_TYPE_REST_API,
            connection_config={"url": "https://example.com/api"},
            query_config={"response_path": "items"},
            params=[],
        ),
    )

    response = api_client.post(
        "/api/v1/operation_analysis/api/data_source/get_source_data/1/",
        {"page_size": 20},
        format="json",
    )
    payload = response.json()

    assert response.status_code == status.HTTP_200_OK
    assert payload["result"] is True
    assert payload["data"] == {
        "data": [{"date": "2026-06-01", "channel": "官网", "users": 120}],
        "warnings": [],
    }
    assert executor.calls[0]["limit"] == 20


def test_get_source_data_returns_saved_excel_items(api_client, authenticated_user, monkeypatch):
    authenticated_user.is_superuser = True
    monkeypatch.setattr(
        datasource_view.DataSourceAPIModelViewSet,
        "get_object",
        lambda self: SimpleNamespace(
            id=1,
            name="excel-demo",
            groups=[1],
            source_type=DataSourceAPIModel.SOURCE_TYPE_EXCEL,
            connection_config={},
            query_config={
                "imported_items": [
                    {"name": "官网", "value": 120},
                    {"name": "广告", "value": 96},
                ],
                "imported_fields": [
                    {"key": "name", "title": "name", "value_type": "string"},
                    {"key": "value", "title": "value", "value_type": "number"},
                ],
            },
            params=[],
        ),
    )
    api_client.cookies["current_team"] = "1"

    response = api_client.post(
        "/api/v1/operation_analysis/api/data_source/get_source_data/1/",
        {"page_size": 1},
        format="json",
    )
    payload = response.json()

    assert response.status_code == status.HTTP_200_OK
    assert payload["result"] is True
    assert payload["data"] == {
        "data": [{"name": "官网", "value": 120}],
        "warnings": [],
    }


def test_preview_rejects_unsupported_source_type(api_client, authenticated_user):
    authenticated_user.is_superuser = True
    api_client.cookies["current_team"] = "1"

    response = api_client.post(
        "/api/v1/operation_analysis/api/data_source/preview/",
        {
            "source_type": DataSourceAPIModel.SOURCE_TYPE_NATS,
            "connection_config": {},
            "query_config": {},
        },
        format="json",
    )
    payload = response.json()

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert payload["result"] is False
    assert "暂不支持" in payload["message"]
