from types import SimpleNamespace

import pytest

from apps.core.utils import current_team_scope
from apps.core.utils.web_utils import WebUtils
from apps.node_mgmt.services.installer import InstallerService

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

URL = "/api/v1/node_mgmt/api/installer/controller/retry/"


class _ScopedSystemMgmt:
    def get_authorized_groups_scoped(self, actor_context, include_children=False):
        return {"result": True, "data": [1]}


class _FakeTaskNodeQuerySet:
    def __init__(self, task_nodes):
        self.task_nodes = task_nodes

    def filter(self, **kwargs):
        requested_ids = {str(value) for value in kwargs["id__in"]}
        return _FakeTaskNodeQuerySet(
            [task_node for task_node in self.task_nodes if str(task_node.id) in requested_ids]
        )

    def __iter__(self):
        return iter(self.task_nodes)


def _task_node(task_node_id, node_id="", result=None):
    return SimpleNamespace(id=task_node_id, node_id=node_id, result=result or {})


def _prepare_client(api_client, authenticated_user, monkeypatch):
    authenticated_user.is_superuser = False
    authenticated_user.permission = {"node": {"cloud_region_node-Edit"}}
    authenticated_user.group_list = [{"id": 1, "name": "Team"}]
    api_client.cookies["current_team"] = "1"
    api_client.cookies["include_children"] = "0"
    monkeypatch.setattr(current_team_scope, "SystemMgmt", _ScopedSystemMgmt)


def test_controller_retry_rejects_task_nodes_outside_authorized_scope(
    api_client,
    authenticated_user,
    monkeypatch,
):
    _prepare_client(api_client, authenticated_user, monkeypatch)
    authorized_nodes = object()
    monkeypatch.setattr(
        "apps.node_mgmt.views.installer.get_authorized_node_queryset",
        lambda request: authorized_nodes,
    )
    monkeypatch.setattr(
        InstallerService,
        "get_authorized_controller_task_node_queryset",
        lambda *args, **kwargs: _FakeTaskNodeQuerySet([_task_node(101, "node-101")]),
    )
    retry_called = {"value": False}
    monkeypatch.setattr(
        "apps.node_mgmt.views.installer.retry_controller.delay",
        lambda *args, **kwargs: retry_called.__setitem__("value", True),
    )

    response = api_client.post(
        URL,
        {"task_id": 39, "task_node_ids": [101, 102], "password": "replacement"},
        format="json",
    )

    assert response.status_code == 403
    assert retry_called["value"] is False


def test_controller_retry_rejects_invalid_port_before_dispatch(
    api_client,
    authenticated_user,
    monkeypatch,
):
    _prepare_client(api_client, authenticated_user, monkeypatch)
    retry_called = {"value": False}
    monkeypatch.setattr(
        "apps.node_mgmt.views.installer.retry_controller.delay",
        lambda *args, **kwargs: retry_called.__setitem__("value", True),
    )

    response = api_client.post(
        URL,
        {"task_id": 39, "task_node_ids": [101], "port": 70000, "password": "replacement"},
        format="json",
    )

    assert response.status_code == 400
    assert retry_called["value"] is False


def test_controller_retry_dispatches_when_all_task_nodes_are_authorized(
    api_client,
    authenticated_user,
    monkeypatch,
):
    _prepare_client(api_client, authenticated_user, monkeypatch)
    authorized_nodes = object()
    captured = {}
    monkeypatch.setattr(
        "apps.node_mgmt.views.installer.get_authorized_node_queryset",
        lambda request: authorized_nodes,
    )
    monkeypatch.setattr(
        "apps.node_mgmt.views.installer.authorize_node_ids",
        lambda request, node_ids, required_permission: (
            captured.update({"required_permission": required_permission}) or [object() for _ in node_ids],
            None,
        ),
    )

    def fake_authorized_task_nodes(task_id, authorized_nodes=None, scope=None, request_user=None):
        captured["task_id"] = task_id
        captured["authorized_nodes"] = authorized_nodes
        captured["scope"] = scope
        captured["request_user"] = request_user
        return _FakeTaskNodeQuerySet([_task_node(101, "node-101"), _task_node(102, "node-102")])

    monkeypatch.setattr(
        InstallerService,
        "get_authorized_controller_task_node_queryset",
        fake_authorized_task_nodes,
    )
    monkeypatch.setattr(
        "apps.node_mgmt.views.installer.retry_controller.delay",
        lambda *args, **kwargs: captured.update({"delay_args": args, "delay_kwargs": kwargs}),
    )

    response = api_client.post(
        URL,
        {
            "task_id": 39,
            "task_node_ids": [101, 102],
            "port": 2222,
            "username": "replacement-user",
            "private_key": "replacement-key",
        },
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["result"] is True
    assert captured["task_id"] == 39
    assert captured["authorized_nodes"] is authorized_nodes
    assert captured["scope"].data_team_ids == frozenset({1})
    assert captured["request_user"].username == authenticated_user.username
    assert captured["required_permission"] == "Operate"
    assert captured["delay_args"] == (39, [101, 102])
    assert captured["delay_kwargs"] == {
        "password": None,
        "port": 2222,
        "username": "replacement-user",
        "private_key": "replacement-key",
        "passphrase": None,
    }


def test_controller_retry_rejects_manual_recovery_after_authorization(
    api_client,
    authenticated_user,
    monkeypatch,
):
    _prepare_client(api_client, authenticated_user, monkeypatch)
    monkeypatch.setattr(
        "apps.node_mgmt.views.installer.get_authorized_node_queryset",
        lambda request: object(),
    )
    monkeypatch.setattr(
        InstallerService,
        "get_authorized_controller_task_node_queryset",
        lambda *args, **kwargs: _FakeTaskNodeQuerySet(
            [_task_node(101, result={"failure": {"type": "manual_recovery_required"}})]
        ),
    )
    retry_called = {"value": False}
    monkeypatch.setattr(
        "apps.node_mgmt.views.installer.retry_controller.delay",
        lambda *args, **kwargs: retry_called.__setitem__("value", True),
    )

    response = api_client.post(
        URL,
        {"task_id": 39, "task_node_ids": [101], "password": "replacement"},
        format="json",
    )

    assert response.status_code == 400
    assert response.json()["message"] == "Manual recovery is required before this node can be retried"
    assert retry_called["value"] is False


def test_controller_retry_requires_operate_permission_for_bound_nodes(
    api_client,
    authenticated_user,
    monkeypatch,
):
    _prepare_client(api_client, authenticated_user, monkeypatch)
    monkeypatch.setattr(
        "apps.node_mgmt.views.installer.get_authorized_node_queryset",
        lambda request: object(),
    )
    monkeypatch.setattr(
        InstallerService,
        "get_authorized_controller_task_node_queryset",
        lambda *args, **kwargs: _FakeTaskNodeQuerySet([_task_node(101, "node-101")]),
    )
    monkeypatch.setattr(
        "apps.node_mgmt.views.installer.authorize_node_ids",
        lambda request, node_ids, required_permission: (None, WebUtils.response_403("denied")),
    )
    retry_called = {"value": False}
    monkeypatch.setattr(
        "apps.node_mgmt.views.installer.retry_controller.delay",
        lambda *args, **kwargs: retry_called.__setitem__("value", True),
    )

    response = api_client.post(
        URL,
        {"task_id": 39, "task_node_ids": [101], "password": "replacement"},
        format="json",
    )

    assert response.status_code == 403
    assert retry_called["value"] is False


def test_controller_task_node_query_uses_same_actor_scope(
    api_client,
    authenticated_user,
    monkeypatch,
):
    _prepare_client(api_client, authenticated_user, monkeypatch)
    captured = {}
    monkeypatch.setattr(
        "apps.node_mgmt.views.installer.get_authorized_node_queryset",
        lambda request: "authorized-nodes",
    )

    def fake_install_controller_nodes(task_id, authorized_nodes=None, scope=None):
        captured.update(
            {
                "task_id": task_id,
                "authorized_nodes": authorized_nodes,
                "scope": scope,
            }
        )
        return []

    monkeypatch.setattr(InstallerService, "install_controller_nodes", fake_install_controller_nodes)

    response = api_client.post(
        "/api/v1/node_mgmt/api/installer/controller/task/39/nodes/",
        {},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["result"] is True
    assert captured["task_id"] == "39"
    assert captured["authorized_nodes"] == "authorized-nodes"
    assert captured["scope"].data_team_ids == frozenset({1})
    assert captured["scope"].username == authenticated_user.username
