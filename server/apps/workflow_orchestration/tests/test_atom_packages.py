import json

import pytest
from django.db import IntegrityError, transaction

from apps.workflow_orchestration.models import AtomDefinition
from apps.workflow_orchestration.services.atom_packages import (
    PACKAGE_HANDLERS,
    AtomPackageError,
    atom_requires_trusted_context,
    package_catalog_payload,
    package_task_definitions,
    register_atom_packages,
)
from apps.workflow_orchestration.services.atoms import execute_atom, package_atom_task_definitions
from apps.workflow_orchestration.services.system_nodes import system_node_catalog_payload


def _package(
    tmp_path,
    *,
    key="custom.example",
    name="示例动作",
    description="可发布描述",
    handler="apps.workflow_orchestration.tests.atom_fixtures:passthrough",
):
    package = tmp_path / f"bk-atom-{key.replace('.', '-')}"
    schemas = package / "schemas"
    schemas.mkdir(parents=True, exist_ok=True)
    (schemas / "input.schema.json").write_text(json.dumps({"type": "object", "properties": {"value": {"type": "string"}}}))
    (schemas / "output.schema.json").write_text(json.dumps({"type": "object", "properties": {"value": {"type": "string"}}}))
    (schemas / "ui.schema.json").write_text(json.dumps({"value": {"ui:widget": "textarea"}}))
    (package / "bk-atom.json").write_text(
        json.dumps(
            {
                "key": key,
                "name": name,
                "category": "动作",
                "description": description,
                "driver": "WORKER",
                "handler": handler,
                "input_schema": "schemas/input.schema.json",
                "output_schema": "schemas/output.schema.json",
                "ui_schema": "schemas/ui.schema.json",
                "timeout_seconds": 60,
                "retry_count": 0,
                "retry_delay_seconds": 5,
                "idempotent": True,
                "idempotency_key": "value",
                "safety_level": "READ_ONLY",
                "resource_scope": "ORGANIZATION",
                "required_permissions": ["workflow-Execute"],
                "error_types": ["execution_failed"],
            }
        )
    )
    return package


@pytest.mark.django_db
def test_development_package_registers_current_atom_contract_and_worker_handler(tmp_path):
    _package(tmp_path)

    summary = register_atom_packages(tmp_path)

    atom = AtomDefinition.objects.get(pk="custom.example")
    assert summary == {"packages": 1, "created_atoms": 1, "updated_atoms": 0}
    assert atom.input_schema["properties"]["value"]["type"] == "string"
    assert atom.ui_schema == {"value": {"ui:widget": "textarea"}}
    assert PACKAGE_HANDLERS["custom.example"]({"value": "ok"}) == {"value": "ok"}
    assert execute_atom("custom.example", {"value": "ok"}) == {"value": "ok"}


@pytest.mark.django_db
def test_platform_executable_atoms_share_the_standard_package_contract():
    summary = register_atom_packages()

    catalog = {item["key"]: item for item in package_catalog_payload()}
    definitions = {item["name"]: item for item in package_task_definitions()}
    expected = {
        "bklite_agent",
        "bklite_intent_classification",
        "bklite_memory_read",
        "bklite_memory_write",
        "bklite_notification",
        "bklite_job_execute",
        "bklite_document_render",
        "bklite_http_request",
    }

    assert summary["packages"] == len(expected)
    assert set(catalog) == expected
    assert set(definitions) == expected
    assert all(item["source_type"] == AtomDefinition.SourceType.PLATFORM for item in catalog.values())
    assert all(item["built_in"] is False for item in catalog.values())
    assert all(AtomDefinition.objects.get(pk=key).built_in is False for key in expected)
    assert set(catalog["bklite_agent"]["input_schema"]["properties"]) == {
        "agent_id",
        "knowledge_files",
        "message",
        "prompt",
        "memory_context",
    }
    assert set(catalog["bklite_intent_classification"]["input_schema"]["properties"]) == {
        "model_id",
        "text",
        "intents",
        "classification_rules",
    }
    assert "__bklite_context" not in catalog["bklite_memory_write"]["input_schema"]["properties"]
    assert catalog["bklite_intent_classification"]["safety_level"] == "READ_ONLY"
    assert catalog["bklite_intent_classification"]["input_schema"]["properties"]["intents"]["default"] == ["默认意图"]
    assert "model_id" in catalog["bklite_memory_write"]["input_schema"]["required"]


def test_job_atom_exposes_script_contract_only():
    catalog = {item["key"]: item for item in package_catalog_payload()}

    job = catalog["bklite_job_execute"]
    assert set(job["input_schema"]["properties"]) == {
        "targets",
        "script_type",
        "script_content",
        "execution_params",
        "timeout_seconds",
    }
    assert "capability_selector" not in job["ui_schema"]
    assert "assessment_rules" not in job["input_schema"]["properties"]
    assert "failure_policy" not in job["input_schema"]["properties"]
    targets = job["input_schema"]["properties"]["targets"]
    assert targets["items"] == {"type": "string", "pattern": r"^(node:[^:]+|manual:[0-9]+)$"}
    assert targets["uniqueItems"] is True
    assert "目标管理" in targets["description"] or "节点管理" in targets["description"]
    assert job["ui_schema"]["script_content"]["ui:widget"] == "code"
    assert atom_requires_trusted_context("bklite_job_execute") is True
    assert atom_requires_trusted_context("bklite_document_render") is True
    assert atom_requires_trusted_context("bklite_notification") is True
    assert atom_requires_trusted_context("bklite_http_request") is True


def test_engine_nodes_are_not_atom_packages_or_conductor_task_definitions():
    package_keys = {item["key"] for item in package_catalog_payload()}
    task_types = {item["name"] for item in package_task_definitions()}
    system_keys = {item["key"] for item in system_node_catalog_payload()}

    assert package_keys.isdisjoint(system_keys)
    assert task_types.isdisjoint(system_keys)


@pytest.mark.django_db
def test_removed_platform_package_is_not_registered_as_an_extra_task_definition():
    AtomDefinition.objects.create(
        key="bklite_removed_atom",
        name="已移除原子",
        category="节点管理",
        source_type=AtomDefinition.SourceType.PLATFORM,
        built_in=False,
    )

    task_types = {item["name"] for item in package_atom_task_definitions()}

    assert "bklite_removed_atom" not in task_types


@pytest.mark.django_db
def test_same_key_can_sync_a_backward_compatible_contract_extension(tmp_path):
    package = _package(tmp_path)
    register_atom_packages(tmp_path)
    manifest_path = package / "bk-atom.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["description"] = "增加可选能力后的兼容描述"
    manifest_path.write_text(json.dumps(manifest))

    summary = register_atom_packages(tmp_path)

    atom = AtomDefinition.objects.get(pk="custom.example")
    assert summary == {"packages": 1, "created_atoms": 0, "updated_atoms": 1}
    assert atom.description == "增加可选能力后的兼容描述"


@pytest.mark.django_db
def test_different_atom_keys_cannot_register_the_same_name(tmp_path):
    _package(tmp_path, key="custom.first", name="重复原子名称")
    _package(tmp_path, key="custom.second", name="重复原子名称")

    with pytest.raises(AtomPackageError, match="原子名称.*重复"):
        register_atom_packages(tmp_path)

    assert not AtomDefinition.objects.exists()


@pytest.mark.django_db
def test_package_atom_name_cannot_conflict_with_platform_package(tmp_path):
    _package(tmp_path, key="custom.notify", name="对外通知")

    with pytest.raises(AtomPackageError, match="原子名称.*重复"):
        register_atom_packages(tmp_path)

    assert not AtomDefinition.objects.exists()


@pytest.mark.django_db
def test_database_rejects_duplicate_atom_names():
    AtomDefinition.objects.create(key="custom.first", name="数据库唯一原子", category="动作")

    with pytest.raises(IntegrityError), transaction.atomic():
        AtomDefinition.objects.create(key="custom.second", name="数据库唯一原子", category="动作")

    assert AtomDefinition.objects.filter(name="数据库唯一原子").count() == 1


@pytest.mark.django_db
def test_atom_key_routes_to_the_current_package_handler(tmp_path):
    _package(tmp_path)
    register_atom_packages(tmp_path)
    _package(
        tmp_path,
        handler="apps.workflow_orchestration.tests.atom_fixtures:uppercase",
    )
    register_atom_packages(tmp_path)

    assert execute_atom("custom.example", {"value": "ok"}) == {"value": "OK"}


@pytest.mark.django_db
def test_http_package_requires_method_and_absolute_url(tmp_path):
    package = _package(tmp_path)
    manifest_path = package / "bk-atom.json"
    manifest = json.loads(manifest_path.read_text())
    manifest.update({"driver": "HTTP", "handler": "", "http": {"method": "POST", "url": "/relative"}})
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(AtomPackageError, match="method 和绝对 URL"):
        register_atom_packages(tmp_path)


@pytest.mark.django_db
def test_package_trusted_context_flag_must_be_boolean(tmp_path):
    package = _package(tmp_path)
    manifest_path = package / "bk-atom.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["trusted_context"] = "false"
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(AtomPackageError, match="trusted_context 必须是布尔值"):
        register_atom_packages(tmp_path)


@pytest.mark.django_db
def test_package_schema_path_cannot_escape_its_directory(tmp_path):
    package = _package(tmp_path)
    outside = tmp_path / "outside.schema.json"
    outside.write_text(json.dumps({"type": "object"}))
    manifest_path = package / "bk-atom.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["input_schema"] = "../outside.schema.json"
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(AtomPackageError, match="必须位于原子包目录内"):
        register_atom_packages(tmp_path)
