from types import SimpleNamespace

from rest_framework.test import APIRequestFactory, force_authenticate

from apps.base.models import User
from apps.core.utils.web_utils import WebUtils
from apps.node_mgmt.services.installer import InstallerService
from apps.node_mgmt.views.installer import InstallerViewSet


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


def _task_node(task_node_id, node_id=""):
    return SimpleNamespace(id=task_node_id, node_id=node_id)


def _make_request(data):
    request = APIRequestFactory().post("/node-mgmt/test", data=data, format="json")
    request.COOKIES["current_team"] = "1"
    request.COOKIES["include_children"] = "0"
    user = User(
        username="permission-test-user",
        domain="domain.com",
        locale="en",
        is_superuser=False,
        roles=[],
        group_list=[{"id": 1, "name": "Team"}],
    )
    user.permission = {"node": {"cloud_region_node-Edit"}}
    force_authenticate(request, user=user)
    return request


def test_controller_retry_rejects_task_nodes_outside_authorized_scope(monkeypatch):
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

    response = InstallerViewSet.as_view({"post": "controller_retry"})(
        _make_request({"task_id": 39, "task_node_ids": [101, 102], "password": "replacement"})
    )

    assert response.status_code == 403
    assert retry_called["value"] is False


def test_controller_retry_dispatches_when_all_task_nodes_are_authorized(monkeypatch):
    authorized_nodes = object()
    captured = {}
    monkeypatch.setattr(
        "apps.node_mgmt.views.installer.get_authorized_node_queryset",
        lambda request: authorized_nodes,
    )
    monkeypatch.setattr(
        "apps.node_mgmt.views.installer.authorize_node_ids",
        lambda request, node_ids: ([object() for _ in node_ids], None),
    )

    def fake_authorized_task_nodes(task_id, authorized_nodes=None, request_user=None):
        captured["task_id"] = task_id
        captured["authorized_nodes"] = authorized_nodes
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

    response = InstallerViewSet.as_view({"post": "controller_retry"})(
        _make_request({"task_id": 39, "task_node_ids": [101, 102], "private_key": "replacement-key"})
    )

    assert response.status_code != 403
    assert captured["task_id"] == 39
    assert captured["authorized_nodes"] is authorized_nodes
    assert captured["request_user"].username == "permission-test-user"
    assert captured["delay_args"] == (39, [101, 102])
    assert captured["delay_kwargs"] == {
        "password": None,
        "private_key": "replacement-key",
        "passphrase": None,
    }


def test_controller_retry_requires_operate_permission_for_bound_nodes(monkeypatch):
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
        lambda request, node_ids: (None, WebUtils.response_403("denied")),
    )
    retry_called = {"value": False}
    monkeypatch.setattr(
        "apps.node_mgmt.views.installer.retry_controller.delay",
        lambda *args, **kwargs: retry_called.__setitem__("value", True),
    )

    response = InstallerViewSet.as_view({"post": "controller_retry"})(
        _make_request({"task_id": 39, "task_node_ids": [101], "password": "replacement"})
    )

    assert response.status_code == 403
    assert retry_called["value"] is False
