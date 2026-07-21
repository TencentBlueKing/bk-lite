from types import SimpleNamespace

import pytest

from apps.operation_analysis.models.datasource_models import DataSourceAPIModel, NameSpace
from apps.operation_analysis.models.models import Architecture, Dashboard, Directory, NetworkTopology, Report, Screen, Topology
from apps.operation_analysis.services.import_export.precheck_service import PrecheckService


@pytest.mark.django_db
def test_identify_conflicts_batches_database_queries_by_object_type(django_assert_num_queries):
    directory = Directory.objects.create(name="issue-3399-directory", groups=[1])

    namespaces = []
    datasources = []
    dashboards = []
    topologies = []
    architectures = []
    screens = []
    reports = []
    network_topologies = []

    for index in range(2):
        namespace_name = f"issue-3399-namespace-{index}"
        NameSpace.objects.create(
            name=namespace_name,
            account="admin",
            password="secret",
            domain="127.0.0.1:4222",
        )
        namespaces.append(SimpleNamespace(key=f"namespace::{index}", name=namespace_name))

        datasource_name = f"issue-3399-datasource-{index}"
        rest_api = f"monitor/query/{index}"
        DataSourceAPIModel.objects.create(name=datasource_name, rest_api=rest_api, groups=[1])
        datasources.append(
            SimpleNamespace(key=f"datasource::{index}", name=datasource_name, rest_api=rest_api)
        )

        canvas_models = (
            (Dashboard, dashboards, "dashboard", {"view_sets": []}),
            (Topology, topologies, "topology", {"view_sets": []}),
            (Architecture, architectures, "architecture", {"view_sets": []}),
            (Screen, screens, "screen", {"view_sets": {}}),
            (Report, reports, "report", {"view_sets": {}}),
        )
        for model, items, object_type, defaults in canvas_models:
            name = f"issue-3399-{object_type}-{index}"
            model.objects.create(name=name, groups=[1], **defaults)
            items.append(SimpleNamespace(key=f"{object_type}::{index}", name=name))

        network_topology_name = f"issue-3399-network-topology-{index}"
        NetworkTopology.objects.create(
            name=network_topology_name,
            directory=directory,
            base_url="https://example.com",
            groups=[1],
        )
        network_topologies.append(
            SimpleNamespace(key=f"network-topology::{index}", name=network_topology_name)
        )

    doc = SimpleNamespace(
        namespaces=namespaces,
        datasources=datasources,
        dashboards=dashboards,
        topologies=topologies,
        architectures=architectures,
        screens=screens,
        reports=reports,
        network_topologies=network_topologies,
    )

    with django_assert_num_queries(8):
        conflicts = PrecheckService.identify_conflicts(doc, current_team=1)

    assert {conflict["object_key"] for conflict in conflicts} == {
        item.key
        for items in (
            namespaces,
            datasources,
            dashboards,
            topologies,
            architectures,
            screens,
            reports,
            network_topologies,
        )
        for item in items
    }
