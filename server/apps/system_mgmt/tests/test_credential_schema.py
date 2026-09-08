import pytest

from apps.system_mgmt.services.credential_schema import (
    SchemaError,
    secret_field_ids,
    validate_instance_fields,
    validate_type_fields,
    visible_field_ids,
)


def test_validate_type_fields_accepts_supported_schema():
    validate_type_fields(
        [
            {"id": "auth_method", "kind": "enum", "values": ["password", "key"]},
            {"id": "password", "kind": "secret"},
            {"id": "private_key", "kind": "secret"},
            {"id": "port_22", "kind": "number"},
            {"id": "note", "kind": "string"},
        ]
    )


@pytest.mark.parametrize(
    "fields",
    [
        [{"id": "9lives", "kind": "string"}],
        [{"id": "bad-id", "kind": "string"}],
        [
            {"id": "username", "kind": "string"},
            {"id": "username", "kind": "secret"},
        ],
        [{"id": "auth_method", "kind": "enum"}],
        [{"id": "auth_method", "kind": "enum", "values": []}],
        [{"id": "auth_method", "kind": "enum", "values": ["password", 1]}],
        [{"id": "auth_method", "kind": "enum", "values": ["password", "password"]}],
        [{"id": "username", "kind": "unknown"}],
    ],
)
def test_validate_type_fields_rejects_invalid_schema(fields):
    with pytest.raises(SchemaError):
        validate_type_fields(fields)


def test_validate_type_fields_rejects_invalid_visible_when_operator():
    with pytest.raises(SchemaError):
        validate_type_fields(
            [
                {"id": "auth_method", "kind": "enum", "values": ["password", "key"]},
                {
                    "id": "password",
                    "kind": "secret",
                    "visible_when": {"auth_method": {"op": "contains", "value": "pass"}},
                },
            ]
        )


def test_validate_type_fields_rejects_unknown_visible_when_reference():
    with pytest.raises(SchemaError):
        validate_type_fields(
            [
                {
                    "id": "password",
                    "kind": "secret",
                    "visible_when": {"missing": "password"},
                }
            ]
        )


def test_visible_when_uses_and_and_supports_eq_ne_conditions():
    fields = [
        {"id": "transport", "kind": "enum", "values": ["ssh", "telnet"]},
        {"id": "auth_method", "kind": "enum", "values": ["password", "key"]},
        {
            "id": "private_key",
            "kind": "secret",
            "visible_when": {
                "transport": {"op": "eq", "value": "ssh"},
                "auth_method": "key",
            },
        },
        {
            "id": "password",
            "kind": "secret",
            "visible_when": {"auth_method": {"op": "ne", "value": "key"}},
        },
    ]
    validate_type_fields(fields)

    assert visible_field_ids(fields, {"transport": "ssh", "auth_method": "key"}) == {
        "transport",
        "auth_method",
        "private_key",
    }
    assert visible_field_ids(fields, {"transport": "telnet", "auth_method": "key"}) == {
        "transport",
        "auth_method",
    }
    assert visible_field_ids(fields, {"transport": "ssh", "auth_method": "password"}) == {
        "transport",
        "auth_method",
        "password",
    }


def test_secret_field_ids_returns_schema_order():
    fields = [
        {"id": "username", "kind": "string"},
        {"id": "password", "kind": "secret"},
        {"id": "private_key", "kind": "secret"},
    ]
    assert secret_field_ids(fields) == ["password", "private_key"]


def test_validate_instance_fields_requires_secrets_on_creation_and_filters_hidden_fields():
    fields = [
        {"id": "auth_method", "kind": "enum", "values": ["password", "key"]},
        {"id": "username", "kind": "string", "required": True},
        {
            "id": "password",
            "kind": "secret",
            "required": True,
            "visible_when": {"auth_method": "password"},
        },
        {
            "id": "private_key",
            "kind": "secret",
            "required": True,
            "visible_when": {"auth_method": "key"},
        },
    ]

    with pytest.raises(SchemaError):
        validate_instance_fields(
            type_fields=fields,
            values={"auth_method": "password", "username": "root"},
            require_secrets=True,
        )

    assert validate_instance_fields(
        type_fields=fields,
        values={
            "auth_method": "password",
            "username": "root",
            "password": "pw",
            "private_key": "must-not-be-persisted",
        },
        require_secrets=True,
    ) == {"auth_method": "password", "username": "root", "password": "pw"}


def test_validate_instance_fields_update_allows_blank_secret_and_does_not_overwrite_hidden_secret():
    fields = [
        {"id": "auth_method", "kind": "enum", "values": ["password", "key"]},
        {"id": "password", "kind": "secret", "required": True, "visible_when": {"auth_method": "password"}},
        {"id": "private_key", "kind": "secret", "required": True, "visible_when": {"auth_method": "key"}}
    ]

    assert validate_instance_fields(
        type_fields=fields,
        values={
            "auth_method": "key",
            "password": "",
            "private_key": "",
        },
        require_secrets=False,
    ) == {"auth_method": "key", "private_key": ""}


@pytest.mark.parametrize(
    "values",
    [
        {"unknown": "value"},
        {"auth_method": "invalid"},
        {"auth_method": "password", "password": 123},
    ],
)
def test_validate_instance_fields_rejects_unknown_or_invalid_values(values):
    fields = [
        {"id": "auth_method", "kind": "enum", "values": ["password", "key"]},
        {"id": "username", "kind": "string", "required": True},
        {"id": "password", "kind": "secret", "required": True, "visible_when": {"auth_method": "password"}},
    ]
    with pytest.raises(SchemaError):
        validate_instance_fields(type_fields=fields, values=values, require_secrets=False)

def test_validate_instance_fields_rejects_blank_required_non_secret():
    with pytest.raises(SchemaError):
        validate_instance_fields(
            type_fields=[{"id": "username", "kind": "string", "required": True}],
            values={"username": ""},
            require_secrets=False,
        )


def test_validate_instance_fields_checks_number_and_required_values():
    fields = [
        {"id": "username", "kind": "string", "required": True},
        {"id": "port", "kind": "number", "required": True},
    ]
    with pytest.raises(SchemaError):
        validate_instance_fields(type_fields=fields, values={"username": "root"}, require_secrets=False)
    with pytest.raises(SchemaError):
        validate_instance_fields(
            type_fields=fields,
            values={"username": "root", "port": "22"},
            require_secrets=False,
        )
    assert validate_instance_fields(
        type_fields=fields,
        values={"username": "root", "port": 22},
        require_secrets=False,
    ) == {"username": "root", "port": 22}


def test_builtin_type_payloads_match_schema():
    from apps.system_mgmt.services.credential_builtin import BUILTIN_TYPES

    for definition in BUILTIN_TYPES.values():
        validate_type_fields(definition["fields"])


def test_new_builtin_instance_shapes_persist_expected_fields():
    from apps.system_mgmt.services.credential_builtin import BUILTIN_TYPES

    platform = validate_instance_fields(
        type_fields=BUILTIN_TYPES["platform_api"]["fields"],
        values={"username": "ops", "password": "secret", "port": 443, "verify_tls": "true"},
        require_secrets=True,
    )
    assert platform["verify_tls"] == "true"

    network = validate_instance_fields(
        type_fields=BUILTIN_TYPES["network_cli"]["fields"],
        values={"username": "cisco", "password": "login"},
        require_secrets=True,
    )
    assert "enable_password" not in network
    with_enable = validate_instance_fields(
        type_fields=BUILTIN_TYPES["network_cli"]["fields"],
        values={"username": "cisco", "password": "login", "enable_password": "enable"},
        require_secrets=True,
    )
    assert with_enable["enable_password"] == "enable"

    token = validate_instance_fields(
        type_fields=BUILTIN_TYPES["token"]["fields"],
        values={"token": "operator-token"},
        require_secrets=True,
    )
    assert token == {"token": "operator-token"}

    oauth = validate_instance_fields(
        type_fields=BUILTIN_TYPES["oauth_client"]["fields"],
        values={
            "client_id": "app",
            "client_secret": "secret",
            "tenant_id": "tenant",
            "extra": "sub-1",
        },
        require_secrets=True,
    )
    assert oauth["extra"] == "sub-1"
