import logging
from types import SimpleNamespace

import pytest

from apps.system_mgmt.models import Group
from apps.system_mgmt.models.credential import Credential, CredentialType
from apps.system_mgmt.services.credential_builtin import BUILTIN_TYPES, builtin_type_payloads
from apps.system_mgmt.services.credential_service import (
    CredentialServiceError,
    create_credential,
    create_type,
    delete_credential,
    delete_type,
    get_credential,
    list_credentials,
    list_types,
    page_credentials,
    query_credentials,
    resolve_credential,
    seed_builtin_types,
    set_disabled,
    update_credential,
    update_type,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def actor(group_id, *authorized, is_superuser=False):
    return SimpleNamespace(
        current_team=group_id,
        group_list=list(authorized or (group_id,)),
        is_superuser=is_superuser,
        username="credential-test",
        domain="domain.com",
    )


def group(name, parent_id=0):
    return Group.objects.create(name=name, parent_id=parent_id, is_delete=False)


def sql_type():
    return CredentialType.objects.create(
        key="sql-test",
        name="SQL test",
        categories=["database"],
        fields=[
            {"id": "username", "kind": "string", "required": True},
            {"id": "password", "kind": "secret", "required": True},
        ],
    )


def test_seed_builtin_types_is_idempotent_and_authoritative():
    seed_builtin_types()
    assert set(CredentialType.objects.values_list("key", flat=True)) >= set(BUILTIN_TYPES)
    seeded = CredentialType.objects.get(key="sql")
    seeded.name = "Operator renamed"
    seeded.categories = ["wrong"]
    seeded.fields = []
    seeded.save(update_fields=["name", "categories", "fields"])

    seed_builtin_types()
    seeded.refresh_from_db()
    assert seeded.name == BUILTIN_TYPES["sql"]["name"]
    assert seeded.categories == BUILTIN_TYPES["sql"]["categories"]
    assert seeded.fields == BUILTIN_TYPES["sql"]["fields"]
    assert seeded.name == "用户名密码"
    assert seeded.categories == ["host", "database", "middleware", "network"]
    assert CredentialType.objects.filter(is_builtin=True).count() == len(builtin_type_payloads())
    assert set(BUILTIN_TYPES) == {
        "ssh",
        "winrm",
        "ipmi",
        "redfish",
        "snmp",
        "sql",
        "cloud",
        "openstack",
        "platform_api",
        "network_cli",
        "token",
        "oauth_client",
        "gateway_secret",
    }
    assert CredentialType.objects.get(key="platform_api").categories == ["cloud", "storage", "network"]
    assert CredentialType.objects.get(key="network_cli").categories == ["network"]
    assert CredentialType.objects.get(key="token").categories == ["database", "other"]
    assert CredentialType.objects.get(key="oauth_client").categories == ["cloud"]
    assert CredentialType.objects.get(key="gateway_secret").categories == ["other"]
    ssh_fields = {field["id"]: field for field in CredentialType.objects.get(key="ssh").fields}
    assert ssh_fields["username"]["name"] == "用户名"
    assert ssh_fields["auth_method"]["name"] == "认证方式"
    assert "port" not in ssh_fields
    assert ssh_fields["passphrase"]["name"] == "私钥口令"
    assert CredentialType.objects.get(key="openstack").name == "OpenStack 账户"
    redfish_fields = {field["id"]: field for field in CredentialType.objects.get(key="redfish").fields}
    assert CredentialType.objects.get(key="redfish").categories == ["host"]
    assert set(redfish_fields) == {"username", "password"}
    platform_fields = {field["id"]: field for field in CredentialType.objects.get(key="platform_api").fields}
    assert set(platform_fields) == {"username", "password"}


def test_list_types_orders_builtin_first_then_by_creation():
    seed_builtin_types()
    CredentialType.objects.create(key="zzz_custom", name="First custom", categories=["other"])
    CredentialType.objects.create(key="aaa_custom", name="Second custom", categories=["other"])
    items = list_types()
    keys = [item["key"] for item in items]
    builtin_keys = [item["key"] for item in items if item["is_builtin"]]
    custom_keys = [item["key"] for item in items if not item["is_builtin"]]
    assert keys == builtin_keys + custom_keys
    assert builtin_keys[0] == next(iter(BUILTIN_TYPES))
    assert custom_keys.index("zzz_custom") < custom_keys.index("aaa_custom")


def test_builtin_type_is_immutable_but_custom_type_is_editable():
    seed_builtin_types()
    builtin = CredentialType.objects.get(key="ssh")
    with pytest.raises(CredentialServiceError) as exc:
        update_type(builtin.key, {"key": "renamed", "fields": []}, actor(1, is_superuser=True))
    assert exc.value.code == "immutable"

    custom = create_type(
        {"key": "custom", "name": "Custom", "categories": ["other"], "fields": []},
        actor(1, is_superuser=True),
    )
    changed = update_type(custom.key, {"name": "Changed", "categories": ["host"]}, actor(1, is_superuser=True))
    assert changed.name == "Changed"
    assert changed.categories == ["host"]


def test_custom_type_with_instance_cannot_delete():
    custom = sql_type()
    owner = group("custom-delete-owner")
    create_credential(
        {"name": "db", "type": custom.key, "group_id": owner.id, "fields": {"username": "u", "password": "p"}},
        actor(owner.id, owner.id),
    )
    with pytest.raises(CredentialServiceError) as exc:
        delete_type(custom.key, actor(owner.id, owner.id))
    assert exc.value.code == "in_use"


def test_create_resolve_encrypts_password_and_list_is_public():
    typ = sql_type()
    owner = group("sql-owner")
    created = create_credential(
        {"name": "Production DB", "type": typ.key, "group_id": owner.id, "fields": {"username": "root", "password": "pw"}},
        actor(owner.id, owner.id),
    )
    row = Credential.objects.get(credential_id=created.credential_id)
    assert row.fields["password"] != "pw"
    resolved = resolve_credential(created.credential_id, owner.id, actor(owner.id, owner.id))
    assert resolved["fields"] == {"username": "root", "password": "pw"}
    listed = list_credentials({"current_team": owner.id}, actor=actor(owner.id, owner.id))
    assert listed[0]["credential_id"] == created.credential_id
    assert "password" not in listed[0]["fields"]


def test_update_preserves_blank_secret_and_rejects_type_change():
    typ = sql_type()
    owner = group("update-owner")
    created = create_credential(
        {"name": "DB", "type": typ.key, "group_id": owner.id, "fields": {"username": "old", "password": "old-pw"}},
        actor(owner.id, owner.id),
    )
    original_ciphertext = Credential.objects.get(credential_id=created.credential_id).fields["password"]
    update_credential(created.credential_id, {"name": "Name only"}, actor(owner.id, owner.id))
    assert Credential.objects.get(credential_id=created.credential_id).fields["password"] == original_ciphertext
    updated = update_credential(
        created.credential_id,
        {"name": "DB renamed", "fields": {"username": "new", "password": ""}},
        actor(owner.id, owner.id),
    )
    row = Credential.objects.get(credential_id=updated.credential_id)
    assert row.name == "DB renamed"
    assert row.fields["username"] == "new"
    assert row.fields["password"] == original_ciphertext
    with pytest.raises(CredentialServiceError) as exc:
        update_credential(created.credential_id, {"type": "ssh"}, actor(owner.id, owner.id))
    assert exc.value.code == "immutable"


@pytest.mark.parametrize("private_key_fields", [{}, {"private_key": ""}])
def test_update_ssh_auth_method_requires_new_mode_secret(private_key_fields):
    seed_builtin_types()
    owner = group("ssh-switch-owner")
    caller = actor(owner.id)
    created = create_credential(
        {
            "name": "SSH",
            "type": "ssh",
            "group_id": owner.id,
            "fields": {"auth_method": "password", "username": "ops", "password": "fixture-password"},
        },
        caller,
    )
    before = resolve_credential(created.credential_id, owner.id, caller)

    with pytest.raises(CredentialServiceError, match="private_key.*required") as exc:
        update_credential(created.credential_id, {"fields": {"auth_method": "key", **private_key_fields}}, caller)

    assert exc.value.code == "invalid"
    assert resolve_credential(created.credential_id, owner.id, caller) == before


@pytest.mark.parametrize(
    ("security_fields", "missing_field"),
    [
        ({"security_level": "authNoPriv", "auth_protocol": "SHA"}, "auth_password"),
        ({"security_level": "authNoPriv", "auth_protocol": "SHA", "auth_password": ""}, "auth_password"),
        ({"security_level": "authPriv", "auth_protocol": "SHA", "priv_protocol": "AES"}, "auth_password"),
        (
            {"security_level": "authPriv", "auth_protocol": "SHA", "priv_protocol": "AES", "auth_password": "fixture-auth"},
            "priv_password",
        ),
        (
            {
                "security_level": "authPriv",
                "auth_protocol": "SHA",
                "priv_protocol": "AES",
                "auth_password": "fixture-auth",
                "priv_password": "",
            },
            "priv_password",
        ),
    ],
)
def test_update_snmp_security_level_requires_new_mode_secrets(security_fields, missing_field):
    seed_builtin_types()
    owner = group("snmp-switch-owner")
    caller = actor(owner.id)
    created = create_credential(
        {
            "name": "SNMP",
            "type": "snmp",
            "group_id": owner.id,
            "fields": {"version": "v3", "security_level": "noAuthNoPriv", "username": "ops"},
        },
        caller,
    )
    before = resolve_credential(created.credential_id, owner.id, caller)

    with pytest.raises(CredentialServiceError, match=f"{missing_field}.*required") as exc:
        update_credential(created.credential_id, {"fields": security_fields}, caller)

    assert exc.value.code == "invalid"
    assert resolve_credential(created.credential_id, owner.id, caller) == before


def test_update_snmp_security_level_reuses_existing_auth_secret_and_accepts_new_priv_secret():
    seed_builtin_types()
    owner = group("snmp-upgrade-owner")
    caller = actor(owner.id)
    created = create_credential(
        {
            "name": "SNMP",
            "type": "snmp",
            "group_id": owner.id,
            "fields": {
                "version": "v3",
                "security_level": "authNoPriv",
                "username": "ops",
                "auth_protocol": "SHA",
                "auth_password": "fixture-auth",
            },
        },
        caller,
    )
    update_credential(
        created.credential_id,
        {"fields": {"security_level": "authPriv", "auth_password": "", "priv_protocol": "AES", "priv_password": "fixture-priv"}},
        caller,
    )
    update_credential(created.credential_id, {"fields": {"auth_password": "", "priv_password": ""}}, caller)

    resolved = resolve_credential(created.credential_id, owner.id, caller)
    assert resolved["fields"]["security_level"] == "authPriv"
    assert resolved["fields"]["auth_password"] == "fixture-auth"
    assert resolved["fields"]["priv_password"] == "fixture-priv"


def test_update_ssh_auth_method_accepts_new_secret_and_preserves_it_on_blank_edit():
    seed_builtin_types()
    owner = group("ssh-key-owner")
    caller = actor(owner.id)
    created = create_credential(
        {"name": "SSH", "type": "ssh", "group_id": owner.id, "fields": {"auth_method": "key", "username": "ops", "private_key": "fixture-key"}},
        caller,
    )
    with pytest.raises(CredentialServiceError, match="password.*required"):
        update_credential(created.credential_id, {"fields": {"auth_method": "password", "password": ""}}, caller)

    update_credential(created.credential_id, {"fields": {"auth_method": "password", "password": "fixture-password"}}, caller)
    update_credential(created.credential_id, {"fields": {"password": ""}}, caller)
    assert resolve_credential(created.credential_id, owner.id, caller)["fields"]["password"] == "fixture-password"


def test_owner_scope_direction_filtering_and_forbidden_resolution():
    typ = sql_type()
    root = group("scope-root")
    child = group("scope-child", root.id)
    sibling = group("scope-sibling")
    root_cred = create_credential(
        {"name": "Root DB", "type": typ.key, "group_id": root.id, "fields": {"username": "r", "password": "r"}},
        actor(root.id, root.id),
    )
    child_cred = create_credential(
        {"name": "Child DB", "type": typ.key, "group_id": child.id, "fields": {"username": "c", "password": "c"}},
        actor(child.id, child.id),
    )
    assert {item["credential_id"] for item in list_credentials({"current_team": root.id}, actor=actor(root.id, root.id))} == {root_cred.credential_id}
    child_items = list_credentials({"current_team": child.id}, actor=actor(child.id, child.id))
    assert {item["credential_id"] for item in child_items} == {root_cred.credential_id, child_cred.credential_id}
    assert (
        list_credentials({"current_team": child.id, "group_id": root.id}, actor=actor(child.id, child.id))[0]["credential_id"]
        == root_cred.credential_id
    )
    with pytest.raises(CredentialServiceError) as exc:
        resolve_credential(child_cred.credential_id, root.id, actor(root.id, root.id))
    assert exc.value.code == "forbidden"
    with pytest.raises(CredentialServiceError) as exc:
        create_credential(
            {"name": "Sibling", "type": typ.key, "group_id": sibling.id, "fields": {"username": "s", "password": "s"}},
            actor(child.id, child.id),
        )
    assert exc.value.code == "forbidden"
    with pytest.raises(CredentialServiceError) as exc:
        set_disabled(root_cred.credential_id, True, actor=actor(child.id, child.id))
    assert exc.value.code == "forbidden"
    with pytest.raises(CredentialServiceError) as exc:
        delete_credential(root_cred.credential_id, actor=actor(child.id, child.id))
    assert exc.value.code == "forbidden"
    assert Credential.objects.filter(credential_id=root_cred.credential_id).exists()
    set_disabled(child_cred.credential_id, True, actor=actor(child.id, child.id))
    assert Credential.objects.get(credential_id=child_cred.credential_id).disabled is True


def test_list_filters_category_type_search_disabled_and_exact_owner():
    typ = sql_type()
    root = group("filter-root")
    child = group("filter-child", root.id)
    first = create_credential(
        {"name": "Alpha database", "type": typ.key, "group_id": root.id, "fields": {"username": "a", "password": "a"}},
        actor(root.id, root.id),
    )
    second = create_credential(
        {"name": "Beta database", "type": typ.key, "group_id": child.id, "fields": {"username": "b", "password": "b"}},
        actor(child.id, child.id),
    )
    set_disabled(second.credential_id, True)
    scoped_actor = actor(child.id, child.id)
    assert [
        row["credential_id"] for row in list_credentials({"current_team": child.id, "category": "database", "type": typ.key}, actor=scoped_actor)
    ] == [first.credential_id, second.credential_id]
    assert [row["credential_id"] for row in list_credentials({"current_team": child.id, "search": "Alpha"}, actor=scoped_actor)] == [
        first.credential_id
    ]
    assert [row["credential_id"] for row in list_credentials({"current_team": child.id, "disabled": True}, actor=scoped_actor)] == [
        second.credential_id
    ]
    assert [row["credential_id"] for row in list_credentials({"current_team": child.id, "group_id": child.id}, actor=scoped_actor)] == [
        second.credential_id
    ]
    id_token = second.credential_id.split("-")[-1][:8]
    assert id_token
    assert id_token.lower() not in first.name.lower()
    assert id_token.lower() not in second.name.lower()
    assert [row["credential_id"] for row in list_credentials({"current_team": child.id, "search": id_token}, actor=scoped_actor)] == []
    assert [row["credential_id"] for row in list_credentials({"current_team": child.id, "search": typ.name}, actor=scoped_actor)] == []


def test_manage_scope_lists_authorized_siblings_consume_scope_does_not():
    typ = sql_type()
    root = group("manage-root")
    child = group("manage-child", root.id)
    sibling = group("manage-sibling")
    root_cred = create_credential(
        {"name": "Root DB", "type": typ.key, "group_id": root.id, "fields": {"username": "r", "password": "r"}},
        actor(root.id, root.id, sibling.id),
    )
    sibling_cred = create_credential(
        {"name": "Sibling DB", "type": typ.key, "group_id": sibling.id, "fields": {"username": "s", "password": "s"}},
        actor(root.id, root.id, sibling.id),
    )
    child_cred = create_credential(
        {"name": "Child DB", "type": typ.key, "group_id": child.id, "fields": {"username": "c", "password": "c"}},
        actor(child.id, child.id),
    )
    manage_actor = actor(root.id, root.id, sibling.id)
    managed_ids = {row.credential_id for row in query_credentials({"current_team": root.id, "owner_scope": "manage"}, actor=manage_actor)}
    assert managed_ids == {root_cred.credential_id, sibling_cred.credential_id}
    assert child_cred.credential_id not in managed_ids
    consume_ids = {row["credential_id"] for row in list_credentials({"current_team": root.id}, actor=manage_actor)}
    assert consume_ids == {root_cred.credential_id}
    with pytest.raises(CredentialServiceError) as exc:
        create_credential(
            {
                "name": "Quick sibling",
                "type": typ.key,
                "group_id": sibling.id,
                "fields": {"username": "q", "password": "q"},
                "owner_mode": "current",
            },
            actor=manage_actor,
        )
    assert exc.value.code == "forbidden"


def test_update_owner_allows_any_authorized_organization():
    typ = sql_type()
    root = group("move-root")
    child = group("move-child", root.id)
    grandchild = group("move-grandchild", child.id)
    sibling = group("move-sibling")
    created = create_credential(
        {"name": "Move me", "type": typ.key, "group_id": child.id, "fields": {"username": "u", "password": "p"}},
        actor(child.id, child.id, grandchild.id, sibling.id),
    )
    moved = update_credential(
        created.credential_id,
        {"group_id": grandchild.id},
        actor(child.id, child.id, grandchild.id, sibling.id),
    )
    assert moved.group_id == grandchild.id
    sideways = update_credential(
        created.credential_id,
        {"group_id": sibling.id},
        actor(child.id, child.id, grandchild.id, sibling.id),
    )
    assert sideways.group_id == sibling.id
    with pytest.raises(CredentialServiceError) as exc:
        update_credential(
            created.credential_id,
            {"group_id": root.id},
            actor(child.id, child.id, grandchild.id, sibling.id),
        )
    assert exc.value.code == "forbidden"


def test_disabled_resolve_and_delete_do_not_report_fake_references():
    typ = sql_type()
    owner = group("disable-owner")
    created = create_credential(
        {"name": "DB", "type": typ.key, "group_id": owner.id, "fields": {"username": "u", "password": "p"}},
        actor(owner.id, owner.id),
    )
    set_disabled(created.credential_id, True)
    with pytest.raises(CredentialServiceError) as exc:
        resolve_credential(created.credential_id, owner.id, actor(owner.id, owner.id))
    assert exc.value.code == "disabled"
    assert list_credentials({"current_team": owner.id, "disabled": True}, actor=actor(owner.id, owner.id))[0]["disabled"] is True
    result = delete_credential(created.credential_id)
    assert result is None or result is True
    assert not Credential.objects.filter(credential_id=created.credential_id).exists()


def test_unauthorized_current_team_and_missing_credentials_are_fail_closed():
    typ = sql_type()
    owner = group("auth-owner")
    created = create_credential(
        {"name": "DB", "type": typ.key, "group_id": owner.id, "fields": {"username": "u", "password": "p"}},
        actor(owner.id, owner.id),
    )
    unauthorized = actor(owner.id, is_superuser=False)
    unauthorized.group_list = []
    with pytest.raises(CredentialServiceError) as exc:
        resolve_credential(created.credential_id, owner.id, unauthorized)
    assert exc.value.code == "forbidden"
    with pytest.raises(CredentialServiceError) as exc:
        resolve_credential("crd-sql-00000000000000000000000000000000", owner.id, actor(owner.id, owner.id))
    assert exc.value.code == "not_found"


def test_delete_and_move_blocked_when_refs_exist_or_inquiry_fails(monkeypatch):
    typ = sql_type()
    owner = group("ref-owner")
    child = group("ref-child", parent_id=owner.id)
    created = create_credential(
        {"name": "DB", "type": typ.key, "group_id": owner.id, "fields": {"username": "u", "password": "p"}},
        actor(owner.id, owner.id),
    )

    def used(credential_ids, **kwargs):
        return {"result": True, "data": {"counts": {cid: 1 for cid in credential_ids}}}

    monkeypatch.setattr(
        "apps.system_mgmt.services.credential_ref_count._live_queriers",
        lambda: (("cmdb", used), ("monitor", used)),
    )
    with pytest.raises(CredentialServiceError) as delete_exc:
        delete_credential(created.credential_id, actor=actor(owner.id, owner.id))
    assert delete_exc.value.code == "in_use"
    with pytest.raises(CredentialServiceError) as move_exc:
        update_credential(created.credential_id, {"group_id": child.id}, actor(owner.id, owner.id, child.id))
    assert move_exc.value.code == "in_use"
    assert Credential.objects.get(credential_id=created.credential_id).group_id == owner.id


def test_list_attaches_ref_chips_from_successful_modules(monkeypatch):
    typ = sql_type()
    owner = group("list-ref-owner")
    created = create_credential(
        {"name": "DB", "type": typ.key, "group_id": owner.id, "fields": {"username": "u", "password": "p"}},
        actor(owner.id, owner.id),
    )

    def cmdb_counts(credential_ids, **kwargs):
        return {"result": True, "data": {"counts": {created.credential_id: 2}}}

    def boom(credential_ids, **kwargs):
        raise TimeoutError("rpc")

    monkeypatch.setattr(
        "apps.system_mgmt.services.credential_ref_count._live_queriers",
        lambda: (("cmdb", cmdb_counts), ("monitor", boom)),
    )
    listed = list_credentials({"current_team": owner.id}, actor=actor(owner.id, owner.id))
    assert listed[0]["refs"] == [{"module": "cmdb", "count": 2}]


def test_page_credentials_skips_ref_inquiry(monkeypatch):
    typ = sql_type()
    owner = group("page-ref-owner")
    create_credential(
        {"name": "DB", "type": typ.key, "group_id": owner.id, "fields": {"username": "u", "password": "p"}},
        actor(owner.id, owner.id),
    )
    calls = []

    def boom(credential_ids, **kwargs):
        calls.append(credential_ids)
        raise AssertionError("picker list must not inquire refs")

    monkeypatch.setattr(
        "apps.system_mgmt.services.credential_ref_count._live_queriers",
        lambda: (("cmdb", boom), ("monitor", boom)),
    )
    items, count = page_credentials({"current_team": owner.id}, actor=actor(owner.id, owner.id))
    assert count == 1
    assert "refs" not in items[0]
    assert calls == []


FALLBACK_TEMPLATE = "event=credential_builtin_key_fallback preferred_key=%s seed_key=%s failed_stage=%s error_type=%s"
SKIP_TEMPLATE = "event=credential_builtin_key_skipped preferred_key=%s fallback_key=%s failed_stage=%s error_type=%s"


def _records_for(caplog, template):
    return [record for record in caplog.records if record.msg == template]


def _assert_seed_warning(record, *, args, message, sentinel):
    assert record.levelno == logging.WARNING
    assert record.args == args
    assert record.getMessage() == message
    formatted = logging.Formatter().format(record)
    assert sentinel not in formatted
    assert sentinel not in record.getMessage()


def test_seed_openstack_uses_fallback_key_when_custom_type_owns_openstack(caplog):
    sentinel = "openstack-password-must-not-appear-in-logs"
    CredentialType.objects.create(
        key="openstack",
        name=sentinel,
        categories=["cloud"],
        fields=[{"id": "password", "kind": "secret", "name": sentinel}],
    )
    with caplog.at_level(logging.WARNING, logger="system-manager"):
        seeded = seed_builtin_types()
    custom = CredentialType.objects.get(key="openstack")
    assert custom.is_builtin is False
    assert custom.name == sentinel
    builtin = CredentialType.objects.get(key="openstack_account")
    assert builtin.is_builtin is True
    assert builtin.name == "OpenStack 账户"
    assert any(row.key == "openstack_account" for row in seeded)
    records = _records_for(caplog, FALLBACK_TEMPLATE)
    assert len(records) == 1
    _assert_seed_warning(
        records[0],
        args=("openstack", "openstack_account", "seed_key", "preferred_key_occupied"),
        message=(
            "event=credential_builtin_key_fallback preferred_key=openstack seed_key=openstack_account "
            "failed_stage=seed_key error_type=preferred_key_occupied"
        ),
        sentinel=sentinel,
    )
    assert sentinel not in caplog.text

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="system-manager"):
        seed_builtin_types()
    assert _records_for(caplog, FALLBACK_TEMPLATE) == []
    assert CredentialType.objects.get(key="openstack_account").is_builtin is True


def test_update_ssh_drops_removed_port_and_keeps_passphrase_unless_key_rotates():
    """Builtin SSH no longer defines port; leftover stored port is dropped on save.

    Connection port belongs to the collection task. Call sites that still read
    credential.fields['port'] must switch to their own task field.
    Blank passphrase keeps the stored value; a new private_key without passphrase
    drops the old passphrase.
    """
    seed_builtin_types()
    owner = group("ssh-port-owner")
    created = create_credential(
        {
            "name": "Jump",
            "type": "ssh",
            "group_id": owner.id,
            "fields": {
                "auth_method": "key",
                "username": "ops",
                "private_key": "PEM",
                "passphrase": "old-pp",
            },
        },
        actor(owner.id, owner.id),
    )
    row = Credential.objects.get(credential_id=created.credential_id)
    row.fields["port"] = 22
    row.save(update_fields=["fields"])
    original_key = row.fields["private_key"]
    original_pp = row.fields["passphrase"]

    public = get_credential(created.credential_id, owner.id, actor=actor(owner.id, owner.id))
    assert "port" not in public["fields"]
    assert "private_key" not in public["fields"]
    assert "passphrase" not in public["fields"]
    assert public["fields"]["username"] == "ops"

    with pytest.raises(CredentialServiceError) as rejected:
        update_credential(
            created.credential_id,
            {"fields": {"auth_method": "key", "username": "ops", "private_key": "", "port": 22}},
            actor(owner.id, owner.id),
        )
    assert rejected.value.code == "invalid"
    still_stored = Credential.objects.get(credential_id=created.credential_id)
    assert still_stored.fields["port"] == 22

    kept = update_credential(
        created.credential_id,
        {"fields": {"auth_method": "key", "username": "ops", "private_key": "", "passphrase": ""}},
        actor(owner.id, owner.id),
    )
    kept_row = Credential.objects.get(credential_id=kept.credential_id)
    assert "port" not in kept_row.fields
    assert kept_row.fields["private_key"] == original_key
    assert kept_row.fields["passphrase"] == original_pp

    rotated = update_credential(
        created.credential_id,
        {"fields": {"auth_method": "key", "username": "ops", "private_key": "NEW-PEM"}},
        actor(owner.id, owner.id),
    )
    rotated_row = Credential.objects.get(credential_id=rotated.credential_id)
    assert "passphrase" not in rotated_row.fields
    assert rotated_row.fields["private_key"] != original_key


def test_create_openstack_fills_default_user_domain_name():
    seed_builtin_types()
    owner = group("os-owner")
    created = create_credential(
        {
            "name": "OS",
            "type": "openstack",
            "group_id": owner.id,
            "fields": {"username": "demo", "password": "secret"},
        },
        actor(owner.id, owner.id),
    )
    row = Credential.objects.get(credential_id=created.credential_id)
    assert row.fields["user_domain_name"] == "Default"


def test_seed_redfish_uses_fallback_key_when_custom_type_owns_redfish(caplog):
    sentinel = "redfish-password-must-not-appear-in-logs"
    CredentialType.objects.create(key="redfish", name=sentinel, categories=["host"], fields=[])
    with caplog.at_level(logging.WARNING, logger="system-manager"):
        seed_builtin_types()
    custom = CredentialType.objects.get(key="redfish")
    assert custom.is_builtin is False
    assert custom.name == sentinel
    builtin = CredentialType.objects.get(key="redfish_bmc")
    assert builtin.is_builtin is True
    assert builtin.name == "Redfish"
    records = _records_for(caplog, FALLBACK_TEMPLATE)
    assert len(records) == 1
    _assert_seed_warning(
        records[0],
        args=("redfish", "redfish_bmc", "seed_key", "preferred_key_occupied"),
        message=(
            "event=credential_builtin_key_fallback preferred_key=redfish seed_key=redfish_bmc "
            "failed_stage=seed_key error_type=preferred_key_occupied"
        ),
        sentinel=sentinel,
    )
    assert sentinel not in caplog.text


def test_seed_skips_when_preferred_and_fallback_keys_are_custom(caplog):
    sentinel = "dual-key-password-must-not-appear-in-logs"
    CredentialType.objects.create(key="openstack", name=sentinel, categories=["cloud"], fields=[])
    CredentialType.objects.create(key="openstack_account", name="Custom Account", categories=["cloud"], fields=[])
    with caplog.at_level(logging.WARNING, logger="system-manager"):
        seeded = seed_builtin_types()
    assert CredentialType.objects.get(key="openstack").is_builtin is False
    assert CredentialType.objects.get(key="openstack").name == sentinel
    account = CredentialType.objects.get(key="openstack_account")
    assert account.is_builtin is False
    assert account.name == "Custom Account"
    assert all(row.key != "openstack_account" for row in seeded)
    assert CredentialType.objects.filter(key="ssh", is_builtin=True).exists()
    records = _records_for(caplog, SKIP_TEMPLATE)
    assert len(records) == 1
    _assert_seed_warning(
        records[0],
        args=("openstack", "openstack_account", "seed_key", "fallback_key_occupied"),
        message=(
            "event=credential_builtin_key_skipped preferred_key=openstack fallback_key=openstack_account "
            "failed_stage=seed_key error_type=fallback_key_occupied"
        ),
        sentinel=sentinel,
    )
    assert sentinel not in caplog.text


def test_seed_does_not_promote_custom_type_when_resolved_seed_key_is_occupied(monkeypatch, caplog):
    sentinel = "occupied-seed-key-password-must-not-appear-in-logs"
    CredentialType.objects.create(key="openstack_account", name=sentinel, categories=["cloud"], fields=[])

    def fake_seed_key(preferred_key):
        if preferred_key == "openstack":
            return "openstack_account"
        return preferred_key

    monkeypatch.setattr(
        "apps.system_mgmt.services.credential_service._builtin_seed_key",
        fake_seed_key,
    )
    with caplog.at_level(logging.WARNING, logger="system-manager"):
        seeded = seed_builtin_types()
    account = CredentialType.objects.get(key="openstack_account")
    assert account.is_builtin is False
    assert account.name == sentinel
    assert all(row.key != "openstack_account" for row in seeded)
    records = _records_for(caplog, SKIP_TEMPLATE)
    assert len(records) == 1
    _assert_seed_warning(
        records[0],
        args=("openstack", "openstack_account", "seed_key", "seed_key_occupied"),
        message=(
            "event=credential_builtin_key_skipped preferred_key=openstack fallback_key=openstack_account "
            "failed_stage=seed_key error_type=seed_key_occupied"
        ),
        sentinel=sentinel,
    )
    assert sentinel not in caplog.text


def test_platform_api_update_drops_connection_fields_but_preserves_password():
    seed_builtin_types()
    owner = group("platform-owner")
    created = create_credential(
        {
            "name": "OceanStor",
            "type": "platform_api",
            "group_id": owner.id,
            "fields": {"username": "admin", "password": "secret"},
        },
        actor(owner.id, owner.id),
    )
    row = Credential.objects.get(credential_id=created.credential_id)
    assert "port" not in row.fields
    assert "verify_tls" not in row.fields
    legacy_type = row.type
    legacy_type.fields += [
        {"id": "port", "name": "端口", "kind": "number"},
        {"id": "verify_tls", "name": "校验 TLS 证书", "kind": "enum", "values": ["true", "false"]},
    ]
    legacy_type.save(update_fields=["fields"])
    row.fields["port"] = 8088
    row.fields["verify_tls"] = "true"
    row.save(update_fields=["fields"])
    encrypted_password = row.fields["password"]
    seed_builtin_types()
    legacy_type.refresh_from_db()
    row.refresh_from_db()
    assert {field["id"] for field in legacy_type.fields} == {"username", "password"}
    # Refreshing type definitions does not rewrite existing credentials.
    assert row.fields["port"] == 8088
    assert row.fields["password"] == encrypted_password
    updated = update_credential(
        created.credential_id,
        {"fields": {"username": "admin", "password": ""}},
        actor(owner.id, owner.id),
    )
    kept = Credential.objects.get(credential_id=updated.credential_id)
    assert set(kept.fields) == {"username", "password"}
    assert kept.fields["password"] == encrypted_password
