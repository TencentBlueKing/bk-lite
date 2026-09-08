import pytest

from apps.system_mgmt.models import Group, Menu, Role, User
from apps.system_mgmt.models.credential import Credential, CredentialType
from apps.system_mgmt.nats import credentials as credential_nats
from apps.system_mgmt.services.credential_service import create_credential, set_disabled

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

SECRET = "nats-secret-password"


def _group(name, parent_id=0):
    return Group.objects.create(name=name, parent_id=parent_id, is_delete=False)


def _sql_type():
    return CredentialType.objects.create(
        key="sqlnats",
        name="SQL NATS",
        categories=["database"],
        fields=[
            {"id": "username", "kind": "string", "required": True},
            {"id": "password", "kind": "secret", "required": True},
        ],
    )


def _user(username, groups, role_ids=None):
    return User.objects.create(
        username=username,
        domain="domain.com",
        password="x",
        display_name=username,
        email=f"{username}@example.com",
        group_list=[group.id for group in groups],
        role_list=list(role_ids or []),
    )


def _ctx(user, current_team):
    return {"username": user.username, "domain": user.domain, "current_team": current_team}


def _grant_menu(user, name, role_name):
    menu = Menu.objects.create(
        name=name,
        display_name=name,
        app="system-manager",
        menu_type="Credential",
        url="",
    )
    role = Role.objects.create(name=role_name, app="system-manager", menu_list=[menu.id])
    user.role_list = [role.id]
    user.save(update_fields=["role_list"])
    return user


def _grant_add(user):
    return _grant_menu(user, "credential-Add", "credential-operator")


def _grant_view(user):
    return _grant_menu(user, "credential-View", "credential-viewer")


@pytest.mark.django_db
def test_list_omits_password_and_disabled_and_cross_org_is_empty():
    typ = _sql_type()
    root = _group("nats-root")
    child = _group("nats-child", root.id)
    other = _group("nats-other")
    actor = _user("nats-list", [root, child, other])
    root_cred = create_credential(
        {"name": "Root DB", "type": typ.key, "group_id": root.id, "fields": {"username": "r", "password": SECRET}},
        actor={"current_team": root.id, "group_list": [root.id], "is_superuser": True, "username": actor.username, "domain": actor.domain},
    )
    child_cred = create_credential(
        {"name": "Child DB", "type": typ.key, "group_id": child.id, "fields": {"username": "c", "password": SECRET}},
        actor={"current_team": child.id, "group_list": [child.id], "is_superuser": True, "username": actor.username, "domain": actor.domain},
    )
    set_disabled(child_cred.credential_id, True)

    denied = credential_nats.list_credentials(_ctx(actor, child.id))
    assert denied == {"result": False, "message": "forbidden"}
    _grant_view(actor)
    missing_category = credential_nats.list_credentials(_ctx(actor, child.id), type=typ.key)
    assert missing_category == {"result": False, "message": "invalid"}

    listed = credential_nats.list_credentials(_ctx(actor, child.id), category="database", type=typ.key)
    assert listed["result"] is True
    ids = {item["credential_id"] for item in listed["data"]}
    assert ids == {root_cred.credential_id}
    assert SECRET not in str(listed)
    assert all("password" not in item.get("fields", {}) for item in listed["data"])

    other_listed = credential_nats.list_credentials(_ctx(actor, other.id))
    assert other_listed["result"] is True
    assert other_listed["data"] == []


@pytest.mark.django_db
def test_resolve_returns_plaintext_and_disabled_fails():
    typ = _sql_type()
    owner = _group("nats-resolve")
    actor = _user("nats-resolve", [owner])
    created = create_credential(
        {"name": "DB", "type": typ.key, "group_id": owner.id, "fields": {"username": "root", "password": SECRET}},
        actor={"current_team": owner.id, "group_list": [owner.id], "is_superuser": True, "username": actor.username, "domain": actor.domain},
    )

    denied = credential_nats.resolve_credential(_ctx(actor, owner.id), created.credential_id)
    assert denied == {"result": False, "message": "forbidden"}
    _grant_view(actor)
    resolved = credential_nats.resolve_credential(_ctx(actor, owner.id), created.credential_id)
    assert resolved["result"] is True
    assert resolved["data"]["fields"]["password"] == SECRET

    set_disabled(created.credential_id, True)
    disabled = credential_nats.resolve_credential(_ctx(actor, owner.id), created.credential_id)
    assert disabled == {"result": False, "message": "disabled"}


@pytest.mark.django_db
def test_create_requires_add_permission_and_returns_public_fields():
    typ = _sql_type()
    owner = _group("nats-create")
    actor = _user("nats-create", [owner])

    denied = credential_nats.create_credential(
        _ctx(actor, owner.id),
        name="Denied",
        type=typ.key,
        group_id=owner.id,
        fields={"username": "u", "password": SECRET},
    )
    assert denied == {"result": False, "message": "forbidden"}
    assert not Credential.objects.filter(name="Denied").exists()

    _grant_add(actor)
    created = credential_nats.create_credential(
        _ctx(actor, owner.id),
        name="Created",
        type=typ.key,
        group_id=owner.id,
        fields={"username": "u", "password": SECRET},
    )
    assert created["result"] is True
    assert created["data"]["name"] == "Created"
    assert "password" not in created["data"]["fields"]
    assert SECRET not in str(created)
    assert Credential.objects.filter(credential_id=created["data"]["credential_id"]).exists()
