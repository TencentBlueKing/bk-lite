from types import SimpleNamespace
from unittest.mock import call, patch

import pytest
from django.urls import path

from apps.cmdb.constants.constants import PERMISSION_INSTANCES
from apps.cmdb.open_api import views as open_views
from apps.core.exceptions.base_app_exception import BaseAppException

pytestmark = pytest.mark.django_db

SRC_UUID = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
DST_UUID = "7de0c6de-f841-44b1-846d-2d75a7c59c50"
KEPT_UUID = "11111111-2222-4333-8444-555555555555"
SECRET_UUID = "22222222-3333-4444-8555-666666666666"
HIDDEN_UUID = "33333333-4444-4555-8666-777777777777"
FOREIGN_UUID = "44444444-5555-4666-8777-888888888888"
CREATOR_UUID = "55555555-6666-4777-8888-999999999999"
GROUP_UUID = "66666666-7777-4888-8999-aaaaaaaaaaaa"

urlpatterns = [
    path(
        "api/v1/cmdb/api/open/models/<str:model_id>/instances/<str:inst_uuid>",
        open_views.OpenInstanceDetailView.as_view(),
    ),
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


def _peer(inst_id, inst_uuid, model_id, inst_name, creator, team_id=7, **extra):
    instance = _instance(inst_id, inst_uuid, model_id, team_id=team_id)
    instance["inst_name"] = inst_name
    instance["_creator"] = creator
    instance.update(extra)
    return instance


def _named_view(*names):
    return {
        7: {
            "permission_instances_map": {name: ["View"] for name in names},
            "inst_names": list(names),
        }
    }


def _org_view():
    return {7: {"permission_instances_map": {}, "inst_names": []}}


def _bind_permissions(context, maps):
    def permission_map(model_id, permission_type):
        return maps[model_id]

    context.permission_map.side_effect = permission_map
    return context


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


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.InstanceManage.instance_association_instance_list_by_uuid")
@patch("apps.cmdb.open_api.services.InstanceManage.query_entity_by_uuid")
def test_list_associations_omits_peer_excluded_by_instance_view(
    mock_query, mock_list, mock_context, api_client, api_secret_allowed
):
    context = _context(mock_context)
    _bind_permissions(context, {"host": _named_view("host-1"), "app": _named_view("app-kept")})
    source = _peer(1, SRC_UUID, "host", "host-1", "other-user")
    secret = _peer(
        2,
        SECRET_UUID,
        "app",
        "app-secret",
        "other-user",
        secret_attr="peer-secret-6691",
    )
    mock_query.side_effect = lambda inst_uuid: {SRC_UUID: source, SECRET_UUID: secret}[inst_uuid]
    mock_list.return_value = [{"model_asst_id": "host_run_app", "inst_list": [secret]}]

    response = api_client.get(
        f"/api/v1/cmdb/api/open/models/host/instances/{SRC_UUID}/associations",
        HTTP_API_AUTHORIZATION="secret",
    )

    assert response.status_code == 200
    assert response.json()["data"] == []
    body = response.content.decode()
    assert SECRET_UUID not in body
    assert "app-secret" not in body
    assert "peer-secret-6691" not in body
    assert [item.args[0] for item in mock_query.call_args_list] == [SRC_UUID]

    detail = api_client.get(
        f"/api/v1/cmdb/api/open/models/app/instances/{SECRET_UUID}",
        HTTP_API_AUTHORIZATION="secret",
    )

    assert detail.status_code == 403
    assert detail.json()["message"] == "权限不足"
    assert detail.json()["code"] == "cmdb.permission.denied"
    assert [item.args[0] for item in mock_query.call_args_list] == [SRC_UUID, SECRET_UUID]


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.InstanceManage.instance_association_instance_list_by_uuid")
@patch("apps.cmdb.open_api.services.InstanceManage.query_entity_by_uuid")
def test_list_associations_keeps_creator_and_org_wide_view(
    mock_query, mock_list, mock_context, api_client, api_secret_allowed
):
    context = _context(mock_context)
    _bind_permissions(
        context,
        {
            "host": _named_view("host-1"),
            "app": _named_view("someone-else"),
            "db": _org_view(),
        },
    )
    source = _peer(1, SRC_UUID, "host", "host-1", "other-user")
    created = _peer(2, CREATOR_UUID, "app", "created-app", "api-user", secret_attr="creator-attr")
    grouped = _peer(3, GROUP_UUID, "db", "grouped-db", "other-user", secret_attr="group-attr")
    mock_query.return_value = source
    mock_list.return_value = [
        {"model_asst_id": "host_run_app", "inst_list": [created]},
        {"model_asst_id": "host_run_db", "inst_list": [grouped]},
    ]

    response = api_client.get(
        f"/api/v1/cmdb/api/open/models/host/instances/{SRC_UUID}/associations",
        HTTP_API_AUTHORIZATION="secret",
    )

    assert response.status_code == 200
    groups = {item["model_asst_id"]: item["inst_list"] for item in response.json()["data"]}
    assert groups["host_run_app"][0]["inst_uuid"] == CREATOR_UUID
    assert groups["host_run_app"][0]["inst_name"] == "created-app"
    assert groups["host_run_app"][0]["secret_attr"] == "creator-attr"
    assert "_id" not in groups["host_run_app"][0]
    assert groups["host_run_db"][0]["inst_uuid"] == GROUP_UUID
    assert groups["host_run_db"][0]["inst_name"] == "grouped-db"
    assert groups["host_run_db"][0]["secret_attr"] == "group-attr"


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.InstanceManage.instance_association_instance_list_by_uuid")
@patch("apps.cmdb.open_api.services.InstanceManage.query_entity_by_uuid")
def test_list_associations_checks_same_model_permission_once(
    mock_query, mock_list, mock_context, api_client, api_secret_allowed
):
    context = _context(mock_context)
    _bind_permissions(context, {"host": _named_view("host-1"), "app": _named_view("app-kept")})
    source = _peer(1, SRC_UUID, "host", "host-1", "other-user")
    kept = _peer(2, KEPT_UUID, "app", "app-kept", "other-user", secret_attr="kept-attr")
    secret = _peer(3, SECRET_UUID, "app", "app-secret", "other-user", secret_attr="peer-secret-6691")
    mock_query.return_value = source
    mock_list.return_value = [{"model_asst_id": "host_run_app", "inst_list": [kept, secret]}]

    response = api_client.get(
        f"/api/v1/cmdb/api/open/models/host/instances/{SRC_UUID}/associations",
        HTTP_API_AUTHORIZATION="secret",
    )

    assert response.status_code == 200
    body = response.content.decode()
    assert SECRET_UUID not in body
    assert "app-secret" not in body
    assert "peer-secret-6691" not in body
    groups = response.json()["data"]
    assert [item["model_asst_id"] for item in groups] == ["host_run_app"]
    assert groups[0]["inst_list"] == [
        {
            "inst_uuid": KEPT_UUID,
            "model_id": "app",
            "inst_name": "app-kept",
            "organization": [7],
            "creator": "other-user",
            "secret_attr": "kept-attr",
        }
    ]
    assert [item.args[0] for item in mock_query.call_args_list] == [SRC_UUID]
    assert context.permission_map.call_args_list == [
        call("host", PERMISSION_INSTANCES),
        call("app", PERMISSION_INSTANCES),
    ]


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.InstanceManage.instance_association_instance_list_by_uuid")
@patch("apps.cmdb.open_api.services.InstanceManage.query_entity_by_uuid")
def test_list_associations_omits_hidden_and_other_org_peers(
    mock_query, mock_list, mock_context, api_client, api_secret_allowed, monkeypatch
):
    context = _context(mock_context)
    _bind_permissions(
        context,
        {
            "host": _named_view("host-1"),
            "app": {
                7: {"permission_instances_map": {"app-kept": ["View"]}, "inst_names": ["app-kept"]},
                8: {"permission_instances_map": {}, "inst_names": []},
            },
            "secret_model": _org_view(),
        },
    )

    def search_model_info(model_id):
        return {"model_id": model_id, "group": [7], "is_visible": model_id != "secret_model"}

    monkeypatch.setattr("apps.cmdb.open_api.services.ModelManage.search_model_info", search_model_info)
    source = _peer(1, SRC_UUID, "host", "host-1", "other-user")
    hidden = _peer(2, HIDDEN_UUID, "secret_model", "hidden-app", "api-user", secret_attr="hidden-secret")
    foreign = _peer(3, FOREIGN_UUID, "app", "foreign-app", "other-user", team_id=8, secret_attr="foreign-secret")
    kept = _peer(4, KEPT_UUID, "app", "app-kept", "other-user")
    mock_query.return_value = source
    mock_list.return_value = [
        {"model_asst_id": "host_hidden", "inst_list": [hidden]},
        {"model_asst_id": "host_foreign", "inst_list": [foreign]},
        {"model_asst_id": "host_mixed", "inst_list": [foreign, kept]},
    ]

    response = api_client.get(
        f"/api/v1/cmdb/api/open/models/host/instances/{SRC_UUID}/associations",
        HTTP_API_AUTHORIZATION="secret",
    )

    assert response.status_code == 200
    body = response.content.decode()
    assert HIDDEN_UUID not in body
    assert "hidden-secret" not in body
    assert FOREIGN_UUID not in body
    assert "foreign-secret" not in body
    assert "host_hidden" not in body
    assert "host_foreign" not in body
    groups = response.json()["data"]
    assert [item["model_asst_id"] for item in groups] == ["host_mixed"]
    assert [item["inst_uuid"] for item in groups[0]["inst_list"]] == [KEPT_UUID]


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.InstanceManage.instance_association_instance_list_by_uuid")
@patch("apps.cmdb.open_api.services.InstanceManage.query_entity_by_uuid")
def test_list_associations_rejects_unreadable_source(
    mock_query, mock_list, mock_context, api_client, api_secret_allowed
):
    context = _context(mock_context)
    _bind_permissions(context, {"host": _named_view("someone-else")})
    mock_query.return_value = _peer(1, SRC_UUID, "host", "host-1", "other-user")

    response = api_client.get(
        f"/api/v1/cmdb/api/open/models/host/instances/{SRC_UUID}/associations",
        HTTP_API_AUTHORIZATION="secret",
    )

    assert response.status_code == 403
    assert response.json()["message"] == "权限不足"
    mock_list.assert_not_called()
