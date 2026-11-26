from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.itsm.models import HandlerGroup, Service, Trigger, Workflow
from apps.system_mgmt.models import Group, User

pytestmark = pytest.mark.django_db
DOMAIN = "vmware.example"


@pytest.fixture(autouse=True)
def team():
    return Group.objects.create(name="虚拟化作业")


@pytest.fixture
def group():
    User.objects.create(domain=DOMAIN, username="operator")
    return HandlerGroup.objects.create(name="运维", domain=DOMAIN, members=["operator"])


def test_demo_is_scoped_to_approval_group_and_only_approved_requests_reach_job(group, team, settings):
    settings.FLOWABLE_PASSWORD = "test-only"
    with patch("apps.itsm.management.commands.init_itsm_vmware.FlowableClient") as engine:
        engine.return_value.deploy_bpmn.return_value = {"id": "deployment"}
        engine.return_value.definition_for_deployment.return_value = "vmware:1"
        call_command("init_itsm_vmware", team=team.pk, demo=True, handler_group=group.pk, domain=DOMAIN)
        service = Service.objects.get()
        assert service.is_enabled and service.handler_group == group
        version = service.workflow.current_version
        assert version.is_published
        nodes = {n["id"]: n for n in version.design["nodes"]}
        assert nodes["approve"]["assignee"]["source"] == "service_group"
        assert nodes["approve"]["field_perm"] == {"*": "read"}
        assert nodes["submit"]["field_perm"]["delivery_result"] == "read"
        assert nodes["provision"]["auto"]["profile"] == "demo"
        assert "out_approve_result == 'approve'" in version.bpmn_xml
        assert {e["to"] for e in version.design["edges"] if e["from"] == "decision" and e.get("default")} == {"end"}
        fields = {f["key"]: f for f in version.design["form_schema"]["fields"]}
        table = fields["vm_requests"]
        assert table["type"] == "table" and table["required"]
        assert fields.keys() == {"title", "purpose", "vm_requests", "delivery_result"}
        assert [c["key"] for c in table["children"]] == ["flavor_id", "template_id", "network_id", "disk_policy_id", "data_disk_gib"]
        assert all(column["type"] == "select" and column["required"] for column in table["children"])
        assert all(column["props"]["defaultFirstOption"] for column in table["children"])
        assert fields["delivery_result"]["state"] == "readonly"
        rule = Trigger.objects.get()
        assert rule.config["scope"]["workflow_ids"] == [service.workflow_id]
        assert rule.config["actions"][0]["notice"]["recipients"]["roles"] == ["creator"]

        service.is_enabled = False
        service.save()
        draft = service.workflow.versions.create(version_no=2, design={"notes": "保留本地修改"})
        call_command("init_itsm_vmware", team=team.pk, demo=True, handler_group=group.pk, domain=DOMAIN)
        service.refresh_from_db()
        draft.refresh_from_db()
        assert not service.is_enabled and not draft.is_published and draft.design == {"notes": "保留本地修改"}
        engine.return_value.deploy_bpmn.assert_called_once()


def test_unbound_live_service_is_disabled_and_unpublished(settings, team):
    settings.FLOWABLE_PASSWORD = "configured"
    with patch("apps.itsm.management.commands.init_itsm_vmware.FlowableClient") as engine:
        call_command("init_itsm_vmware", team=team.pk, profile="production", domain=DOMAIN)
    assert not Service.objects.get().is_enabled
    assert not Workflow.objects.get().current_version
    assert Workflow.objects.get().versions.get().design["nodes"][4]["auto"]["profile"] == "production"
    engine.assert_not_called()


def test_foreign_or_empty_group_is_rejected_before_creating_resources(group, team):
    for domain, group_id in [(DOMAIN + ".other", group.pk), (DOMAIN, HandlerGroup.objects.create(name="空组", domain=DOMAIN).pk)]:
        with pytest.raises(CommandError, match="处理组"):
            call_command("init_itsm_vmware", team=team.pk, demo=True, handler_group=group_id, domain=domain)
    assert not Workflow.objects.exists()


def test_vmware_portal_rows_load_authorized_choices_in_row_context(group, team, settings):
    from apps.core.openapi.identity import CallerIdentity
    from apps.itsm.services.form.fetch import fetch_field

    settings.OPENAPI_INVOKE_TIMEOUT = 0
    settings.FLOWABLE_PASSWORD = ""
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    call_command("init_itsm_vmware", team=team.pk, demo=True, handler_group=group.pk, domain=DOMAIN)
    service = Service.objects.get()
    schema = service.workflow.versions.get().design["form_schema"]
    who = CallerIdentity(user="operator", domain=DOMAIN, team_ids=[team.pk], credential_type="jwt", permission={"itsm": ["ticket-Add"]})
    context = f"service:{service.pk}"
    table = next(f for f in schema["fields"] if f["key"] == "vm_requests")
    row = {}
    assert table["props"]["maxRows"] == 5
    for column in table["children"]:
        key = column["key"]
        result = fetch_field(schema, f"vm_requests.{key}", {"vm_requests": [row]}, who, context=context)
        row[key] = result["options"][0]["value"]
    assert row == {
        "flavor_id": "small",
        "template_id": "vm-demo-ubuntu",
        "network_id": "network-demo",
        "disk_policy_id": "standard",
        "data_disk_gib": 0,
    }


def test_applicant_can_read_delivery_after_workflow_closes(settings, team, group):
    from apps.itsm.models import Ticket
    from apps.itsm.views.tickets import ticket_form_view

    settings.FLOWABLE_PASSWORD = ""
    call_command("init_itsm_vmware", team=team.pk, demo=True, handler_group=group.pk, domain=DOMAIN)
    service = Service.objects.get()
    version = service.workflow.versions.get()
    ticket = Ticket.objects.create(
        domain=DOMAIN,
        sn="DEMO",
        workflow=service.workflow,
        workflow_version=version,
        service=service,
        creator="operator",
        form_data={"delivery_result": "第 1 台已交付"},
    )
    fields, values, _, _ = ticket_form_view(ticket, version.design, None, "finished")
    assert any(field["key"] == "delivery_result" and field["state"] == "readonly" for field in fields)
    assert values["delivery_result"] == "第 1 台已交付"


def test_distinct_applicant_group_restricts_portal_to_members(group, team, settings):
    from types import SimpleNamespace

    from apps.itsm.services.service_access import visible_services

    applicant = User.objects.create(domain=DOMAIN, username="applicant")
    applicants = HandlerGroup.objects.create(domain=DOMAIN, name="申请人员", members=["applicant"])
    settings.FLOWABLE_PASSWORD = "test-only"
    with patch("apps.itsm.management.commands.init_itsm_vmware.FlowableClient") as engine:
        engine.return_value.deploy_bpmn.return_value = {"id": "deployment"}
        engine.return_value.definition_for_deployment.return_value = "vmware:1"
        call_command("init_itsm_vmware", team=team.pk, handler_group=group.pk, applicant_group=applicants.pk, demo=True, domain=DOMAIN)
    service = Service.objects.get()
    assert service.visibility == "restricted" and service.visible_groups == [applicants.pk]
    assert visible_services(SimpleNamespace(user=applicant), service_id=service.pk).exists()
    assert not visible_services(SimpleNamespace(user=User.objects.get(username="operator")), service_id=service.pk).exists()
