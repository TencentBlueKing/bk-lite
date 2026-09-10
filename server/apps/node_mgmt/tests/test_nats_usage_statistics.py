from types import SimpleNamespace

import pytest

from apps.node_mgmt.models import Collector, Node
from apps.node_mgmt.models.cloud_region import CloudRegion
from apps.node_mgmt.models.sidecar import NodeOrganization
from apps.node_mgmt.nats import node as node_nats

pytestmark = pytest.mark.django_db


def _user_info(team=1):
    return {
        "user": SimpleNamespace(username="alice", domain="domain.com"),
        "domain": "domain.com",
        "team": team,
        "include_children": False,
        "is_superuser": False,
    }


def _grant(mocker, team=1):
    mocker.patch(
        "apps.node_mgmt.services.node.SystemMgmt.get_authorized_groups_scoped",
        side_effect=lambda actor_context, include_children=False: {
            "result": True,
            "data": [actor_context["current_team"]],
            "is_superuser": False,
        },
    )
    mocker.patch("apps.node_mgmt.services.node.get_permission_rules", return_value={"team": [team]})


def test_node_usage_statistics_counts_online_and_regions(mocker):
    _grant(mocker)
    region_a = CloudRegion.objects.create(name="region-a")
    region_b = CloudRegion.objects.create(name="region-b")
    Collector.objects.create(
        id="col-usage",
        name="Telegraf",
        service_type="svc",
        node_operating_system="linux",
        executable_path="/bin/telegraf",
        execute_parameters="-c",
    )
    online = Node.objects.create(
        id="n-online",
        name="online",
        ip="10.0.0.1",
        operating_system="linux",
        collector_configuration_directory="/etc",
        cloud_region=region_a,
        status={"status": 0},
    )
    offline = Node.objects.create(
        id="n-offline",
        name="offline",
        ip="10.0.0.2",
        operating_system="linux",
        collector_configuration_directory="/etc",
        cloud_region=region_a,
        status={"status": 1},
    )
    other = Node.objects.create(
        id="n-other",
        name="other",
        ip="10.0.0.3",
        operating_system="linux",
        collector_configuration_directory="/etc",
        cloud_region=region_b,
        status={"status": 0},
    )
    NodeOrganization.objects.create(node=online, organization=1)
    NodeOrganization.objects.create(node=offline, organization=1)
    NodeOrganization.objects.create(node=other, organization=2)

    result = node_nats.get_node_usage_statistics(user_info=_user_info())
    top = node_nats.get_cloud_region_node_top(user_info=_user_info(), limit=10)

    assert result["data"]["node_total"] == 2
    assert result["data"]["online_count"] == 1
    assert result["data"]["online_rate"] == 50.0
    assert result["data"]["cloud_region_total"] == 1
    assert result["data"]["collector_total"] >= 1
    assert top["data"] == [{"cloud_region_id": region_a.id, "cloud_region_name": "region-a", "count": 2}]
