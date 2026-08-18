from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.urls import path

from apps.alerts.open_api import views as open_views


pytestmark = pytest.mark.django_db

urlpatterns = [
    path(
        "api/v1/alerts/api/open/alerts/actions/<str:action>",
        open_views.OpenAlertBatchActionView.as_view(),
    ),
    path(
        "api/v1/alerts/api/open/alerts/<str:alert_id>/events",
        open_views.OpenAlertEventsView.as_view(),
    ),
    path(
        "api/v1/alerts/api/open/alerts/<str:alert_id>/<str:action>",
        open_views.OpenAlertActionView.as_view(),
    ),
    path(
        "api/v1/alerts/api/open/alerts/<str:alert_id>",
        open_views.OpenAlertDetailView.as_view(),
    ),
    path("api/v1/alerts/api/open/alerts", open_views.OpenAlertListView.as_view()),
]


def _api_request(client, url, *, method="get", data=None):
    headers = {"HTTP_API_AUTHORIZATION": "secret"}
    if method == "get":
        return client.get(url, **headers)
    return client.post(url, data or {}, format="json", **headers)


@pytest.fixture(autouse=True)
def open_api_test_urlconf(settings):
    settings.ROOT_URLCONF = __name__
    settings.LICENSE_MGMT_ENABLED = False
    settings.MIDDLEWARE = tuple(
        middleware
        for middleware in settings.MIDDLEWARE
        if middleware != "django.contrib.messages.middleware.MessageMiddleware"
    )


@pytest.fixture
def api_secret_allowed(monkeypatch):
    monkeypatch.setattr(
        "apps.alerts.open_api.views.APISecretRequired.has_permission",
        lambda self, request, view: True,
    )


def _context(mock_context):
    context = mock_context.return_value
    context.team_id = 1
    context.user = SimpleNamespace(
        username="api-user",
        group_list=[{"id": 1}],
        permission={"alarm": {"Alarms-Edit"}},
        is_superuser=False,
    )
    return context


@patch("apps.alerts.open_api.views.AlertsOpenAPIService.operate_alert")
@patch("apps.alerts.open_api.views.AlertsOpenAPIContext.from_request")
def test_operate_alert_assign_returns_success_envelope(
    mock_context, mock_operate, api_client, api_secret_allowed
):
    _context(mock_context)
    mock_operate.return_value = {"alert_id": "A-1", "status": "assigned"}

    response = _api_request(
        api_client,
        "/api/v1/alerts/api/open/alerts/A-1/assign",
        method="post",
        data={"assignee": ["api-user"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["result"] is True
    assert body["code"] == "ok"
    assert body["data"] == mock_operate.return_value
    mock_operate.assert_called_once_with("A-1", "assign", {"assignee": ["api-user"]})


@patch("apps.alerts.open_api.views.AlertsOpenAPIService.operate_alerts_batch")
@patch("apps.alerts.open_api.views.AlertsOpenAPIContext.from_request")
def test_operate_alerts_batch_close_partial_success(
    mock_context, mock_batch, api_client, api_secret_allowed
):
    _context(mock_context)
    mock_batch.return_value = {
        "succeeded": ["A-1"],
        "failed": [{"alert_id": "A-2", "code": "alerts.alert.not_found", "message": "告警不存在"}],
    }

    response = _api_request(
        api_client,
        "/api/v1/alerts/api/open/alerts/actions/close",
        method="post",
        data={"alert_ids": ["A-1", "A-2"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["result"] is True
    assert body["code"] == "ok"
    assert body["data"] == mock_batch.return_value
    mock_batch.assert_called_once_with("close", {"alert_ids": ["A-1", "A-2"]})


@patch("apps.alerts.open_api.views.AlertsOpenAPIContext.from_request")
def test_invalid_action_returns_validation_failed(
    mock_context, api_client, api_secret_allowed
):
    _context(mock_context)

    response = _api_request(
        api_client,
        "/api/v1/alerts/api/open/alerts/A-1/invalid-action",
        method="post",
        data={},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["result"] is False
    assert body["code"] == "alerts.validation.failed"
    assert "不支持的操作" in body["message"]
