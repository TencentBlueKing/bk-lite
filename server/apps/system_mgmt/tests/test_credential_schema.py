import pytest

from apps.system_mgmt.services.credential_schema import (
    SchemaError,
    secret_field_ids,
    type_field_ids,
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
    assert type_field_ids(fields) == {"username", "password", "private_key"}


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
        {"id": "private_key", "kind": "secret", "required": True, "visible_when": {"auth_method": "key"}},
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
    from apps.system_mgmt.services.credential_builtin import builtin_type_payloads

    for definition in builtin_type_payloads().values():
        validate_type_fields(definition["fields"])


def test_new_builtin_instance_shapes_persist_expected_fields():
    from apps.system_mgmt.services.credential_builtin import BUILTIN_TYPES

    # 平台凭据只保存认证信息，端口和 TLS 属于采集任务的连接参数。
    with pytest.raises(SchemaError, match="unknown field ids: port, verify_tls"):
        validate_instance_fields(
            type_fields=BUILTIN_TYPES["platform_api"]["fields"],
            values={"username": "ops", "password": "secret", "port": 443, "verify_tls": True},
            require_secrets=True,
        )
    assert validate_instance_fields(
        type_fields=BUILTIN_TYPES["platform_api"]["fields"],
        values={"username": "ops", "password": "secret"},
        require_secrets=True,
    ) == {"username": "ops", "password": "secret"}

    redfish = validate_instance_fields(
        type_fields=BUILTIN_TYPES["redfish"]["fields"],
        values={"username": "root", "password": "secret"},
        require_secrets=True,
    )
    assert redfish == {"username": "root", "password": "secret"}
    assert {field["id"] for field in BUILTIN_TYPES["redfish"]["fields"]} == {"username", "password"}

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

    ssh_fields = {field["id"]: field for field in BUILTIN_TYPES["ssh"]["fields"]}
    assert "port" not in ssh_fields
    assert ssh_fields["passphrase"]["kind"] == "secret"
    assert ssh_fields["passphrase"].get("required") is not True
    assert ssh_fields["passphrase"]["visible_when"] == {"auth_method": "key"}

    openstack = validate_instance_fields(
        type_fields=BUILTIN_TYPES["openstack"]["fields"],
        values={"username": "demo", "password": "secret"},
        require_secrets=True,
    )
    assert openstack == {"username": "demo", "password": "secret", "user_domain_name": "Default"}
    with pytest.raises(SchemaError, match="user_domain_name"):
        validate_instance_fields(
            type_fields=BUILTIN_TYPES["openstack"]["fields"],
            values={"username": "demo", "password": "secret", "user_domain_name": ""},
            require_secrets=True,
        )


def test_snmp_v3_conditional_required_and_v2c_ignores_leftover_level():
    from apps.system_mgmt.services.credential_builtin import BUILTIN_TYPES

    snmp = BUILTIN_TYPES["snmp"]["fields"]
    version_field = next(field for field in snmp if field["id"] == "version")
    community_field = next(field for field in snmp if field["id"] == "community")
    assert version_field["values"] == ["v2", "v2c", "v3"]
    assert community_field["visible_when"] == {"version": {"op": "ne", "value": "v3"}}
    auth_protocol = next(field for field in snmp if field["id"] == "auth_protocol")
    priv_protocol = next(field for field in snmp if field["id"] == "priv_protocol")
    assert auth_protocol["values"] == ["SHA-1", "SHA-224", "SHA-256", "SHA-384", "SHA-512", "MD5"]
    assert auth_protocol["aliases"] == {"SHA": "SHA-1"}
    assert auth_protocol["default"] == "SHA-1"
    assert priv_protocol["values"] == ["AES-128", "AES-256", "DES"]
    assert priv_protocol["aliases"] == {"AES": "AES-128"}
    assert priv_protocol["default"] == "AES-128"

    v2 = validate_instance_fields(
        type_fields=snmp,
        values={"version": "v2", "community": "public", "security_level": "authPriv"},
        require_secrets=True,
    )
    assert v2 == {"version": "v2", "community": "public"}

    v2c = validate_instance_fields(
        type_fields=snmp,
        values={"version": "v2c", "community": "public", "security_level": "authPriv"},
        require_secrets=True,
    )
    assert v2c == {"version": "v2c", "community": "public"}

    with pytest.raises(SchemaError, match="username"):
        validate_instance_fields(
            type_fields=snmp,
            values={"version": "v3", "security_level": "noAuthNoPriv"},
            require_secrets=True,
        )

    no_auth = validate_instance_fields(
        type_fields=snmp,
        values={"version": "v3", "security_level": "noAuthNoPriv", "username": "monitor"},
        require_secrets=True,
    )
    assert no_auth == {"version": "v3", "security_level": "noAuthNoPriv", "username": "monitor"}

    with pytest.raises(SchemaError, match="auth_password"):
        validate_instance_fields(
            type_fields=snmp,
            values={
                "version": "v3",
                "security_level": "authNoPriv",
                "username": "monitor",
                "auth_protocol": "SHA",
            },
            require_secrets=True,
        )

    auth_priv = validate_instance_fields(
        type_fields=snmp,
        values={
            "version": "v3",
            "security_level": "authPriv",
            "username": "monitor",
            "auth_protocol": "SHA",
            "auth_password": "auth",
            "priv_protocol": "AES",
            "priv_password": "priv",
        },
        require_secrets=True,
    )
    assert auth_priv["auth_protocol"] == "SHA-1"
    assert auth_priv["priv_protocol"] == "AES-128"


def test_enum_aliases_canonicalize_and_reject_invalid_maps():
    fields = [
        {
            "id": "auth_protocol",
            "kind": "enum",
            "values": ["SHA-1", "SHA-256"],
            "aliases": {"SHA": "SHA-1"},
        }
    ]
    assert validate_instance_fields(
        type_fields=fields,
        values={"auth_protocol": "SHA"},
        require_secrets=False,
    ) == {"auth_protocol": "SHA-1"}

    with pytest.raises(SchemaError, match="aliases must point"):
        validate_type_fields([{"id": "auth_protocol", "kind": "enum", "values": ["SHA-1"], "aliases": {"SHA": "SHA-256"}}])


def test_effective_type_fields_uses_code_owned_builtin_snmp_even_when_db_copy_is_stale():
    from types import SimpleNamespace

    from apps.system_mgmt.services.credential_builtin import BUILTIN_TYPES, effective_type_fields

    stale = SimpleNamespace(
        is_builtin=True,
        key="snmp",
        fields=[{"id": "auth_protocol", "kind": "enum", "values": ["MD5", "SHA"]}],
    )
    fields = effective_type_fields(stale)
    auth = next(field for field in fields if field["id"] == "auth_protocol")
    priv = next(field for field in fields if field["id"] == "priv_protocol")
    expected = {field["id"]: field for field in BUILTIN_TYPES["snmp"]["fields"]}
    assert auth["values"] == expected["auth_protocol"]["values"]
    assert auth["aliases"] == expected["auth_protocol"]["aliases"]
    assert priv["values"] == expected["priv_protocol"]["values"]
    assert priv["aliases"] == expected["priv_protocol"]["aliases"]
    fields[0]["values"] = ["mutated"]
    assert BUILTIN_TYPES["snmp"]["fields"][0]["values"] != ["mutated"]

    custom = SimpleNamespace(is_builtin=False, key="custom", fields=[{"id": "token", "kind": "secret"}])
    assert effective_type_fields(custom) == [{"id": "token", "kind": "secret"}]


def test_effective_type_fields_resolves_builtin_seed_fallback_keys():
    from types import SimpleNamespace

    from apps.system_mgmt.services.credential_builtin import BUILTIN_TYPES, effective_type_fields

    fallback = SimpleNamespace(is_builtin=True, key="openstack_account", fields=[])
    fields = effective_type_fields(fallback)
    assert [field["id"] for field in fields] == [field["id"] for field in BUILTIN_TYPES["openstack"]["fields"]]


def test_public_type_overlays_stale_builtin_snmp_fields():
    from types import SimpleNamespace

    from apps.system_mgmt.services.credential_service import _public_type

    listed = _public_type(
        SimpleNamespace(
            key="snmp",
            name="SNMP",
            is_builtin=True,
            categories=["network"],
            fields=[{"id": "auth_protocol", "kind": "enum", "values": ["MD5", "SHA"]}],
            credential_count=1,
        )
    )
    auth = next(field for field in listed["fields"] if field["id"] == "auth_protocol")
    priv = next(field for field in listed["fields"] if field["id"] == "priv_protocol")
    assert auth["values"] == ["SHA-1", "SHA-224", "SHA-256", "SHA-384", "SHA-512", "MD5"]
    assert "SHA-256" in auth["values"]
    assert priv["values"] == ["AES-128", "AES-256", "DES"]
