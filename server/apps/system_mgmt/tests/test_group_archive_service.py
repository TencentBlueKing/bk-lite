"""GroupArchiveService：手工归档、恢复、永久删除与授权边界。"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.db import transaction

from apps.system_mgmt.models import Group, IntegrationInstance, User, UserSyncSource
from apps.system_mgmt.services.archived_group_query import ArchivedGroupQuery
from apps.system_mgmt.services.group_archive_service import GroupArchiveService

pytestmark = pytest.mark.django_db


def _super_actor(**overrides):
    defaults = {
        "is_superuser": True,
        "group_list": [],
        "locale": "en",
        "username": "archive-admin",
        "domain": "domain.com",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_user(username, group_list, domain="domain.com"):
    return User.objects.create(
        username=username,
        password="x",
        display_name=username,
        email=f"{username}@example.com",
        domain=domain,
        group_list=group_list,
    )


def _make_sync_source(name="archive-sync-source"):
    instance = IntegrationInstance.objects.create(
        name=f"{name}-instance",
        provider_key="feishu",
        enabled=True,
        status="ready",
        capability_status={"user_sync": "ready"},
        config={},
    )
    return UserSyncSource.objects.create(
        name=name,
        integration_instance=instance,
        root_group_name="同步根组织",
        business_config={"root_department_id": "0"},
        field_mapping={"username": "user_id"},
    )


def test_group_has_is_delete_default_false():
    g = Group.objects.create(name="archive-model-probe", parent_id=0)
    assert g.is_delete is False


def test_is_archive_root_when_parent_active_or_missing():
    parent = Group.objects.create(name="ar-parent", parent_id=0, is_delete=False)
    archived_child = Group.objects.create(name="ar-child", parent_id=parent.id, is_delete=True)
    assert GroupArchiveService.is_archive_root(archived_child, parent) is True

    archived_root = Group.objects.create(name="ar-root", parent_id=0, is_delete=True)
    assert GroupArchiveService.is_archive_root(archived_root, None) is True

    archived_parent = Group.objects.create(name="ar-aparent", parent_id=0, is_delete=True)
    nested = Group.objects.create(name="ar-nested", parent_id=archived_parent.id, is_delete=True)
    assert GroupArchiveService.is_archive_root(nested, archived_parent) is False

    active = Group.objects.create(name="ar-active", parent_id=0, is_delete=False)
    assert GroupArchiveService.is_archive_root(active, None) is False


def test_archive_keeps_group_list_and_sets_is_delete():
    parent = Group.objects.create(name="p-arch", parent_id=0)
    child = Group.objects.create(name="c-arch", parent_id=parent.id)
    other = Group.objects.create(name="other-arch", parent_id=0)
    user = _make_user("u1", [parent.id, other.id])

    result = GroupArchiveService.archive_subtree(actor=_super_actor(), group_id=parent.id)

    assert result["result"] is True
    assert set(result["archived_ids"]) == {parent.id, child.id}
    parent.refresh_from_db()
    child.refresh_from_db()
    user.refresh_from_db()
    assert parent.is_delete is True and child.is_delete is True
    assert user.group_list == [parent.id, other.id]


@pytest.mark.parametrize(
    "op",
    ["archive", "permanently_delete"],
)
def test_rejects_when_user_would_have_no_active_group(op):
    if op == "archive":
        g = Group.objects.create(name="only", parent_id=0)
        _make_user("lonely", [g.id])
        result = GroupArchiveService.archive_subtree(actor=_super_actor(), group_id=g.id)
        g.refresh_from_db()
        assert g.is_delete is False
        username = "lonely"
    else:
        g = Group.objects.create(name="perm-lonely-root", parent_id=0, is_delete=True)
        _make_user("perm-lonely", [g.id])
        result = GroupArchiveService.permanently_delete_archived_root(actor=_super_actor(), group_id=g.id)
        assert Group.objects.filter(id=g.id, is_delete=True).exists()
        username = "perm-lonely"

    assert result["result"] is False
    assert {"username": username, "domain": "domain.com"} in result["affected_users"]


def test_archive_rejects_synced_subtree():
    source = _make_sync_source()
    parent = Group.objects.create(name="local-parent", parent_id=0)
    Group.objects.create(name="synced-child", parent_id=parent.id, sync_source=source)

    result = GroupArchiveService.archive_subtree(actor=_super_actor(), group_id=parent.id)

    assert result["result"] is False
    parent.refresh_from_db()
    assert parent.is_delete is False


def test_archive_rejects_default_and_virtual_top():
    Group.objects.filter(name="Default", parent_id=0).delete()
    default = Group.objects.create(name="Default", parent_id=0)
    virtual = Group.objects.create(name="VTopArch", parent_id=0, is_virtual=True)

    assert GroupArchiveService.archive_subtree(actor=_super_actor(), group_id=default.id)["result"] is False
    assert GroupArchiveService.archive_subtree(actor=_super_actor(), group_id=virtual.id)["result"] is False
    default.refresh_from_db()
    virtual.refresh_from_db()
    assert default.is_delete is False
    assert virtual.is_delete is False


@pytest.mark.parametrize("op", ["archive", "restore", "permanently_delete"])
def test_nonsuperuser_write_rejects_outside_group_list(op):
    allowed = Group.objects.create(
        name=f"{op}-allowed",
        parent_id=0,
        is_delete=(op != "archive"),
    )
    target = Group.objects.create(
        name=f"{op}-forbidden",
        parent_id=0,
        is_delete=(op != "archive"),
    )
    actor = _super_actor(is_superuser=False, group_list=[{"id": allowed.id, "name": allowed.name}])

    if op == "archive":
        result = GroupArchiveService.archive_subtree(actor=actor, group_id=target.id)
        target.refresh_from_db()
        assert target.is_delete is False
    elif op == "restore":
        result = GroupArchiveService.restore_archived_root(actor=actor, group_id=target.id)
        target.refresh_from_db()
        assert target.is_delete is True
    else:
        result = GroupArchiveService.permanently_delete_archived_root(actor=actor, group_id=target.id)
        assert Group.objects.filter(id=target.id, is_delete=True).exists()

    assert result["result"] is False


def test_restore_recursively_clears_is_delete_on_subtree():
    root = Group.objects.create(name="restore-root", parent_id=0, is_delete=True)
    child = Group.objects.create(name="restore-child", parent_id=root.id, is_delete=True)
    grandchild = Group.objects.create(name="restore-gc", parent_id=child.id, is_delete=True)

    result = GroupArchiveService.restore_archived_root(actor=_super_actor(), group_id=root.id)

    assert result["result"] is True
    for node in (root, child, grandchild):
        node.refresh_from_db()
        assert node.is_delete is False


def test_restore_rejects_non_root_archived_node():
    root = Group.objects.create(name="nr-root", parent_id=0, is_delete=True)
    nested = Group.objects.create(name="nr-nested", parent_id=root.id, is_delete=True)

    result = GroupArchiveService.restore_archived_root(actor=_super_actor(), group_id=nested.id)

    assert result["result"] is False
    nested.refresh_from_db()
    root.refresh_from_db()
    assert nested.is_delete is True
    assert root.is_delete is True


def test_list_archived_roots_hides_unauthorized_for_nonsuperuser():
    allowed = Group.objects.create(name="list-allowed", parent_id=0, is_delete=True)
    Group.objects.create(name="list-forbidden", parent_id=0, is_delete=True)
    actor = _super_actor(is_superuser=False, group_list=[{"id": allowed.id, "name": allowed.name}])

    items = ArchivedGroupQuery.list_archived_roots(actor=actor).items

    assert [item.id for item in items] == [allowed.id]
    assert items[0].kind == "local"
    assert items[0].can_restore is True
    assert items[0].can_permanently_delete is True


def test_permanent_delete_removes_group_list_refs():
    root = Group.objects.create(name="perm-root", parent_id=0, is_delete=True)
    child = Group.objects.create(name="perm-child", parent_id=root.id, is_delete=True)
    other = Group.objects.create(name="perm-other", parent_id=0, is_delete=False)
    user = _make_user("perm-user", [root.id, child.id, other.id])

    result = GroupArchiveService.permanently_delete_archived_root(actor=_super_actor(), group_id=root.id)

    assert result["result"] is True
    assert not Group.objects.filter(id__in=[root.id, child.id]).exists()
    user.refresh_from_db()
    assert user.group_list == [other.id]


@pytest.mark.parametrize(
    ("kind", "external_id", "with_source", "can_restore", "can_delete"),
    [
        ("synced_active_source", None, True, False, True),
        ("synced_deleted_source", "user-sync:99:dept-gone", False, False, True),
    ],
)
def test_synced_kind_capabilities(kind, external_id, with_source, can_restore, can_delete):
    source = _make_sync_source("active-src") if with_source else None
    root = Group.objects.create(
        name=f"{kind}-root",
        parent_id=0,
        is_delete=True,
        sync_source=source,
        external_id=external_id or (f"user-sync:{source.id}:dept-1" if source else None),
    )
    other = Group.objects.create(name=f"{kind}-other", parent_id=0, is_delete=False)
    _make_user(f"{kind}-user", [root.id, other.id])

    matched = next(item for item in ArchivedGroupQuery.list_archived_roots(actor=_super_actor()).items if item.id == root.id)
    assert matched.kind == kind
    assert matched.can_restore is can_restore
    assert matched.can_permanently_delete is can_delete

    assert GroupArchiveService.restore_archived_root(actor=_super_actor(), group_id=root.id)["result"] is False
    root.refresh_from_db()
    assert root.is_delete is True

    delete = GroupArchiveService.permanently_delete_archived_root(actor=_super_actor(), group_id=root.id)
    assert delete["result"] is can_delete
    if can_delete:
        assert not Group.objects.filter(id=root.id).exists()
    else:
        assert Group.objects.filter(id=root.id, is_delete=True).exists()


def test_permanent_delete_recomputes_after_concurrent_user_org_edit():
    root = Group.objects.create(name="conc-perm-root", parent_id=0, is_delete=True)
    other = Group.objects.create(name="conc-perm-other", parent_id=0, is_delete=False)
    user = _make_user("conc-perm-user", [root.id, other.id])
    real_overlapping = GroupArchiveService._users_overlapping_groups

    def overlapping_with_race(subtree_ids):
        real_qs = real_overlapping(subtree_ids)

        class RacingQS:
            def only(self, *args):
                return real_qs.only(*args)

            def select_for_update(self):
                User.objects.filter(id=user.id).update(group_list=[root.id])
                return self

            def order_by(self, *args):
                return real_qs.select_for_update().order_by(*args)

            def __iter__(self):
                return iter(real_qs)

        return RacingQS()

    with patch.object(GroupArchiveService, "_users_overlapping_groups", side_effect=overlapping_with_race):
        result = GroupArchiveService.permanently_delete_archived_root(actor=_super_actor(), group_id=root.id)

    assert result["result"] is False
    assert {"username": "conc-perm-user", "domain": "domain.com"} in result["affected_users"]
    assert Group.objects.filter(id=root.id, is_delete=True).exists()
    user.refresh_from_db()
    assert user.group_list == [root.id]


def test_nonsuperuser_write_reject_uses_forbidden_status():
    target = Group.objects.create(name="status-forbidden", parent_id=0)
    actor = _super_actor(is_superuser=False, group_list=[])
    result = GroupArchiveService.archive_subtree(actor=actor, group_id=target.id)
    assert result["result"] is False
    assert result["http_status"] == 403


def test_list_archived_roots_only_walks_authorized_trees():
    allowed = Group.objects.create(name="list-auth-root", parent_id=0, is_delete=True)
    Group.objects.create(name="list-auth-child", parent_id=allowed.id, is_delete=True)
    foreign = Group.objects.create(name="list-foreign-root", parent_id=0, is_delete=True)
    Group.objects.create(name="list-foreign-child", parent_id=foreign.id, is_delete=True)
    actor = _super_actor(is_superuser=False, group_list=[{"id": allowed.id, "name": allowed.name}])

    items = ArchivedGroupQuery.list_archived_roots(actor=actor).items
    assert [item.id for item in items] == [allowed.id]
    assert [child["name"] for child in items[0].children] == ["list-auth-child"]


def test_archive_rejects_when_remaining_group_is_archived():
    remaining = Group.objects.create(name="remain-already-archived", parent_id=0, is_delete=True)
    target = Group.objects.create(name="target-with-archived-remain", parent_id=0)
    _make_user("remain-arch-user", [target.id, remaining.id])

    result = GroupArchiveService.archive_subtree(actor=_super_actor(), group_id=target.id)

    assert result["result"] is False
    target.refresh_from_db()
    assert target.is_delete is False


def test_list_archived_roots_paginates():
    for index in range(3):
        Group.objects.create(name=f"paged-root-{index}", parent_id=0, is_delete=True)

    page1 = ArchivedGroupQuery.list_archived_roots(actor=_super_actor(), page=1, page_size=2)
    page2 = ArchivedGroupQuery.list_archived_roots(actor=_super_actor(), page=2, page_size=2)
    assert page1.count >= 3
    assert len(page1.items) == 2
    assert len(page2.items) >= 1
    assert {item.id for item in page1.items}.isdisjoint({item.id for item in page2.items})


def test_list_archived_roots_caps_descendants_per_root(monkeypatch):
    monkeypatch.setattr(
        "apps.system_mgmt.services.archived_group_query.ARCHIVED_LIST_MAX_DESCENDANTS_PER_ROOT",
        2,
    )
    root = Group.objects.create(name="cap-root", parent_id=0, is_delete=True)
    for index in range(5):
        Group.objects.create(name=f"cap-child-{index}", parent_id=root.id, is_delete=True)

    matched = next(
        item for item in ArchivedGroupQuery.list_archived_roots(actor=_super_actor()).items if item.id == root.id
    )
    assert matched.children_truncated is True
    assert len(matched.children) == 2


def test_lock_groups_and_overlapping_users_relocks_remaining_after_user_lock():
    stale = Group.objects.create(name="lock-proto-stale", parent_id=0)
    remaining = Group.objects.create(name="lock-proto-remain", parent_id=0)
    user = _make_user("lock-proto-user", [stale.id])
    real_lock_groups = GroupArchiveService._lock_groups_sorted

    def lock_groups_then_attach_remaining(group_ids):
        User.objects.filter(id=user.id).update(group_list=[stale.id, remaining.id])
        return real_lock_groups(group_ids)

    with transaction.atomic():
        with patch.object(GroupArchiveService, "_lock_groups_sorted", side_effect=lock_groups_then_attach_remaining):
            locked_by_id, users = GroupArchiveService.lock_groups_and_overlapping_users([stale.id])

    assert remaining.id in locked_by_id
    assert user.id in {locked.id for locked in users}


def test_list_all_archived_groups_includes_descendants_and_skips_active():
    active = Group.objects.create(name="svc-arch-active", parent_id=0)
    root = Group.objects.create(name="svc-arch-root", parent_id=0, is_delete=True)
    child = Group.objects.create(name="svc-arch-child", parent_id=root.id, is_delete=True)

    page = ArchivedGroupQuery.list_all_archived_groups(page=1, page_size=50)
    ids = {item["id"] for item in page.items}
    assert root.id in ids
    assert child.id in ids
    assert active.id not in ids
    assert page.count >= 2
    assert page.page == 1
    assert page.page_size == 50


def _cache_identities(clear_cache):
    users = clear_cache.call_args[0][0]
    return {(row["username"], row.get("domain", "domain.com")) for row in users}


@pytest.mark.parametrize("op", ["archive", "restore", "permanently_delete"])
def test_write_clears_actor_cache_even_when_not_overlapping(op, django_capture_on_commit_callbacks):
    is_delete = op != "archive"
    root = Group.objects.create(name=f"actor-cache-{op}", parent_id=0, is_delete=is_delete)
    other = Group.objects.create(name=f"actor-cache-other-{op}", parent_id=0)
    member = _make_user(f"overlap-{op}", [root.id, other.id])
    actor = _super_actor(id=9001, username=f"actor-{op}")

    with patch("apps.system_mgmt.services.group_archive_service.clear_users_permission_cache") as clear_cache:
        with django_capture_on_commit_callbacks(execute=True):
            if op == "archive":
                result = GroupArchiveService.archive_subtree(actor=actor, group_id=root.id)
            elif op == "restore":
                result = GroupArchiveService.restore_archived_root(actor=actor, group_id=root.id)
            else:
                result = GroupArchiveService.permanently_delete_archived_root(actor=actor, group_id=root.id)

    assert result["result"] is True
    clear_cache.assert_called_once()
    identities = _cache_identities(clear_cache)
    assert (actor.username, actor.domain) in identities
    assert (member.username, member.domain) in identities


def test_archive_does_not_duplicate_overlapping_actor(django_capture_on_commit_callbacks):
    root = Group.objects.create(name="actor-dup-root", parent_id=0)
    other = Group.objects.create(name="actor-dup-other", parent_id=0)
    actor_user = _make_user("actor-dup", [root.id, other.id])
    actor = _super_actor(id=actor_user.id, username=actor_user.username, domain=actor_user.domain)

    with patch("apps.system_mgmt.services.group_archive_service.clear_users_permission_cache") as clear_cache:
        with django_capture_on_commit_callbacks(execute=True):
            result = GroupArchiveService.archive_subtree(actor=actor, group_id=root.id)

    assert result["result"] is True
    clear_cache.assert_called_once()
    users = clear_cache.call_args[0][0]
    assert [row["username"] for row in users].count("actor-dup") == 1
