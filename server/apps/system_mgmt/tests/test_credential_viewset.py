from unittest.mock import patch

import pytest

from apps.system_mgmt.models import Group
from apps.system_mgmt.models.credential import Credential, CredentialType
from apps.system_mgmt.services.credential_service import CredentialServiceError, create_credential

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
    assert mock_log.call_args.kwargs["outcome"] == "success"
    assert mock_log.call_args.kwargs["target_name"] == "Prod DB"
    assert mock_log.call_args.kwargs["target_type"] == "credential"

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
    with patch("apps.system_mgmt.viewset.credential_viewset.log_operation") as mock_log:
        missing = api_client.get(f"{V}/credential/crd-sqlhttp-00000000000000000000000000000000/")
    assert missing.status_code == 404
    mock_log.assert_not_called()

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

    with patch("apps.system_mgmt.viewset.credential_viewset.log_operation") as mock_log:
        response = api_client.post(
            f"{V}/credential/",
            {"name": "Escalate", "type": sql_type.key, "group_id": root.id, "fields": {"username": "u", "password": SECRET}},
            format="json",
        )
    assert response.status_code == 403
    mock_log.assert_not_called()


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
def test_selectable_does_not_require_view_but_ledger_and_groups_do(api_client, authenticated_user, sql_type):
    owner = _group("http-no-view")
    _actor(authenticated_user, owner, is_superuser=False, permissions=[])
    _cookie(api_client, owner)
    created = create_credential(
        {
            "name": "Selectable DB",
            "type": sql_type.key,
            "group_id": owner.id,
            "fields": {"username": "u", "password": SECRET},
        },
        actor={
            "current_team": owner.id,
            "group_list": [owner.id],
            "is_superuser": True,
            "username": authenticated_user.username,
            "domain": authenticated_user.domain,
        },
    )
    selectable = api_client.get(f"{V}/credential/selectable/")
    assert selectable.status_code == 200
    items = _payload(selectable)
    assert items[0]["credential_id"] == created.credential_id
    assert items[0]["name"] == "Selectable DB"
    assert "password" not in (items[0].get("fields") or {})
    assert SECRET not in str(selectable.data)
    assert api_client.get(f"{V}/credential_type/selectable/").status_code == 200
    assert api_client.get(f"{V}/credential/").status_code == 403
    assert api_client.get(f"{V}/credential/assignable_groups/").status_code == 403
    assert api_client.get(f"{V}/credential/usable_groups/").status_code == 403


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
    with patch("apps.system_mgmt.viewset.credential_viewset.log_operation") as mock_log:
        disabled = api_client.post(f"{V}/credential/{credential_id}/disable/", {"disabled": True}, format="json")
        deleted = api_client.delete(f"{V}/credential/{credential_id}/")
    assert disabled.status_code == 403
    assert deleted.status_code == 403
    assert Credential.objects.filter(credential_id=credential_id).exists()
    mock_log.assert_not_called()


def _type_payload(key, name="HTTP Type"):
    return {
        "key": key,
        "name": name,
        "categories": ["database"],
        "fields": [{"id": "username", "kind": "string", "required": True}, {"id": "password", "kind": "secret", "required": True}],
    }


@pytest.mark.django_db
def test_credential_service_errors_log_failure_only_for_selected_codes(api_client, authenticated_user, sql_type):
    owner = _group("http-fail-audit")
    _actor(authenticated_user, owner)
    _cookie(api_client, owner)

    with (
        patch(
            "apps.system_mgmt.viewset.credential_viewset.create_type",
            side_effect=CredentialServiceError("conflict"),
        ),
        patch("apps.system_mgmt.viewset.credential_viewset.log_operation") as mock_log,
    ):
        conflict = api_client.post(f"{V}/credential_type/", _type_payload("dupkey", "Second"), format="json")
    assert conflict.status_code == 409
    assert conflict.json()["message"] == "conflict"
    mock_log.assert_called_once()
    assert mock_log.call_args.kwargs["outcome"] == "failure"
    assert mock_log.call_args.kwargs["failure_reason"] == "conflict"
    assert mock_log.call_args.kwargs["target_name"] == "Second"
    assert SECRET not in str(mock_log.call_args)
    assert "password" not in str(mock_log.call_args.kwargs.get("detail") or {})

    builtin = CredentialType.objects.create(
        key="builtinhttp",
        name="Builtin HTTP",
        categories=["database"],
        fields=[{"id": "username", "kind": "string", "required": True}],
        is_builtin=True,
    )
    with patch("apps.system_mgmt.viewset.credential_viewset.log_operation") as mock_log:
        immutable = api_client.put(
            f"{V}/credential_type/{builtin.key}/",
            {
                "key": builtin.key,
                "name": "Builtin HTTP",
                "categories": ["changed"],
                "fields": builtin.fields,
            },
            format="json",
        )
    assert immutable.status_code == 400
    assert immutable.json()["message"] == "immutable"
    mock_log.assert_called_once()
    assert mock_log.call_args.kwargs["outcome"] == "failure"
    assert mock_log.call_args.kwargs["failure_reason"] == "immutable"
    assert mock_log.call_args.kwargs["target_name"] == "Builtin HTTP"

    created = api_client.post(
        f"{V}/credential/",
        {"name": "In Use DB", "type": sql_type.key, "group_id": owner.id, "fields": {"username": "u", "password": SECRET}},
        format="json",
    )
    assert created.status_code == 201
    credential_id = created.data["credential_id"]

    with patch("apps.system_mgmt.viewset.credential_viewset.log_operation") as mock_log:
        in_use_type = api_client.delete(f"{V}/credential_type/{sql_type.key}/")
    assert in_use_type.status_code == 409
    assert in_use_type.json()["message"] == "in_use"
    mock_log.assert_called_once()
    assert mock_log.call_args.kwargs["outcome"] == "failure"
    assert mock_log.call_args.kwargs["failure_reason"] == "in_use"
    assert mock_log.call_args.kwargs["target_name"] == sql_type.name

    with (
        patch(
            "apps.system_mgmt.viewset.credential_viewset.delete_credential",
            side_effect=CredentialServiceError("in_use"),
        ),
        patch("apps.system_mgmt.viewset.credential_viewset.log_operation") as mock_log,
    ):
        in_use_cred = api_client.delete(f"{V}/credential/{credential_id}/")
    assert in_use_cred.status_code == 409
    assert in_use_cred.json()["message"] == "in_use"
    mock_log.assert_called_once()
    assert mock_log.call_args.kwargs["outcome"] == "failure"
    assert mock_log.call_args.kwargs["failure_reason"] == "in_use"
    assert mock_log.call_args.kwargs["target_name"] == "In Use DB"
    assert SECRET not in str(mock_log.call_args)

    with (
        patch(
            "apps.system_mgmt.viewset.credential_viewset.set_disabled",
            side_effect=CredentialServiceError("disabled"),
        ),
        patch("apps.system_mgmt.viewset.credential_viewset.log_operation") as mock_log,
    ):
        disabled = api_client.post(f"{V}/credential/{credential_id}/disable/", {"disabled": True}, format="json")
    assert disabled.status_code == 400
    assert disabled.json()["message"] == "disabled"
    mock_log.assert_called_once()
    assert mock_log.call_args.kwargs["outcome"] == "failure"
    assert mock_log.call_args.kwargs["failure_reason"] == "disabled"
    assert mock_log.call_args.kwargs["target_name"] == "In Use DB"

    with (
        patch(
            "apps.system_mgmt.viewset.credential_viewset.create_credential",
            side_effect=CredentialServiceError("invalid"),
        ),
        patch("apps.system_mgmt.viewset.credential_viewset.log_operation") as mock_log,
    ):
        invalid = api_client.post(
            f"{V}/credential/",
            {"name": "Invalid DB", "type": sql_type.key, "group_id": owner.id, "fields": {"username": "u", "password": SECRET}},
            format="json",
        )
    assert invalid.status_code == 400
    assert invalid.json()["message"] == "invalid"
    mock_log.assert_not_called()

    with (
        patch(
            "apps.system_mgmt.viewset.credential_viewset.update_credential",
            side_effect=CredentialServiceError("not_found"),
        ),
        patch("apps.system_mgmt.viewset.credential_viewset.log_operation") as mock_log,
    ):
        missing = api_client.patch(
            f"{V}/credential/{credential_id}/",
            {"name": "In Use DB", "fields": {"username": "new"}},
            format="json",
        )
    assert missing.status_code == 404
    mock_log.assert_not_called()

    with patch("apps.system_mgmt.viewset.credential_viewset.log_operation") as mock_log:
        ok = api_client.patch(
            f"{V}/credential/{credential_id}/",
            {"name": "In Use DB renamed", "fields": {"username": "new"}},
            format="json",
        )
    assert ok.status_code == 200
    mock_log.assert_called_once()
    assert mock_log.call_args.kwargs["outcome"] == "success"
    assert not mock_log.call_args.kwargs.get("failure_reason")
    assert SECRET not in str(mock_log.call_args)
