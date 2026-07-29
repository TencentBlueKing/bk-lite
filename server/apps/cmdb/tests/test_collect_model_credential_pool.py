from types import SimpleNamespace

import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.serializers.collect_serializer import CollectModelLIstSerializer, CollectModelSerializer
from apps.cmdb.services.collect_credential_pool_service import CollectCredentialPoolService
from apps.cmdb.services.collect_service import CollectModelService


def test_collect_model_decrypt_credentials_supports_credential_pool(monkeypatch):
    instance = CollectModels(
        model_id="host",
        driver_type="job",
        credential=[
            {"credential_id": "cred-1", "password": "enc:first", "username": "admin"},
            {"credential_id": "cred-2", "password": "enc:second", "username": "ops"},
        ],
    )

    monkeypatch.setattr(
        "apps.cmdb.models.collect_model.get_collect_model_passwords",
        lambda collect_model_id, driver_type=None: ["password"],
    )
    monkeypatch.setattr(CollectModels, "decrypt_password", staticmethod(lambda value: f"plain:{value}"))

    decrypted = instance.decrypt_credentials

    assert decrypted == [
        {"credential_id": "cred-1", "password": "plain:enc:first", "username": "admin"},
        {"credential_id": "cred-2", "password": "plain:enc:second", "username": "ops"},
    ]


@pytest.mark.django_db
def test_collect_model_serializer_masks_each_credential_password(monkeypatch):
    instance = CollectModels(
        model_id="host",
        driver_type="job",
        execution_claim_token="must-not-leak",
        credential=[
            {"credential_id": "cred-1", "password": "enc:first", "username": "admin"},
            {"credential_id": "cred-2", "password": "enc:second", "username": "ops"},
        ],
    )

    monkeypatch.setattr(
        "apps.cmdb.serializers.collect_serializer.get_collect_model_passwords",
        lambda collect_model_id, driver_type=None: ["password"],
    )
    monkeypatch.setattr(
        "apps.core.utils.serializers.get_permission_rules",
        lambda user, current_team, app_name, permission_key, include_children: {},
    )

    request = SimpleNamespace(
        user=SimpleNamespace(group_list=[]),
        COOKIES={},
    )

    data = CollectModelSerializer(instance=instance, context={"request": request}).data

    assert data["credential"][0]["password"] == "******"
    assert data["credential"][1]["password"] == "******"
    assert "execution_claim_token" not in data

    list_data = CollectModelLIstSerializer(instance=instance, context={"request": request}).data
    assert "execution_claim_token" not in list_data


def test_collect_model_service_format_update_credential_supports_pool():
    instance = SimpleNamespace(
        is_k8s=False,
        decrypt_credentials=[
            {"credential_id": "cred-1", "password": "old-1", "username": "admin", "port": 22},
            {"credential_id": "cred-2", "password": "old-2", "username": "ops", "port": 22},
        ],
        params={},
    )
    data = {
        "credential": [
            {"credential_id": "cred-1", "password": "", "username": "admin", "port": 22},
            {"credential_id": "cred-2", "username": "ops-new", "port": 22},
        ],
        "params": {},
    }

    CollectModelService.format_update_credential(instance, data)

    assert data["credential"] == [
        {"credential_id": "cred-1", "password": "", "username": "admin", "port": 22},
        {"credential_id": "cred-2", "password": "old-2", "username": "ops-new", "port": 22},
    ]


def test_collect_credential_pool_service_normalize_wraps_legacy_dict():
    pool = CollectCredentialPoolService.normalize_pool({"username": "admin", "password": "plain"})

    assert len(pool) == 1
    assert pool[0]["username"] == "admin"
    assert pool[0]["password"] == "plain"
    assert pool[0]["credential_id"].startswith("cred_")


def test_collect_credential_pool_service_diff_ignores_reorder_and_marks_edit():
    old_pool = [
        {"credential_id": "cred-1", "username": "admin", "password": "one"},
        {"credential_id": "cred-2", "username": "ops", "password": "two"},
    ]
    new_pool = [
        {"credential_id": "cred-2", "username": "ops", "password": "two"},
        {"credential_id": "cred-1", "username": "admin-new", "password": "one"},
    ]

    added_ids, removed_ids, edited_ids = CollectCredentialPoolService.diff_pool(old_pool, new_pool)

    assert added_ids == []
    assert removed_ids == []
    assert edited_ids == ["cred-1"]


def test_validate_pool_shape_allows_mixed_snmp_versions():
    # SNMP 凭据池可混合 v2c 与 v3（每条自带 version，字段集合不同也放行）
    pool = [
        {"credential_id": "cred-1", "version": "v2c", "community": "public", "snmp_port": 161},
        {
            "credential_id": "cred-2", "version": "v3", "username": "ops", "level": "authPriv",
            "integrity": "sha", "privacy": "aes", "authkey": "auth-key-1", "privkey": "priv-key-1",
        },
    ]
    # 不抛异常即通过
    CollectCredentialPoolService.validate_pool_shape(pool)


def test_validate_pool_shape_rejects_v2c_missing_community():
    pool = [{"credential_id": "cred-1", "version": "v2c", "snmp_port": 161}]
    with pytest.raises(BaseAppException):
        CollectCredentialPoolService.validate_pool_shape(pool)


def test_validate_pool_shape_rejects_v3_missing_authkey():
    pool = [
        {"credential_id": "cred-1", "version": "v2c", "community": "public"},
        {"credential_id": "cred-2", "version": "v3", "username": "ops", "level": "authPriv",
         "integrity": "sha", "privacy": "aes", "privkey": "priv-key-1"},  # 缺 authkey
    ]
    with pytest.raises(BaseAppException):
        CollectCredentialPoolService.validate_pool_shape(pool)


def test_validate_pool_shape_rejects_unknown_snmp_version():
    pool = [{"credential_id": "cred-1", "version": "v9", "community": "public"}]
    with pytest.raises(BaseAppException):
        CollectCredentialPoolService.validate_pool_shape(pool)


def test_validate_pool_shape_keeps_field_consistency_for_non_snmp():
    # 非 SNMP（无 version）凭据池：维持原"字段结构一致"约束，混合不同字段应被拒
    pool = [
        {"credential_id": "cred-1", "username": "admin", "password": "one"},
        {"credential_id": "cred-2", "username": "ops", "password": "two", "port": 22},
    ]
    with pytest.raises(BaseAppException):
        CollectCredentialPoolService.validate_pool_shape(pool)


def test_validate_pool_shape_allows_consistent_non_snmp_pool():
    pool = [
        {"credential_id": "cred-1", "username": "admin", "password": "one"},
        {"credential_id": "cred-2", "username": "ops", "password": "two"},
    ]
    CollectCredentialPoolService.validate_pool_shape(pool)


@pytest.mark.django_db
def test_collect_model_serializer_normalizes_legacy_dict_to_pool(monkeypatch):
    instance = CollectModels(
        model_id="host",
        driver_type="job",
        credential={"username": "admin", "password": "enc:first"},
    )

    monkeypatch.setattr(
        "apps.cmdb.serializers.collect_serializer.get_collect_model_passwords",
        lambda collect_model_id, driver_type=None: ["password"],
    )
    monkeypatch.setattr(
        "apps.core.utils.serializers.get_permission_rules",
        lambda user, current_team, app_name, permission_key, include_children: {},
    )

    request = SimpleNamespace(
        user=SimpleNamespace(group_list=[]),
        COOKIES={},
    )

    data = CollectModelSerializer(instance=instance, context={"request": request}).data

    assert isinstance(data["credential"], list)
    assert len(data["credential"]) == 1
    assert data["credential"][0]["credential_id"].startswith("cred_")
    assert data["credential"][0]["password"] == "******"
