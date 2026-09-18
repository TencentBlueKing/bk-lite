"""凭据接入不得改变历史表单；每个入口按冻结的原表单清单核对。"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.cmdb.services.collect_vault_binding import actual_builtin_type_keys, binding_for_collect_object
from apps.cmdb.services.collect_vault_resolver import resolve_task_credential_pool
from apps.system_mgmt.models import Credential, CredentialType
from apps.system_mgmt.services.credential_builtin import BUILTIN_TYPES
from apps.system_mgmt.services.credential_service import seed_builtin_types

ENTRIES = json.loads((Path(__file__).parent / "fixtures/collection_original_forms.json").read_text())
ACTOR = {"username": "operator", "domain": "test", "current_team": 1}
FIELDS = {
    "ssh": {"username": "account-value", "password": "secret-value", "auth_method": "password"},
    "sql": {"username": "account-value", "password": "secret-value"},
    "platform_api": {"username": "account-value", "password": "secret-value"},
    "winrm": {"username": "account-value", "password": "secret-value"},
    "ipmi": {"username": "account-value", "password": "secret-value"},
    "redfish": {"username": "account-value", "password": "secret-value"},
    "snmp": {"version": "v2c", "community": "secret-value"},
    "cloud": {"access_key": "account-value", "secret_key": "secret-value"},
    "token": {"token": "secret-value"},
    "network_cli": {"username": "account-value", "password": "secret-value", "enable_password": "enable-value"},
    "oauth_client": {"client_id": "account-value", "client_secret": "secret-value", "tenant_id": "tenant-value"},
    "openstack": {"username": "account-value", "password": "secret-value", "user_domain_name": "Default"},
}


@pytest.mark.parametrize("entry", ENTRIES, ids=lambda entry: entry["id"])
def test_each_original_entry_has_its_classified_credential_type(entry):
    assert (
        binding_for_collect_object(
            entry["id"],
            model_id=entry["model_id"],
            driver_type=entry["type"],
            protocol=entry["credential_protocol"],
        )
        == entry["binding"]
    )


@pytest.mark.django_db
def test_all_118_entries_find_real_seeded_types_after_repeated_initialization():
    seed_builtin_types()
    first = set(CredentialType.objects.values_list("pk", flat=True))
    seed_builtin_types()
    assert set(CredentialType.objects.values_list("pk", flat=True)) == first
    rows = list(CredentialType.objects.all())
    for entry in ENTRIES:
        keys = actual_builtin_type_keys(entry["binding"], rows)
        assert bool(keys) == bool(entry["binding"]), entry["id"]
        if keys:
            assert keys == [entry["binding"].split("/")[1]], entry["id"]


@pytest.mark.django_db
def test_upgrade_old_categories_restores_all_entries_without_changing_credentials():
    seed_builtin_types()
    for key, categories in {
        "sql": ["database", "middleware"],
        "snmp": ["network"],
        "platform_api": ["cloud", "storage"],
        "cloud": ["cloud"],
    }.items():
        CredentialType.objects.filter(key=key).update(categories=categories)
    custom = CredentialType.objects.create(key="custom-device", name="自定义", categories=["network"], fields=[])
    credential = Credential.objects.create(
        credential_id="upgrade-test",
        name="已有账户",
        type_id="sql",
        group_id=1,
        fields={"username": "test-account", "password": "opaque-encrypted-test-value"},
    )
    original_fields = dict(credential.fields)
    rows = list(CredentialType.objects.all())
    missing = {e["id"] for e in ENTRIES if e["binding"] and not actual_builtin_type_keys(e.get("legacy_binding", e["binding"]), rows)}
    assert missing == {
        "docker",
        "host",
        "config_file",
        "physcial_server",
        "hmc",
        "brocade_fc",
        "cisco_fc",
        "network_config_file",
        "ibm_ds",
        "xsky",
        "tape_library",
        "macrosan",
    }
    seed_builtin_types()
    seed_builtin_types()
    rows = list(CredentialType.objects.all())
    assert all(actual_builtin_type_keys(e["binding"], rows) for e in ENTRIES if e["binding"])
    credential.refresh_from_db()
    custom.refresh_from_db()
    assert credential.fields == original_fields
    assert credential.type_id == "sql"
    assert custom.categories == ["network"]
    assert custom.fields == []
    assert not custom.is_builtin


@pytest.mark.parametrize("entry", ENTRIES, ids=lambda entry: entry["id"])
def test_original_inline_fields_reach_dispatch_unchanged(entry):
    credential = {field: f"original-{field}" for field in entry["inline_fields"]}
    task = SimpleNamespace(decrypt_credentials=[{**credential, "credential_source": "inline"}])
    assert resolve_task_credential_pool(task, resolver=lambda *_: pytest.fail("一次性认证不读取凭据库")) == [credential]


@pytest.mark.parametrize("entry", [row for row in ENTRIES if row["binding"]], ids=lambda entry: entry["id"])
def test_vault_auth_maps_to_original_form_keys_without_page_secrets(monkeypatch, entry):
    key = entry["binding"].split("/")[1]
    monkeypatch.setattr("apps.cmdb.services.collect_vault_resolver.actual_builtin_type_keys", lambda _: [key])
    task = SimpleNamespace(
        model_id=entry["model_id"],
        collect_object_id=entry["id"],
        driver_type=entry["type"],
        params={"collection_protocol": entry["credential_protocol"]},
        decrypt_credentials=[
            {
                "credential_source": "vault",
                "vault_type_key": key,
                "vault_credential_id": "selected-id",
                "vault_actor_context": ACTOR,
                "port": 12345,
                "snmp_port": 12345,
                "password": "obsolete-page-secret",
            }
        ],
    )
    seen = []

    def resolve(actor, credential_id):
        seen.append((actor, credential_id))
        return {"result": True, "data": {"type": key, "fields": FIELDS[key]}}

    result = resolve_task_credential_pool(task, resolver=resolve)[0]
    assert seen == [(ACTOR, "selected-id")]
    assert result["port"] == 12345
    assert "vault_credential_id" not in result
    assert "obsolete-page-secret" not in result.values()
    form = entry.get("effective_form", entry["original_form"])
    if form == "snmp":
        assert result["version"] == "v2"
        assert result["community"] == "secret-value"
    elif form == "influxdb":
        assert result["token"] == "secret-value"
    elif form == "cloud":
        assert result["accessKey"] == "account-value"
        assert result["accessSecret"] == "secret-value"
    else:
        assert result["user" if form in {"sql", "winsphere"} else "username"] == "account-value"
        assert result["password"] == "secret-value"


@pytest.mark.parametrize("entry", [e for e in ENTRIES if e["type"] == "job" and e["id"] != "pc"], ids=lambda e: e["id"])
def test_script_jobs_select_ssh_type_in_their_object_category(entry):
    expected = entry["binding"].split("/")[0] + "/ssh"
    assert binding_for_collect_object(entry["id"], model_id=entry["model_id"], driver_type="job") == expected
    assert expected.split("/")[0] in BUILTIN_TYPES["ssh"]["categories"]


@pytest.mark.django_db
@pytest.mark.parametrize("type_key", ["ssh", "sql"])
@pytest.mark.parametrize("stored_type", [None, "ssh", "sql"])
def test_job_vault_actual_builtin_validation_and_saved_type_lock(type_key, stored_type):
    from apps.core.exceptions.base_app_exception import BaseAppException

    seed_builtin_types()
    fields = {"username": "account", "password": "test-secret"}
    if type_key == "ssh":
        fields["auth_method"] = "password"
    task = SimpleNamespace(
        model_id="informix",
        driver_type="job",
        params={},
        decrypt_credentials=[
            {
                "credential_source": "vault",
                "vault_credential_id": "test-ref",
                "vault_type_key": stored_type,
                "vault_actor_context": ACTOR,
                "port": 2222,
            }
        ],
    )

    def resolve(*_):
        return {"result": True, "data": {"type": type_key, "fields": fields}}

    if stored_type and stored_type != type_key:
        with pytest.raises(BaseAppException, match="类型与采集对象不匹配"):
            resolve_task_credential_pool(task, resolver=resolve)
    else:
        result = resolve_task_credential_pool(task, resolver=resolve)[0]
        assert result["username"] == "account"
        assert result["password"] == "test-secret"
        assert result["port"] == 2222
        assert "test-secret" not in str(task.decrypt_credentials)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "model,driver,params,type_key",
    [
        ("pc", "job", {"os_type": "windows"}, "ssh"),
        ("pc", "job", {"os_type": "macos"}, "winrm"),
        ("pc", "job", {"os_type": "macos"}, "sql"),
        ("mysql", "protocol", {}, "ssh"),
        ("informix", "job", {}, "winrm"),
    ],
)
def test_protocol_and_pc_branches_do_not_accept_unrelated_job_types(model, driver, params, type_key):
    from apps.core.exceptions.base_app_exception import BaseAppException

    seed_builtin_types()
    task = SimpleNamespace(
        model_id=model,
        driver_type=driver,
        params=params,
        decrypt_credentials=[
            {
                "credential_source": "vault",
                "vault_credential_id": "test-ref",
                "vault_actor_context": ACTOR,
            }
        ],
    )
    with pytest.raises(BaseAppException, match="类型与采集对象不匹配"):
        resolve_task_credential_pool(
            task,
            resolver=lambda *_: {
                "result": True,
                "data": {
                    "type": type_key,
                    "fields": {"username": "account", "password": "test-secret", "auth_method": "password"},
                },
            },
        )
