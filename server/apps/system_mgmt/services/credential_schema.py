import re
from collections.abc import Mapping


class SchemaError(ValueError):
    """Raised when a credential type or instance does not match its schema."""


_FIELD_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_KINDS = {"string", "number", "secret", "enum"}


def _schema_fields(fields: list) -> list[dict]:
    if not isinstance(fields, list):
        raise SchemaError("fields must be a list")

    ids: set[str] = set()
    for field in fields:
        if not isinstance(field, Mapping):
            raise SchemaError("each field must be an object")
        field_id = field.get("id")
        if not isinstance(field_id, str) or not _FIELD_ID.fullmatch(field_id):
            raise SchemaError(f"invalid field id: {field_id!r}")
        if field_id in ids:
            raise SchemaError(f"duplicate field id: {field_id}")
        ids.add(field_id)

        kind = field.get("kind")
        if kind not in _KINDS:
            raise SchemaError(f"invalid field kind for {field_id}")
        if kind == "enum":
            enum_values = field.get("values")
            if (
                not isinstance(enum_values, list)
                or not enum_values
                or any(not isinstance(value, str) for value in enum_values)
                or len(set(enum_values)) != len(enum_values)
            ):
                raise SchemaError(f"enum field {field_id} requires unique string values")

    for field in fields:
        visible_when = field.get("visible_when")
        if visible_when is None:
            continue
        if not isinstance(visible_when, Mapping):
            raise SchemaError(f"visible_when for {field['id']} must be an object")
        for referenced_id, condition in visible_when.items():
            if referenced_id not in ids:
                raise SchemaError(
                    f"visible_when for {field['id']} references unknown field {referenced_id}"
                )
            if isinstance(condition, str):
                continue
            if not isinstance(condition, Mapping):
                raise SchemaError(f"invalid visible_when condition for {field['id']}")
            if condition.get("op") not in {"eq", "ne"} or not isinstance(
                condition.get("value"), str
            ):
                raise SchemaError(f"invalid visible_when condition for {field['id']}")

    return [dict(field) for field in fields]


def validate_type_fields(fields: list) -> None:
    _schema_fields(fields)


def secret_field_ids(fields: list) -> list[str]:
    return [field["id"] for field in _schema_fields(fields) if field["kind"] == "secret"]


def _condition_matches(condition: object, actual: object) -> bool:
    if not isinstance(actual, str):
        return False
    if isinstance(condition, str):
        return actual == condition
    if condition["op"] == "eq":
        return actual == condition["value"]
    return actual != condition["value"]


def visible_field_ids(fields: list, values: dict) -> set[str]:
    schema_fields = _schema_fields(fields)
    if not isinstance(values, dict):
        raise SchemaError("values must be an object")

    visible: set[str] = set()
    for field in schema_fields:
        conditions = field.get("visible_when")
        if not conditions or all(
            referenced_id in values
            and _condition_matches(condition, values[referenced_id])
            for referenced_id, condition in conditions.items()
        ):
            visible.add(field["id"])
    return visible


def _validate_value(field: dict, value: object) -> None:
    field_id = field["id"]
    kind = field["kind"]
    if kind in {"string", "secret"}:
        if not isinstance(value, str):
            raise SchemaError(f"field {field_id} must be a string")
    elif kind == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise SchemaError(f"field {field_id} must be a number")
    elif value not in field["values"]:
        raise SchemaError(f"field {field_id} has an invalid enum value")


def validate_instance_fields(*, type_fields, values, require_secrets: bool) -> dict:
    schema_fields = _schema_fields(type_fields)
    if not isinstance(values, dict):
        raise SchemaError("values must be an object")

    schema_by_id = {field["id"]: field for field in schema_fields}
    unknown_ids = set(values) - schema_by_id.keys()
    if unknown_ids:
        raise SchemaError(
            f"unknown field ids: {', '.join(sorted(map(str, unknown_ids)))}"
        )

    visible_ids = visible_field_ids(schema_fields, values)
    persisted: dict = {}
    for field in schema_fields:
        field_id = field["id"]
        if field_id not in visible_ids:
            continue
        if field_id not in values:
            if field.get("required") and field["kind"] != "secret":
                raise SchemaError(f"field {field_id} is required")
            if require_secrets and field["kind"] == "secret" and field.get("required"):
                raise SchemaError(f"secret field {field_id} is required")
            continue

        value = values[field_id]
        _validate_value(field, value)
        if field.get("required") and value == "" and (
            require_secrets or field["kind"] != "secret"
        ):
            raise SchemaError(f"field {field_id} is required")
        if require_secrets and field["kind"] == "secret" and field.get("required") and value == "":
            raise SchemaError(f"secret field {field_id} is required")
        if field["kind"] == "secret" and value == "" and not field.get("required"):
            continue
        persisted[field_id] = value

    return persisted
