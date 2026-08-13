from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.urls import path

from apps.cmdb.open_api import views as open_views
from apps.core.exceptions.base_app_exception import BaseAppException

pytestmark = pytest.mark.django_db

SRC_UUID = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
DST_UUID = "7de0c6de-f841-44b1-846d-2d75a7c59c50"

urlpatterns = [
    path(
        "api/v1/cmdb/api/open/models/<str:model_id>/instances/<str:inst_uuid>/associations",
        open_views.OpenInstanceAssociationsView.as_view(),
    ),
    path(
        "api/v1/cmdb/api/open/models/<str:model_id>/instances/<str:inst_uuid>/associations/" "<str:dst_inst_uuid>/<str:model_asst_id>",
        open_views.OpenInstanceAssociationDetailView.as_view(),
    ),
]


@pytest.fixture(autouse=True)
def open_api_test_urlconf(settings, monkeypatch):
    settings.ROOT_URLCONF = __name__
    monkeypatch.setattr(
        "apps.cmdb.open_api.services.ModelManage.search_model_info",
        lambda model_id: {"model_id": model_id, "group": [7], "is_visible": True},
    )
    settings.MIDDLEWARE = tuple(
        middleware for middleware in settings.MIDDLEWARE if middleware != "django.contrib.messages.middleware.MessageMiddleware"
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


def _instance(inst_id, inst_uuid, model_id, team_id=7):
    return {
        "_id": inst_id,
        "inst_uuid": inst_uuid,
        "model_id": model_id,
        "inst_name": f"{model_id}-{inst_id}",
        "organization": [team_id],
        "_creator": "api-user",
    }


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.InstanceManage.instance_association_instance_list_by_uuid")
@patch("apps.cmdb.open_api.services.InstanceManage.query_entity_by_uuid")
def test_list_associations_uses_uuid_and_hides_graph_ids(mock_query, mock_list, mock_context, api_client, api_secret_allowed):
    _context(mock_context)
    mock_query.return_value = _instance(1, SRC_UUID, "host")
    mock_list.return_value = [
        {
            "model_asst_id": "host_run_app",
            "inst_list": [_instance(2, DST_UUID, "app")],
        }
    ]

    response = api_client.get(
        f"/api/v1/cmdb/api/open/models/host/instances/{SRC_UUID}/associations",
        HTTP_API_AUTHORIZATION="secret",
    )

    assert response.status_code == 200
    target = response.json()["data"][0]["inst_list"][0]
    assert target["inst_uuid"] == DST_UUID
    assert "_id" not in target
    mock_list.assert_called_once_with("host", SRC_UUID, business_only=True)


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.InstanceManage.instance_association_create_by_uuid")
@patch("apps.cmdb.open_api.services.ModelManage.model_association_info_search")
@patch("apps.cmdb.open_api.services.InstanceManage.query_entity_by_uuid")
def test_create_association_rejects_cross_team_target(mock_query, mock_association, mock_create, mock_context, api_client, api_secret_allowed):
    _context(mock_context)
    mock_query.side_effect = [
        _instance(1, SRC_UUID, "host"),
        _instance(2, DST_UUID, "app", team_id=8),
    ]

    response = api_client.post(
        f"/api/v1/cmdb/api/open/models/host/instances/{SRC_UUID}/associations",
        {"model_asst_id": "host_run_app", "target_model_id": "app", "target_inst_uuid": DST_UUID},
        format="json",
        HTTP_API_AUTHORIZATION="secret",
    )

    assert response.status_code == 404
    mock_association.assert_not_called()
    mock_create.assert_not_called()


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.InstanceManage.instance_association_create_by_uuid")
@patch("apps.cmdb.open_api.services.ModelManage.model_association_info_search")
@patch("apps.cmdb.open_api.services.InstanceManage.query_entity_by_uuid")
def test_create_association_writes_stable_business_key(mock_query, mock_association, mock_create, mock_context, api_client, api_secret_allowed):
    _context(mock_context)
    mock_query.side_effect = [_instance(1, SRC_UUID, "host"), _instance(2, DST_UUID, "app")]
    mock_association.return_value = {
        "model_asst_id": "host_run_app",
        "src_model_id": "host",
        "dst_model_id": "app",
    }
    expected = {
        "model_asst_id": "host_run_app",
        "src_inst_uuid": SRC_UUID,
        "dst_inst_uuid": DST_UUID,
    }
    mock_create.return_value = expected

    response = api_client.post(
        f"/api/v1/cmdb/api/open/models/host/instances/{SRC_UUID}/associations",
        {"model_asst_id": "host_run_app", "target_model_id": "app", "target_inst_uuid": DST_UUID},
        format="json",
        HTTP_API_AUTHORIZATION="secret",
    )

    assert response.status_code == 201
    assert response.json()["data"] == expected
    mock_create.assert_called_once_with(
        src_inst_uuid=SRC_UUID,
        dst_inst_uuid=DST_UUID,
        model_asst_id="host_run_app",
        operator="api-user",
    )


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.InstanceManage.instance_association_create_by_uuid")
@patch("apps.cmdb.open_api.services.ModelManage.model_association_info_search")
@patch("apps.cmdb.open_api.services.InstanceManage.query_entity_by_uuid")
def test_create_association_returns_stable_conflict_for_duplicate(
    mock_query, mock_association, mock_create, mock_context, api_client, api_secret_allowed
):
    _context(mock_context)
    mock_query.side_effect = [_instance(1, SRC_UUID, "host"), _instance(2, DST_UUID, "app")]
    mock_association.return_value = {
        "model_asst_id": "host_run_app",
        "src_model_id": "host",
        "dst_model_id": "app",
    }
    mock_create.side_effect = BaseAppException("instance association repetition")

    response = api_client.post(
        f"/api/v1/cmdb/api/open/models/host/instances/{SRC_UUID}/associations",
        {"model_asst_id": "host_run_app", "target_model_id": "app", "target_inst_uuid": DST_UUID},
        format="json",
        HTTP_API_AUTHORIZATION="secret",
    )

    assert response.status_code == 409
    assert response.json()["code"] == "cmdb.association.conflict"


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.InstanceManage.instance_association_delete_by_key")
@patch("apps.cmdb.open_api.services.ModelManage.model_association_info_search")
@patch("apps.cmdb.open_api.services.InstanceManage.query_entity_by_uuid")
def test_delete_association_checks_both_endpoints_and_uses_business_key(
    mock_query, mock_association, mock_delete, mock_context, api_client, api_secret_allowed
):
    _context(mock_context)
    mock_association.return_value = {
        "model_asst_id": "host_run_app",
        "src_model_id": "host",
        "dst_model_id": "app",
    }
    mock_query.side_effect = [_instance(1, SRC_UUID, "host"), _instance(2, DST_UUID, "app")]
    expected = {
        "model_asst_id": "host_run_app",
        "src_inst_uuid": SRC_UUID,
        "dst_inst_uuid": DST_UUID,
    }
    mock_delete.return_value = expected

    response = api_client.delete(
        f"/api/v1/cmdb/api/open/models/host/instances/{SRC_UUID}/associations/" f"{DST_UUID}/host_run_app",
        HTTP_API_AUTHORIZATION="secret",
    )

    assert response.status_code == 200
    assert response.json()["data"] == expected
    mock_delete.assert_called_once_with(
        src_inst_uuid=SRC_UUID,
        dst_inst_uuid=DST_UUID,
        model_asst_id="host_run_app",
        operator="api-user",
    )
