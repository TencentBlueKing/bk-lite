import copy
import json
from unittest.mock import patch

import pytest

from apps.itsm.models import HandlerGroup, Service, Ticket, Workflow, WorkflowVersion
from apps.itsm.openapi_api import openapi_vmware_catalog
from apps.itsm.services.vmware_catalog import DEMO_CONFIG, bind_catalog, install_demo_catalog, load_delivery
from apps.system_mgmt.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture
def ticket():
    workflow = Workflow.objects.create(name="交付", key="vm")
    service = Service.objects.create(workflow=workflow, name="虚拟机", team=[20], handler_group=HandlerGroup.objects.create(name="运维", members=["ops"]))
    install_demo_catalog(service, 20)
    User.objects.create(username="applicant", group_list=[20])
    version = WorkflowVersion.objects.create(
        workflow=workflow,
        version_no=1,
        is_published=True,
        design={
            "form_schema": {
                "fields": [
                    {"key": k, "type": "select"} for k in ("flavor_id", "template_id", "network_id", "disk_policy_id", "data_disk_gib", "quantity")
                ]
            },
            "nodes": [{"type": "auto", "auto": {"kind": "vmware_provision", "profile": "demo"}}],
        },
    )
    return Ticket.objects.create(
        workflow_version=version,
        sn="REQ1",
        creator="applicant",
        service=service,
        workflow=workflow,
        form_data={
            "flavor_id": "small",
            "template_id": "vm-demo-ubuntu",
            "network_id": "network-demo",
            "disk_policy_id": "standard",
            "quantity": 1,
            "data_disk_gib": 20,
        },
    )


def test_catalog_is_scoped_and_only_returns_allowed_fields(ticket):
    def get(team, domain="domain.com", **params):
        return openapi_vmware_catalog(profile="demo", team=team, user_info={"domain": domain}, **params)

    assert get([20], kind="flavor", keyword="small")["items"][0]["memory_gib"] == 4
    assert [row["value"] for row in get([20], kind="quantity")["items"]] == list(range(1, 6))
    assert get([20], kind="disk_size", disk_policy_id="standard")["items"][0]["value"] == 0
    assert get([20], kind="disk_size", disk_policy_id="other")["items"] == []
    assert set(get([20], kind="disk_policy")["items"][0]) == {"label", "value"}
    assert not get([21], kind="flavor")["result"]
    assert not get([20], "another.domain", kind="flavor")["result"]


def test_delivery_revalidates_policy_membership_and_service(ticket):
    ticket.form_data["quantity"] = 2
    legacy = load_delivery("demo", ticket)["machines"]
    assert len(legacy) == 2 and all(machine["cpu"] == 2 for machine in legacy)
    ticket.form_data["data_disk_gib"] = 101
    with pytest.raises(ValueError):
        load_delivery("demo", ticket)
    ticket.form_data["data_disk_gib"] = True
    with pytest.raises(ValueError):
        load_delivery("demo", ticket)
    ticket.form_data["data_disk_gib"] = 20
    User.objects.filter(username="applicant").update(group_list=[21])
    with pytest.raises(PermissionError):
        load_delivery("demo", ticket)
    User.objects.filter(username="applicant").update(group_list=[20])
    ticket.service = Service.objects.create(workflow=ticket.workflow, team=[20])
    with pytest.raises(PermissionError):
        load_delivery("demo", ticket)


def test_real_catalog_requires_scoped_target_and_cmdb_vcenter(ticket):
    cfg = copy.deepcopy(DEMO_CONFIG)
    cfg.update(target_id=4, vc_instance_uuid="example", vc_host="vc.example.invalid")
    with patch("apps.itsm.services.vmware_catalog._check_target") as target, patch("apps.itsm.services.vmware_catalog._check_vcenter") as vc:
        bind_catalog("dev", ticket.service, 20, cfg)
        ticket.workflow_version.design["nodes"][0]["auto"]["profile"] = "dev"
        assert load_delivery("dev", ticket)["target_id"] == 4
        assert target.call_count == vc.call_count == 2
        cfg["catalog"]["flavor"][0]["cpu"] = 8
        with pytest.raises(ValueError):
            bind_catalog("dev", ticket.service, 20, cfg)
        cfg["password"] = "invalid"
        with pytest.raises(ValueError):
            bind_catalog("invalid", ticket.service, 20, cfg)


def test_discovery_only_exports_approved_existing_resources():
    import runpy
    from pathlib import Path

    export = runpy.run_path(str(Path(__file__).resolve().parents[1] / "support-files/vmware/discover_vmware_catalog.py"))["export_catalog"]
    profile = {
        **copy.deepcopy(DEMO_CONFIG),
        "host": "vc.internal",
        "password_file": "/private/secret",
        "folder_id": "folder",
        "resource_pool_id": "pool",
    }
    inventory = {kind: profile["catalog"][kind] for kind in ("network", "template")} | {
        "folder": [{"value": "folder"}],
        "resource_pool": [{"value": "pool"}],
        "datastore": [{"value": "datastore-demo"}],
    }
    cfg = export(profile, inventory, 1, "root-uuid", 1)
    assert set(cfg) == {"catalog", "target_id", "vc_instance_uuid", "vc_host", "max_quantity"}
    inventory["template"] = []
    with pytest.raises(ValueError, match="不可用"):
        export(profile, inventory, 1, "root-uuid", 1)


def test_batch_validates_each_row_in_the_published_version(ticket):
    from apps.itsm.services.ticket.service import TicketService

    version = ticket.workflow_version
    columns = [{"key": key, "label": key, "type": "select", "required": True} for key in ticket.form_data if key != "quantity"]
    version.design["form_schema"] = {"fields": [{"key": "vm_requests", "label": "配置", "type": "table", "required": True, "children": columns}]}
    version.save()
    row = {k: v for k, v in ticket.form_data.items() if k != "quantity"}
    valid = {"vm_requests": [row, {**row, "flavor_id": "medium", "data_disk_gib": 0}]}

    def create(values):
        return TicketService().create(version, values, "applicant", service=ticket.service)

    for values in (ticket.form_data, {"vm_requests": []}, {"vm_requests": [row] * 6}, {"vm_requests": [row, {**row, "flavor_id": "unknown"}]}):
        with pytest.raises(ValueError):
            create(values)
    assert Ticket.objects.count() == 1
    from apps.itsm.models import ItsmSetting

    profile = ItsmSetting.objects.get(key="vmware_profile_demo")
    profile.value["catalog"]["disk_policy"].append({"value": "fast", "label": "高速盘", "datastore_id": "fast-ds", "allowed_disk_gib": [60]})
    profile.save()
    valid["vm_requests"][1].update(disk_policy_id="fast", data_disk_gib=60)
    with pytest.raises(ValueError, match="第 2 行"):
        create({"vm_requests": [row, {**valid["vm_requests"][1], "data_disk_gib": 20}]})
    stored = create(valid)
    assert [m["cpu"] for m in load_delivery("demo", stored)["machines"]] == [2, 4]
    assert stored.form_data["_field_labels"]["vm_requests.flavor_id"][0]["label"] != "small"
    ticket.form_data = {"vm_requests": [row, {**row, "data_disk_gib": 19}]}
    with pytest.raises(ValueError, match="第 2 行"):
        load_delivery("demo", ticket)
    User.objects.filter(username="applicant").update(group_list=[999])
    with pytest.raises(PermissionError):
        create(valid)


def test_fetch_disk_sizes_with_row_values(ticket, settings):
    from apps.core.openapi.identity import CallerIdentity
    from apps.itsm.management.commands.init_itsm_vmware import _form_schema
    from apps.itsm.models.integration import Integration
    from apps.itsm.services.form.fetch import fetch_field

    settings.OPENAPI_INVOKE_TIMEOUT = 0
    integration = Integration.objects.create(kind="api", config={"path": "itsm/vmware/catalog", "method": "GET"})
    schema = _form_schema(integration, "demo", ticket.domain)
    identity = CallerIdentity("applicant", ticket.domain, "jwt", team_ids=[20], permission={"itsm": {"ticket-Add"}})
    values = {"vm_requests": [{"disk_policy_id": "standard"}]}
    assert [r["value"] for r in fetch_field(schema, "vm_requests.data_disk_gib", values, identity, context="service:1")["options"]] == [0, 20, 40, 80]
    identity.team_ids = [21]
    with pytest.raises(ValueError):
        fetch_field(schema, "vm_requests.data_disk_gib", values, identity, context="service:1")


def test_http_batch_create_save_approve_revalidates_policy(ticket, settings):
    from apps.itsm.management.commands.init_itsm_vmware import _form_schema
    from apps.itsm.models import TicketTask
    from apps.itsm.models.integration import Integration
    from apps.itsm.tests.test_review_regressions import request
    from apps.itsm.views.field_fetch import field_fetch
    from apps.itsm.views.tickets import operate_ticket, ticket_form_view, tickets

    settings.OPENAPI_INVOKE_TIMEOUT = 0
    integration = Integration.objects.create(kind="api", config={"path": "itsm/vmware/catalog", "method": "GET"})
    version = ticket.workflow_version
    version.design["form_schema"] = _form_schema(integration, "demo", ticket.domain)
    version.design["nodes"] += [{"type": "submit", "id": "apply"}, {"type": "approval", "id": "approve", "field_perm": {"*": "read"}}]
    version.save()
    ticket.workflow.current_version = version
    ticket.workflow.save()
    values = {"title": "明细试验", "purpose": "整批校验", "vm_requests": [{k: v for k, v in ticket.form_data.items() if k != "quantity"}]}
    base = {"workflow_version_id": version.pk, "service_id": ticket.service_id}
    perms = ["ticket-View", "ticket-Add", "ticket-Operate"]

    def post(body):
        req = request("post", body, username="applicant", permissions=perms)
        req.user.group_list = [20]
        return req

    options = field_fetch(post({**base, "field": "vm_requests.flavor_id", "values": {"vm_requests": [{}]}}))
    assert json.loads(options.content)["data"]["options"][0]["value"] == "small"
    error = {**values, "vm_requests": [*values["vm_requests"], {**values["vm_requests"][0], "data_disk_gib": 42}]}
    assert tickets(post({**base, "form_data": error})).status_code == 400
    response = tickets(post({**base, "form_data": values}))
    assert response.status_code == 200
    instance = Ticket.objects.get(pk=json.loads(response.content)["data"]["id"])
    task = TicketTask.objects.create(ticket=instance, node_id="apply", assignee="applicant")
    assert operate_ticket(post({"task_id": task.pk, "action": "save", "form_data": error}), instance.pk).status_code == 400
    instance.refresh_from_db()
    fields, _, _, _ = ticket_form_view(instance, version.design, task, "processing")
    table = next(f for f in fields if f["key"] == "vm_requests")
    assert table["children"][0]["source"]["options"][0]["label"] == DEMO_CONFIG["catalog"]["flavor"][0]["label"]
    assert instance.form_data["vm_requests"] == values["vm_requests"]
    task.node_id = "approve"
    task.save()
    instance.form_data["vm_requests"] = error["vm_requests"]
    instance.save()
    assert operate_ticket(post({"task_id": task.pk, "action": "approve"}), instance.pk).status_code == 400
    task.refresh_from_db()
    assert task.status == "pending"
    assert operate_ticket(post({"task_id": task.pk, "action": "reject"}), instance.pk).status_code == 200


def test_real_binding_matches_cmdb_address_and_organization():
    from apps.itsm.services.vmware_catalog import _check_vcenter

    with patch("apps.cmdb.graph.drivers.graph_client.GraphClient") as client:
        graph = client.return_value.__enter__.return_value
        graph.query_entity.return_value = ([{"inst_uuid": "root", "ip_addr": "Ops-Vc.Example.Invalid."}], 0)
        assert _check_vcenter("root", 3, "ops-vc.example.invalid") == "ops-vc.example.invalid"
        assert {"field": "organization", "type": "list[]", "value": [3]} in graph.query_entity.call_args.args[1]
        with pytest.raises(ValueError, match="不一致"):
            _check_vcenter("root", 3, "another.example.invalid")
        graph.query_entity.return_value = ([], 0)
        with pytest.raises(ValueError, match="本组织"):
            _check_vcenter("root", 3, "another.example.invalid")


def test_basic_settings_cannot_read_or_edit_catalog(ticket):
    import json

    from apps.itsm.models import ItsmSetting
    from apps.itsm.tests.test_review_regressions import request
    from apps.itsm.views.api import basic_settings

    setting = ItsmSetting.objects.get(key="vmware_profile_demo")
    original = setting.value
    data = {"key": setting.key, "value": {"service_id": 999}, "team": [21]}
    assert basic_settings(request("post", data, permissions=["ticket-Add"])).status_code == 403
    response = basic_settings(request("post", data, permissions=["setting-Edit"]))
    assert response.status_code == 200
    assert "catalog" not in json.loads(response.content)["data"]
    setting.refresh_from_db()
    assert setting.value == original and setting.team == [20]


def test_job_target_uses_current_ownership_and_domain():
    from django.apps import apps

    if not apps.is_installed("apps.job_mgmt"):
        pytest.skip("当前安装未启用作业平台")
    from apps.itsm.services.vmware_catalog import _check_target
    from apps.job_mgmt.models import Target

    target = Target.objects.create(ip="192.0.2.100", name="执行机", domain="domain.com", team=[20])
    _check_target(target.pk, 20, "domain.com")
    for team, domain in ((21, "domain.com"), (20, "another.domain")):
        with pytest.raises(ValueError):
            _check_target(target.pk, team, domain)
    target.team = [21]
    target.save(update_fields=["team"])
    with pytest.raises(ValueError):
        _check_target(target.pk, 20, "domain.com")


def test_unbound_draft_catalog_preview_is_scoped_and_labels_examples(ticket):
    from apps.itsm.services.vmware_catalog import catalog_options

    flow = Workflow.objects.create(key="vmware_lab_20", name="实验环境", team=[20])
    Service.objects.create(workflow=flow, name="实验环境", team=[20], is_enabled=False)
    preview = catalog_options("lab", "template", flow.domain, [20], preview=True)
    assert preview["items"][0]["label"].startswith("示例（尚未绑定目录）")
    assert not catalog_options("lab", "template", flow.domain, [20])["items"]
    for domain, teams in [(flow.domain, [21]), ("other", [20])]:
        with pytest.raises(PermissionError):
            catalog_options("lab", "template", domain, teams, preview=True)
    assert catalog_options("demo", "template", flow.domain, [20], preview=True) == catalog_options("demo", "template", flow.domain, [20])
