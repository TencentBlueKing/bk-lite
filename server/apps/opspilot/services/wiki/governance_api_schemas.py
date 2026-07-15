"""Versioned JSON Schema contracts for Wiki directory governance APIs."""

from __future__ import annotations

from copy import deepcopy
from enum import Enum
from types import MappingProxyType

JSON_SCHEMA_DRAFT = "https://json-schema.org/draft/2020-12/schema"
API_SCHEMA_VERSION = 1
STRUCTURE_FORMAT_VERSION = 1
_SCHEMA_ID_BASE = "https://opspilot.bklite.io/schemas/wiki"


class SchemaName(str, Enum):
    STRUCTURE_SAVE_REQUEST = "structure-save-request"
    STRUCTURE_SAVE_RESPONSE = "structure-save-response"
    GENERATION_ACTIVATE_REQUEST = "generation-activate-request"
    GENERATION_ACTIVATE_RESPONSE = "generation-activate-response"
    GENERATION_ROLLBACK_PREVIEW_REQUEST = "generation-rollback-preview-request"
    GENERATION_ROLLBACK_PREVIEW_RESPONSE = "generation-rollback-preview-response"
    GENERATION_ROLLBACK_EXECUTE_REQUEST = "generation-rollback-execute-request"
    GENERATION_ROLLBACK_EXECUTE_RESPONSE = "generation-rollback-execute-response"
    DIRECTORY_OPERATION_PREVIEW_REQUEST = "directory-operation-preview-request"
    DIRECTORY_OPERATION_PREVIEW_RESPONSE = "directory-operation-preview-response"
    DIRECTORY_OPERATION_EXECUTE_REQUEST = "directory-operation-execute-request"
    DIRECTORY_OPERATION_EXECUTE_RESPONSE = "directory-operation-execute-response"
    IMPORT_PREFLIGHT_REQUEST = "import-preflight-request"
    IMPORT_PREFLIGHT_RESPONSE = "import-preflight-response"
    IMPORT_EXECUTE_REQUEST = "import-execute-request"
    IMPORT_EXECUTE_RESPONSE = "import-execute-response"


class UnknownSchemaName(ValueError):
    """Raised when a caller requests an unregistered governance contract."""


def _object(properties, required=(), **keywords):
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": list(required),
    }
    schema.update(keywords)
    return schema


def _positive_id(*, read_only=False):
    schema = {"type": "integer", "minimum": 1}
    if read_only:
        schema["readOnly"] = True
    return schema


def _version():
    return {"type": "integer", "minimum": 0}


def _key(*, read_only=False):
    schema = {
        "type": "string",
        "minLength": 1,
        "maxLength": 128,
        "pattern": "^[A-Za-z][A-Za-z0-9._:-]*$",
    }
    if read_only:
        schema["readOnly"] = True
    return schema


def _hash():
    return {"type": "string", "pattern": "^[0-9a-f]{64}$"}


def _token():
    return {"type": "string", "minLength": 8}


def _nullable_ref(ref):
    return {"oneOf": [{"type": "null"}, {"$ref": ref}]}


def _directory_defs():
    parent_ref = {
        "oneOf": [
            {"type": "null"},
            {"$ref": "#/$defs/existing_directory_ref"},
            {"$ref": "#/$defs/new_directory_ref"},
        ]
    }
    rules = _object(
        {
            "allowed_page_types": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
                "uniqueItems": True,
            },
            "default_for_page_types": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
                "uniqueItems": True,
            },
        },
        ("allowed_page_types", "default_for_page_types"),
    )
    common = {
        "name": {"type": "string", "minLength": 1, "maxLength": 255},
        "description": {"type": "string", "maxLength": 2000},
        "order": {"type": "integer", "minimum": 0},
        "rules": {"$ref": "#/$defs/directory_rules"},
        "parent": {"$ref": "#/$defs/parent_ref"},
    }
    existing = {
        "kind": {"const": "existing"},
        "id": _positive_id(read_only=True),
        "key": _key(read_only=True),
        "origin": {
            "type": "string",
            "enum": ["system", "schema", "manual"],
            "readOnly": True,
        },
        "status": {
            "type": "string",
            "enum": ["active", "retired", "merged", "archived"],
            "readOnly": True,
        },
        **common,
    }
    new = {
        "kind": {"const": "new"},
        "client_ref": {"type": "string", "minLength": 1, "maxLength": 128},
        **common,
    }
    canonical = {
        "id": _positive_id(read_only=True),
        "key": _key(read_only=True),
        "origin": {
            "type": "string",
            "enum": ["system", "schema", "manual"],
            "readOnly": True,
        },
        "status": {
            "type": "string",
            "enum": ["active", "retired", "merged", "archived"],
            "readOnly": True,
        },
        **common,
    }
    canonical["parent"] = {"$ref": "#/$defs/canonical_parent_ref"}
    return {
        "existing_directory_ref": _object(
            {"id": _positive_id(read_only=True), "key": _key(read_only=True)},
            ("id", "key"),
        ),
        "new_directory_ref": _object(
            {"client_ref": {"type": "string", "minLength": 1, "maxLength": 128}},
            ("client_ref",),
        ),
        "parent_ref": parent_ref,
        "canonical_parent_ref": {
            "oneOf": [
                {"type": "null"},
                {"$ref": "#/$defs/existing_directory_ref"},
            ]
        },
        "directory_rules": rules,
        "existing_directory_node": _object(existing, tuple(existing)),
        "new_directory_node": _object(new, tuple(new)),
        "canonical_directory": _object(canonical, tuple(canonical)),
        "client_ref_mapping": _object(
            {
                "client_ref": {"type": "string", "minLength": 1, "maxLength": 128},
                "id": _positive_id(read_only=True),
                "key": _key(read_only=True),
            },
            ("client_ref", "id", "key"),
        ),
    }


def _structure_revision():
    return _object(
        {
            "id": _positive_id(read_only=True),
            "version": _version(),
            "fingerprint": _hash(),
        },
        ("id", "version", "fingerprint"),
    )


def _active_generation():
    return _object(
        {
            "id": _positive_id(read_only=True),
            "structure_revision_id": _positive_id(read_only=True),
            "structure_version": _version(),
            "status": {"const": "active"},
        },
        ("id", "structure_revision_id", "structure_version", "status"),
    )


def _root(name, title, properties, required, *, defs=None, comment=None, **keywords):
    schema = _object(properties, required, **keywords)
    schema.update(
        {
            "$schema": JSON_SCHEMA_DRAFT,
            "$id": f"{_SCHEMA_ID_BASE}/v{API_SCHEMA_VERSION}/{name.value}.json",
            "title": title,
        }
    )
    if defs:
        schema["$defs"] = defs
    if comment:
        schema["$comment"] = comment
    return schema


def _target_only_for_merge():
    return {
        "if": {"properties": {"action": {"const": "merge"}}, "required": ["action"]},
        "then": {"required": ["target"]},
        "else": {"not": {"required": ["target"]}},
    }


def _structure_save_request():
    defs = _directory_defs()
    defs["structure_snapshot"] = _object(
        {
            "format_version": {
                "const": STRUCTURE_FORMAT_VERSION,
                "default": STRUCTURE_FORMAT_VERSION,
            },
            "directories": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "oneOf": [
                        {"$ref": "#/$defs/existing_directory_node"},
                        {"$ref": "#/$defs/new_directory_node"},
                    ]
                },
            },
        },
        ("format_version", "directories"),
    )
    return _root(
        SchemaName.STRUCTURE_SAVE_REQUEST,
        "Wiki structure save request",
        {
            "structure_version": _version(),
            "base_generation_id": _positive_id(),
            "structure": {"$ref": "#/$defs/structure_snapshot"},
        },
        ("structure_version", "base_generation_id", "structure"),
        defs=defs,
    )


def _structure_save_response():
    defs = _directory_defs()
    defs.update(
        {
            "structure_revision": _structure_revision(),
            "active_generation": _active_generation(),
            "structure_snapshot": _object(
                {
                    "format_version": {
                        "const": STRUCTURE_FORMAT_VERSION,
                        "default": STRUCTURE_FORMAT_VERSION,
                    },
                    "directories": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"$ref": "#/$defs/canonical_directory"},
                    },
                },
                ("format_version", "directories"),
            ),
        }
    )
    return _root(
        SchemaName.STRUCTURE_SAVE_RESPONSE,
        "Wiki structure save response",
        {
            "structure_revision": {"$ref": "#/$defs/structure_revision"},
            "active_generation": {"$ref": "#/$defs/active_generation"},
            "structure": {"$ref": "#/$defs/structure_snapshot"},
            "client_ref_map": {
                "type": "array",
                "items": {"$ref": "#/$defs/client_ref_mapping"},
            },
        },
        ("structure_revision", "active_generation", "structure", "client_ref_map"),
        defs=defs,
    )


def _generation_activate_request():
    return _root(
        SchemaName.GENERATION_ACTIVATE_REQUEST,
        "Wiki generation activate request",
        {
            "candidate_generation_id": _positive_id(),
            "base_generation_id": _positive_id(),
            "expected_structure_revision_id": _positive_id(),
            "structure_version": _version(),
        },
        (
            "candidate_generation_id",
            "base_generation_id",
            "expected_structure_revision_id",
            "structure_version",
        ),
    )


def _generation_activate_response():
    defs = {
        "candidate_generation": _object(
            {
                "id": _positive_id(read_only=True),
                "structure_revision_id": _positive_id(read_only=True),
                "structure_version": _version(),
                "status": {"type": "string", "enum": ["active", "superseded", "failed"]},
            },
            ("id", "structure_revision_id", "structure_version", "status"),
        ),
        "active_generation": _active_generation(),
        "superseded_generation": _object(
            {"id": _positive_id(read_only=True), "status": {"const": "superseded"}},
            ("id", "status"),
        ),
        "latest_structure": _object(
            {"revision_id": _positive_id(read_only=True), "version": _version()},
            ("revision_id", "version"),
        ),
    }
    variants = []
    for outcome in ("active", "superseded", "failed"):
        active = outcome == "active"
        variants.append(
            {
                "properties": {
                    "outcome": {"const": outcome},
                    "candidate_generation": {"properties": {"status": {"const": outcome}}},
                    "previous_generation": ({"$ref": "#/$defs/superseded_generation"} if active else {"type": "null"}),
                    "code": {"type": "null"} if active else {"type": "string", "minLength": 1},
                    "reason": {"type": "null"} if active else {"type": "string", "minLength": 1},
                }
            }
        )
    return _root(
        SchemaName.GENERATION_ACTIVATE_RESPONSE,
        "Wiki generation activate outcome",
        {
            "outcome": {"type": "string", "enum": ["active", "superseded", "failed"]},
            "candidate_generation": {"$ref": "#/$defs/candidate_generation"},
            "previous_generation": _nullable_ref("#/$defs/superseded_generation"),
            "latest_active_generation": {"$ref": "#/$defs/active_generation"},
            "latest_structure": {"$ref": "#/$defs/latest_structure"},
            "code": {"oneOf": [{"type": "null"}, {"type": "string", "minLength": 1}]},
            "reason": {"oneOf": [{"type": "null"}, {"type": "string", "minLength": 1}]},
        },
        (
            "outcome",
            "candidate_generation",
            "previous_generation",
            "latest_active_generation",
            "latest_structure",
            "code",
            "reason",
        ),
        defs=defs,
        oneOf=variants,
    )


def _rollback_preview_request():
    return _root(
        SchemaName.GENERATION_ROLLBACK_PREVIEW_REQUEST,
        "Wiki generation rollback preview request",
        {
            "target_generation_id": _positive_id(),
            "base_generation_id": _positive_id(),
            "structure_version": _version(),
        },
        ("target_generation_id", "base_generation_id", "structure_version"),
    )


def _difference():
    return _object(
        {
            "code": {"type": "string", "minLength": 1},
            "path": {"type": "string"},
            "details": {"type": "string", "minLength": 1},
        },
        ("code", "path", "details"),
    )


def _block_reason():
    return _object(
        {
            "code": {"type": "string", "minLength": 1},
            "details": {"type": "string", "minLength": 1},
        },
        ("code", "details"),
    )


def _rollback_preview_response():
    variants = [
        {
            "properties": {
                "outcome": {"const": "compatible"},
                "allow_restore": {"const": False},
            }
        },
        {
            "properties": {
                "outcome": {"const": "requires_structure_restore"},
                "allow_restore": {"const": True},
            }
        },
        {
            "properties": {
                "outcome": {"const": "blocked"},
                "allow_restore": {"const": False},
            }
        },
    ]
    defs = {
        "structure_difference": _difference(),
        "rollback_impact": _object(
            {
                "page_count": {"type": "integer", "minimum": 0},
                "directory_count": {"type": "integer", "minimum": 0},
                "relation_count": {"type": "integer", "minimum": 0},
            },
            ("page_count", "directory_count", "relation_count"),
        ),
        "block_reason": _block_reason(),
    }
    return _root(
        SchemaName.GENERATION_ROLLBACK_PREVIEW_RESPONSE,
        "Wiki generation rollback preview response",
        {
            "outcome": {
                "type": "string",
                "enum": ["compatible", "requires_structure_restore", "blocked"],
            },
            "target_generation_id": _positive_id(read_only=True),
            "structure_diff": {
                "type": "array",
                "items": {"$ref": "#/$defs/structure_difference"},
            },
            "impact": {"$ref": "#/$defs/rollback_impact"},
            "allow_restore": {"type": "boolean"},
            "block_reasons": {
                "type": "array",
                "items": {"$ref": "#/$defs/block_reason"},
            },
        },
        (
            "outcome",
            "target_generation_id",
            "structure_diff",
            "impact",
            "allow_restore",
            "block_reasons",
        ),
        defs=defs,
        oneOf=variants,
    )


def _rollback_execute_request():
    return _root(
        SchemaName.GENERATION_ROLLBACK_EXECUTE_REQUEST,
        "Wiki generation rollback execute request",
        {
            "target_generation_id": _positive_id(),
            "base_generation_id": _positive_id(),
            "structure_version": _version(),
            "confirm_structure_restore": {"type": "boolean"},
        },
        (
            "target_generation_id",
            "base_generation_id",
            "structure_version",
            "confirm_structure_restore",
        ),
    )


def _rollback_execute_response():
    defs = {
        "superseded_generation": _object(
            {"id": _positive_id(read_only=True), "status": {"const": "superseded"}},
            ("id", "status"),
        ),
        "rollback_generation": _object(
            {
                "id": _positive_id(read_only=True),
                "kind": {"const": "rollback"},
                "rollback_of": _positive_id(read_only=True),
                "structure_revision_id": _positive_id(read_only=True),
                "structure_version": _version(),
                "status": {"const": "active"},
            },
            (
                "id",
                "kind",
                "rollback_of",
                "structure_revision_id",
                "structure_version",
                "status",
            ),
        ),
        "structure_result": _object(
            {
                "restored": {"type": "boolean"},
                "previous_structure_revision_id": _positive_id(read_only=True),
                "active_structure_revision_id": _positive_id(read_only=True),
                "structure_version": _version(),
                "fingerprint": _hash(),
            },
            (
                "restored",
                "previous_structure_revision_id",
                "active_structure_revision_id",
                "structure_version",
                "fingerprint",
            ),
        ),
    }
    return _root(
        SchemaName.GENERATION_ROLLBACK_EXECUTE_RESPONSE,
        "Wiki generation rollback execute response",
        {
            "previous_generation": {"$ref": "#/$defs/superseded_generation"},
            "active_generation": {"$ref": "#/$defs/rollback_generation"},
            "structure_result": {"$ref": "#/$defs/structure_result"},
        },
        ("previous_generation", "active_generation", "structure_result"),
        defs=defs,
        comment=(
            "active_generation.id MUST differ from the requested target_generation_id; "
            "active_generation.rollback_of must equal that target. Domain validation enforces "
            "this cross-field invariant."
        ),
    )


def _operation_defs():
    defs = _directory_defs()
    defs.update(
        {
            "redirect": _object(
                {
                    "source": {"$ref": "#/$defs/existing_directory_ref"},
                    "target": {"$ref": "#/$defs/existing_directory_ref"},
                },
                ("source", "target"),
            ),
            "operation_conflict": _object(
                {
                    "code": {"type": "string", "minLength": 1},
                    "details": {"type": "string", "minLength": 1},
                    "source": {"$ref": "#/$defs/existing_directory_ref"},
                    "target": _nullable_ref("#/$defs/existing_directory_ref"),
                },
                ("code", "details", "source", "target"),
            ),
            "block_reason": _block_reason(),
        }
    )
    return defs


def _operation_request(name, title, *, token=False):
    properties = {
        "structure_version": _version(),
        "base_generation_id": _positive_id(),
        "action": {"type": "string", "enum": ["merge", "retire", "archive"]},
        "source": {"$ref": "#/$defs/existing_directory_ref"},
        "target": {"$ref": "#/$defs/existing_directory_ref"},
    }
    required = ["structure_version", "base_generation_id", "action", "source"]
    if token:
        properties = {
            "operation_token": _token(),
            **properties,
            "impact_hash": _hash(),
        }
        required = ["operation_token", *required, "impact_hash"]
    return _root(
        name,
        title,
        properties,
        required,
        defs=_operation_defs(),
        allOf=[_target_only_for_merge()],
    )


def _operation_binding():
    properties = {
        "knowledge_base_id": _positive_id(read_only=True),
        "structure_version": _version(),
        "base_generation_id": _positive_id(),
        "action": {"type": "string", "enum": ["merge", "retire", "archive"]},
        "source": {"$ref": "#/$defs/existing_directory_ref"},
        "target": {"$ref": "#/$defs/existing_directory_ref"},
        "impact_hash": _hash(),
    }
    return _object(
        properties,
        (
            "knowledge_base_id",
            "structure_version",
            "base_generation_id",
            "action",
            "source",
            "impact_hash",
        ),
        allOf=[_target_only_for_merge()],
    )


def _operation_preview_response():
    defs = _operation_defs()
    defs.update(
        {
            "operation_impact": _object(
                {
                    "direct_page_count": {"type": "integer", "minimum": 0},
                    "descendant_page_count": {"type": "integer", "minimum": 0},
                    "manual_page_count": {"type": "integer", "minimum": 0},
                    "child_directory_count": {"type": "integer", "minimum": 0},
                    "conflicts": {
                        "type": "array",
                        "items": {"$ref": "#/$defs/operation_conflict"},
                    },
                    "block_reasons": {
                        "type": "array",
                        "items": {"$ref": "#/$defs/block_reason"},
                    },
                    "redirect": _nullable_ref("#/$defs/redirect"),
                },
                (
                    "direct_page_count",
                    "descendant_page_count",
                    "manual_page_count",
                    "child_directory_count",
                    "conflicts",
                    "block_reasons",
                    "redirect",
                ),
            ),
            "operation_binding": _operation_binding(),
        }
    )
    return _root(
        SchemaName.DIRECTORY_OPERATION_PREVIEW_RESPONSE,
        "Wiki directory destructive operation preview response",
        {
            "impact": {"$ref": "#/$defs/operation_impact"},
            "can_execute": {"type": "boolean"},
            "impact_hash": _hash(),
            "operation_token": _token(),
            "expires_at": {"type": "string", "format": "date-time"},
            "single_use": {"const": True},
            "binding": {"$ref": "#/$defs/operation_binding"},
        },
        (
            "impact",
            "can_execute",
            "impact_hash",
            "operation_token",
            "expires_at",
            "single_use",
            "binding",
        ),
        defs=defs,
    )


def _operation_execute_response():
    defs = _operation_defs()
    action_result = _object(
        {
            "action": {"type": "string", "enum": ["merge", "retire", "archive"]},
            "source": {"$ref": "#/$defs/existing_directory_ref"},
            "target": {"$ref": "#/$defs/existing_directory_ref"},
            "source_status": {"type": "string", "enum": ["merged", "retired", "archived"]},
            "redirect": _nullable_ref("#/$defs/redirect"),
        },
        ("action", "source", "source_status", "redirect"),
        oneOf=[
            {
                "properties": {
                    "action": {"const": "merge"},
                    "source_status": {"const": "merged"},
                    "redirect": {"$ref": "#/$defs/redirect"},
                },
                "required": ["target"],
            },
            {
                "properties": {
                    "action": {"const": "retire"},
                    "source_status": {"const": "retired"},
                },
                "not": {"required": ["target"]},
            },
            {
                "properties": {
                    "action": {"const": "archive"},
                    "source_status": {"const": "archived"},
                },
                "not": {"required": ["target"]},
            },
        ],
    )
    defs.update(
        {
            "structure_revision": _structure_revision(),
            "active_generation": _active_generation(),
            "action_result": action_result,
        }
    )
    return _root(
        SchemaName.DIRECTORY_OPERATION_EXECUTE_RESPONSE,
        "Wiki directory destructive operation execute response",
        {
            "structure_revision": {"$ref": "#/$defs/structure_revision"},
            "active_generation": {"$ref": "#/$defs/active_generation"},
            "action_result": {"$ref": "#/$defs/action_result"},
        },
        ("structure_revision", "active_generation", "action_result"),
        defs=defs,
    )


def _import_defs():
    defs = _directory_defs()
    defs["import_options"] = _object(
        {
            "restore_native_structure": {"type": "boolean"},
            "create_directories_from_folders": {"type": "boolean"},
            "allow_fallback": {"type": "boolean"},
        },
        (
            "restore_native_structure",
            "create_directories_from_folders",
            "allow_fallback",
        ),
    )
    return defs


def _import_target_properties():
    return {
        "target_directory": _nullable_ref("#/$defs/existing_directory_ref"),
        "classification_root_directory": _nullable_ref("#/$defs/existing_directory_ref"),
        "structure_version": _version(),
        "base_generation_id": _positive_id(),
        "options": {"$ref": "#/$defs/import_options"},
    }


def _import_preflight_request():
    properties = {
        "archive_kind": {"type": "string", "enum": ["opspilot_native", "third_party"]},
        **_import_target_properties(),
    }
    return _root(
        SchemaName.IMPORT_PREFLIGHT_REQUEST,
        "Wiki import preflight multipart metadata",
        properties,
        tuple(properties),
        defs=_import_defs(),
        comment=(
            "This JSON document is the metadata part of the same multipart preflight request. "
            "Archive bytes are a separate multipart part; no public upload handle or client hash "
            "is accepted."
        ),
    )


def _import_binding():
    properties = {
        "archive_hash": _hash(),
        "knowledge_base_id": _positive_id(read_only=True),
        "actor_id": _positive_id(read_only=True),
        "archive_kind": {"type": "string", "enum": ["opspilot_native", "third_party"]},
        **_import_target_properties(),
        "quota_version": {"type": "string", "minLength": 1},
    }
    return _object(properties, tuple(properties))


def _import_preflight_response():
    defs = _import_defs()
    defs.update(
        {
            "import_issue": _object(
                {
                    "code": {
                        "type": "string",
                        "enum": [
                            "title_conflict",
                            "unknown_key",
                            "unmapped_path",
                            "invalid_title",
                            "duplicate_file",
                            "directory_depth",
                            "security_limit",
                        ],
                    },
                    "path": {"type": "string"},
                    "details": {"type": "string", "minLength": 1},
                    "severity": {"type": "string", "enum": ["warning", "error"]},
                    "fallback": {"oneOf": [{"type": "null"}, {"type": "string", "minLength": 1}]},
                },
                ("code", "path", "details", "severity", "fallback"),
            ),
            "structure_preview": _object(
                {
                    "restore_native_structure": {"type": "boolean"},
                    "create_directory_count": {"type": "integer", "minimum": 0},
                },
                ("restore_native_structure", "create_directory_count"),
            ),
            "structure_difference": _difference(),
            "import_binding": _import_binding(),
        }
    )
    return _root(
        SchemaName.IMPORT_PREFLIGHT_RESPONSE,
        "Wiki import preflight response",
        {
            "archive_hash": _hash(),
            "new_page_count": {"type": "integer", "minimum": 0},
            "update_page_count": {"type": "integer", "minimum": 0},
            "issues": {"type": "array", "items": {"$ref": "#/$defs/import_issue"}},
            "executable": {"type": "boolean"},
            "requires_confirmation": {"type": "boolean"},
            "structure_preview": _nullable_ref("#/$defs/structure_preview"),
            "structure_diff": {
                "type": "array",
                "items": {"$ref": "#/$defs/structure_difference"},
            },
            "preflight_token": _token(),
            "expires_at": {"type": "string", "format": "date-time"},
            "single_use": {"const": True},
            "binding": {"$ref": "#/$defs/import_binding"},
        },
        (
            "archive_hash",
            "new_page_count",
            "update_page_count",
            "issues",
            "executable",
            "requires_confirmation",
            "structure_preview",
            "structure_diff",
            "preflight_token",
            "expires_at",
            "single_use",
            "binding",
        ),
        defs=defs,
        comment=(
            "The single-use token binds the server-computed archive hash and the server-managed "
            "temporary archive; execute must reauthorize and recompute the hash."
        ),
    )


def _import_execute_request():
    properties = {
        "preflight_token": _token(),
        "archive_hash": _hash(),
        **_import_target_properties(),
    }
    return _root(
        SchemaName.IMPORT_EXECUTE_REQUEST,
        "Wiki import execute request",
        properties,
        tuple(properties),
        defs=_import_defs(),
        comment=(
            "archive_hash is an untrusted echo used for TOCTOU comparison. The server recomputes "
            "the hash from token-associated temporary bytes and rechecks current route KB, actor, "
            "quota and all echoed fields."
        ),
    )


def _import_execute_response():
    defs = {
        "accepted_build": _object(
            {"id": _positive_id(read_only=True), "status": {"const": "accepted"}},
            ("id", "status"),
        ),
        "preparing_generation": _object(
            {"id": _positive_id(read_only=True), "status": {"const": "preparing"}},
            ("id", "status"),
        ),
    }
    return _root(
        SchemaName.IMPORT_EXECUTE_RESPONSE,
        "Wiki import execute response",
        {
            "build": {"$ref": "#/$defs/accepted_build"},
            "generation": {"$ref": "#/$defs/preparing_generation"},
        },
        ("build", "generation"),
        defs=defs,
    )


_SCHEMA_CATALOG = MappingProxyType(
    {
        SchemaName.STRUCTURE_SAVE_REQUEST: _structure_save_request(),
        SchemaName.STRUCTURE_SAVE_RESPONSE: _structure_save_response(),
        SchemaName.GENERATION_ACTIVATE_REQUEST: _generation_activate_request(),
        SchemaName.GENERATION_ACTIVATE_RESPONSE: _generation_activate_response(),
        SchemaName.GENERATION_ROLLBACK_PREVIEW_REQUEST: _rollback_preview_request(),
        SchemaName.GENERATION_ROLLBACK_PREVIEW_RESPONSE: _rollback_preview_response(),
        SchemaName.GENERATION_ROLLBACK_EXECUTE_REQUEST: _rollback_execute_request(),
        SchemaName.GENERATION_ROLLBACK_EXECUTE_RESPONSE: _rollback_execute_response(),
        SchemaName.DIRECTORY_OPERATION_PREVIEW_REQUEST: _operation_request(
            SchemaName.DIRECTORY_OPERATION_PREVIEW_REQUEST,
            "Wiki directory destructive operation preview request",
        ),
        SchemaName.DIRECTORY_OPERATION_PREVIEW_RESPONSE: _operation_preview_response(),
        SchemaName.DIRECTORY_OPERATION_EXECUTE_REQUEST: _operation_request(
            SchemaName.DIRECTORY_OPERATION_EXECUTE_REQUEST,
            "Wiki directory destructive operation execute request",
            token=True,
        ),
        SchemaName.DIRECTORY_OPERATION_EXECUTE_RESPONSE: _operation_execute_response(),
        SchemaName.IMPORT_PREFLIGHT_REQUEST: _import_preflight_request(),
        SchemaName.IMPORT_PREFLIGHT_RESPONSE: _import_preflight_response(),
        SchemaName.IMPORT_EXECUTE_REQUEST: _import_execute_request(),
        SchemaName.IMPORT_EXECUTE_RESPONSE: _import_execute_response(),
    }
)


def get_schema(name: SchemaName | str):
    """Return an isolated copy of a registered schema, failing closed for unknown names."""

    try:
        schema_name = name if isinstance(name, SchemaName) else SchemaName(name)
    except (TypeError, ValueError) as error:
        raise UnknownSchemaName(f"Unknown Wiki governance schema: {name!r}") from error
    return deepcopy(_SCHEMA_CATALOG[schema_name])


__all__ = [
    "JSON_SCHEMA_DRAFT",
    "API_SCHEMA_VERSION",
    "STRUCTURE_FORMAT_VERSION",
    "SchemaName",
    "UnknownSchemaName",
    "get_schema",
]
