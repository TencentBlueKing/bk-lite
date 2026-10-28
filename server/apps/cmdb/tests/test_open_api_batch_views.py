from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.urls import path

from apps.cmdb.constants.constants import CLASSIFICATION, OPERATE, PERMISSION_INSTANCES
from apps.cmdb.open_api import views as open_views
from apps.cmdb.open_api.services import CMDBOpenAPIService
from apps.cmdb.services import instance as instance_service
from apps.cmdb.utils.permission_util import CmdbRulesFormatUtil

pytestmark = pytest.mark.django_db
UUID_1 = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
UUID_2 = "7de0c6de-f841-44b1-846d-2d75a7c59c50"

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
    context.user_groups = [{"id": 7}]
    context.permission_map.return_value = {7: {"permission_instances_map": {}, "inst_names": []}}
    return context


def _model_and_attrs(mock_model, mock_attrs):
    mock_model.return_value = {"model_id": "host", "group": [7]}
    mock_attrs.return_value = [
        {"attr_id": "inst_name", "attr_type": "str", "editable": True},
        {"attr_id": "status", "attr_type": "str", "editable": True},
    ]


def _batch_uuids(size):
    return [f"00000000-0000-4000-8000-{index:012d}" for index in range(1, size + 1)]


def _batch_instances(inst_uuids, *, organization=7, creator="other-user"):
    return [
        {
            "_id": index,
            "inst_uuid": inst_uuid,
            "model_id": "host",
            "inst_name": f"h{index}",
            "organization": [organization],
            "_creator": creator,
        }
        for index, inst_uuid in enumerate(inst_uuids, start=1)
    ]


def _install_precheck_counters(monkeypatch, instances, *, classification_id=None, permission_map=None):
    state = {
        "model": 0,
        "classification": 0,
        "single": 0,
        "batch": 0,
        "batch_calls": [],
        "permissions": [],
        "domain_calls": 0,
        "frozen": False,
    }
    slot = getattr(monkeypatch, "_precheck_slot", None)
    if slot is None:
        slot = {}
        monkeypatch._precheck_slot = slot
        original_permission = CmdbRulesFormatUtil.has_object_permission
        original_get_model_attrs = CMDBOpenAPIService.get_model_attrs

        def search_model_info(model_id):
            current = slot["state"]
            if not current["frozen"]:
                current["model"] += 1
            model = {"model_id": model_id, "group": [7], "is_visible": True}
            if slot["classification_id"]:
                model["classification_id"] = slot["classification_id"]
            return model

        def query_entity_by_uuid(inst_uuid):
            current = slot["state"]
            if not current["frozen"]:
                current["single"] += 1
            return slot["by_uuid"].get(str(inst_uuid), {})

        def query_entity_by_uuids(inst_uuids, **kwargs):
            del kwargs
            current = slot["state"]
            if not current["frozen"]:
                current["batch"] += 1
                current["batch_calls"].append([str(item) for item in inst_uuids])
            return [slot["by_uuid"][str(item)] for item in inst_uuids if str(item) in slot["by_uuid"]]

        class _Graph:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def query_entity(self, label, params, **kwargs):
                del params, kwargs
                current = slot["state"]
                if not current["frozen"] and label == CLASSIFICATION:
                    current["classification"] += 1
                return [], 0

        def has_object_permission(*args, **kwargs):
            current = slot["state"]
            if (
                not current["frozen"]
                and kwargs.get("obj_type") == PERMISSION_INSTANCES
                and kwargs.get("operator") == OPERATE
            ):
                instance = kwargs.get("instance") or {}
                current["permissions"].append(str(instance.get("inst_uuid")))
            return original_permission(*args, **kwargs)

        def finish_domain(*args, **kwargs):
            del args, kwargs
            current = slot["state"]
            current["frozen"] = True
            current["domain_calls"] += 1
            return slot["instances"]

        def get_model_attrs(self, model_id):
            slot["state"]["frozen"] = True
            return original_get_model_attrs(self, model_id)

        def from_request(request):
            del request
            context = MagicMock()
            context.team_id = 7
            context.user = SimpleNamespace(locale="zh-CN", username="api-user", roles=[])
            context.user_groups = [{"id": 7}]
            context.permission_map.return_value = slot["permission_map"] or {
                7: {"permission_instances_map": {}, "inst_names": []},
            }
            return context

        monkeypatch.setattr("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request", from_request)
        monkeypatch.setattr("apps.cmdb.open_api.services.ModelManage.search_model_info", search_model_info)
        monkeypatch.setattr(
            "apps.cmdb.open_api.services.ModelManage.search_model_attr",
            lambda model_id: [
                {"attr_id": "inst_name", "attr_type": "str", "editable": True},
                {"attr_id": "status", "attr_type": "str", "editable": True},
            ],
        )
        monkeypatch.setattr("apps.cmdb.open_api.services.InstanceManage.query_entity_by_uuid", query_entity_by_uuid)
        monkeypatch.setattr("apps.cmdb.open_api.services.InstanceManage.query_entity_by_uuids", query_entity_by_uuids)
        monkeypatch.setattr("apps.cmdb.open_api.services.CmdbRulesFormatUtil.has_object_permission", has_object_permission)
        monkeypatch.setattr("apps.cmdb.services.model_visibility.GraphClient", lambda: _Graph())
        monkeypatch.setattr(CMDBOpenAPIService, "get_model_attrs", get_model_attrs)
        monkeypatch.setattr("apps.cmdb.open_api.services.InstanceManage.batch_instance_update_by_uuids", finish_domain)
        monkeypatch.setattr("apps.cmdb.open_api.services.InstanceManage.instance_batch_delete_by_uuids", finish_domain)

    slot["state"] = state
    slot["by_uuid"] = {item["inst_uuid"]: item for item in instances}
    slot["classification_id"] = classification_id
    slot["instances"] = instances
    slot["permission_map"] = permission_map
    return state


def _post_batch(api_client, action, inst_uuids):
    if action == "update":
        return api_client.post(
            "/api/v1/cmdb/api/open/models/host/instances/batch_update",
            {"inst_uuids": inst_uuids, "update_data": {"status": "active"}},
            format="json",
            HTTP_API_AUTHORIZATION="secret",
        )
    return api_client.post(
        "/api/v1/cmdb/api/open/models/host/instances/batch_delete",
        {"inst_uuids": inst_uuids},
        format="json",
        HTTP_API_AUTHORIZATION="secret",
    )


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
        {"_id": 1, "inst_uuid": UUID_1, "model_id": "host", "inst_name": "h1", "organization": [7]},
        {"_id": 2, "inst_uuid": UUID_2, "model_id": "host", "inst_name": "h2", "organization": [7]},
    ]

    response = api_client.post(
        "/api/v1/cmdb/api/open/models/host/instances/batch_create",
        {"items": [{"inst_name": "h1"}, {"inst_name": "h2"}]},
        format="json",
        HTTP_API_AUTHORIZATION="secret",
    )

    assert response.status_code == 201
    assert [item["inst_uuid"] for item in response.json()["data"]["created"]] == [UUID_1, UUID_2]
    assert all("_id" not in item for item in response.json()["data"]["created"])
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


def _precheck_reads(state):
    return state["model"] + state["classification"] + state["single"] + state["batch"]


def test_batch_precheck_reads_model_once_and_instances_once(monkeypatch, api_client, api_secret_allowed):
    observed = []
    expected = []
    for action in ("update", "delete"):
        for classification_id in (None, "biz"):
            for size in (1, 10, 100):
                inst_uuids = _batch_uuids(size)
                state = _install_precheck_counters(
                    monkeypatch,
                    _batch_instances(inst_uuids),
                    classification_id=classification_id,
                )
                response = _post_batch(api_client, action, inst_uuids)
                observed.append(
                    (
                        action,
                        classification_id or "",
                        size,
                        response.status_code,
                        _precheck_reads(state),
                        state["single"],
                        state["batch"],
                        len(state["permissions"]),
                        state["domain_calls"],
                    )
                )
                expected.append(
                    (
                        action,
                        classification_id or "",
                        size,
                        200,
                        3 if classification_id else 2,
                        0,
                        1,
                        size,
                        1,
                    )
                )

    assert observed == expected, (
        "columns: action, classification, size, status, reads, single, batch, permissions, domain; "
        f"observed={observed}"
    )


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.InstanceManage.batch_instance_update_by_uuids")
@patch("apps.cmdb.open_api.services.InstanceManage.query_entity_by_uuids")
def test_batch_update_rejects_cross_team_member_before_write(
    mock_query,
    mock_update,
    mock_context,
    api_client,
    api_secret_allowed,
):
    _context(mock_context)
    mock_query.return_value = [
        {"_id": 1, "inst_uuid": UUID_1, "model_id": "host", "inst_name": "h1", "organization": [7], "_creator": "api-user"},
        {"_id": 2, "inst_uuid": UUID_2, "model_id": "host", "inst_name": "h2", "organization": [8], "_creator": "api-user"},
    ]

    response = api_client.post(
        "/api/v1/cmdb/api/open/models/host/instances/batch_update",
        {"inst_uuids": [UUID_1, UUID_2], "update_data": {"status": "active"}},
        format="json",
        HTTP_API_AUTHORIZATION="secret",
    )

    assert response.status_code == 404
    assert response.json()["data"] == {"inst_uuid": UUID_2}
    mock_query.assert_called_once_with([UUID_1, UUID_2])
    mock_update.assert_not_called()


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.CmdbRulesFormatUtil.has_object_permission", return_value=True)
@patch("apps.cmdb.open_api.services.InstanceManage.batch_instance_update_by_uuids")
@patch("apps.cmdb.open_api.services.InstanceManage.query_entity_by_uuids")
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
    mock_query.return_value = [
        {"_id": 1, "inst_uuid": UUID_1, "model_id": "host", "inst_name": "h1", "organization": [7], "_creator": "api-user"},
        {"_id": 2, "inst_uuid": UUID_2, "model_id": "host", "inst_name": "h2", "organization": [7], "_creator": "api-user"},
    ]
    mock_update.return_value = [
        {"_id": 1, "inst_uuid": UUID_1, "model_id": "host", "inst_name": "h1", "status": "active"},
        {"_id": 2, "inst_uuid": UUID_2, "model_id": "host", "inst_name": "h2", "status": "active"},
    ]

    response = api_client.post(
        "/api/v1/cmdb/api/open/models/host/instances/batch_update",
        {"inst_uuids": [UUID_1, UUID_2], "update_data": {"status": "active"}},
        format="json",
        HTTP_API_AUTHORIZATION="secret",
    )

    assert response.status_code == 200
    assert [item["inst_uuid"] for item in response.json()["data"]["updated"]] == [UUID_1, UUID_2]
    mock_query.assert_called_once_with([UUID_1, UUID_2])
    mock_update.assert_called_once_with(
        context.user_groups,
        context.user.roles,
        [UUID_1, UUID_2],
        {"status": "active"},
        "api-user",
        [7],
    )


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.CmdbRulesFormatUtil.has_object_permission", return_value=True)
@patch("apps.cmdb.open_api.services.InstanceManage.batch_instance_update_by_uuids")
@patch("apps.cmdb.open_api.services.InstanceManage.query_entity_by_uuids")
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
    mock_query.return_value = [
        {"_id": 1, "inst_uuid": UUID_1, "model_id": "host", "inst_name": "h1", "organization": [7]},
        {"_id": 2, "inst_uuid": UUID_2, "model_id": "host", "inst_name": "h2", "organization": [7]},
    ]
    mock_update.side_effect = instance_service.InstanceBatchError(
        "字段值违反唯一性约束",
        reason="unique_conflict",
        inst_uuid=UUID_2,
        field="status",
    )

    response = api_client.post(
        "/api/v1/cmdb/api/open/models/host/instances/batch_update",
        {"inst_uuids": [UUID_1, UUID_2], "update_data": {"status": "active"}},
        format="json",
        HTTP_API_AUTHORIZATION="secret",
    )

    assert response.status_code == 409
    assert response.json()["code"] == "cmdb.instance.unique_conflict"
    assert response.json()["data"] == {"inst_uuid": UUID_2, "field": "status"}
    mock_query.assert_called_once_with([UUID_1, UUID_2])


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.InstanceManage.instance_batch_delete_by_uuids")
@patch("apps.cmdb.open_api.services.InstanceManage.query_entity_by_uuids")
def test_batch_delete_does_not_report_success_when_domain_requery_is_incomplete(
    mock_query,
    mock_delete,
    mock_context,
    api_client,
    api_secret_allowed,
):
    _context(mock_context)
    mock_query.return_value = [
        {"_id": 1, "inst_uuid": UUID_1, "model_id": "host", "inst_name": "h1", "organization": [7]},
        {"_id": 2, "inst_uuid": UUID_2, "model_id": "host", "inst_name": "h2", "organization": [7]},
    ]
    mock_delete.side_effect = instance_service.InstanceBatchError(
        "实例不存在",
        reason="not_found",
        inst_uuid=UUID_2,
    )

    response = api_client.post(
        "/api/v1/cmdb/api/open/models/host/instances/batch_delete",
        {"inst_uuids": [UUID_1, UUID_2]},
        format="json",
        HTTP_API_AUTHORIZATION="secret",
    )

    assert response.status_code == 404
    assert response.json()["code"] == "cmdb.instance.not_found"
    assert response.json()["data"] == {"inst_uuid": UUID_2}
    mock_query.assert_called_once_with([UUID_1, UUID_2])


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.InstanceManage.instance_batch_delete_by_uuids")
@patch("apps.cmdb.open_api.services.InstanceManage.query_entity_by_uuids")
def test_batch_delete_rejects_cross_team_member_before_write(
    mock_query,
    mock_delete,
    mock_context,
    api_client,
    api_secret_allowed,
):
    _context(mock_context)
    mock_query.return_value = [
        {"_id": 1, "inst_uuid": UUID_1, "model_id": "host", "inst_name": "h1", "organization": [7], "_creator": "api-user"},
        {"_id": 2, "inst_uuid": UUID_2, "model_id": "host", "inst_name": "h2", "organization": [8], "_creator": "api-user"},
    ]

    response = api_client.post(
        "/api/v1/cmdb/api/open/models/host/instances/batch_delete",
        {"inst_uuids": [UUID_1, UUID_2]},
        format="json",
        HTTP_API_AUTHORIZATION="secret",
    )

    assert response.status_code == 404
    assert response.json()["data"] == {"inst_uuid": UUID_2}
    mock_query.assert_called_once_with([UUID_1, UUID_2])
    mock_delete.assert_not_called()


@patch("apps.cmdb.open_api.views.CMDBOpenAPIContext.from_request")
@patch("apps.cmdb.open_api.services.InstanceManage.instance_batch_delete_by_uuids")
@patch("apps.cmdb.open_api.services.InstanceManage.query_entity_by_uuids")
def test_batch_delete_calls_domain_once_after_all_members_are_authorized(
    mock_query,
    mock_delete,
    mock_context,
    api_client,
    api_secret_allowed,
):
    context = _context(mock_context)
    mock_query.return_value = [
        {"_id": 1, "inst_uuid": UUID_1, "model_id": "host", "inst_name": "h1", "organization": [7], "_creator": "api-user"},
        {"_id": 2, "inst_uuid": UUID_2, "model_id": "host", "inst_name": "h2", "organization": [7], "_creator": "api-user"},
    ]

    response = api_client.post(
        "/api/v1/cmdb/api/open/models/host/instances/batch_delete",
        {"inst_uuids": [UUID_1, UUID_2]},
        format="json",
        HTTP_API_AUTHORIZATION="secret",
    )

    assert response.status_code == 200
    assert response.json()["data"] == {"deleted": [UUID_1, UUID_2]}
    mock_query.assert_called_once_with([UUID_1, UUID_2])
    mock_delete.assert_called_once_with(
        context.user_groups,
        context.user.roles,
        [UUID_1, UUID_2],
        "api-user",
    )


@pytest.mark.parametrize("action", ["update", "delete"])
def test_batch_precheck_dedupes_uuids_before_one_instance_read(
    action,
    monkeypatch,
    api_client,
    api_secret_allowed,
):
    unique = [UUID_1, UUID_2]
    state = _install_precheck_counters(monkeypatch, _batch_instances(unique))

    response = _post_batch(api_client, action, [UUID_1, UUID_1, UUID_2])

    assert response.status_code == 200
    assert state["batch_calls"] == [unique]
    assert all(len(call) == len(set(call)) for call in state["batch_calls"])
    assert state["permissions"] == unique
    assert state["domain_calls"] == 1


@pytest.mark.parametrize("action", ["update", "delete"])
def test_batch_precheck_denies_second_uuid_without_operate_permission(
    action,
    monkeypatch,
    api_client,
    api_secret_allowed,
):
    inst_uuids = [UUID_1, UUID_2]
    state = _install_precheck_counters(
        monkeypatch,
        _batch_instances(inst_uuids),
        permission_map={
            7: {
                "permission_instances_map": {"h1": [OPERATE]},
                "inst_names": ["h1"],
            }
        },
    )

    response = _post_batch(api_client, action, inst_uuids)

    assert response.status_code == 403
    assert response.json()["message"] == "权限不足"
    assert response.json()["data"] == {"inst_uuid": UUID_2}
    assert state["single"] == 0
    assert state["batch_calls"] == [inst_uuids]
    assert state["permissions"] == inst_uuids
    assert state["domain_calls"] == 0


def test_single_instance_read_stays_per_uuid(monkeypatch):
    state = _install_precheck_counters(monkeypatch, _batch_instances([UUID_1], creator="api-user"))
    context = MagicMock()
    context.team_id = 7
    context.user = SimpleNamespace(username="api-user", roles=[], locale="zh-CN")
    context.permission_map.return_value = {7: {"permission_instances_map": {}, "inst_names": []}}
    service = CMDBOpenAPIService(context)

    instance = service._get_instance("host", UUID_1, OPERATE)

    assert instance["inst_uuid"] == UUID_1
    assert state["model"] == 1
    assert state["single"] == 1
    assert state["batch"] == 0
