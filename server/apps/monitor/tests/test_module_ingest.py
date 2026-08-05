"""MonitorModuleIngestService：按 node_id / cmdb_id 归并。"""

import pytest

from apps.monitor.models import MonitorInstance, MonitorInstanceOrganization, MonitorObject
from apps.monitor.services.module_ingest import MonitorModuleIngestService
from apps.node_mgmt.services.module_push_contract import LINK_CONFLICT


@pytest.fixture
def host_object(db):
    return MonitorObject.objects.create(name="Host", display_name="主机", level="base")


def _params(**overrides):
    base = {
        "source_module": "node_mgmt",
        "source_id": "n1",
        "event_type": "upsert",
        "occurred_at": "2026-08-05T12:00:00Z",
        "raw": {
            "ip": "10.0.0.1",
            "name": "host-1",
            "cloud_region_id": 1,
            "organization_ids": [1],
        },
        "link_ids": {"node_id": "n1"},
        "allowed_org_ids": [1],
        "operator": "alice",
    }
    base.update(overrides)
    if "raw" in overrides and isinstance(overrides["raw"], dict):
        raw = dict(base["raw"])
        raw.update(overrides["raw"])
        base["raw"] = raw
    if "link_ids" in overrides and isinstance(overrides["link_ids"], dict):
        link_ids = dict(overrides["link_ids"])
        base["link_ids"] = link_ids
    return base


@pytest.mark.django_db
def test_requires_auth_scope(host_object):
    with pytest.raises(ValueError, match="authorization"):
        MonitorModuleIngestService.ingest(_params(allowed_org_ids=[]))

    with pytest.raises(ValueError, match="authorization"):
        MonitorModuleIngestService.ingest(
            {k: v for k, v in _params().items() if k != "allowed_org_ids"}
        )


@pytest.mark.django_db
def test_monitor_ingest_merges_by_node_id(host_object):
    first = MonitorModuleIngestService.ingest(_params())
    assert first["created"] is True
    assert first["updated"] is False
    assert first["id"]

    second = MonitorModuleIngestService.ingest(
        _params(raw={"name": "host-1-renamed", "ip": "10.0.0.2"})
    )
    assert second["updated"] is True
    assert second["created"] is False
    assert second["id"] == first["id"]

    assert MonitorInstance.objects.filter(is_deleted=False).count() == 1
    inst = MonitorInstance.objects.get(id=first["id"])
    assert inst.node_id == "n1"
    assert inst.name == "host-1-renamed"
    assert str(inst.ip) == "10.0.0.2"
    assert MonitorInstanceOrganization.objects.filter(
        monitor_instance=inst, organization=1
    ).exists()


@pytest.mark.django_db
def test_monitor_ingest_by_cmdb_id_when_no_node_id(host_object):
    result = MonitorModuleIngestService.ingest(
        _params(
            source_module="cmdb",
            source_id="42",
            link_ids={"cmdb_id": "42"},
            raw={"name": "from-cmdb", "ip": "10.0.0.9", "organization_ids": [1]},
        )
    )
    assert result["created"] is True
    inst = MonitorInstance.objects.get(id=result["id"])
    assert inst.cmdb_id == "42"
    assert inst.node_id is None
    assert inst.name == "from-cmdb"

    again = MonitorModuleIngestService.ingest(
        _params(
            source_module="cmdb",
            source_id="42",
            link_ids={"cmdb_id": "42"},
            raw={"name": "from-cmdb-2", "ip": "10.0.0.9"},
        )
    )
    assert again["updated"] is True
    assert again["id"] == result["id"]
    assert MonitorInstance.objects.filter(is_deleted=False).count() == 1


@pytest.mark.django_db
def test_node_then_same_node_id_single_instance(host_object):
    a = MonitorModuleIngestService.ingest(_params(link_ids={"node_id": "shared-n"}))
    b = MonitorModuleIngestService.ingest(
        _params(
            source_id="shared-n",
            link_ids={"node_id": "shared-n", "cmdb_id": "99"},
            raw={"name": "after-cmdb-link", "ip": "10.0.0.1"},
        )
    )
    assert a["id"] == b["id"]
    assert MonitorInstance.objects.filter(node_id="shared-n", is_deleted=False).count() == 1
    inst = MonitorInstance.objects.get(id=a["id"])
    assert inst.cmdb_id == "99"
    assert inst.name == "after-cmdb-link"


@pytest.mark.django_db
def test_link_conflict_when_ids_disagree(host_object):
    by_node = MonitorModuleIngestService.ingest(_params(link_ids={"node_id": "n-a"}))
    by_cmdb = MonitorModuleIngestService.ingest(
        _params(
            source_module="cmdb",
            source_id="77",
            link_ids={"cmdb_id": "77"},
            raw={"name": "other", "ip": "10.0.0.8", "organization_ids": [1]},
        )
    )
    assert by_node["id"] != by_cmdb["id"]

    conflict = MonitorModuleIngestService.ingest(
        _params(
            link_ids={"node_id": "n-a", "cmdb_id": "77"},
            raw={"name": "conflict", "ip": "10.0.0.1"},
        )
    )
    assert conflict["conflict"] == LINK_CONFLICT
    assert conflict["created"] is False
    assert conflict["updated"] is False
    assert MonitorInstance.objects.filter(is_deleted=False).count() == 2


@pytest.mark.django_db
def test_lifecycle_retire_soft_deactivates_without_hard_delete(host_object):
    created = MonitorModuleIngestService.ingest(_params(link_ids={"node_id": "n-ret"}))
    inst_id = created["id"]
    assert MonitorInstance.objects.filter(id=inst_id, is_deleted=False, is_active=True).exists()

    result = MonitorModuleIngestService.ingest(
        _params(
            source_id="n-ret",
            event_type="lifecycle",
            link_ids={"node_id": "n-ret", "monitor_id": inst_id},
            raw={"action": "retire"},
        )
    )

    assert result["updated"] is True
    assert result["id"] == inst_id
    # 仍在库中：软删，非物理删除
    assert MonitorInstance.objects.filter(id=inst_id).count() == 1
    inst = MonitorInstance.objects.get(id=inst_id)
    assert inst.is_deleted is True
    assert inst.is_active is False
    assert MonitorInstance.objects.filter(id=inst_id, is_deleted=False).count() == 0


@pytest.mark.django_db
def test_lifecycle_idempotent_when_already_retired(host_object):
    created = MonitorModuleIngestService.ingest(_params(link_ids={"node_id": "n-ret2"}))
    MonitorModuleIngestService.ingest(
        _params(
            source_id="n-ret2",
            event_type="lifecycle",
            link_ids={"node_id": "n-ret2", "monitor_id": created["id"]},
            raw={"action": "retire"},
        )
    )
    again = MonitorModuleIngestService.ingest(
        _params(
            source_id="n-ret2",
            event_type="lifecycle",
            link_ids={"monitor_id": created["id"]},
            raw={"action": "retire"},
        )
    )
    assert again["ignored"] is True
    assert MonitorInstance.objects.filter(id=created["id"]).count() == 1
