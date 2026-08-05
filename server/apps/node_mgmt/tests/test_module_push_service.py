import pytest

from apps.node_mgmt.models import Node
from apps.node_mgmt.models.cloud_region import CloudRegion
from apps.node_mgmt.models.sidecar import NodeOrganization
from apps.node_mgmt.services.module_push_contract import LINK_CONFLICT


@pytest.fixture
def node(db):
    region = CloudRegion.objects.create(name="default-push")
    n = Node.objects.create(
        id="n-push-1",
        name="push-node",
        ip="10.0.0.9",
        operating_system="linux",
        collector_configuration_directory="/tmp",
        cloud_region=region,
    )
    NodeOrganization.objects.create(node=n, organization=1)
    return n


@pytest.mark.django_db
def test_push_cmdb_only_does_not_call_monitor(mocker, node):
    cmdb = mocker.patch("apps.node_mgmt.services.module_push.CMDB")
    cmdb.return_value.ingest_from_source.return_value = {
        "id": 99,
        "created": True,
        "updated": False,
        "ignored": False,
        "claimed": False,
    }
    monitor = mocker.patch("apps.node_mgmt.services.module_push.MonitorLinkage")
    from apps.node_mgmt.services.module_push import ModulePushService

    ModulePushService.push_node(
        node.id,
        targets=["cmdb"],
        actor_scope={"allowed_org_ids": [1], "operator": "u"},
    )

    cmdb.return_value.ingest_from_source.assert_called_once()
    assert monitor.call_count == 0
    node.refresh_from_db()
    assert node.cmdb_id == "99"
    assert node.push_status["cmdb"]["state"] == "ok"


@pytest.mark.django_db
def test_push_retries_then_skips(mocker, node):
    cmdb = mocker.patch("apps.node_mgmt.services.module_push.CMDB")
    cmdb.return_value.ingest_from_source.side_effect = TimeoutError("x")
    from apps.node_mgmt.services.module_push import ModulePushService

    ModulePushService.push_node(
        node.id,
        targets=["cmdb"],
        actor_scope={"allowed_org_ids": [1], "operator": "u"},
        max_attempts=3,
    )

    assert cmdb.return_value.ingest_from_source.call_count == 3
    node.refresh_from_db()
    assert node.push_status["cmdb"]["state"] == "skipped"
    assert node.cmdb_id == ""


@pytest.mark.django_db
def test_push_conflict_skips_without_cmdb_id(mocker, node):
    cmdb = mocker.patch("apps.node_mgmt.services.module_push.CMDB")
    cmdb.return_value.ingest_from_source.return_value = {
        "id": 42,
        "created": False,
        "updated": False,
        "ignored": False,
        "claimed": False,
        "conflict": LINK_CONFLICT,
    }
    from apps.node_mgmt.services.module_push import ModulePushService

    ModulePushService.push_node(
        node.id,
        targets=["cmdb"],
        actor_scope={"allowed_org_ids": [1], "operator": "u"},
    )

    node.refresh_from_db()
    assert node.cmdb_id == ""
    assert node.push_status["cmdb"]["state"] in ("skipped", "conflict")


@pytest.mark.django_db
def test_push_passes_actor_scope_and_envelope(mocker, node):
    cmdb = mocker.patch("apps.node_mgmt.services.module_push.CMDB")
    cmdb.return_value.ingest_from_source.return_value = {
        "id": 7,
        "created": True,
        "updated": False,
        "ignored": False,
        "claimed": False,
    }
    from apps.node_mgmt.services.module_push import ModulePushService

    ModulePushService.push_node(
        node.id,
        targets=["cmdb"],
        actor_scope={"allowed_org_ids": [1], "operator": "alice"},
    )

    kwargs = cmdb.return_value.ingest_from_source.call_args.kwargs
    assert kwargs["allowed_org_ids"] == [1]
    assert kwargs["operator"] == "alice"
    assert kwargs["source_module"] == "node_mgmt"
    assert kwargs["link_ids"]["node_id"] == node.id
    assert kwargs["raw"]["ip"] == node.ip
    assert kwargs["raw"]["name"] == node.name
