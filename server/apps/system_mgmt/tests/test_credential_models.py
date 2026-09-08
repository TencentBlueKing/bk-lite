import pytest
from django.db import IntegrityError
from django.db.models.deletion import ProtectedError

from apps.system_mgmt.models.credential import Credential, CredentialType


@pytest.mark.django_db
def test_create_credential_type_and_credential():
    credential_type = CredentialType.objects.create(
        key="sql",
        name="数据库账密",
        is_builtin=True,
        categories=["database"],
        fields=[{"id": "username", "kind": "string"}],
    )

    credential = Credential.objects.create(
        credential_id="crd-sql-123",
        name="生产数据库",
        type=credential_type,
        group_id=1,
        fields={"username": "readonly"},
    )

    credential.refresh_from_db()
    assert credential.type_id == "sql"
    assert credential.type == credential_type
    assert credential.fields == {"username": "readonly"}
    assert CredentialType._meta.db_table == "system_mgmt_credentialtype"
    assert Credential._meta.db_table == "system_mgmt_credential"


@pytest.mark.django_db
def test_deleting_referenced_credential_type_raises_protected_error():
    credential_type = CredentialType.objects.create(
        key="ssh",
        name="SSH",
        categories=["host"],
        fields=[],
    )
    Credential.objects.create(
        credential_id="crd-ssh-123",
        name="跳板机",
        type=credential_type,
        group_id=1,
        fields={},
    )

    with pytest.raises(ProtectedError):
        credential_type.delete()


@pytest.mark.django_db
def test_credential_id_is_unique():
    credential_type = CredentialType.objects.create(key="snmp", name="SNMP")
    Credential.objects.create(
        credential_id="crd-snmp-123",
        name="网络设备 1",
        type=credential_type,
        group_id=1,
        fields={},
    )

    with pytest.raises(IntegrityError):
        Credential.objects.create(
            credential_id="crd-snmp-123",
            name="网络设备 2",
            type=credential_type,
            group_id=1,
            fields={},
        )
