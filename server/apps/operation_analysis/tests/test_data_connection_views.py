import json

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.operation_analysis.constants.import_export import SENSITIVE_PLACEHOLDER
from apps.operation_analysis.models.datasource_models import DataConnection
from apps.operation_analysis.services.data_connection.config_crypto import encrypt_connection_config
from apps.operation_analysis.views import data_connection_view

pytestmark = [pytest.mark.django_db]


class FakeExecutor:
    def __init__(self):
        self.test_connection_calls = []

    def test_connection(self, connection_config):
        self.test_connection_calls.append(connection_config)


def _build_request(user, path, data=None, *, current_team="1"):
    request = APIRequestFactory().post(path, data=data or {}, format="json")
    request.COOKIES["current_team"] = str(current_team)
    request.COOKIES["include_children"] = "0"
    force_authenticate(request, user=user)
    return request


def _response_payload(response):
    response.render()
    return json.loads(response.rendered_content)


def test_unsaved_connection_test_uses_draft_config(authenticated_user, monkeypatch):
    authenticated_user.is_superuser = False
    authenticated_user.permission = {"ops-analysis": {"data_source-Edit"}}
    executor = FakeExecutor()
    monkeypatch.setattr(data_connection_view, "get_preview_executor", lambda connection_type: executor)

    request = _build_request(
        authenticated_user,
        "/operation_analysis/api/data_connection/test_connection/",
        data={
            "connection_type": DataConnection.TYPE_MYSQL,
            "config": {
                "host": "draft.example.com",
                "port": 3306,
                "database": "ops",
                "username": "reader",
                "password": "draft-secret",
            },
        },
    )
    response = data_connection_view.DataConnectionViewSet.as_view({"post": "test_connection_config"})(request)
    payload = _response_payload(response)

    assert response.status_code == status.HTTP_200_OK
    assert payload["result"] is True
    assert executor.test_connection_calls == [
        {
            "host": "draft.example.com",
            "port": 3306,
            "database": "ops",
            "username": "reader",
            "password": "draft-secret",
        }
    ]


def test_saved_connection_test_merges_redacted_secret_into_draft(authenticated_user, monkeypatch):
    authenticated_user.is_superuser = False
    authenticated_user.permission = {"ops-analysis": {"data_source-Edit"}}
    executor = FakeExecutor()
    monkeypatch.setattr(data_connection_view, "get_preview_executor", lambda connection_type: executor)
    connection = DataConnection.objects.create(
        name="mysql-draft-test",
        connection_type=DataConnection.TYPE_MYSQL,
        groups=[1],
        config=encrypt_connection_config(
            {
                "host": "saved.example.com",
                "port": 3306,
                "database": "ops",
                "username": "reader",
                "password": "saved-secret",
            }
        ),
    )

    request = _build_request(
        authenticated_user,
        f"/operation_analysis/api/data_connection/{connection.id}/test_connection/",
        data={
            "connection_type": DataConnection.TYPE_MYSQL,
            "config": {
                "host": "draft.example.com",
                "port": 3307,
                "database": "ops_next",
                "username": "reader_next",
                "password": SENSITIVE_PLACEHOLDER,
            },
        },
    )
    response = data_connection_view.DataConnectionViewSet.as_view({"post": "test_connection"})(
        request,
        pk=connection.id,
    )

    assert response.status_code == status.HTTP_200_OK
    assert executor.test_connection_calls == [
        {
            "host": "draft.example.com",
            "port": 3307,
            "database": "ops_next",
            "username": "reader_next",
            "password": "saved-secret",
        }
    ]


def test_unsaved_connection_test_rejects_incomplete_config(authenticated_user, monkeypatch):
    authenticated_user.is_superuser = False
    authenticated_user.permission = {"ops-analysis": {"data_source-Edit"}}
    executor = FakeExecutor()
    monkeypatch.setattr(data_connection_view, "get_preview_executor", lambda connection_type: executor)

    request = _build_request(
        authenticated_user,
        "/operation_analysis/api/data_connection/test_connection/",
        data={
            "connection_type": DataConnection.TYPE_MYSQL,
            "config": {"host": "draft.example.com"},
        },
    )
    response = data_connection_view.DataConnectionViewSet.as_view({"post": "test_connection_config"})(request)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert executor.test_connection_calls == []


def test_saved_connection_test_rejects_other_team(authenticated_user, monkeypatch):
    authenticated_user.is_superuser = False
    authenticated_user.permission = {"ops-analysis": {"data_source-Edit"}}
    executor = FakeExecutor()
    monkeypatch.setattr(data_connection_view, "get_preview_executor", lambda connection_type: executor)
    connection = DataConnection.objects.create(
        name="mysql-team-test",
        connection_type=DataConnection.TYPE_MYSQL,
        groups=[2],
        config=encrypt_connection_config(
            {
                "host": "saved.example.com",
                "port": 3306,
                "database": "ops",
                "username": "reader",
                "password": "saved-secret",
            }
        ),
    )

    request = _build_request(
        authenticated_user,
        f"/operation_analysis/api/data_connection/{connection.id}/test_connection/",
        data={},
        current_team="1",
    )
    response = data_connection_view.DataConnectionViewSet.as_view({"post": "test_connection"})(
        request,
        pk=connection.id,
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert executor.test_connection_calls == []
