import json
from io import BytesIO
from types import SimpleNamespace

import openpyxl
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import Http404
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.operation_analysis.models.datasource_models import DataSourceAPIModel
from apps.operation_analysis.services.datasource_preview import PreviewResult
from apps.operation_analysis.views import datasource_view


def _build_preview_request(user, data=None, path="/operation_analysis/api/data_source/preview/"):
    factory = APIRequestFactory()
    request = factory.post(path, data=data or {}, format="json")
    request.COOKIES["current_team"] = "1"
    request.COOKIES["include_children"] = "0"
    force_authenticate(request, user=user)
    return request


def _build_multipart_preview_request(user, data=None, path="/operation_analysis/api/data_source/preview/"):
    factory = APIRequestFactory()
    request = factory.post(path, data=data or {}, format="multipart")
    request.COOKIES["current_team"] = "1"
    request.COOKIES["include_children"] = "0"
    force_authenticate(request, user=user)
    return request


def _build_source_data_request(user, data=None, path="/operation_analysis/api/data_source/get_source_data/1/"):
    factory = APIRequestFactory()
    request = factory.post(path, data=data or {}, format="json")
    request.COOKIES["current_team"] = "1"
    request.COOKIES["include_children"] = "0"
    force_authenticate(request, user=user)
    return request


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


@pytest.mark.django_db
def test_preview_unsaved_datasource_executes_inline_config(authenticated_user, monkeypatch):
    authenticated_user.is_superuser = True
    executor = FakePreviewExecutor()
    monkeypatch.setattr(datasource_view, "get_preview_executor", lambda source_type: executor)

    request = _build_preview_request(
        authenticated_user,
        data={
            "source_type": DataSourceAPIModel.SOURCE_TYPE_REST_API,
            "connection_config": {"url": "https://example.com/api", "method": "GET"},
            "query_config": {"response_path": "data"},
            "limit": 10,
        },
    )

    response = datasource_view.DataSourceAPIModelViewSet.as_view({"post": "preview_config"})(request)
    response.render()
    payload = json.loads(response.rendered_content)

    assert response.status_code == status.HTTP_200_OK
    assert payload["result"] is True
    assert payload["data"]["count"] == 1
    assert payload["data"]["fields"][2]["value_type"] == "number"
    assert executor.calls[0]["connection_config"]["url"] == "https://example.com/api"
    assert executor.calls[0]["query_config"]["response_path"] == "data"
    assert executor.calls[0]["limit"] == 10


@pytest.mark.django_db
def test_preview_unsaved_excel_datasource_accepts_upload(authenticated_user):
    authenticated_user.is_superuser = True
    request = _build_multipart_preview_request(
        authenticated_user,
        data={
            "source_type": DataSourceAPIModel.SOURCE_TYPE_EXCEL,
            "file": _build_excel_upload(),
            "limit": "10",
        },
    )

    response = datasource_view.DataSourceAPIModelViewSet.as_view({"post": "preview_config"})(request)
    response.render()
    payload = json.loads(response.rendered_content)

    assert response.status_code == status.HTTP_200_OK
    assert payload["result"] is True
    assert payload["data"]["items"] == [{"date": "2026-06-01", "channel": "官网", "users": 120}]
    assert payload["data"]["fields"][2]["key"] == "users"


@pytest.mark.django_db
def test_preview_saved_datasource_checks_group(authenticated_user, monkeypatch):
    authenticated_user.is_superuser = True
    request = _build_preview_request(
        authenticated_user,
        path="/operation_analysis/api/data_source/1/preview/",
    )

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

    response = datasource_view.DataSourceAPIModelViewSet.as_view({"post": "preview"})(request, pk="1")
    response.render()
    payload = json.loads(response.rendered_content)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert payload["result"] is False
    assert payload["message"] == "无权访问当前数据源"


@pytest.mark.django_db
def test_preview_saved_datasource_uses_persisted_config(authenticated_user, monkeypatch):
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

    request = _build_preview_request(
        authenticated_user,
        data={"limit": 5},
        path="/operation_analysis/api/data_source/1/preview/",
    )

    response = datasource_view.DataSourceAPIModelViewSet.as_view({"post": "preview"})(request, pk="1")
    response.render()
    payload = json.loads(response.rendered_content)

    assert response.status_code == status.HTTP_200_OK
    assert payload["result"] is True
    assert executor.calls[0]["connection_config"]["url"] == "https://example.com/api"
    assert executor.calls[0]["query_config"]["response_path"] == "data.items"
    assert executor.calls[0]["limit"] == 5


@pytest.mark.django_db
def test_preview_returns_not_found_for_deleted_datasource(authenticated_user, monkeypatch):
    authenticated_user.is_superuser = True
    request = _build_preview_request(
        authenticated_user,
        path="/operation_analysis/api/data_source/1/preview/",
    )
    monkeypatch.setattr(
        datasource_view.DataSourceAPIModelViewSet,
        "get_object",
        lambda self: (_ for _ in ()).throw(Http404()),
    )

    response = datasource_view.DataSourceAPIModelViewSet.as_view({"post": "preview"})(request, pk="1")
    response.render()
    payload = json.loads(response.rendered_content)

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert payload["result"] is False
    assert payload["message"] == "数据源不存在或已删除"


@pytest.mark.django_db
def test_get_source_data_executes_inline_datasource(authenticated_user, monkeypatch):
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
            query_config={"response_path": "items"},
            params=[],
        ),
    )

    request = _build_source_data_request(authenticated_user, data={"page_size": 20})

    response = datasource_view.DataSourceAPIModelViewSet.as_view({"post": "get_source_data"})(request, pk="1")
    response.render()
    payload = json.loads(response.rendered_content)

    assert response.status_code == status.HTTP_200_OK
    assert payload["result"] is True
    assert payload["data"] == [{"date": "2026-06-01", "channel": "官网", "users": 120}]
    assert executor.calls[0]["limit"] == 20


@pytest.mark.django_db
def test_get_source_data_returns_saved_excel_items(authenticated_user, monkeypatch):
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

    request = _build_source_data_request(authenticated_user, data={"page_size": 1})

    response = datasource_view.DataSourceAPIModelViewSet.as_view({"post": "get_source_data"})(request, pk="1")
    response.render()
    payload = json.loads(response.rendered_content)

    assert response.status_code == status.HTTP_200_OK
    assert payload["result"] is True
    assert payload["data"] == [{"name": "官网", "value": 120}]


@pytest.mark.django_db
def test_preview_rejects_unsupported_source_type(authenticated_user):
    authenticated_user.is_superuser = True
    request = _build_preview_request(
        authenticated_user,
        data={
            "source_type": DataSourceAPIModel.SOURCE_TYPE_NATS,
            "connection_config": {},
            "query_config": {},
        },
    )

    response = datasource_view.DataSourceAPIModelViewSet.as_view({"post": "preview_config"})(request)
    response.render()
    payload = json.loads(response.rendered_content)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert payload["result"] is False
    assert "暂不支持" in payload["message"]
