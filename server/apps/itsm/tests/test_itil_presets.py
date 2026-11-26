from unittest.mock import patch

import pytest
from django.core.management import call_command

from apps.itsm.models import FormModel, Service, Workflow, WorkflowVersion
from apps.itsm.services.ticket.service import workflow_schema

pytestmark = pytest.mark.django_db


@pytest.fixture
def engine(settings):
    settings.FLOWABLE_PASSWORD = "test-only"
    call_command("init_itsm")
    with patch("apps.itsm.management.commands.init_itsm_itil.FlowableClient") as factory:
        client = factory.return_value
        client.deploy_bpmn.side_effect = lambda key, xml: {"id": f"deployment-{key}"}
        client.definition_for_deployment.side_effect = lambda deployment, key: f"{key}:1"
        yield client


def test_new_pack_publishes_independent_forms_and_leaves_services_disabled(engine):
    call_command("init_itsm_itil")
    assert FormModel.objects.count() == 3
    assert not Service.objects.filter(is_enabled=True).exists()
    for workflow in Workflow.objects.select_related("form__current_version", "current_version"):
        version = workflow.current_version
        assert workflow.form.current_version.is_published and version.is_published
        assert version.design["form_model_id"] == workflow.form_id
        assert version.design["form_schema"] == workflow.form.current_version.schema
        fields = {field["key"]: field for field in workflow_schema(version)["fields"]}
        assert fields["title"]["required"] and fields["description"]["type"] == "textarea"
        assert {fields[key]["fetch"]["resource_key"] for key in ("priority", "impact")} == {"priority", "impact"}
        for node in version.design["nodes"]:
            if node["id"] in {"approve", "handle"}:
                assert node["assignee"] == {"source": "service_group", "value": []}
                assert not node.get("fallback")
    assert engine.deploy_bpmn.call_count == 3


def test_install_does_not_publish_or_overwrite_an_administrator_draft(engine):
    call_command("init_itsm_itil")
    req = Workflow.objects.get(key="itsm_request")
    existing = req.current_version
    edited = {**existing.design, "settings": {"draft_note": "处理中"}}
    draft = WorkflowVersion.objects.create(workflow=req, version_no=2, design=edited, created_by="designer", domain=req.domain)
    call_command("init_itsm_itil")
    req.refresh_from_db()
    draft.refresh_from_db()
    assert req.current_version_id == existing.pk
    assert not draft.is_published and draft.design == edited
    assert engine.deploy_bpmn.call_count == 3
    assert FormModel.objects.count() == 3
    assert WorkflowVersion.objects.count() == 4


def test_unpublished_first_version_is_also_preserved_on_rerun(engine, settings):
    settings.FLOWABLE_PASSWORD = ""
    call_command("init_itsm_itil")
    req = Workflow.objects.get(key="itsm_request")
    draft = req.versions.get()
    modified = {**draft.design, "notes": "待管理员审核"}
    draft.design = modified
    draft.save()
    settings.FLOWABLE_PASSWORD = "test-only"
    call_command("init_itsm_itil")
    draft.refresh_from_db()
    assert req.versions.count() == 1 and draft.design == modified
    assert not draft.is_published
    assert not Workflow.objects.filter(current_version__isnull=False).exists()
    engine.deploy_bpmn.assert_not_called()


def test_standalone_itil_install_initializes_referenced_dictionary_options(settings):
    from apps.itsm.models import DataDictionary

    settings.FLOWABLE_PASSWORD = ""
    call_command("init_itsm_itil")
    assert set(DataDictionary.objects.get(key="priority").items.values_list("key", flat=True)) == {"P1", "P2", "P3", "P4"}
    assert set(DataDictionary.objects.get(key="impact").items.values_list("key", flat=True)) == {"高", "中", "低"}


def test_deployment_lookup_failure_leaves_a_draft_for_explicit_publish(engine):
    from apps.itsm.flowable.client import FlowableError

    engine.definition_for_deployment.side_effect = FlowableError(503, "")
    with pytest.raises(RuntimeError, match="草稿"):
        call_command("init_itsm_itil")
    workflow = Workflow.objects.get(key="itsm_request")
    draft = workflow.versions.get()
    assert workflow.current_version is None and not draft.is_published
    assert draft.bpmn_xml and draft.flowable_deployment_id == "deployment-itsm_request"
    engine.definition_for_deployment.side_effect = lambda deployment, key: f"{key}:1"
    call_command("init_itsm_itil")
    draft.refresh_from_db()
    assert not draft.is_published
    assert engine.deploy_bpmn.call_count == 3
