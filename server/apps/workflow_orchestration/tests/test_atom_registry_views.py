import pytest
from django.contrib.auth import get_user_model
from django.urls import resolve
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.workflow_orchestration.models import AtomDefinition
from apps.workflow_orchestration.views import AtomDefinitionViewSet, WorkflowViewSet


@pytest.fixture
def atom_admin(db):
    return get_user_model().objects.create(username="atom-admin", domain="example.com", is_superuser=True)


def _request(method, path, user, data=None):
    request = getattr(APIRequestFactory(), method)(path, data or {}, format="json")
    request.COOKIES["current_team"] = "7"
    force_authenticate(request, user=user)
    return request


def test_atom_detail_route_accepts_dotted_atom_keys():
    match = resolve("/api/v1/workflow_orchestration/api/atoms/custom.disk-summary/")

    assert match.url_name == "workflow-orchestration-atom-detail"
    assert match.kwargs["pk"] == "custom.disk-summary"


@pytest.mark.django_db
def test_atom_api_only_keeps_catalog_and_creation_rejection(atom_admin):
    create = AtomDefinitionViewSet.as_view({"post": "create"})

    created = create(_request("post", "/atoms/", atom_admin, {"key": "custom.disk-summary"}))

    assert created.status_code == 405
    assert not hasattr(AtomDefinitionViewSet, "set_status")
    assert not hasattr(AtomDefinitionViewSet, "publish")
    assert not hasattr(AtomDefinitionViewSet, "new_version")
    assert not hasattr(AtomDefinitionViewSet, "validate_draft")


@pytest.mark.django_db
def test_atom_catalog_lists_platform_actions_and_system_nodes(atom_admin):
    listed = AtomDefinitionViewSet.as_view({"get": "list"})(_request("get", "/atoms/?page_size=100", atom_admin))

    assert listed.status_code == 200
    items = listed.data["items"]
    assert any(item["source_type"] == "PLATFORM" and item["node_type"] == "ACTION" for item in items)
    assert {item["node_type"] for item in items}.issuperset({"TRIGGER", "CONTROL", "RETURN"})
    keys = {item["key"] for item in items}
    assert {item["key"] for item in items if item["node_type"] == "TRIGGER"} == {
        "builtin.trigger.form",
        "builtin.trigger.schedule",
        "builtin.trigger.webhook",
        "builtin.trigger.nats",
    }
    assert {item["key"] for item in items if item["node_type"] == "RETURN"} == {
        "builtin.return.webhook",
    }
    assert "bklite_job_execute" in keys
    assert "bklite_rule_evaluate" not in keys
    assert "bklite_data_transform" not in keys
    assert "bklite_document_render" in keys
    assert "bklite_http_request" in keys
    assert "bklite_inspection_group_targets" not in keys
    assert "bklite_inspection_scan" not in keys
    assert "bklite_inspection_scan_linux" not in keys
    assert "bklite_inspection_scan_windows" not in keys

    detail = AtomDefinitionViewSet.as_view({"get": "retrieve"})(
        _request("get", "/atoms/bklite_job_execute/", atom_admin),
        pk="bklite_job_execute",
    )
    assert detail.status_code == 200
    assert "capability_selector" not in detail.data["ui_schema"]
    assert "execution_mode" not in detail.data["input_schema"]["properties"]
    assert "operation" not in detail.data["input_schema"]["properties"]
    assert "assessment_rules" not in detail.data["input_schema"]["properties"]


@pytest.mark.django_db
def test_atom_catalog_filters_node_type_on_server(atom_admin):
    AtomDefinition.objects.create(
        key="package.notify",
        name="包通知",
        category="通知",
        source_type=AtomDefinition.SourceType.PACKAGE,
        team=[],
    )
    list_view = AtomDefinitionViewSet.as_view({"get": "list"})

    listed = list_view(_request("get", "/atoms/?page_size=100&node_type=TRIGGER", atom_admin))

    assert listed.status_code == 200
    assert listed.data["items"]
    assert {item["node_type"] for item in listed.data["items"]} == {"TRIGGER"}
    assert all(item["key"] != "package.notify" for item in listed.data["items"])

    invalid = list_view(_request("get", "/atoms/?node_type=UNKNOWN", atom_admin))
    assert invalid.status_code == 400


@pytest.mark.django_db
def test_atom_catalog_uses_summary_items_and_loads_system_detail_on_demand(atom_admin):
    listed = AtomDefinitionViewSet.as_view({"get": "list"})(_request("get", "/atoms/?page_size=100", atom_admin))

    system_node = next(item for item in listed.data["items"] if item["source_type"] == "SYSTEM")
    assert "input_schema" not in system_node
    assert "output_schema" not in system_node
    assert "ui_schema" not in system_node

    detail = AtomDefinitionViewSet.as_view({"get": "retrieve"})(
        _request("get", f"/atoms/{system_node['key']}/", atom_admin),
        pk=system_node["key"],
    )

    assert detail.status_code == 200
    assert detail.data["key"] == system_node["key"]
    assert detail.data["input_schema"] == {"type": "object"}
    assert detail.data["output_schema"] == {"type": "object"}


@pytest.mark.django_db
def test_platform_actions_are_available_in_the_designer_without_enablement(atom_admin):
    catalog_view = AtomDefinitionViewSet.as_view({"get": "list"})
    designer_view = WorkflowViewSet.as_view({"get": "atoms"})

    listed = catalog_view(_request("get", "/atoms/?page_size=100", atom_admin))
    notification = next(item for item in listed.data["items"] if item["key"] == "bklite_notification")
    assert notification["source_type"] == "PLATFORM"
    assert "status" not in notification
    assert "availability_policy" not in notification

    designer = designer_view(_request("get", "/workflows/atoms/", atom_admin))
    assert "bklite_notification" in {item["key"] for item in designer.data}
    assert all("version" not in item and "driver" not in item and "execution_config" not in item for item in designer.data)

    other_team_request = _request("get", "/workflows/atoms/", atom_admin)
    other_team_request.COOKIES["current_team"] = "8"
    other_team = designer_view(other_team_request)
    assert "bklite_notification" in {item["key"] for item in other_team.data}


@pytest.mark.django_db
def test_system_nodes_are_always_listed_and_are_not_persisted_by_catalog_reads(atom_admin):
    catalog_view = AtomDefinitionViewSet.as_view({"get": "list"})

    listed = catalog_view(_request("get", "/atoms/?page_size=100", atom_admin))
    form_trigger = next(item for item in listed.data["items"] if item["key"] == "builtin.trigger.form")

    assert form_trigger["source_type"] == "SYSTEM"
    assert "status" not in form_trigger
    assert not AtomDefinition.objects.filter(key="builtin.trigger.form").exists()
