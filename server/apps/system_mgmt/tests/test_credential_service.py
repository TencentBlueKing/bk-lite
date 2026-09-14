from types import SimpleNamespace

import pytest

from apps.system_mgmt.models import Group
from apps.system_mgmt.models.credential import Credential, CredentialType
from apps.system_mgmt.services.credential_builtin import BUILTIN_TYPES
from apps.system_mgmt.services.credential_service import (
    CredentialServiceError,
    create_credential,
    create_type,
    delete_credential,
    delete_type,
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
    assert seeded.categories == ["database", "middleware"]
    assert CredentialType.objects.filter(is_builtin=True).count() == len(BUILTIN_TYPES)
    assert set(BUILTIN_TYPES) == {
        "ssh",
        "winrm",
        "ipmi",
        "snmp",
        "sql",
        "cloud",
        "platform_api",
        "network_cli",
        "token",
        "oauth_client",
        "gateway_secret",
    }
    assert CredentialType.objects.get(key="platform_api").categories == ["cloud", "storage"]
    assert CredentialType.objects.get(key="network_cli").categories == ["network"]
    assert CredentialType.objects.get(key="token").categories == ["database", "other"]
    assert CredentialType.objects.get(key="oauth_client").categories == ["cloud"]
    assert CredentialType.objects.get(key="gateway_secret").categories == ["other"]
    ssh_fields = {field["id"]: field for field in CredentialType.objects.get(key="ssh").fields}
    assert ssh_fields["username"]["name"] == "用户名"
    assert ssh_fields["auth_method"]["name"] == "认证方式"
    assert ssh_fields["port"]["name"] == "端口"


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
