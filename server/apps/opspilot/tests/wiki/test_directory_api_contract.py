from copy import deepcopy

import pytest
from jsonschema import Draft202012Validator, ValidationError

from apps.opspilot.services.wiki import governance_api_schemas
from apps.opspilot.services.wiki.governance_api_schemas import API_SCHEMA_VERSION, JSON_SCHEMA_DRAFT, SchemaName, UnknownSchemaName, get_schema


def _validate(name, payload):
    Draft202012Validator(get_schema(name)).validate(payload)


def _assert_invalid(name, payload):
    with pytest.raises(ValidationError):
        _validate(name, payload)


def _directory_ref(directory_id=11, key="dir_product"):
    return {"id": directory_id, "key": key}


def _rules():
    return {
        "allowed_page_types": ["procedure", "faq"],
        "default_for_page_types": ["procedure"],
    }


def _structure_request():
    return {
        "structure_version": 3,
        "base_generation_id": 41,
        "structure": {
            "format_version": 1,
            "page_types": ["concept", "procedure", "faq"],
            "directories": [
                {
                    "kind": "existing",
                    "id": 11,
                    "key": "dir_product",
                    "name": "产品知识",
                    "description": "产品知识根目录",
                    "order": 10,
                    "origin": "schema",
                    "status": "active",
                    "rules": _rules(),
                    "parent": None,
                },
                {
                    "kind": "new",
                    "client_ref": "draft-install",
                    "name": "部署与升级",
                    "description": "安装、升级和回滚流程",
                    "order": 20,
                    "rules": _rules(),
                    "parent": _directory_ref(),
                },
                {
                    "kind": "new",
                    "client_ref": "draft-faq",
                    "name": "常见问题",
                    "description": "常见问题",
                    "order": 30,
                    "rules": _rules(),
                    "parent": {"client_ref": "draft-install"},
                },
            ],
        },
    }


def _active_generation(generation_id=42, structure_revision_id=8, structure_version=4):
    return {
        "id": generation_id,
        "structure_revision_id": structure_revision_id,
        "structure_version": structure_version,
        "status": "active",
    }


def _canonical_directory(directory_id=11, key="dir_product", parent=None):
    return {
        "id": directory_id,
        "key": key,
        "name": "产品知识",
        "description": "产品知识根目录",
        "order": 10,
        "origin": "schema",
        "status": "active",
        "rules": _rules(),
        "parent": parent,
    }


def _operation_binding(action="merge", target=None):
    binding = {
        "knowledge_base_id": 7,
        "structure_version": 3,
        "base_generation_id": 41,
        "action": action,
        "source": _directory_ref(12, "dir_source"),
        "impact_hash": "a" * 64,
    }
    if target is not None:
        binding["target"] = target
    return binding


def _operation_preview_response():
    target = _directory_ref(13, "dir_target")
    return {
        "impact": {
            "direct_page_count": 2,
            "descendant_page_count": 5,
            "manual_page_count": 3,
            "child_directory_count": 1,
            "conflicts": [],
            "block_reasons": [],
            "redirect": {
                "source": _directory_ref(12, "dir_source"),
                "target": target,
            },
        },
        "can_execute": True,
        "impact_hash": "a" * 64,
        "operation_token": "operation-token",
        "expires_at": "2026-07-15T12:00:00Z",
        "single_use": True,
        "binding": _operation_binding(target=target),
    }


def _import_options():
    return {
        "restore_native_structure": True,
        "create_directories_from_folders": False,
        "allow_fallback": True,
    }


def _import_preflight_request():
    return {
        "archive_kind": "opspilot_native",
        "target_directory": _directory_ref(11, "dir_product"),
        "classification_root_directory": _directory_ref(11, "dir_product"),
        "structure_version": 3,
        "base_generation_id": 41,
        "options": _import_options(),
    }


def _import_binding():
    return {
        "archive_hash": "b" * 64,
        "knowledge_base_id": 7,
        "actor_id": 99,
        "archive_kind": "opspilot_native",
        "target_directory": _directory_ref(11, "dir_product"),
        "classification_root_directory": _directory_ref(11, "dir_product"),
        "structure_version": 3,
        "base_generation_id": 41,
        "options": _import_options(),
        "quota_version": "quota-v1",
    }


def _assert_all_object_schemas_are_closed(node):
    if isinstance(node, dict):
        if node.get("type") == "object":
            assert node.get("additionalProperties") is False
        for value in node.values():
            _assert_all_object_schemas_are_closed(value)
    elif isinstance(node, list):
        for value in node:
            _assert_all_object_schemas_are_closed(value)


def test_catalog_is_versioned_draft_2020_12_and_all_objects_are_closed():
    assert set(SchemaName) == {
        SchemaName.STRUCTURE_SAVE_REQUEST,
        SchemaName.STRUCTURE_SAVE_RESPONSE,
        SchemaName.GENERATION_ACTIVATE_REQUEST,
        SchemaName.GENERATION_ACTIVATE_RESPONSE,
        SchemaName.GENERATION_ROLLBACK_PREVIEW_REQUEST,
        SchemaName.GENERATION_ROLLBACK_PREVIEW_RESPONSE,
        SchemaName.GENERATION_ROLLBACK_EXECUTE_REQUEST,
        SchemaName.GENERATION_ROLLBACK_EXECUTE_RESPONSE,
        SchemaName.DIRECTORY_OPERATION_PREVIEW_REQUEST,
        SchemaName.DIRECTORY_OPERATION_PREVIEW_RESPONSE,
        SchemaName.DIRECTORY_OPERATION_EXECUTE_REQUEST,
        SchemaName.DIRECTORY_OPERATION_EXECUTE_RESPONSE,
        SchemaName.IMPORT_PREFLIGHT_REQUEST,
        SchemaName.IMPORT_PREFLIGHT_RESPONSE,
        SchemaName.IMPORT_EXECUTE_REQUEST,
        SchemaName.IMPORT_EXECUTE_RESPONSE,
    }

    for name in SchemaName:
        schema = get_schema(name)
        assert schema["$schema"] == JSON_SCHEMA_DRAFT
        assert schema["$id"].endswith(f"/v{API_SCHEMA_VERSION}/{name.value}.json")
        Draft202012Validator.check_schema(schema)
        _assert_all_object_schemas_are_closed(schema)


def test_api_schema_and_structure_format_versions_can_evolve_independently(monkeypatch):
    monkeypatch.setattr(governance_api_schemas, "API_SCHEMA_VERSION", 7, raising=False)
    monkeypatch.setattr(governance_api_schemas, "STRUCTURE_FORMAT_VERSION", 9, raising=False)

    request_schema = governance_api_schemas._structure_save_request()
    response_schema = governance_api_schemas._structure_save_response()

    assert request_schema["$id"].endswith("/v7/structure-save-request.json")
    assert response_schema["$id"].endswith("/v7/structure-save-response.json")
    for schema in (request_schema, response_schema):
        format_version = schema["$defs"]["structure_snapshot"]["properties"]["format_version"]
        assert format_version == {"const": 9, "default": 9}


def test_catalog_returns_deep_copies_and_unknown_names_fail_closed():
    schema = get_schema(SchemaName.STRUCTURE_SAVE_REQUEST)
    schema["required"].append("caller_mutation")
    schema["$defs"]["directory_rules"]["properties"]["allowed_page_types"]["items"]["minLength"] = 99

    fresh = get_schema(SchemaName.STRUCTURE_SAVE_REQUEST.value)

    assert "caller_mutation" not in fresh["required"]
    assert fresh["$defs"]["directory_rules"]["properties"]["allowed_page_types"]["items"]["minLength"] == 1
    with pytest.raises(UnknownSchemaName):
        get_schema("unregistered-schema")


def test_structure_save_request_separates_existing_and_new_node_identity_shapes():
    payload = _structure_request()
    _validate(SchemaName.STRUCTURE_SAVE_REQUEST, payload)

    schema = get_schema(SchemaName.STRUCTURE_SAVE_REQUEST)
    existing_properties = schema["$defs"]["existing_directory_node"]["properties"]
    for field in ("id", "key", "origin", "status"):
        assert existing_properties[field]["readOnly"] is True

    for forged_field, value in (("id", 999), ("key", "forged-key"), ("origin", "manual"), ("status", "active")):
        invalid = deepcopy(payload)
        invalid["structure"]["directories"][1][forged_field] = value
        _assert_invalid(SchemaName.STRUCTURE_SAVE_REQUEST, invalid)

    invalid = deepcopy(payload)
    invalid["structure"]["directories"][0]["client_ref"] = "forged-client-ref"
    _assert_invalid(SchemaName.STRUCTURE_SAVE_REQUEST, invalid)


def test_structure_save_request_rejects_mixed_parent_identity_and_missing_cas():
    mixed_parent = _structure_request()
    mixed_parent["structure"]["directories"][1]["parent"]["client_ref"] = "draft-install"
    _assert_invalid(SchemaName.STRUCTURE_SAVE_REQUEST, mixed_parent)

    for missing in ("structure_version", "base_generation_id"):
        payload = _structure_request()
        payload.pop(missing)
        _assert_invalid(SchemaName.STRUCTURE_SAVE_REQUEST, payload)

    extra = _structure_request()
    extra["schema_md"] = "not part of the machine contract"
    _assert_invalid(SchemaName.STRUCTURE_SAVE_REQUEST, extra)


def test_structure_snapshot_freezes_revision_page_type_domain():
    payload = _structure_request()
    _validate(SchemaName.STRUCTURE_SAVE_REQUEST, payload)

    missing = deepcopy(payload)
    missing["structure"].pop("page_types")
    _assert_invalid(SchemaName.STRUCTURE_SAVE_REQUEST, missing)

    for invalid_page_types in ([], ["procedure", "procedure"], ["procedure", "   "]):
        invalid = deepcopy(payload)
        invalid["structure"]["page_types"] = invalid_page_types
        _assert_invalid(SchemaName.STRUCTURE_SAVE_REQUEST, invalid)


def test_structure_save_response_returns_canonical_snapshot_and_client_ref_map():
    payload = {
        "structure_revision": {
            "id": 8,
            "version": 4,
            "fingerprint": "c" * 64,
        },
        "active_generation": _active_generation(),
        "structure": {
            "format_version": 1,
            "page_types": ["concept", "procedure", "faq"],
            "directories": [
                _canonical_directory(),
                _canonical_directory(14, "dir_install", _directory_ref()),
            ],
        },
        "client_ref_map": [{"client_ref": "draft-install", "id": 14, "key": "dir_install"}],
    }
    _validate(SchemaName.STRUCTURE_SAVE_RESPONSE, payload)

    client_parent = deepcopy(payload)
    client_parent["structure"]["directories"][1]["parent"] = {"client_ref": "draft-install"}
    _assert_invalid(SchemaName.STRUCTURE_SAVE_RESPONSE, client_parent)


def test_generation_activate_contract_freezes_dual_cas_and_active_outcome():
    request = {
        "candidate_generation_id": 42,
        "base_generation_id": 41,
        "expected_structure_revision_id": 8,
        "structure_version": 4,
    }
    response = {
        "outcome": "active",
        "candidate_generation": _active_generation(),
        "previous_generation": {"id": 41, "status": "superseded"},
        "latest_active_generation": _active_generation(),
        "latest_structure": {"revision_id": 8, "version": 4},
        "code": None,
        "reason": None,
    }

    _validate(SchemaName.GENERATION_ACTIVATE_REQUEST, request)
    _validate(SchemaName.GENERATION_ACTIVATE_RESPONSE, response)

    for missing in ("base_generation_id", "expected_structure_revision_id", "structure_version"):
        invalid = deepcopy(request)
        invalid.pop(missing)
        _assert_invalid(SchemaName.GENERATION_ACTIVATE_REQUEST, invalid)

    invalid = deepcopy(response)
    invalid["previous_generation"]["status"] = "active"
    _assert_invalid(SchemaName.GENERATION_ACTIVATE_RESPONSE, invalid)


@pytest.mark.parametrize(
    ("outcome", "status"),
    [("superseded", "superseded"), ("failed", "failed")],
)
def test_generation_activate_contract_reports_nonactive_machine_outcomes(outcome, status):
    response = {
        "outcome": outcome,
        "candidate_generation": {
            "id": 42,
            "structure_revision_id": 8,
            "structure_version": 4,
            "status": status,
        },
        "previous_generation": None,
        "latest_active_generation": _active_generation(44, 9, 5),
        "latest_structure": {"revision_id": 9, "version": 5},
        "code": f"generation_{outcome}",
        "reason": "active pointers changed or validation failed",
    }
    _validate(SchemaName.GENERATION_ACTIVATE_RESPONSE, response)

    response["reason"] = None
    _assert_invalid(SchemaName.GENERATION_ACTIVATE_RESPONSE, response)


def test_generation_rollback_preview_reports_compatibility_without_a_token():
    request = {
        "target_generation_id": 30,
        "base_generation_id": 41,
        "structure_version": 4,
    }
    response = {
        "outcome": "requires_structure_restore",
        "target_generation_id": 30,
        "structure_diff": [
            {
                "code": "directory_retired",
                "path": "产品知识/旧版",
                "details": "target uses a retired directory",
            }
        ],
        "impact": {"page_count": 12, "directory_count": 3, "relation_count": 7},
        "allow_restore": True,
        "block_reasons": [],
    }
    _validate(SchemaName.GENERATION_ROLLBACK_PREVIEW_REQUEST, request)
    _validate(SchemaName.GENERATION_ROLLBACK_PREVIEW_RESPONSE, response)

    response["operation_token"] = "rollback-does-not-use-token"
    _assert_invalid(SchemaName.GENERATION_ROLLBACK_PREVIEW_RESPONSE, response)


def test_generation_rollback_execute_creates_new_active_row_and_freezes_restore_intent():
    target_generation_id = 30
    request = {
        "target_generation_id": target_generation_id,
        "base_generation_id": 41,
        "structure_version": 4,
        "confirm_structure_restore": True,
    }
    response = {
        "previous_generation": {"id": 41, "status": "superseded"},
        "active_generation": {
            "id": 43,
            "kind": "rollback",
            "rollback_of": target_generation_id,
            "structure_revision_id": 9,
            "structure_version": 5,
            "status": "active",
        },
        "structure_result": {
            "restored": True,
            "previous_structure_revision_id": 8,
            "active_structure_revision_id": 9,
            "structure_version": 5,
            "fingerprint": "d" * 64,
        },
    }

    _validate(SchemaName.GENERATION_ROLLBACK_EXECUTE_REQUEST, request)
    _validate(SchemaName.GENERATION_ROLLBACK_EXECUTE_RESPONSE, response)
    assert response["active_generation"]["id"] != target_generation_id
    assert response["active_generation"]["rollback_of"] == target_generation_id
    assert "MUST differ" in get_schema(SchemaName.GENERATION_ROLLBACK_EXECUTE_RESPONSE)["$comment"]

    missing_confirmation = deepcopy(request)
    missing_confirmation.pop("confirm_structure_restore")
    _assert_invalid(SchemaName.GENERATION_ROLLBACK_EXECUTE_REQUEST, missing_confirmation)

    forged_snapshot = deepcopy(request)
    forged_snapshot["structure_snapshot"] = {"directories": []}
    _assert_invalid(SchemaName.GENERATION_ROLLBACK_EXECUTE_REQUEST, forged_snapshot)


@pytest.mark.parametrize("action", ["retire", "archive"])
def test_directory_operation_preview_allows_target_only_for_merge(action):
    merge = {
        "structure_version": 3,
        "base_generation_id": 41,
        "action": "merge",
        "source": _directory_ref(12, "dir_source"),
        "target": _directory_ref(13, "dir_target"),
    }
    _validate(SchemaName.DIRECTORY_OPERATION_PREVIEW_REQUEST, merge)

    missing_target = deepcopy(merge)
    missing_target.pop("target")
    _assert_invalid(SchemaName.DIRECTORY_OPERATION_PREVIEW_REQUEST, missing_target)

    non_merge = deepcopy(merge)
    non_merge["action"] = action
    _assert_invalid(SchemaName.DIRECTORY_OPERATION_PREVIEW_REQUEST, non_merge)
    non_merge.pop("target")
    _validate(SchemaName.DIRECTORY_OPERATION_PREVIEW_REQUEST, non_merge)

    injected_kb = deepcopy(merge)
    injected_kb["knowledge_base_id"] = 7
    _assert_invalid(SchemaName.DIRECTORY_OPERATION_PREVIEW_REQUEST, injected_kb)


def test_directory_operation_preview_response_echoes_complete_single_use_binding():
    payload = _operation_preview_response()
    _validate(SchemaName.DIRECTORY_OPERATION_PREVIEW_RESPONSE, payload)

    for missing in (
        "knowledge_base_id",
        "structure_version",
        "base_generation_id",
        "action",
        "source",
        "target",
        "impact_hash",
    ):
        invalid = _operation_preview_response()
        invalid["binding"].pop(missing)
        _assert_invalid(SchemaName.DIRECTORY_OPERATION_PREVIEW_RESPONSE, invalid)

    replayable = _operation_preview_response()
    replayable["single_use"] = False
    _assert_invalid(SchemaName.DIRECTORY_OPERATION_PREVIEW_RESPONSE, replayable)


def test_directory_operation_preview_impact_requires_manual_page_count():
    schema = get_schema(SchemaName.DIRECTORY_OPERATION_PREVIEW_RESPONSE)
    impact_schema = schema["$defs"]["operation_impact"]
    assert "manual_page_count" in impact_schema["properties"]
    assert "manual_page_count" in impact_schema["required"]

    payload = _operation_preview_response()
    _validate(SchemaName.DIRECTORY_OPERATION_PREVIEW_RESPONSE, payload)

    payload["impact"].pop("manual_page_count")
    _assert_invalid(SchemaName.DIRECTORY_OPERATION_PREVIEW_RESPONSE, payload)


def test_directory_operation_execute_repeats_comparable_binding_fields():
    payload = {
        "operation_token": "operation-token",
        "structure_version": 3,
        "base_generation_id": 41,
        "action": "merge",
        "source": _directory_ref(12, "dir_source"),
        "target": _directory_ref(13, "dir_target"),
        "impact_hash": "a" * 64,
    }
    _validate(SchemaName.DIRECTORY_OPERATION_EXECUTE_REQUEST, payload)

    for missing in ("structure_version", "base_generation_id", "impact_hash"):
        invalid = deepcopy(payload)
        invalid.pop(missing)
        _assert_invalid(SchemaName.DIRECTORY_OPERATION_EXECUTE_REQUEST, invalid)

    unexpected_kb = deepcopy(payload)
    unexpected_kb["knowledge_base_id"] = 7
    _assert_invalid(SchemaName.DIRECTORY_OPERATION_EXECUTE_REQUEST, unexpected_kb)


def test_directory_operation_execute_response_returns_revision_generation_and_result():
    payload = {
        "structure_revision": {
            "id": 9,
            "version": 4,
            "fingerprint": "e" * 64,
        },
        "active_generation": _active_generation(42, 9, 4),
        "action_result": {
            "action": "merge",
            "source": _directory_ref(12, "dir_source"),
            "target": _directory_ref(13, "dir_target"),
            "source_status": "merged",
            "redirect": {
                "source": _directory_ref(12, "dir_source"),
                "target": _directory_ref(13, "dir_target"),
            },
        },
    }
    _validate(SchemaName.DIRECTORY_OPERATION_EXECUTE_RESPONSE, payload)


def test_import_preflight_request_is_multipart_metadata_without_client_archive_identity():
    payload = _import_preflight_request()
    _validate(SchemaName.IMPORT_PREFLIGHT_REQUEST, payload)

    schema = get_schema(SchemaName.IMPORT_PREFLIGHT_REQUEST)
    assert "multipart" in schema["$comment"]

    for forbidden in ("archive_hash", "archive_upload_id", "archive_base64"):
        invalid = deepcopy(payload)
        invalid[forbidden] = "caller-controlled"
        _assert_invalid(SchemaName.IMPORT_PREFLIGHT_REQUEST, invalid)

    injected_kb = deepcopy(payload)
    injected_kb["knowledge_base_id"] = 7
    _assert_invalid(SchemaName.IMPORT_PREFLIGHT_REQUEST, injected_kb)

    missing_cas = deepcopy(payload)
    missing_cas.pop("base_generation_id")
    _assert_invalid(SchemaName.IMPORT_PREFLIGHT_REQUEST, missing_cas)


def test_import_preflight_response_aggregates_issues_and_complete_binding():
    issue_codes = [
        "title_conflict",
        "unknown_key",
        "unmapped_path",
        "invalid_title",
        "duplicate_file",
        "directory_depth",
        "security_limit",
    ]
    payload = {
        "archive_hash": "b" * 64,
        "new_page_count": 4,
        "update_page_count": 2,
        "issues": [
            {
                "code": code,
                "path": f"docs/{code}.md",
                "details": f"detected {code}",
                "severity": "error",
                "fallback": None,
            }
            for code in issue_codes
        ],
        "executable": False,
        "requires_confirmation": True,
        "structure_preview": {
            "restore_native_structure": True,
            "create_directory_count": 3,
        },
        "structure_diff": [
            {
                "code": "directory_missing",
                "path": "产品知识/旧版",
                "details": "directory will be restored",
            }
        ],
        "preflight_token": "preflight-token",
        "expires_at": "2026-07-15T12:00:00Z",
        "single_use": True,
        "binding": _import_binding(),
    }
    _validate(SchemaName.IMPORT_PREFLIGHT_RESPONSE, payload)
    assert {issue["code"] for issue in payload["issues"]} == set(issue_codes)

    for missing in (
        "archive_hash",
        "knowledge_base_id",
        "actor_id",
        "archive_kind",
        "target_directory",
        "classification_root_directory",
        "structure_version",
        "base_generation_id",
        "options",
        "quota_version",
    ):
        invalid = deepcopy(payload)
        invalid["binding"].pop(missing)
        _assert_invalid(SchemaName.IMPORT_PREFLIGHT_RESPONSE, invalid)

    incomplete_issue = deepcopy(payload)
    incomplete_issue["issues"][0].pop("details")
    _assert_invalid(SchemaName.IMPORT_PREFLIGHT_RESPONSE, incomplete_issue)

    replayable = deepcopy(payload)
    replayable["single_use"] = False
    _assert_invalid(SchemaName.IMPORT_PREFLIGHT_RESPONSE, replayable)


def test_import_execute_echoes_recheck_fields_but_rejects_other_server_binding_fields():
    payload = {
        "preflight_token": "preflight-token",
        "archive_hash": "b" * 64,
        "target_directory": _directory_ref(11, "dir_product"),
        "classification_root_directory": _directory_ref(11, "dir_product"),
        "structure_version": 3,
        "base_generation_id": 41,
        "options": _import_options(),
    }
    _validate(SchemaName.IMPORT_EXECUTE_REQUEST, payload)

    for forbidden in (
        "archive_upload_id",
        "knowledge_base_id",
        "actor_id",
        "quota_version",
    ):
        invalid = deepcopy(payload)
        invalid[forbidden] = "caller-controlled"
        _assert_invalid(SchemaName.IMPORT_EXECUTE_REQUEST, invalid)

    for missing in ("archive_hash", "structure_version", "base_generation_id", "options"):
        invalid = deepcopy(payload)
        invalid.pop(missing)
        _assert_invalid(SchemaName.IMPORT_EXECUTE_REQUEST, invalid)


def test_import_execute_response_returns_accepted_build_and_generation():
    payload = {
        "build": {"id": 501, "status": "accepted"},
        "generation": {"id": 42, "status": "preparing"},
    }
    _validate(SchemaName.IMPORT_EXECUTE_RESPONSE, payload)
