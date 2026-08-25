import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.urls import path
from rest_framework.test import APIRequestFactory

from apps.alerts.open_api import views as open_views


pytestmark = pytest.mark.django_db

urlpatterns = [
    path(
        "api/v1/alerts/api/open/alerts/<str:alert_id>/events",
        open_views.OpenAlertEventsView.as_view(),
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
        permission={"alarm": {"Alarms-View"}},
        is_superuser=False,
    )
    return context


@patch("apps.alerts.open_api.views.AlertsOpenAPIService.list_alerts")
@patch("apps.alerts.open_api.views.AlertsOpenAPIContext.from_request")
def test_list_alerts_returns_success_envelope(
    mock_context, mock_list, api_client, api_secret_allowed
):
    _context(mock_context)
    mock_list.return_value = {
        "count": 1,
        "page": 1,
        "page_size": 20,
        "items": [{"alert_id": "A-1", "title": "test"}],
    }

    response = _api_request(api_client, "/api/v1/alerts/api/open/alerts?page=1&page_size=20")

    assert response.status_code == 200
    body = response.json()
    assert body["result"] is True
    assert body["code"] == "ok"
    assert body["data"] == mock_list.return_value
    mock_list.assert_called_once()


@patch("apps.alerts.open_api.views.AlertsOpenAPIService.get_alert")
@patch("apps.alerts.open_api.views.AlertsOpenAPIContext.from_request")
def test_get_alert_returns_success_envelope(
    mock_context, mock_get, api_client, api_secret_allowed
):
    _context(mock_context)
    mock_get.return_value = {"alert_id": "A-1", "title": "detail", "labels": {}}

    response = _api_request(api_client, "/api/v1/alerts/api/open/alerts/A-1")

    assert response.status_code == 200
    body = response.json()
    assert body["result"] is True
    assert body["code"] == "ok"
    assert body["data"]["alert_id"] == "A-1"
    mock_get.assert_called_once_with("A-1")


@patch("apps.alerts.open_api.views.AlertsOpenAPIService.list_alert_events")
@patch("apps.alerts.open_api.views.AlertsOpenAPIContext.from_request")
def test_list_alert_events_returns_success_envelope(
    mock_context, mock_events, api_client, api_secret_allowed
):
    _context(mock_context)
    mock_events.return_value = {
        "count": 1,
        "page": 1,
        "page_size": 20,
        "items": [{"event_id": "E-1", "title": "event"}],
    }

    response = _api_request(api_client, "/api/v1/alerts/api/open/alerts/A-1/events")

    assert response.status_code == 200
    body = response.json()
    assert body["result"] is True
    assert body["code"] == "ok"
    assert body["data"]["items"][0]["event_id"] == "E-1"
    mock_events.assert_called_once()


def test_api_secret_rejection_returns_stable_error_envelope(api_client):
    response = _api_request(api_client, "/api/v1/alerts/api/open/alerts")

    body = response.json()
    assert response.status_code == 403
    assert body["result"] is False
    assert body["code"] == "alerts.auth.api_secret_required"
    assert body["data"] == {}


def test_non_get_request_returns_stable_method_not_allowed_envelope():
    request = APIRequestFactory().post("/api/v1/alerts/api/open/alerts")
    request.api_pass = True

    response = open_views.OpenAlertListView.as_view()(request)
    body = json.loads(response.content)

    assert response.status_code == 405
    assert body["result"] is False
    assert body["code"] == "alerts.request.method_not_allowed"
    assert body["data"] == {}
