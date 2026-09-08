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
    {"id": "password", "kind": "secret"},
    {"id": "private_key", "kind": "secret"},
]


def encrypted_secret(value):
    payload = {"password": value}
    EncryptMixin.encrypt_field("password", payload)
    return payload["password"]


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
    encrypted_values = {
        "username": "user",
        "password": encrypted_secret("password"),
        "private_key": encrypted_secret("private-key"),
    }
    snapshot = dict(encrypted_values)

    result = public_instance_fields(FIELDS, encrypted_values)

    assert result == {"username": "user"}
    assert "password" not in result
    assert "private_key" not in result
    assert "password" in encrypted_values
    assert encrypted_values == snapshot
