from types import SimpleNamespace

import pytest

from apps.operation_analysis.constants.import_export import ConflictAction, ConflictReason
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
            SimpleNamespace(
                key=f"datasource::{index}",
                name=datasource_name,
                rest_api=rest_api,
                source_type="nats",
            )
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
        network_topologies.append(SimpleNamespace(key=f"network-topology::{index}", name=network_topology_name))

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


@pytest.mark.django_db
def test_identify_conflicts_empty_groups_builtin_datasource_is_name_conflict():
    """内置空组织全员可见：导入冲突应为名称冲突并可 skip，不得逼成只能 rename。"""
    DataSourceAPIModel.objects.create(
        name="global-builtin-top",
        rest_api="monitor/get_host_resource_top",
        groups=[],
        is_build_in=True,
        build_in_key="builtin::global-top",
        created_by="system",
        updated_by="system",
    )
    DataSourceAPIModel.objects.create(
        name="restricted-builtin",
        rest_api="monitor/restricted",
        groups=[2],
        is_build_in=True,
        build_in_key="builtin::restricted",
        created_by="system",
        updated_by="system",
    )
    DataSourceAPIModel.objects.create(
        name="custom-other-org",
        rest_api="monitor/custom",
        groups=[2],
        is_build_in=False,
        created_by="u",
        updated_by="u",
    )

    doc = SimpleNamespace(
        namespaces=[],
        datasources=[
            SimpleNamespace(
                key="global-builtin-top::monitor/get_host_resource_top",
                name="global-builtin-top",
                rest_api="monitor/get_host_resource_top",
                source_type="nats",
            ),
            SimpleNamespace(
                key="restricted-builtin::monitor/restricted",
                name="restricted-builtin",
                rest_api="monitor/restricted",
                source_type="nats",
            ),
            SimpleNamespace(
                key="custom-other-org::monitor/custom",
                name="custom-other-org",
                rest_api="monitor/custom",
                source_type="nats",
            ),
        ],
        dashboards=[],
        topologies=[],
        architectures=[],
        screens=[],
        reports=[],
        network_topologies=[],
    )

    conflicts = {item["object_key"]: item for item in PrecheckService.identify_conflicts(doc, current_team=1)}

    global_conflict = conflicts["global-builtin-top::monitor/get_host_resource_top"]
    assert global_conflict["reason"] == ConflictReason.NAME_CONFLICT
    assert global_conflict["suggested_actions"] == [
        ConflictAction.SKIP.value,
        ConflictAction.OVERWRITE.value,
        ConflictAction.RENAME.value,
    ]

    restricted = conflicts["restricted-builtin::monitor/restricted"]
    assert restricted["reason"] == ConflictReason.NO_PERMISSION_CONFLICT
    assert restricted["suggested_actions"] == [ConflictAction.RENAME.value]

    custom = conflicts["custom-other-org::monitor/custom"]
    assert custom["reason"] == ConflictReason.NO_PERMISSION_CONFLICT
    assert custom["suggested_actions"] == [ConflictAction.RENAME.value]
