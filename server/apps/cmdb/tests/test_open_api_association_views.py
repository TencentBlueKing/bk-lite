from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.urls import path

from apps.cmdb.open_api import views as open_views
from apps.core.exceptions.base_app_exception import BaseAppException


pytestmark = pytest.mark.django_db

urlpatterns = [
    path(
        "api/v1/cmdb/api/open/models/<str:model_id>/instances/<int:inst_id>/associations",
        open_views.OpenInstanceAssociationsView.as_view(),
    ),
    path(
        "api/v1/cmdb/api/open/models/<str:model_id>/instances/<int:inst_id>/associations/<int:association_id>",
        open_views.OpenInstanceAssociationDetailView.as_view(),
    ),
]


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
    context.team_id = 7
    context.user = SimpleNamespace(locale="zh-CN", username="api-user", roles=[])
    context.permission_map.return_value = {7: {"permission_instances_map": {}, "inst_names": []}}
    return context


def _instance(inst_id, model_id, team_id=7):
    return {
        "_id": inst_id,
        "model_id": model_id,
        "inst_name": f"{model_id}-{inst_id}",
        "organization": [team_id],
        "_creator": "api-user",
    }


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.InstanceManage.instance_association_instance_list")
@patch("apps.cmdb.open_api.services.InstanceManage.query_entity_by_id")
def test_list_associations_requires_visible_source(
    mock_query, mock_list, mock_context, api_client, api_secret_allowed
):
    _context(mock_context)
    mock_query.return_value = _instance(1, "host")
    mock_list.return_value = [{"model_asst_id": "host_run_app", "inst_list": []}]

    response = api_client.get(
        "/api/v1/cmdb/api/open/models/host/instances/1/associations",
        HTTP_API_AUTHORIZATION="secret",
    )

    assert response.status_code == 200
    assert response.json()["data"] == [{"model_asst_id": "host_run_app", "inst_list": []}]
    mock_list.assert_called_once_with("host", 1)


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.InstanceManage.instance_association_create")
@patch("apps.cmdb.open_api.services.ModelManage.model_association_info_search")
@patch("apps.cmdb.open_api.services.InstanceManage.query_entity_by_id")
def test_create_association_rejects_cross_team_target(
    mock_query, mock_association, mock_create, mock_context, api_client, api_secret_allowed
):
    _context(mock_context)
    mock_query.side_effect = [_instance(1, "host"), _instance(2, "app", team_id=8)]

    response = api_client.post(
        "/api/v1/cmdb/api/open/models/host/instances/1/associations",
        {"model_asst_id": "host_run_app", "target_model_id": "app", "target_inst_id": 2},
        format="json",
        HTTP_API_AUTHORIZATION="secret",
    )

    assert response.status_code == 404
    assert response.json()["code"] == "cmdb.instance.not_found"
    mock_association.assert_not_called()
    mock_create.assert_not_called()


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.InstanceManage.instance_association_create")
@patch("apps.cmdb.open_api.services.ModelManage.model_association_info_search")
@patch("apps.cmdb.open_api.services.InstanceManage.query_entity_by_id")
def test_create_association_requires_matching_model_direction(
    mock_query, mock_association, mock_create, mock_context, api_client, api_secret_allowed
):
    _context(mock_context)
    mock_query.side_effect = [_instance(1, "host"), _instance(2, "app")]
    mock_association.return_value = {
        "model_asst_id": "app_run_host",
        "src_model_id": "app",
        "dst_model_id": "host",
    }

    response = api_client.post(
        "/api/v1/cmdb/api/open/models/host/instances/1/associations",
        {"model_asst_id": "app_run_host", "target_model_id": "app", "target_inst_id": 2},
        format="json",
        HTTP_API_AUTHORIZATION="secret",
    )

    assert response.status_code == 400
    assert response.json()["code"] == "cmdb.association.invalid_direction"
    mock_create.assert_not_called()


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.InstanceManage.instance_association_create")
@patch("apps.cmdb.open_api.services.ModelManage.model_association_info_search")
@patch("apps.cmdb.open_api.services.InstanceManage.query_entity_by_id")
def test_create_association_writes_after_both_endpoints_are_authorized(
    mock_query, mock_association, mock_create, mock_context, api_client, api_secret_allowed
):
    _context(mock_context)
    mock_query.side_effect = [_instance(1, "host"), _instance(2, "app")]
    mock_association.return_value = {
        "model_asst_id": "host_run_app",
        "src_model_id": "host",
        "dst_model_id": "app",
    }
    mock_create.return_value = {"_id": 10}

    response = api_client.post(
        "/api/v1/cmdb/api/open/models/host/instances/1/associations",
        {"model_asst_id": "host_run_app", "target_model_id": "app", "target_inst_id": 2},
        format="json",
        HTTP_API_AUTHORIZATION="secret",
    )

    assert response.status_code == 201
    assert response.json()["data"] == {"association_id": 10, "model_asst_id": "host_run_app"}
    mock_create.assert_called_once_with(
        {"src_inst_id": 1, "dst_inst_id": 2, "model_asst_id": "host_run_app"}, "api-user"
    )


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.InstanceManage.instance_association_create")
@patch("apps.cmdb.open_api.services.ModelManage.model_association_info_search")
@patch("apps.cmdb.open_api.services.InstanceManage.query_entity_by_id")
def test_create_association_returns_stable_conflict_for_duplicate(
    mock_query, mock_association, mock_create, mock_context, api_client, api_secret_allowed
):
    _context(mock_context)
    mock_query.side_effect = [_instance(1, "host"), _instance(2, "app")]
    mock_association.return_value = {
        "model_asst_id": "host_run_app",
        "src_model_id": "host",
        "dst_model_id": "app",
    }
    mock_create.side_effect = BaseAppException("instance association repetition")

    response = api_client.post(
        "/api/v1/cmdb/api/open/models/host/instances/1/associations",
        {"model_asst_id": "host_run_app", "target_model_id": "app", "target_inst_id": 2},
        format="json",
        HTTP_API_AUTHORIZATION="secret",
    )

    assert response.status_code == 409
    assert response.json()["code"] == "cmdb.association.conflict"


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.InstanceManage.instance_association_delete")
@patch("apps.cmdb.open_api.services.InstanceManage.instance_association_by_asso_id")
def test_delete_association_requires_url_source_match(
    mock_association, mock_delete, mock_context, api_client, api_secret_allowed
):
    _context(mock_context)
    mock_association.return_value = {
        "_id": 10,
        "src": _instance(99, "host"),
        "dst": _instance(2, "app"),
    }

    response = api_client.delete(
        "/api/v1/cmdb/api/open/models/host/instances/1/associations/10",
        HTTP_API_AUTHORIZATION="secret",
    )

    assert response.status_code == 404
    assert response.json()["code"] == "cmdb.association.not_found"
    mock_delete.assert_not_called()


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.InstanceManage.instance_association_delete")
@patch("apps.cmdb.open_api.services.InstanceManage.instance_association_by_asso_id")
def test_delete_association_hides_malformed_edge_as_not_found(
    mock_association, mock_delete, mock_context, api_client, api_secret_allowed
):
    _context(mock_context)
    mock_association.return_value = {"_id": 10, "src": _instance(1, "host"), "dst": {}}

    response = api_client.delete(
        "/api/v1/cmdb/api/open/models/host/instances/1/associations/10",
        HTTP_API_AUTHORIZATION="secret",
    )

    assert response.status_code == 404
    assert response.json()["code"] == "cmdb.association.not_found"
    mock_delete.assert_not_called()


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.InstanceManage.instance_association_delete")
@patch("apps.cmdb.open_api.services.InstanceManage.query_entity_by_id")
@patch("apps.cmdb.open_api.services.InstanceManage.instance_association_by_asso_id")
def test_delete_association_checks_both_visible_endpoints(
    mock_association, mock_query, mock_delete, mock_context, api_client, api_secret_allowed
):
    _context(mock_context)
    mock_association.return_value = {
        "_id": 10,
        "src": _instance(1, "host"),
        "dst": _instance(2, "app", team_id=8),
    }
    mock_query.side_effect = [_instance(1, "host"), _instance(2, "app", team_id=8)]

    response = api_client.delete(
        "/api/v1/cmdb/api/open/models/host/instances/1/associations/10",
        HTTP_API_AUTHORIZATION="secret",
    )

    assert response.status_code == 404
    assert response.json()["code"] == "cmdb.instance.not_found"
    mock_delete.assert_not_called()


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.InstanceManage.instance_association_delete")
@patch("apps.cmdb.open_api.services.InstanceManage.query_entity_by_id")
@patch("apps.cmdb.open_api.services.InstanceManage.instance_association_by_asso_id")
def test_delete_association_deletes_after_both_endpoints_are_authorized(
    mock_association, mock_query, mock_delete, mock_context, api_client, api_secret_allowed
):
    _context(mock_context)
    mock_association.return_value = {
        "_id": 10,
        "src": _instance(1, "host"),
        "dst": _instance(2, "app"),
    }
    mock_query.side_effect = [_instance(1, "host"), _instance(2, "app")]

    response = api_client.delete(
        "/api/v1/cmdb/api/open/models/host/instances/1/associations/10",
        HTTP_API_AUTHORIZATION="secret",
    )

    assert response.status_code == 200
    assert response.json()["data"] == {"deleted": 10}
    mock_delete.assert_called_once_with(10, "api-user")
