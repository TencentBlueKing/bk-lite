import json
from types import SimpleNamespace
from unittest.mock import Mock

from apps.core.utils.web_utils import WebUtils
from apps.node_mgmt.utils import permission as node_permission
from apps.node_mgmt.views import collector_configuration, node as node_view


class FakeOrganizations(list):
    def all(self):
        return self


class FakeNode:
    def __init__(self, node_id="node-1", organizations=None):
        self.id = node_id
        self.name = f"name-{node_id}"
        self.ip = "127.0.0.1"
        self.operating_system = "linux"
        self.install_method = "manual"
        self.nodeorganization_set = FakeOrganizations(
            [SimpleNamespace(organization=org) for org in organizations or [2]]
        )

    def save(self):
        self.saved = True


class FakeNodeQuerySet(list):
    def filter(self, **kwargs):
        if "id__in" in kwargs:
            ids = {str(value) for value in kwargs["id__in"]}
            return FakeNodeQuerySet([node for node in self if str(node.id) in ids])
        if "cloud_region_id" in kwargs:
            return self
        return self

    def prefetch_related(self, *args):
        return self

    def distinct(self):
        return self

    def values_list(self, field, flat=False):
        if field == "id" and flat:
            return [node.id for node in self]
        return []


class FakeConfigQuerySet(list):
    def select_related(self, *args):
        return self

    def prefetch_related(self, *args):
        return self

    def filter(self, **kwargs):
        return self


class FakeConfig:
    id = "cfg-1"
    name = "cfg"
    config_template = "x"
    collector_id = "collector-1"
    cloud_region_id = 1
    is_pre = False
    collector = SimpleNamespace(node_operating_system="linux")

    def __init__(self, nodes):
        self.nodes = FakeOrganizations(nodes)


def make_request(data=None):
    return SimpleNamespace(
        user=SimpleNamespace(username="alice", domain="default"),
        data=data or {},
        COOKIES={"current_team": "1", "include_children": "0"},
    )


def response_data(response):
    return json.loads(response.content.decode())


def test_authorize_node_ids_requires_operate_permission(monkeypatch):
    node = FakeNode()
    monkeypatch.setattr(node_permission.Node.objects, "filter", Mock(return_value=FakeNodeQuerySet([node])))
    monkeypatch.setattr(
        node_permission,
        "get_permission_rules",
        Mock(return_value={"instance": [{"id": node.id, "permission": ["View"]}], "team": []}),
    )

    nodes, response = node_permission.authorize_node_ids(make_request(), [node.id])

    assert nodes is None
    assert response.status_code == 403


def test_authorize_target_organizations_rejects_out_of_scope_org(monkeypatch):
    monkeypatch.setattr(
        node_permission,
        "get_permission_rules",
        Mock(return_value={"team": [2], "instance": []}),
    )

    response = node_permission.authorize_target_organizations(make_request(), [3])

    assert response.status_code == 403


def test_batch_operate_node_collector_requires_node_permission(monkeypatch):
    authorize = Mock(return_value=(None, WebUtils.response_403("denied")))
    service = Mock()
    monkeypatch.setattr(node_view, "authorize_node_ids", authorize)
    monkeypatch.setattr(node_view.NodeService, "batch_operate_node_collector", service)

    response = node_view.NodeViewSet().batch_operate_node_collector(
        make_request({"node_ids": ["node-1"], "collector_id": "collector-1", "operation": "restart"})
    )

    assert response.status_code == 403
    service.assert_not_called()


def test_config_node_asso_hides_unauthorized_nodes(monkeypatch):
    allowed = FakeNode("node-allowed")
    denied = FakeNode("node-denied")
    authorized_nodes = FakeNodeQuerySet([allowed])
    config_qs = FakeConfigQuerySet([FakeConfig([allowed, denied])])

    monkeypatch.setattr(collector_configuration, "get_authorized_node_queryset", Mock(return_value=authorized_nodes))
    monkeypatch.setattr(
        collector_configuration.CollectorConfiguration.objects,
        "select_related",
        Mock(return_value=config_qs),
    )

    response = collector_configuration.CollectorConfigurationViewSet().get_config_node_asso(make_request({}))

    payload = response_data(response)
    assert payload["data"][0]["nodes"] == [
        {
            "id": "node-allowed",
            "name": "name-node-allowed",
            "ip": "127.0.0.1",
            "operating_system": "linux",
        }
    ]
