from types import SimpleNamespace

import pytest

from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.serializers.collect_serializer import CollectModelLIstSerializer, CollectModelSerializer
from apps.cmdb.services.collect_credential_pool_service import CollectCredentialPoolService
from apps.cmdb.services.collect_service import CollectModelService
from apps.core.exceptions.base_app_exception import BaseAppException


@pytest.mark.django_db
@pytest.mark.parametrize("source", ["inline", "vault"])
def test_task_name_uniqueness_is_independent_of_credential_source(source, monkeypatch):
    from rest_framework.exceptions import ValidationError

    existing = CollectModels.objects.create(name="vc254", model_id="vmware_vc", driver_type="protocol", task_type="vmware")
    attrs = {
        "name": "vc254",
        "model_id": "vmware_vc",
        "driver_type": "protocol",
        "credential": {"credential_source": source, "port": 443, "ssl": False},
    }
    monkeypatch.setattr("apps.core.utils.serializers.get_permission_rules", lambda *args, **kwargs: {})
    context = {"request": SimpleNamespace(user=SimpleNamespace(group_list=[]), COOKIES={})}
    create_serializer = CollectModelSerializer(context=context)
    with pytest.raises(ValidationError) as error:
        create_serializer.run_validators(attrs)
    assert error.value.get_codes() == ["unique"]
    # Editing the existing task excludes itself; a differently named new task is valid.
    CollectModelSerializer(instance=existing, context=context).run_validators(attrs)
    create_serializer.run_validators({**attrs, "name": "vc254-new"})


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


def test_collect_credential_pool_accepts_mixed_sources_without_copying_vault_secret():
    pool = CollectCredentialPoolService.normalize_pool(
        [
            {"username": "ops", "password": "inline-only", "port": 22},
            {"credential_source": "vault", "vault_credential_id": "crd-ssh-1", "port": 2222},
        ]
    )
    CollectCredentialPoolService.validate_pool_shape(pool)
    assert pool[0].get("credential_source", "inline") == "inline"
    assert pool[1] == {
        "credential_source": "vault",
        "vault_credential_id": "crd-ssh-1",
        "port": 2222,
        "credential_id": pool[1]["credential_id"],
        "credential_version": 1,
    }


@pytest.mark.parametrize(
    "item",
    [
        {"credential_source": "vault", "port": 22},
        {"credential_source": "vault", "vault_credential_id": 123},
        {"credential_source": "inline", "vault_credential_id": "crd-ssh-1"},
        {"credential_source": "unknown", "username": "ops"},
    ],
)
def test_collect_credential_pool_rejects_invalid_source(item):
    with pytest.raises(BaseAppException):
        CollectCredentialPoolService.normalize_pool(item)


def test_inline_source_cleans_stale_vault_type_and_actor_metadata():
    item = CollectCredentialPoolService.normalize_pool(
        {
            "credential_source": "inline",
            "vault_type_key": "sql",
            "vault_actor_context": {"username": "old"},
            "username": "db",
            "password": "secret",
        }
    )[0]
    assert "vault_type_key" not in item
    assert "vault_actor_context" not in item


def test_switch_from_inline_to_vault_drops_old_auth_fields():
    instance = SimpleNamespace(
        is_k8s=False,
        decrypt_credentials=[{"credential_id": "cred-1", "username": "old-user", "password": "old-secret", "port": 22}],
    )
    data = {"credential": [{"credential_id": "cred-1", "credential_source": "vault", "vault_credential_id": "crd-ssh-1", "port": 2222}]}
    CollectModelService.format_update_credential(instance, data)
    assert data["credential"] == [{"credential_id": "cred-1", "credential_source": "vault", "vault_credential_id": "crd-ssh-1", "port": 2222}]


def test_switch_from_vault_to_inline_drops_reference_and_requires_new_auth():
    instance = SimpleNamespace(
        is_k8s=False,
        decrypt_credentials=[{"credential_id": "cred-1", "credential_source": "vault", "vault_credential_id": "crd-ssh-1", "port": 22}],
    )
    data = {"credential": [{"credential_id": "cred-1", "credential_source": "inline", "username": "new", "password": "new-secret", "port": 22}]}
    CollectModelService.format_update_credential(instance, data)
    assert data["credential"][0].get("vault_credential_id") is None
    assert data["credential"][0]["password"] == "new-secret"


def test_switch_from_vault_to_inline_without_new_auth_is_rejected():
    instance = SimpleNamespace(
        is_k8s=False,
        decrypt_credentials=[{"credential_id": "cred-1", "credential_source": "vault", "vault_credential_id": "crd-1", "port": 22}],
    )
    with pytest.raises(BaseAppException):
        CollectModelService.format_update_credential(
            instance, {"credential": [{"credential_id": "cred-1", "credential_source": "inline", "username": "ops", "port": 22}]}
        )


def _validation_serializer(monkeypatch):
    monkeypatch.setattr("apps.core.utils.serializers.get_permission_rules", lambda *args, **kwargs: {})
    request = SimpleNamespace(user=SimpleNamespace(username="operator", group_list=[]), COOKIES={})
    return CollectModelSerializer(context={"request": request})


def test_serializer_accepts_vault_reference_and_keeps_only_dynamic_port(monkeypatch):
    serializer = _validation_serializer(monkeypatch)
    attrs = {
        "model_id": "mysql",
        "task_type": "sql",
        "driver_type": "protocol",
        "credential": [{"credential_source": "vault", "vault_credential_id": "crd-sql-1", "port": 3306}],
        "params": {},
    }
    result = serializer.validate(attrs)
    assert result["credential"][0]["vault_credential_id"] == "crd-sql-1"
    assert "password" not in result["credential"][0]


def test_serializer_rejects_invalid_dynamic_port_for_vault_reference(monkeypatch):
    serializer = _validation_serializer(monkeypatch)
    attrs = {
        "model_id": "mysql",
        "task_type": "sql",
        "driver_type": "protocol",
        "credential": [{"credential_source": "vault", "vault_credential_id": "crd-sql-1", "port": 70000}],
        "params": {},
    }
    with pytest.raises(Exception) as exc:
        serializer.validate(attrs)
    assert "端口" in str(exc.value)


@pytest.mark.parametrize(
    "model_id,task_type,credential,params",
    [
        ("influxdb", "sql", {"credential_source": "inline", "scheme": "http", "port": 8086, "verify_tls": True, "token": "fixture-token"}, {}),
        ("storage", "storage", {"credential_source": "inline", "username": "ops", "password": "fixture-secret", "port": 443, "verify_tls": True}, {}),
        (
            "physcial_server",
            "host",
            {"credential_source": "inline", "username": "admin", "password": "fixture-secret", "port": 443, "verify_tls": True},
            {"collection_protocol": "redfish"},
        ),
    ],
)
def test_inline_source_marker_keeps_existing_specialized_validation(monkeypatch, model_id, task_type, credential, params):
    serializer = _validation_serializer(monkeypatch)
    attrs = {
        "model_id": model_id,
        "task_type": task_type,
        "driver_type": "protocol",
        "credential": [credential],
        "params": params,
    }
    if model_id == "influxdb":
        attrs["instances"] = [{"inst_uuid": "df5e941f-26d7-4d85-9988-5e6c4a0c9c00", "ip_addr": "192.0.2.1"}]
        monkeypatch.setattr(serializer, "_normalize_instance_identity_contract", lambda instances, model: instances)
    result = serializer.validate(attrs)
    assert result["credential"][0]["credential_source"] == "inline"


def test_pc_windows_vault_reference_passes_policy_without_copying_auth(monkeypatch):
    serializer = _validation_serializer(monkeypatch)
    attrs = {
        "model_id": "pc",
        "task_type": "host",
        "driver_type": "job",
        "timeout": 60,
        "credential": [{"credential_source": "vault", "vault_credential_id": "crd-winrm-1", "port": 5986}],
        "params": {"os_type": "windows", "winrm_scheme": "https"},
    }
    result = serializer.validate(attrs)
    assert result["credential"][0]["vault_credential_id"] == "crd-winrm-1"
    assert "password" not in result["credential"][0]


def test_service_overwrites_client_supplied_vault_actor_and_keeps_unchanged_binder(monkeypatch):
    monkeypatch.setattr("apps.cmdb.services.collect_service.get_current_team_from_request", lambda request: 4)
    request = SimpleNamespace(user=SimpleNamespace(username="new-operator", domain="example.com"))
    old = [
        {
            "credential_id": "cred-1",
            "credential_source": "vault",
            "vault_credential_id": "crd-1",
            "vault_actor_context": {"username": "old", "domain": "example.com", "current_team": 3},
        }
    ]
    changed = [
        {
            "credential_id": "cred-1",
            "credential_source": "vault",
            "vault_credential_id": "crd-2",
            "vault_actor_context": {"username": "attacker", "domain": "bad", "current_team": 999},
        }
    ]
    CollectModelService._bind_vault_credentials(request, changed, old)
    assert changed[0]["vault_actor_context"] == {"username": "new-operator", "domain": "example.com", "current_team": 4}
    unchanged = [
        {"credential_id": "cred-1", "credential_source": "vault", "vault_credential_id": "crd-1", "vault_actor_context": {"username": "attacker"}}
    ]
    CollectModelService._bind_vault_credentials(request, unchanged, old)
    assert unchanged[0]["vault_actor_context"] == old[0]["vault_actor_context"]
    CollectModelService._bind_vault_credentials(request, unchanged, old, force_rebind=True)
    assert unchanged[0]["vault_actor_context"] == {"username": "new-operator", "domain": "example.com", "current_team": 4}


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


def test_collect_credential_versions_only_advance_for_edited_item():
    old_pool = [
        {
            "credential_id": "cred-1",
            "credential_version": 4,
            "username": "admin",
            "password": "one",
        },
        {
            "credential_id": "cred-2",
            "credential_version": 7,
            "username": "ops",
            "password": "two",
        },
    ]
    reordered_and_edited = [
        {"credential_id": "cred-2", "username": "ops", "password": "two"},
        {
            "credential_id": "cred-1",
            "username": "admin-new",
            "password": "one",
        },
        {"credential_id": "cred-3", "username": "new", "password": "three"},
    ]

    versioned = CollectCredentialPoolService.assign_versions(
        old_pool,
        CollectCredentialPoolService.normalize_pool(reordered_and_edited),
    )

    assert [(item["credential_id"], item["credential_version"]) for item in versioned] == [
        ("cred-2", 7),
        ("cred-1", 5),
        ("cred-3", 1),
    ]


def test_validate_pool_shape_allows_mixed_snmp_versions():
    # SNMP 凭据池可混合 v2c 与 v3（每条自带 version，字段集合不同也放行）
    pool = [
        {"credential_id": "cred-1", "version": "v2c", "community": "public", "snmp_port": 161},
        {
            "credential_id": "cred-2",
            "version": "v3",
            "username": "ops",
            "level": "authPriv",
            "integrity": "sha",
            "privacy": "aes",
            "authkey": "auth-key-1",
            "privkey": "priv-key-1",
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
        {
            "credential_id": "cred-2",
            "version": "v3",
            "username": "ops",
            "level": "authPriv",
            "integrity": "sha",
            "privacy": "aes",
            "privkey": "priv-key-1",
        },  # 缺 authkey
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


# ---- PC 发现：真实加密字段集合与序列化脱敏（不 mock get_collect_model_passwords） ----


def test_pc_encrypted_fields_cover_all_secret_kinds():
    from apps.cmdb.services.encrypt_collect_password import get_collect_model_passwords

    assert set(get_collect_model_passwords("pc", "job")) == {"password", "private_key", "passphrase"}


@pytest.mark.django_db
def test_pc_serializer_masks_password_private_key_and_passphrase(monkeypatch):
    instance = CollectModels(
        model_id="pc",
        driver_type="job",
        credential=[
            {
                "credential_id": "cred-win",
                "username": "ACME\\alice",
                "password": "enc:win-secret",
                "port": 5986,
            },
            {
                "credential_id": "cred-mac",
                "username": "admin",
                "private_key": "enc:-----BEGIN OPENSSH PRIVATE KEY-----\nKEYDATA\n-----END OPENSSH PRIVATE KEY-----",
                "passphrase": "enc:pc-passphrase",
                "port": 22,
            },
        ],
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

    win, mac = data["credential"]
    assert win["password"] == "******"
    assert win["username"] == "ACME\\alice"
    assert win["port"] == 5986
    assert mac["private_key"] == "******"
    assert mac["passphrase"] == "******"
    assert mac["username"] == "admin"
    blob = str(data)
    assert "win-secret" not in blob
    assert "KEYDATA" not in blob
    assert "pc-passphrase" not in blob


@pytest.mark.django_db
@pytest.mark.parametrize("type_key", ["platform_api", "ssh"])
def test_platform_reference_supplemental_secret_is_encrypted_and_masked(monkeypatch, type_key):
    monkeypatch.setattr("apps.core.utils.serializers.get_permission_rules", lambda *args, **kwargs: {})
    task = CollectModels.objects.create(
        model_id="network_config_file",
        driver_type="protocol",
        credential=CollectCredentialPoolService.normalize_pool(
            [
                {
                    "credential_source": "vault",
                    "vault_type_key": type_key,
                    "vault_credential_id": "platform-1",
                    "enable_password": "supplemental-secret",
                    "port": 22,
                }
            ]
        ),
    )
    task.refresh_from_db()
    assert task.credential[0]["enable_password"] != "supplemental-secret"
    assert task.decrypt_credentials[0]["enable_password"] == "supplemental-secret"
    request = SimpleNamespace(user=SimpleNamespace(group_list=[]), COOKIES={})
    assert CollectModelSerializer(instance=task, context={"request": request}).data["credential"][0]["enable_password"] == "******"
