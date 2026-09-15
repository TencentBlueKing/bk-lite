import pytest

from apps.core.mixinx import EncryptMixin
from apps.system_mgmt.services.credential_crypto import (
    decrypt_instance_fields,
    encrypt_instance_fields,
    public_instance_fields,
)

pytestmark = pytest.mark.unit


FIELDS = [
    {"id": "username", "kind": "string"},
    {"id": "password", "kind": "secret", "required": True},
    {"id": "private_key", "kind": "secret", "required": True},
    {"id": "passphrase", "kind": "secret"},
]


def encrypted_secret(value, field_id="password"):
    payload = {field_id: value}
    EncryptMixin.encrypt_field(field_id, payload)
    return payload[field_id]


def test_name_only_update_keeps_existing_secret_ciphertext_and_does_not_mutate_inputs():
    old_encrypted = {"username": "old-user", "password": encrypted_secret("old-password")}
    new_values = {"username": "new-user", "password": ""}
    old_snapshot = dict(old_encrypted)
    new_snapshot = dict(new_values)

    result = encrypt_instance_fields(FIELDS, new_values, old_encrypted)

    assert result == {"username": "new-user", "password": old_encrypted["password"]}
    assert old_encrypted == old_snapshot
    assert new_values == new_snapshot


def test_new_secret_is_encrypted_and_decrypts_to_new_value():
    old_encrypted = {"password": encrypted_secret("old-password")}
    new_values = {"username": "new-user", "password": "new-password"}

    result = encrypt_instance_fields(FIELDS, new_values, old_encrypted)

    assert result["password"] != "new-password"
    assert result["password"] != old_encrypted["password"]
    assert decrypt_instance_fields(FIELDS, result) == {
        "username": "new-user",
        "password": "new-password",
    }


def test_decrypt_instance_fields_only_decrypts_secret_values_without_mutating_input():
    encrypted_values = {
        "username": "user",
        "password": encrypted_secret("password"),
        "private_key": encrypted_secret("private-key"),
    }
    snapshot = dict(encrypted_values)

    result = decrypt_instance_fields(FIELDS, encrypted_values)

    assert result == {
        "username": "user",
        "password": "password",
        "private_key": "private-key",
    }
    assert encrypted_values == snapshot


def test_public_instance_fields_removes_every_secret_without_masking_or_mutating_input():
    leftover_secret = encrypted_secret("stale-token", "legacy_token")
    encrypted_values = {
        "username": "user",
        "password": encrypted_secret("password"),
        "private_key": encrypted_secret("private-key"),
        "port": 22,
        "legacy_token": leftover_secret,
    }
    snapshot = dict(encrypted_values)

    result = public_instance_fields(FIELDS, encrypted_values)

    assert result == {"username": "user"}
    assert "password" not in result
    assert "private_key" not in result
    assert "port" not in result
    assert "legacy_token" not in result
    assert "password" in encrypted_values
    assert encrypted_values == snapshot


def test_blank_secret_keeps_ciphertext_including_passphrase_when_private_key_rotates():
    old_encrypted = {
        "username": "user",
        "password": encrypted_secret("old-password"),
        "private_key": encrypted_secret("old-key", "private_key"),
        "passphrase": encrypted_secret("old-passphrase", "passphrase"),
    }

    kept = encrypt_instance_fields(
        FIELDS,
        {"username": "user", "password": "", "private_key": "", "passphrase": ""},
        old_encrypted,
    )
    assert kept["password"] == old_encrypted["password"]
    assert kept["private_key"] == old_encrypted["private_key"]
    assert kept["passphrase"] == old_encrypted["passphrase"]

    rotated = encrypt_instance_fields(
        FIELDS,
        {"username": "user", "private_key": "new-key"},
        old_encrypted,
    )
    assert rotated["passphrase"] == old_encrypted["passphrase"]
    assert decrypt_instance_fields(FIELDS, rotated)["private_key"] == "new-key"

    replaced = encrypt_instance_fields(
        FIELDS,
        {"username": "user", "private_key": "new-key", "passphrase": "new-pp"},
        old_encrypted,
    )
    decrypted = decrypt_instance_fields(FIELDS, replaced)
    assert decrypted["private_key"] == "new-key"
    assert decrypted["passphrase"] == "new-pp"
