import json

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.urls import path
from rest_framework.test import APIRequestFactory

from apps.cmdb.open_api import views as open_views


pytestmark = pytest.mark.django_db

urlpatterns = [
    path("api/v1/cmdb/api/open/classifications", open_views.OpenClassificationListView.as_view()),
    path("api/v1/cmdb/api/open/models", open_views.OpenModelListView.as_view()),
    path("api/v1/cmdb/api/open/models/<str:model_id>", open_views.OpenModelDetailView.as_view()),
    path(
        "api/v1/cmdb/api/open/models/<str:model_id>/attributes",
        open_views.OpenModelAttrsView.as_view(),
    ),
    path(
        "api/v1/cmdb/api/open/models/<str:model_id>/associations",
        open_views.OpenModelAssociationsView.as_view(),
    ),
]


def _api_request(client, url):
    return client.get(url, HTTP_API_AUTHORIZATION="secret")


@pytest.fixture(autouse=True)
def open_api_test_urlconf(settings):
    settings.ROOT_URLCONF = __name__
    settings.MIDDLEWARE = tuple(
        middleware
        for middleware in settings.MIDDLEWARE
        if middleware != "django.contrib.messages.middleware.MessageMiddleware"
    )


@pytest.fixture
def api_secret_allowed(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.open_api.views.APISecretRequired.has_permission",
        lambda self, request, view: True,
    )


def _context(mock_context):
    context = mock_context.return_value
    context.user = SimpleNamespace(locale="zh-CN")
    context.permission_map.return_value = {7: {"permission_instances_map": {}, "inst_names": []}}
    return context


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.get_default_group_id", return_value=[1])
@patch("apps.cmdb.open_api.services.ModelManage.search_model")
def test_model_list_returns_only_service_visible_models(
    mock_search, mock_group, mock_context, api_client, api_secret_allowed
):
    _context(mock_context)
    mock_search.return_value = [{"model_id": "host", "classification_id": "infra"}]

    response = _api_request(api_client, "/api/v1/cmdb/api/open/models")

    assert response.status_code == 200
    assert response.json()["data"] == [{"model_id": "host", "classification_id": "infra"}]
    mock_search.assert_called_once_with(
        language="zh-CN",
        permissions_map={
            1: {
                "permission_instances_map": {},
                "inst_names": [],
                "__default_model": ["View"],
            },
            7: {"permission_instances_map": {}, "inst_names": []},
        },
        include_hidden=False,
    )


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.get_default_group_id", return_value=[1])
@patch("apps.cmdb.open_api.services.ModelManage.search_model")
@patch("apps.cmdb.open_api.services.ClassificationManage.search_model_classification")
def test_classifications_only_include_visible_model_categories(
    mock_classifications, mock_models, mock_group, mock_context, api_client, api_secret_allowed
):
    _context(mock_context)
    mock_models.return_value = [{"model_id": "host", "classification_id": "infra"}]
    mock_classifications.return_value = [
        {"classification_id": "infra"},
        {"classification_id": "hidden"},
    ]

    response = _api_request(api_client, "/api/v1/cmdb/api/open/classifications")

    assert response.status_code == 200
    assert response.json()["data"] == [{"classification_id": "infra"}]
    mock_classifications.assert_called_once_with("zh-CN", include_hidden=False)


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.ModelManage.search_model_info", return_value={})
def test_model_detail_missing_returns_stable_404(
    mock_info, mock_context, api_client, api_secret_allowed
):
    _context(mock_context)

    response = _api_request(api_client, "/api/v1/cmdb/api/open/models/missing")

    body = response.json()
    assert response.status_code == 404
    assert body["code"] == "cmdb.model.not_found"


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.get_default_group_id", return_value=[1])
@patch("apps.cmdb.open_api.services.CmdbRulesFormatUtil.has_object_permission", return_value=True)
@patch(
    "apps.cmdb.open_api.services.ModelManage.search_model_attr",
    return_value=[
        {"attr_id": "ip_addr", "is_required": True},
        {"attr_id": "comment", "is_required": False},
    ],
)
@patch(
    "apps.cmdb.open_api.services.ModelManage.search_model_info",
    return_value={"model_id": "host", "group": [7]},
)
def test_model_attributes_are_returned_after_model_visibility_check(
    mock_info, mock_attrs, mock_permission, mock_group, mock_context, api_client, api_secret_allowed
):
    _context(mock_context)

    response = _api_request(api_client, "/api/v1/cmdb/api/open/models/host/attributes")

    assert response.status_code == 200
    assert response.json()["data"] == [
        {"attr_id": "ip_addr", "is_required": True, "required": True},
        {"attr_id": "comment", "is_required": False, "required": False},
    ]
    mock_attrs.assert_called_once_with("host")


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.get_default_group_id", return_value=[1])
@patch("apps.cmdb.open_api.services.CmdbRulesFormatUtil.has_object_permission", return_value=True)
@patch(
    "apps.cmdb.open_api.services.ModelManage.model_association_search",
    return_value=[{"model_asst_id": "host_run"}],
)
@patch(
    "apps.cmdb.open_api.services.ModelManage.search_model_info",
    return_value={"model_id": "host", "group": [7]},
)
def test_model_associations_are_returned_after_model_visibility_check(
    mock_info,
    mock_associations,
    mock_permission,
    mock_group,
    mock_context,
    api_client,
    api_secret_allowed,
):
    _context(mock_context)

    response = _api_request(api_client, "/api/v1/cmdb/api/open/models/host/associations")

    assert response.status_code == 200
    assert response.json()["data"] == [{"model_asst_id": "host_run"}]
    mock_associations.assert_called_once_with("host")


def test_api_secret_rejection_returns_stable_error_envelope(api_client):
    response = _api_request(api_client, "/api/v1/cmdb/api/open/models")

    body = response.json()
    assert response.status_code == 403
    assert body["result"] is False
    assert body["code"] == "cmdb.auth.api_secret_required"
    assert body["data"] == {}


def test_non_get_request_returns_stable_method_not_allowed_envelope():
    request = APIRequestFactory().post("/api/v1/cmdb/api/open/models")
    request.api_pass = True

    response = open_views.OpenModelListView.as_view()(request)
    body = json.loads(response.content)

    assert response.status_code == 405
    assert body["result"] is False
    assert body["code"] == "cmdb.request.method_not_allowed"
    assert body["data"] == {}
