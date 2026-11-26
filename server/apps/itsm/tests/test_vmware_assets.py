import hashlib
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.test import RequestFactory

from apps.itsm.services.vmware_assets import resolve_cmdb_assets
from apps.itsm.views.vmware_assets import ticket_vmware_assets

pytestmark = pytest.mark.django_db
VM_UUID = "62052f61-01b6-48f2-8719-f2393f36bd4c"
ROOT = "1dbefa9a-da3d-4f4b-ae07-890c142e966a"
ASSET = "25515aa0-e533-408c-8888-034592855b74"


def test_links_only_unique_delivered_resource_owned_by_same_collection_and_team():
    payload = {"profile": "prod", "delivery_id": "itsm-7-1", "vc_host": "vc.local"}
    machines = {"itsm-7-1": {"request": payload, "receipt": {"vm_id": "vm-31", "vm_uuid": VM_UUID, "hostname": "vm-test"}}}
    plan = {"vc_instance_uuid": ROOT, "team_id": 5}
    http = RequestFactory().get("/")
    http.user = SimpleNamespace(username="owner", domain="domain.com", group_list=[{"id": 5}])
    base = {
        "model_id": "vmware_vm",
        "resource_id": "vm-31",
        "collect_task": "15",
        "inst_uuid": ASSET,
        "organization": [5],
        "annotation": "BK-Lite-ITSM:" + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
    }
    rows = [base]

    def query(label, filters, **kwargs):
        params = {i["field"]: i["value"] for i in filters}
        if params["model_id"] == "vmware_vc":
            return [{"inst_uuid": ROOT, "collect_task": "15", "vc_source_key": "s" * 64, "organization": [5]}], 1
        return (rows, len(rows)) if params["collect_task"] == "15" else ([], 0)

    graph = MagicMock()
    graph.__enter__.return_value.query_entity.side_effect = query
    with (
        patch("apps.itsm.services.vmware_assets.GraphClient", return_value=graph),
        patch("apps.itsm.services.vmware_assets.CollectModels.objects.filter") as tasks,
        patch("apps.itsm.services.vmware_assets.CmdbPermissionMixin.require_instance_permission", return_value=None) as permitted,
        patch("apps.itsm.services.vmware_assets.InstanceViewSet._is_model_visible", return_value=True),
    ):
        tasks.return_value.values_list.return_value.first.return_value = [5]

        def links():
            return resolve_cmdb_assets(http, plan, machines)

        assert ASSET in links()["itsm-7-1"]
        rows.append(dict(base, inst_uuid=ROOT))
        assert links() == {}
        rows.pop()
        rows[0] = dict(base, annotation="foreign")
        assert links() == {}
        rows[0] = base
        tasks.return_value.values_list.return_value.first.return_value = [8]
        assert links() == {}
        tasks.return_value.values_list.return_value.first.return_value = [5]
        permitted.return_value = object()
        assert links() == {}


def test_ticket_lookup_requires_ticket_and_cmdb_view():
    request = RequestFactory().get("/")
    request.user = SimpleNamespace(username="owner", domain="domain.com", is_superuser=False, permission={"itsm": {"ticket-View"}}, locale="zh-Hans")
    assert ticket_vmware_assets(request, 99).status_code == 403


def test_endpoint_uses_persisted_receipts_and_is_scoped_to_ticket():
    from apps.itsm.models import AutoExecution, Ticket, Workflow

    workflow = Workflow.objects.create(domain="domain.com", key="test-vm", name="测试交付")
    ticket = Ticket.objects.create(domain="domain.com", sn="REQ-VM", title="申请", workflow=workflow, creator="owner")
    plan = {"vc_instance_uuid": ROOT, "team_id": 5}
    item = {"request": {"delivery_id": "D1"}, "receipt": {"hostname": "vm-owned"}}
    AutoExecution.objects.create(
        domain=ticket.domain,
        ticket=ticket,
        kind="external",
        status="done",
        detail={"delivery": {"plan": plan, "machines": {"D1": item, "D2": {"job": 9}}}},
    )
    http = RequestFactory().get("/", {"vm_id": "untrusted"})
    http.user = SimpleNamespace(
        username="owner",
        domain=ticket.domain,
        is_superuser=False,
        locale="zh-Hans",
        permission={"itsm": {"ticket-View"}, "cmdb": {"asset_info-View"}},
        group_list=[{"id": 5}],
    )
    view = ticket_vmware_assets
    with patch("apps.itsm.services.vmware_assets.resolve_cmdb_assets", return_value={}) as resolver:
        assert json.loads(view(http, ticket.id).content)["data"]["items"] == [{"delivery_id": "D1", "hostname": "vm-owned", "url": None}]
        resolver.assert_called_once_with(http, plan, {"D1": item})
        http.user.domain = "other-domain"
        assert view(http, ticket.id).status_code == 404
        resolver.assert_called_once()
