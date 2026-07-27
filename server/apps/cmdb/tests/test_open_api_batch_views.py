from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.urls import path

from apps.cmdb.open_api import views as open_views
from apps.cmdb.services import instance as instance_service


pytestmark = pytest.mark.django_db

urlpatterns = [
    path(
        "api/v1/cmdb/api/open/models/<str:model_id>/instances/batch_create",
        getattr(open_views, "OpenBatchCreateView", open_views.CMDBOpenAPIView).as_view(),
    ),
    path(
        "api/v1/cmdb/api/open/models/<str:model_id>/instances/batch_update",
        getattr(open_views, "OpenBatchUpdateView", open_views.CMDBOpenAPIView).as_view(),
    ),
    path(
        "api/v1/cmdb/api/open/models/<str:model_id>/instances/batch_delete",
        getattr(open_views, "OpenBatchDeleteView", open_views.CMDBOpenAPIView).as_view(),
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
    context.user_groups = [{"id": 7}]
    context.permission_map.return_value = {7: {"permission_instances_map": {}, "inst_names": []}}
    return context


def _model_and_attrs(mock_model, mock_attrs):
    mock_model.return_value = {"model_id": "host", "group": [7]}
    mock_attrs.return_value = [
        {"attr_id": "inst_name", "attr_type": "str", "editable": True},
        {"attr_id": "status", "attr_type": "str", "editable": True},
    ]


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.InstanceManage.instance_batch_create")
def test_batch_create_caps_items_at_one_hundred(
    mock_create,
    mock_context,
    api_client,
    api_secret_allowed,
):
    _context(mock_context)

    response = api_client.post(
        "/api/v1/cmdb/api/open/models/host/instances/batch_create",
        {"items": [{"inst_name": f"h{i}"} for i in range(101)]},
        format="json",
        HTTP_API_AUTHORIZATION="secret",
    )

    assert response.status_code == 400
    mock_create.assert_not_called()


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.CmdbRulesFormatUtil.has_object_permission", return_value=True)
@patch("apps.cmdb.open_api.services.InstanceManage.instance_batch_create")
@patch("apps.cmdb.open_api.services.ModelManage.search_model_attr")
@patch("apps.cmdb.open_api.services.ModelManage.search_model_info")
def test_batch_create_forces_bound_team_for_every_item(
    mock_model,
    mock_attrs,
    mock_create,
    mock_permission,
    mock_context,
    api_client,
    api_secret_allowed,
):
    _context(mock_context)
    _model_and_attrs(mock_model, mock_attrs)
    mock_create.return_value = [
        {"_id": 1, "model_id": "host", "inst_name": "h1", "organization": [7]},
        {"_id": 2, "model_id": "host", "inst_name": "h2", "organization": [7]},
    ]

    response = api_client.post(
        "/api/v1/cmdb/api/open/models/host/instances/batch_create",
        {"items": [{"inst_name": "h1"}, {"inst_name": "h2"}]},
        format="json",
        HTTP_API_AUTHORIZATION="secret",
    )

    assert response.status_code == 201
    assert [item["inst_id"] for item in response.json()["data"]["created"]] == [1, 2]
    mock_create.assert_called_once_with(
        "host",
        [
            {"inst_name": "h1", "organization": [7]},
            {"inst_name": "h2", "organization": [7]},
        ],
        "api-user",
        [7],
    )


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.CmdbRulesFormatUtil.has_object_permission", return_value=True)
@patch("apps.cmdb.open_api.services.InstanceManage.instance_batch_create")
@patch("apps.cmdb.open_api.services.ModelManage.search_model_attr")
@patch("apps.cmdb.open_api.services.ModelManage.search_model_info")
def test_batch_create_reports_invalid_item_before_domain_write(
    mock_model,
    mock_attrs,
    mock_create,
    mock_permission,
    mock_context,
    api_client,
    api_secret_allowed,
):
    _context(mock_context)
    _model_and_attrs(mock_model, mock_attrs)

    response = api_client.post(
        "/api/v1/cmdb/api/open/models/host/instances/batch_create",
        {"items": [{"inst_name": "h1"}, {"inst_name": "h2", "organization": [8]}]},
        format="json",
        HTTP_API_AUTHORIZATION="secret",
    )

    assert response.status_code == 400
    assert response.json()["data"] == {"index": 1}
    mock_create.assert_not_called()


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.CmdbRulesFormatUtil.has_object_permission", return_value=True)
@patch("apps.cmdb.open_api.services.InstanceManage.instance_batch_create")
@patch("apps.cmdb.open_api.services.ModelManage.search_model_attr")
@patch("apps.cmdb.open_api.services.ModelManage.search_model_info")
def test_batch_create_maps_domain_preprocessing_index_to_stable_error(
    mock_model,
    mock_attrs,
    mock_create,
    mock_permission,
    mock_context,
    api_client,
    api_secret_allowed,
):
    _context(mock_context)
    _model_and_attrs(mock_model, mock_attrs)
    error_class = getattr(instance_service, "InstanceBatchError", None)
    assert error_class is not None, "领域层应提供结构化批量异常"
    mock_create.side_effect = error_class("枚举值非法", reason="validation", index=1)

    response = api_client.post(
        "/api/v1/cmdb/api/open/models/host/instances/batch_create",
        {"items": [{"inst_name": "h1"}, {"inst_name": "h2"}]},
        format="json",
        HTTP_API_AUTHORIZATION="secret",
    )

    assert response.status_code == 400
    assert response.json()["code"] == "cmdb.validation.failed"
    assert response.json()["data"] == {"index": 1}


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.InstanceManage.batch_instance_update")
@patch("apps.cmdb.open_api.services.InstanceManage.query_entity_by_id")
def test_batch_update_rejects_cross_team_member_before_write(
    mock_query,
    mock_update,
    mock_context,
    api_client,
    api_secret_allowed,
):
    _context(mock_context)
    mock_query.side_effect = [
        {"_id": 1, "model_id": "host", "inst_name": "h1", "organization": [7], "_creator": "api-user"},
        {"_id": 2, "model_id": "host", "inst_name": "h2", "organization": [8], "_creator": "api-user"},
    ]

    response = api_client.post(
        "/api/v1/cmdb/api/open/models/host/instances/batch_update",
        {"inst_ids": [1, 2], "update_data": {"status": "active"}},
        format="json",
        HTTP_API_AUTHORIZATION="secret",
    )

    assert response.status_code == 404
    assert response.json()["data"] == {"inst_id": 2}
    mock_update.assert_not_called()


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.CmdbRulesFormatUtil.has_object_permission", return_value=True)
@patch("apps.cmdb.open_api.services.InstanceManage.batch_instance_update")
@patch("apps.cmdb.open_api.services.InstanceManage.query_entity_by_id")
@patch("apps.cmdb.open_api.services.ModelManage.search_model_attr")
@patch("apps.cmdb.open_api.services.ModelManage.search_model_info")
def test_batch_update_calls_domain_once_after_all_members_are_authorized(
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
    mock_query.side_effect = [
        {"_id": 1, "model_id": "host", "inst_name": "h1", "organization": [7], "_creator": "api-user"},
        {"_id": 2, "model_id": "host", "inst_name": "h2", "organization": [7], "_creator": "api-user"},
    ]
    mock_update.return_value = [
        {"_id": 1, "model_id": "host", "inst_name": "h1", "status": "active"},
        {"_id": 2, "model_id": "host", "inst_name": "h2", "status": "active"},
    ]

    response = api_client.post(
        "/api/v1/cmdb/api/open/models/host/instances/batch_update",
        {"inst_ids": [1, 2], "update_data": {"status": "active"}},
        format="json",
        HTTP_API_AUTHORIZATION="secret",
    )

    assert response.status_code == 200
    assert [item["inst_id"] for item in response.json()["data"]["updated"]] == [1, 2]
    mock_update.assert_called_once_with(
        context.user_groups,
        context.user.roles,
        [1, 2],
        {"status": "active"},
        "api-user",
        [7],
    )


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.CmdbRulesFormatUtil.has_object_permission", return_value=True)
@patch("apps.cmdb.open_api.services.InstanceManage.batch_instance_update")
@patch("apps.cmdb.open_api.services.InstanceManage.query_entity_by_id")
@patch("apps.cmdb.open_api.services.ModelManage.search_model_attr")
@patch("apps.cmdb.open_api.services.ModelManage.search_model_info")
def test_batch_update_maps_domain_unique_conflict_to_409(
    mock_model,
    mock_attrs,
    mock_query,
    mock_update,
    mock_permission,
    mock_context,
    api_client,
    api_secret_allowed,
):
    _context(mock_context)
    _model_and_attrs(mock_model, mock_attrs)
    mock_query.side_effect = [
        {"_id": 1, "model_id": "host", "inst_name": "h1", "organization": [7]},
        {"_id": 2, "model_id": "host", "inst_name": "h2", "organization": [7]},
    ]
    mock_update.side_effect = instance_service.InstanceBatchError(
        "字段值违反唯一性约束",
        reason="unique_conflict",
        inst_id=2,
        field="status",
    )

    response = api_client.post(
        "/api/v1/cmdb/api/open/models/host/instances/batch_update",
        {"inst_ids": [1, 2], "update_data": {"status": "active"}},
        format="json",
        HTTP_API_AUTHORIZATION="secret",
    )

    assert response.status_code == 409
    assert response.json()["code"] == "cmdb.instance.unique_conflict"
    assert response.json()["data"] == {"inst_id": 2, "field": "status"}


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.InstanceManage.instance_batch_delete")
@patch("apps.cmdb.open_api.services.InstanceManage.query_entity_by_id")
def test_batch_delete_does_not_report_success_when_domain_requery_is_incomplete(
    mock_query,
    mock_delete,
    mock_context,
    api_client,
    api_secret_allowed,
):
    _context(mock_context)
    mock_query.side_effect = [
        {"_id": 1, "model_id": "host", "inst_name": "h1", "organization": [7]},
        {"_id": 2, "model_id": "host", "inst_name": "h2", "organization": [7]},
    ]
    mock_delete.side_effect = instance_service.InstanceBatchError(
        "实例不存在",
        reason="not_found",
        inst_id=2,
    )

    response = api_client.post(
        "/api/v1/cmdb/api/open/models/host/instances/batch_delete",
        {"inst_ids": [1, 2]},
        format="json",
        HTTP_API_AUTHORIZATION="secret",
    )

    assert response.status_code == 404
    assert response.json()["code"] == "cmdb.instance.not_found"
    assert response.json()["data"] == {"inst_id": 2}


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.InstanceManage.instance_batch_delete")
@patch("apps.cmdb.open_api.services.InstanceManage.query_entity_by_id")
def test_batch_delete_rejects_cross_team_member_before_write(
    mock_query,
    mock_delete,
    mock_context,
    api_client,
    api_secret_allowed,
):
    _context(mock_context)
    mock_query.side_effect = [
        {"_id": 1, "model_id": "host", "inst_name": "h1", "organization": [7], "_creator": "api-user"},
        {"_id": 2, "model_id": "host", "inst_name": "h2", "organization": [8], "_creator": "api-user"},
    ]

    response = api_client.post(
        "/api/v1/cmdb/api/open/models/host/instances/batch_delete",
        {"inst_ids": [1, 2]},
        format="json",
        HTTP_API_AUTHORIZATION="secret",
    )

    assert response.status_code == 404
    assert response.json()["data"] == {"inst_id": 2}
    mock_delete.assert_not_called()


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.InstanceManage.instance_batch_delete")
@patch("apps.cmdb.open_api.services.InstanceManage.query_entity_by_id")
def test_batch_delete_calls_domain_once_after_all_members_are_authorized(
    mock_query,
    mock_delete,
    mock_context,
    api_client,
    api_secret_allowed,
):
    context = _context(mock_context)
    mock_query.side_effect = [
        {"_id": 1, "model_id": "host", "inst_name": "h1", "organization": [7], "_creator": "api-user"},
        {"_id": 2, "model_id": "host", "inst_name": "h2", "organization": [7], "_creator": "api-user"},
    ]

    response = api_client.post(
        "/api/v1/cmdb/api/open/models/host/instances/batch_delete",
        {"inst_ids": [1, 2]},
        format="json",
        HTTP_API_AUTHORIZATION="secret",
    )

    assert response.status_code == 200
    assert response.json()["data"] == {"deleted": [1, 2]}
    mock_delete.assert_called_once_with(
        context.user_groups,
        context.user.roles,
        [1, 2],
        "api-user",
    )
