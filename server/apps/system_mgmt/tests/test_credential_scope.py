import pytest

from apps.system_mgmt.models import Group
from apps.system_mgmt.services.credential_scope import (
    is_current_team_authorized,
    manageable_owner_group_ids,
    usable_owner_group_ids,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def make_group(name, *, parent_id=0, is_delete=False):
    return Group.objects.create(name=name, parent_id=parent_id, is_delete=is_delete)


def test_owner_visibility_is_current_team_and_active_ancestors_only():
    root = make_group("credential-scope-root")
    child = make_group("credential-scope-child", parent_id=root.id)

    assert usable_owner_group_ids(child.id) == frozenset({root.id, child.id})
    assert usable_owner_group_ids(root.id) == frozenset({root.id})


def test_parent_does_not_see_child_owned_credentials_but_child_sees_both():
    root = make_group("credential-owner-root")
    child = make_group("credential-owner-child", parent_id=root.id)

    assert child.id in usable_owner_group_ids(child.id)
    assert root.id in usable_owner_group_ids(child.id)
    assert child.id not in usable_owner_group_ids(root.id)


def test_unauthorized_current_team_fails_closed_for_authorization_and_management():
    root = make_group("credential-unauthorized-root")
    child = make_group("credential-unauthorized-child", parent_id=root.id)

    assert not is_current_team_authorized(child.id, [root.id], is_superuser=False)
    assert manageable_owner_group_ids(child.id, [root.id], is_superuser=False) == frozenset()
    assert child.id not in manageable_owner_group_ids(child.id, [root.id], is_superuser=False)


def test_manageable_owner_ids_are_authorized_active_groups_including_siblings():
    root = make_group("credential-manage-root")
    child = make_group("credential-manage-child", parent_id=root.id)
    sibling = make_group("credential-manage-sibling")
    outsider = make_group("credential-manage-outsider")

    assert is_current_team_authorized(root.id, [{"id": root.id}], is_superuser=False)
    assert manageable_owner_group_ids(
        root.id,
        [{"id": root.id}, {"id": sibling.id}],
        is_superuser=False,
    ) == frozenset({root.id, sibling.id})
    assert child.id not in manageable_owner_group_ids(root.id, [root.id, sibling.id], is_superuser=False)
    assert outsider.id not in manageable_owner_group_ids(root.id, [root.id, sibling.id], is_superuser=False)


def test_archived_group_breaks_ancestor_chain_and_is_not_manageable():
    root = make_group("credential-archive-root")
    archived = make_group("credential-archive-parent", parent_id=root.id, is_delete=True)
    child = make_group("credential-archive-child", parent_id=archived.id)

    assert usable_owner_group_ids(child.id) == frozenset({child.id})
    assert archived.id not in manageable_owner_group_ids(
        root.id, [root.id, archived.id, child.id], is_superuser=False
    )
    assert not is_current_team_authorized(archived.id, [archived.id], is_superuser=False)


def test_superuser_manageable_ids_are_all_active_organizations():
    active = make_group("credential-superuser-active")
    sibling = make_group("credential-superuser-sibling")
    archived = make_group("credential-superuser-archived", is_delete=True)

    assert is_current_team_authorized(active.id, [], is_superuser=True)
    managed = manageable_owner_group_ids(active.id, [], is_superuser=True)
    assert {active.id, sibling.id}.issubset(managed)
    assert archived.id not in managed
    assert not is_current_team_authorized(archived.id, [], is_superuser=True)
    assert manageable_owner_group_ids(archived.id, [], is_superuser=True) == frozenset()
    assert not is_current_team_authorized(999999999, [], is_superuser=True)
