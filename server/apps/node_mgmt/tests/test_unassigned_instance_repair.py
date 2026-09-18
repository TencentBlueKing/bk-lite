import json
import uuid
from unittest.mock import Mock

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.base.tests.factories import UserFactory
from apps.core.exceptions.base_app_exception import ForbiddenException
from apps.core.utils.current_team_scope import CurrentTeamDataScope
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models import CloudRegion, Node
from apps.node_mgmt.models.sidecar import NodeOrganization
from apps.node_mgmt.utils import permission as node_permission
from apps.node_mgmt.views import node as node_view

pytestmark = pytest.mark.django_db
factory = APIRequestFactory()


def _user(*, is_superuser=True):
    user = UserFactory(username=f"node-unassigned-{uuid.uuid4().hex[:8]}", domain="domain.com", is_superuser=is_superuser)
    user.permission = {"node": {"cloud_region_node-View", "cloud_region_node-Edit", "cloud_region_node-Delete"}}
    user.locale = "en"
    return user


def _auth(request, user):
    force_authenticate(request, user=user)
    request.COOKIES["current_team"] = "1"
    return user


def _region():
    return CloudRegion.objects.create(name=f"unassigned-{uuid.uuid4().hex[:8]}")


def _node(region, name, organization=None):
    node = Node.objects.create(
        id=f"{name}-{uuid.uuid4().hex[:8]}",
        name=name,
        ip="10.0.0.8",
        operating_system=NodeConstants.LINUX_OS,
        collector_configuration_directory="/tmp",
        cloud_region=region,
        status={},
    )
    if organization is not None:
        NodeOrganization.objects.create(node=node, organization=organization)
    return node


def _patch_scope(monkeypatch, *, is_superuser=True):
    monkeypatch.setattr(
        node_permission,
        "resolve_current_team_data_scope",
        lambda request: CurrentTeamDataScope(1, frozenset({1}), False, "tester", "domain.com", is_superuser),
    )
    monkeypatch.setattr(node_permission, "get_node_permission", lambda request: {"team": [1], "instance": []})
    monkeypatch.setattr(node_view, "get_node_permission", lambda request: {"team": [1], "instance": []})
    monkeypatch.setattr(node_view.NodeService, "process_node_data", staticmethod(lambda data: data))


def test_superuser_default_search_hides_unassigned_nodes(monkeypatch):
    region = _region()
    assigned = _node(region, "keep", 1)
    _node(region, "ghost")
    _patch_scope(monkeypatch)
    request = factory.post("/node/search/", {}, format="json")
    _auth(request, _user(is_superuser=True))

    resp = node_view.NodeViewSet.as_view({"post": "search"})(request)
    body = json.loads(resp.content)

    assert [item["id"] for item in body["data"]] == [assigned.id]


def test_superuser_unassigned_search_shows_only_zero_org_nodes(monkeypatch):
    region = _region()
    _node(region, "keep", 1)
    ghost = _node(region, "ghost")
    _patch_scope(monkeypatch)
    request = factory.post("/node/search/?unassigned=true", {}, format="json")
    _auth(request, _user(is_superuser=True))

    resp = node_view.NodeViewSet.as_view({"post": "search"})(request)
    body = json.loads(resp.content)

    assert [item["id"] for item in body["data"]] == [ghost.id]


def test_non_superuser_unassigned_search_is_forbidden(monkeypatch):
    _patch_scope(monkeypatch, is_superuser=False)
    request = factory.post("/node/search/?unassigned=true", {}, format="json")
    _auth(request, _user(is_superuser=False))

    with pytest.raises(ForbiddenException):
        node_view.NodeViewSet.as_view({"post": "search"})(request)


def test_superuser_can_assign_organization_to_unassigned_node(monkeypatch):
    region = _region()
    ghost = _node(region, "ghost")
    _patch_scope(monkeypatch)
    monkeypatch.setattr(
        "apps.core.utils.current_team_scope.SystemMgmt.get_assignable_groups",
        Mock(return_value={"result": True, "data": [1, 7]}),
    )
    request = factory.post(
        "/node/batch_update_organizations/",
        {"node_ids": [ghost.id], "organizations": [7]},
        format="json",
    )
    _auth(request, _user(is_superuser=True))
    monkeypatch.setattr(node_view.sync_nodes_organizations_to_sidecar, "delay", lambda **kwargs: None)

    resp = node_view.NodeViewSet.as_view({"post": "batch_update_organizations"})(request)

    assert resp.status_code == 200
    assert set(NodeOrganization.objects.filter(node=ghost).values_list("organization", flat=True)) == {7}
