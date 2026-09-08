from unittest.mock import patch

import pytest

from apps.system_mgmt.models import Group
from apps.system_mgmt.models.credential import Credential, CredentialType

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

V = "/api/v1/system_mgmt"
SECRET = "http-secret-password"


def _payload(response):
    data = response.data if hasattr(response, "data") else response.json()
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "items" in data:
        return data["items"]
    if isinstance(data, dict) and "results" in data:
        return data["results"]
    return data


def _group(name, parent_id=0):
    return Group.objects.create(name=name, parent_id=parent_id, is_delete=False)


def _sql_type():
    return CredentialType.objects.create(
        key="sqlhttp",
        name="SQL HTTP",
        categories=["database"],
        fields=[
            {"id": "username", "kind": "string", "required": True},
            {"id": "password", "kind": "secret", "required": True},
        ],
    )


def _actor(user, *groups, is_superuser=True, permissions=None):
    user.is_superuser = is_superuser
    user.group_list = [{"id": group.id, "name": group.name} for group in groups]
    if permissions is not None:
        user.permission = {"system-manager": set(permissions)}
    elif is_superuser:
        user.permission = {"system-manager": {"credential-View", "credential-Add", "credential-Edit", "credential-Delete"}}
    user.save(update_fields=["is_superuser"])
    return user


def _cookie(api_client, group):
    api_client.cookies["current_team"] = str(group.id)


@pytest.fixture
def sql_type(db):
    return _sql_type()


@pytest.mark.django_db
def test_create_list_retrieve_never_echo_secret(api_client, authenticated_user, sql_type):
    owner = _group("http-owner")
    _actor(authenticated_user, owner)
    _cookie(api_client, owner)

    with patch("apps.system_mgmt.viewset.credential_viewset.log_operation") as mock_log:
        created = api_client.post(
            f"{V}/credential/",
            {
                "name": "Prod DB",
                "type": sql_type.key,
                "group_id": owner.id,
                "fields": {"username": "root", "password": SECRET},
            },
            format="json",
        )

    assert created.status_code == 201
    body = created.data if hasattr(created, "data") else created.json()
    assert SECRET not in str(body)
    assert "password" not in (body.get("fields") or {})
    assert body["credential_id"].startswith("crd-sqlhttp-")
    mock_log.assert_called_once()
    assert SECRET not in str(mock_log.call_args)

    listed = api_client.get(f"{V}/credential/")
    assert listed.status_code == 200
    items = _payload(listed)
    assert items[0]["credential_id"] == body["credential_id"]
    assert SECRET not in str(listed.data)
    assert "password" not in items[0]["fields"]
    assert "******" not in str(listed.data)

    detail = api_client.get(f"{V}/credential/{body['credential_id']}/")
    assert detail.status_code == 200
    assert SECRET not in str(detail.data)
    assert "password" not in (detail.data.get("fields") or {})


@pytest.mark.django_db
def test_create_without_add_permission_is_forbidden(api_client, authenticated_user, sql_type):
    owner = _group("http-no-add")
    _actor(authenticated_user, owner, is_superuser=False, permissions=["credential-View"])
    _cookie(api_client, owner)

    response = api_client.post(
        f"{V}/credential/",
        {
            "name": "Denied",
            "type": sql_type.key,
            "group_id": owner.id,
            "fields": {"username": "u", "password": SECRET},
        },
        format="json",
    )
    assert response.status_code == 403
    assert not Credential.objects.filter(name="Denied").exists()


@pytest.mark.django_db
def test_http_ledger_lists_authorized_orgs_not_consume_share(api_client, authenticated_user, sql_type):
    root = _group("http-root")
    child = _group("http-child", root.id)
    sibling = _group("http-sibling")
    _actor(authenticated_user, root, child, sibling)
    _cookie(api_client, root)

    root_resp = api_client.post(
        f"{V}/credential/",
        {"name": "Root", "type": sql_type.key, "group_id": root.id, "fields": {"username": "r", "password": SECRET}},
        format="json",
    )
    assert root_resp.status_code == 201
    root_id = root_resp.data["credential_id"]

    _cookie(api_client, child)
    child_resp = api_client.post(
        f"{V}/credential/",
        {"name": "Child", "type": sql_type.key, "group_id": child.id, "fields": {"username": "c", "password": SECRET}},
        format="json",
    )
    assert child_resp.status_code == 201
    child_id = child_resp.data["credential_id"]

    expected = {root_id, child_id}
    _cookie(api_client, root)
    assert {item["credential_id"] for item in _payload(api_client.get(f"{V}/credential/"))} == expected
    assert api_client.get(f"{V}/credential/{child_id}/").status_code == 200

    _cookie(api_client, child)
    assert {item["credential_id"] for item in _payload(api_client.get(f"{V}/credential/"))} == expected

    _cookie(api_client, sibling)
    assert {item["credential_id"] for item in _payload(api_client.get(f"{V}/credential/"))} == expected

    _actor(authenticated_user, child, is_superuser=False, permissions=["credential-View"])
    _cookie(api_client, child)
    child_only = {item["credential_id"] for item in _payload(api_client.get(f"{V}/credential/"))}
    assert child_only == {child_id}
    selectable = {item["credential_id"] for item in _payload(api_client.get(f"{V}/credential/selectable/"))}
    assert selectable == expected


@pytest.mark.django_db
def test_create_cannot_assign_parent_without_parent_authorization(api_client, authenticated_user, sql_type):
    root = _group("http-assign-root")
    child = _group("http-assign-child", root.id)
    _actor(
        authenticated_user,
        child,
        is_superuser=False,
        permissions=["credential-View", "credential-Add"],
    )
    _cookie(api_client, child)

    response = api_client.post(
        f"{V}/credential/",
        {"name": "Escalate", "type": sql_type.key, "group_id": root.id, "fields": {"username": "u", "password": SECRET}},
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_patch_blank_secret_does_not_echo_and_type_list_is_public(api_client, authenticated_user, sql_type):
    owner = _group("http-patch")
    _actor(authenticated_user, owner)
    _cookie(api_client, owner)
    created = api_client.post(
        f"{V}/credential/",
        {"name": "DB", "type": sql_type.key, "group_id": owner.id, "fields": {"username": "old", "password": SECRET}},
        format="json",
    )
    credential_id = created.data["credential_id"]
    patched = api_client.patch(
        f"{V}/credential/{credential_id}/",
        {"name": "DB renamed", "fields": {"username": "new", "password": ""}},
        format="json",
    )
    assert patched.status_code == 200
    assert patched.data["name"] == "DB renamed"
    assert patched.data["fields"]["username"] == "new"
    assert "password" not in patched.data["fields"]
    assert SECRET not in str(patched.data)

    types = api_client.get(f"{V}/credential_type/")
    assert types.status_code == 200
    keys = {item["key"] for item in _payload(types)}
    assert sql_type.key in keys


@pytest.mark.django_db
def test_selectable_and_groups_require_view(api_client, authenticated_user, sql_type):
    owner = _group("http-no-view")
    _actor(authenticated_user, owner, is_superuser=False, permissions=[])
    _cookie(api_client, owner)
    assert api_client.get(f"{V}/credential/selectable/").status_code == 403
    assert api_client.get(f"{V}/credential/assignable_groups/").status_code == 403
    assert api_client.get(f"{V}/credential/usable_groups/").status_code == 403
    assert api_client.get(f"{V}/credential_type/selectable/").status_code == 403


@pytest.mark.django_db
def test_child_without_parent_auth_cannot_disable_or_delete_parent_credential(api_client, authenticated_user, sql_type):
    root = _group("http-disable-root")
    child = _group("http-disable-child", root.id)
    _actor(authenticated_user, root)
    _cookie(api_client, root)
    created = api_client.post(
        f"{V}/credential/",
        {"name": "Root", "type": sql_type.key, "group_id": root.id, "fields": {"username": "r", "password": SECRET}},
        format="json",
    )
    assert created.status_code == 201
    credential_id = created.data["credential_id"]
    _actor(
        authenticated_user,
        child,
        is_superuser=False,
        permissions=["credential-View", "credential-Edit", "credential-Delete"],
    )
    _cookie(api_client, child)
    disabled = api_client.post(f"{V}/credential/{credential_id}/disable/", {"disabled": True}, format="json")
    assert disabled.status_code == 403
    deleted = api_client.delete(f"{V}/credential/{credential_id}/")
    assert deleted.status_code == 403
    assert Credential.objects.filter(credential_id=credential_id).exists()
