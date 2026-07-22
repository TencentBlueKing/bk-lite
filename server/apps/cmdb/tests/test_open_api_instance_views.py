from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.urls import path

from apps.cmdb.open_api import views as open_views


pytestmark = pytest.mark.django_db

urlpatterns = [
    path(
        "api/v1/cmdb/api/open/models/<str:model_id>/instances",
        open_views.OpenInstanceCollectionView.as_view(),
    ),
    path(
        "api/v1/cmdb/api/open/models/<str:model_id>/instances/<int:inst_id>",
        open_views.OpenInstanceDetailView.as_view(),
    ),
]


@pytest.fixture(autouse=True)
def open_api_test_urlconf(settings, monkeypatch):
    settings.ROOT_URLCONF = __name__
    monkeypatch.setattr("apps.cmdb.open_api.services.get_default_group_id", lambda: [1])
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
    context.team_id = 7
    context.user = SimpleNamespace(locale="zh-CN", username="api-user", roles=[])
    context.permission_map.return_value = {7: {"permission_instances_map": {}, "inst_names": []}}
    return context


def _model_and_attrs(mock_model, mock_attrs):
    mock_model.return_value = {"model_id": "host", "group": [7]}
    mock_attrs.return_value = [
        {"attr_id": "inst_name", "attr_type": "str", "editable": True},
        {"attr_id": "ip", "attr_type": "str", "editable": True},
        {"attr_id": "readonly", "attr_type": "str", "editable": False},
    ]


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.CmdbRulesFormatUtil.has_object_permission", return_value=True)
@patch("apps.cmdb.open_api.services.ModelManage.search_model_attr")
@patch("apps.cmdb.open_api.services.ModelManage.search_model_info")
@patch("apps.cmdb.open_api.services.InstanceManage.instance_list")
def test_list_uses_bound_team_permission_map_and_serializes_instances(
    mock_list, mock_model, mock_attrs, mock_permission, mock_context, api_client, api_secret_allowed
):
    context = _context(mock_context)
    _model_and_attrs(mock_model, mock_attrs)
    mock_list.return_value = (
        [{"_id": 11, "model_id": "host", "inst_name": "h1", "_labels": "instance"}],
        1,
    )

    response = api_client.get(
        "/api/v1/cmdb/api/open/models/host/instances?page=2&page_size=10&order=-inst_id",
        HTTP_API_AUTHORIZATION="secret",
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "count": 1,
        "page": 2,
        "page_size": 10,
        "items": [{"inst_id": 11, "model_id": "host", "inst_name": "h1"}],
    }
    mock_list.assert_called_once_with(
        model_id="host",
        params=[],
        page=2,
        page_size=10,
        order="-_id",
        permission_map=context.permission_map.return_value,
        creator="api-user",
    )


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.InstanceManage.query_entity_by_id")
def test_cross_team_instance_is_hidden_as_404(mock_query, mock_context, api_client, api_secret_allowed):
    _context(mock_context)
    mock_query.return_value = {"_id": 12, "model_id": "host", "inst_name": "other", "organization": [8]}

    response = api_client.get(
        "/api/v1/cmdb/api/open/models/host/instances/12",
        HTTP_API_AUTHORIZATION="secret",
    )

    assert response.status_code == 404
    assert response.json()["code"] == "cmdb.instance.not_found"


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.CmdbRulesFormatUtil.has_object_permission", return_value=True)
@patch("apps.cmdb.open_api.services.InstanceManage.instance_create")
@patch("apps.cmdb.open_api.services.ModelManage.search_model_attr")
@patch("apps.cmdb.open_api.services.ModelManage.search_model_info")
def test_create_rejects_client_organization_before_domain_write(
    mock_model, mock_attrs, mock_create, mock_permission, mock_context, api_client, api_secret_allowed
):
    _context(mock_context)
    _model_and_attrs(mock_model, mock_attrs)

    response = api_client.post(
        "/api/v1/cmdb/api/open/models/host/instances",
        {"inst_name": "h1", "organization": [999]},
        format="json",
        HTTP_API_AUTHORIZATION="secret",
    )

    assert response.status_code == 400
    mock_create.assert_not_called()


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.CmdbRulesFormatUtil.has_object_permission", return_value=True)
@patch("apps.cmdb.open_api.services.InstanceManage.instance_create")
@patch("apps.cmdb.open_api.services.ModelManage.search_model_attr")
@patch("apps.cmdb.open_api.services.ModelManage.search_model_info")
def test_create_forces_bound_team(
    mock_model, mock_attrs, mock_create, mock_permission, mock_context, api_client, api_secret_allowed
):
    _context(mock_context)
    _model_and_attrs(mock_model, mock_attrs)
    mock_create.return_value = {"_id": 11, "model_id": "host", "inst_name": "h1", "organization": [7]}

    response = api_client.post(
        "/api/v1/cmdb/api/open/models/host/instances",
        {"inst_name": "h1"},
        format="json",
        HTTP_API_AUTHORIZATION="secret",
    )

    assert response.status_code == 201
    assert response.json()["data"]["inst_id"] == 11
    mock_create.assert_called_once_with(
        "host",
        {"inst_name": "h1", "organization": [7]},
        "api-user",
        allowed_org_ids=[7],
    )


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.CmdbRulesFormatUtil.has_object_permission", return_value=True)
@patch("apps.cmdb.open_api.services.InstanceManage.instance_update")
@patch("apps.cmdb.open_api.services.InstanceManage.query_entity_by_id")
@patch("apps.cmdb.open_api.services.ModelManage.search_model_attr")
@patch("apps.cmdb.open_api.services.ModelManage.search_model_info")
def test_update_rejects_organization_before_domain_write(
    mock_model, mock_attrs, mock_query, mock_update, mock_permission, mock_context, api_client, api_secret_allowed
):
    _context(mock_context)
    _model_and_attrs(mock_model, mock_attrs)
    mock_query.return_value = {"_id": 12, "model_id": "host", "inst_name": "h1", "organization": [7]}

    response = api_client.patch(
        "/api/v1/cmdb/api/open/models/host/instances/12",
        {"organization": [8]},
        format="json",
        HTTP_API_AUTHORIZATION="secret",
    )

    assert response.status_code == 400
    mock_update.assert_not_called()


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.CmdbRulesFormatUtil.has_object_permission", return_value=True)
@patch("apps.cmdb.open_api.services.InstanceManage.instance_update")
@patch("apps.cmdb.open_api.services.InstanceManage.query_entity_by_id")
@patch("apps.cmdb.open_api.services.ModelManage.search_model_attr")
@patch("apps.cmdb.open_api.services.ModelManage.search_model_info")
def test_update_writes_only_after_visible_operate_permission(
    mock_model,
    mock_attrs,
    mock_query,
    mock_update,
    mock_permission,
    mock_context,
    api_client,
    api_secret_allowed,
):
    context = _context(mock_context)
    _model_and_attrs(mock_model, mock_attrs)
    mock_query.return_value = {"_id": 12, "model_id": "host", "inst_name": "h1", "organization": [7]}
    mock_update.return_value = {"_id": 12, "model_id": "host", "inst_name": "h1", "ip": "10.0.0.1"}

    response = api_client.patch(
        "/api/v1/cmdb/api/open/models/host/instances/12",
        {"ip": "10.0.0.1"},
        format="json",
        HTTP_API_AUTHORIZATION="secret",
    )

    assert response.status_code == 200
    assert response.json()["data"]["inst_id"] == 12
    mock_update.assert_called_once_with(
        context.user_groups,
        context.user.roles,
        12,
        {"ip": "10.0.0.1"},
        "api-user",
        allowed_org_ids=[7],
    )


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.CmdbRulesFormatUtil.has_object_permission", return_value=True)
@patch("apps.cmdb.open_api.services.InstanceManage.instance_batch_delete")
@patch("apps.cmdb.open_api.services.InstanceManage.query_entity_by_id")
def test_delete_uses_single_instance_operate_permission(
    mock_query, mock_delete, mock_permission, mock_context, api_client, api_secret_allowed
):
    context = _context(mock_context)
    mock_query.return_value = {"_id": 12, "model_id": "host", "inst_name": "h1", "organization": [7]}

    response = api_client.delete(
        "/api/v1/cmdb/api/open/models/host/instances/12",
        HTTP_API_AUTHORIZATION="secret",
    )

    assert response.status_code == 200
    assert response.json()["data"] == {"deleted": [12]}
    mock_delete.assert_called_once_with(context.user_groups, context.user.roles, [12], "api-user")
