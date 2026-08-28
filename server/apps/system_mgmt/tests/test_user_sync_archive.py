"""用户同步与组织归档：对账归档、根/子复用、删源与同步启动行锁。"""
import uuid
from unittest.mock import patch

import pytest
from django.contrib.auth.hashers import make_password
from django.db.models.query import QuerySet

from apps.system_mgmt.models import (
    Group,
    User,
    UserSyncRun,
    UserSyncRunStatusChoices,
    UserSyncSource,
)
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult
from apps.system_mgmt.services import user_sync_service as user_sync_service_module
from apps.system_mgmt.services.user_sync_service import _sync_groups, execute_user_sync

pytestmark = pytest.mark.django_db


@pytest.fixture
def ready_integration_instance(db):
    from apps.system_mgmt.models import IntegrationInstance

    return IntegrationInstance.objects.create(
        name="feishu-sync-archive",
        provider_key="feishu",
        enabled=True,
        status="ready",
        capability_status={
            "user_sync": "ready",
            "login_auth": "pending_verification",
            "im_notification": "pending_verification",
        },
        config={},
    )


def _source(ready_integration_instance, name, root_name):
    return UserSyncSource.objects.create(
        name=name,
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name=root_name,
        business_config={"root_department_id": "0"},
        field_mapping={"username": "user_id"},
        schedule_config={"mode": "disabled"},
    )


def test_sync_groups_reuses_archived_by_scoped_external_id_across_parents(ready_integration_instance):
    source = _source(ready_integration_instance, "reuse-archived-group", "Reuse Root")
    root = Group.objects.create(
        name="Reuse Root",
        parent_id=0,
        sync_source=source,
        external_id=f"user-sync:{source.id}:0",
    )
    old_parent = Group.objects.create(
        name="Old Parent",
        parent_id=root.id,
        sync_source=source,
        external_id=f"user-sync:{source.id}:old-parent",
    )
    new_parent = Group.objects.create(
        name="New Parent",
        parent_id=root.id,
        sync_source=source,
        external_id=f"user-sync:{source.id}:new-parent",
    )
    archived = Group.objects.create(
        name="Moved Dept",
        parent_id=old_parent.id,
        sync_source=source,
        external_id=f"user-sync:{source.id}:moved",
        is_delete=True,
    )
    archived_id = archived.id

    mapping, active_ids = _sync_groups(
        source,
        [
            {"id": "old-parent", "parent_id": "0", "name": "Old Parent"},
            {"id": "new-parent", "parent_id": "0", "name": "New Parent"},
            {"id": "moved", "parent_id": "new-parent", "name": "Moved Dept Renamed"},
        ],
        root,
        "0",
    )

    archived.refresh_from_db()
    assert mapping["moved"] == archived_id
    assert archived.is_delete is False
    assert archived.parent_id == new_parent.id
    assert archived.name == "Moved Dept Renamed"
    assert archived_id in active_ids


def test_get_or_create_root_reactivates_archived_root_same_id(ready_integration_instance):
    source = _source(ready_integration_instance, "reactivate-root", "Archive Root Name")
    root = Group.objects.create(
        name="Archive Root Name",
        parent_id=0,
        sync_source=source,
        external_id=f"user-sync:{source.id}:0",
        is_delete=True,
    )
    root_id = root.id

    restored = user_sync_service_module._get_or_create_root_group(source)

    assert restored.id == root_id
    restored.refresh_from_db()
    assert restored.is_delete is False
    assert restored.external_id == f"user-sync:{source.id}:0"
    assert restored.sync_source_id == source.id


def test_get_or_create_root_does_not_promote_non_root_with_same_external_id(ready_integration_instance):
    source = _source(ready_integration_instance, "no-promote-root", "No Promote Root")
    parent = Group.objects.create(name="No Promote Parent", parent_id=0)
    child = Group.objects.create(
        name="Looks Like Root Scope",
        parent_id=parent.id,
        sync_source=source,
        external_id=f"user-sync:{source.id}:0",
    )

    created = user_sync_service_module._get_or_create_root_group(source)

    child.refresh_from_db()
    assert created.id != child.id
    assert created.parent_id == 0
    assert created.sync_source_id == source.id
    assert created.external_id == f"user-sync:{source.id}:0"
    assert child.parent_id == parent.id
    assert child.external_id == f"user-sync:{source.id}:0"


def test_get_or_create_root_rejects_unrelated_local_name_collision(ready_integration_instance):
    source = _source(ready_integration_instance, "root-name-collision", "Shared Root Name")
    local_root = Group.objects.create(name="Shared Root Name", parent_id=0, sync_source=None, external_id=None)

    with pytest.raises(ValueError, match="(?i)conflict|冲突|already exists|占用"):
        user_sync_service_module._get_or_create_root_group(source)

    local_root.refresh_from_db()
    assert local_root.sync_source_id is None
    assert local_root.external_id in (None, "")
    assert not Group.objects.filter(sync_source=source, parent_id=0).exclude(id=local_root.id).exists()


def test_ad_single_to_multi_releases_root_external_id_and_reparents_child_ou(db):
    """单 DN 改多 DN：本地根让出原 DN 外部标识，原 OU 成子组织，已有子 OU 只改父不换主键。"""
    from apps.system_mgmt.models import IntegrationInstance

    instance = IntegrationInstance.objects.create(
        name="ad-multi-handoff",
        provider_key="ad",
        enabled=True,
        status="ready",
        capability_status={"user_sync": "ready"},
        config={},
    )
    dn_a = "OU=BizA,DC=corp,DC=com"
    dn_c = "OU=BizC,DC=corp,DC=com"
    child_dn = "OU=Dev,OU=BizA,DC=corp,DC=com"

    source = UserSyncSource.objects.create(
        name="ad-handoff-source",
        integration_instance=instance,
        enabled=True,
        root_group_name="AD Local Root",
        business_config={"root_dns": [dn_a]},
        field_mapping={"username": "sAMAccountName"},
        schedule_config={"mode": "disabled"},
    )
    root = Group.objects.create(
        name="AD Local Root",
        parent_id=0,
        sync_source=source,
        external_id=f"user-sync:{source.id}:{dn_a}",
    )
    existing_child = Group.objects.create(
        name="Dev",
        parent_id=root.id,
        sync_source=source,
        external_id=f"user-sync:{source.id}:{child_dn}",
    )
    existing_child_id = existing_child.id

    source.business_config = {"root_dns": [dn_a, dn_c]}
    source.save(update_fields=["business_config"])

    new_root = user_sync_service_module._get_or_create_root_group(source)
    assert new_root.id == root.id
    new_root.refresh_from_db()
    assert new_root.external_id == f"user-sync:{source.id}:__local_root__"

    group_list = [
        {"id": dn_a, "name": "BizA", "parent_id": "__local_root__"},
        {"id": dn_c, "name": "BizC", "parent_id": "__local_root__"},
        {"id": child_dn, "name": "Dev", "parent_id": dn_a},
    ]
    mapping = _sync_groups(source, group_list, new_root, "__local_root__")

    existing_child.refresh_from_db()
    assert existing_child.id == existing_child_id
    assert existing_child.parent_id == mapping[dn_a]
    assert mapping[dn_a] != new_root.id
    assert Group.objects.get(id=mapping[dn_a]).external_id == f"user-sync:{source.id}:{dn_a}"
    assert Group.objects.get(id=mapping[dn_c]).parent_id == new_root.id


def test_execute_user_sync_locks_source_before_creating_running_run(ready_integration_instance):
    source = _source(ready_integration_instance, "lock-before-running", "Lock Before Running Root")
    events = []
    real_lock = user_sync_service_module._lock_user_sync_source
    real_create = UserSyncRun.objects.create

    def tracking_lock(source_id):
        events.append(("lock", source_id))
        return real_lock(source_id)

    def tracking_create(*args, **kwargs):
        events.append(("create", kwargs.get("status")))
        return real_create(*args, **kwargs)

    payload = CapabilityExecutionResult.success_result("ok", payload={"group_list": [], "user_list": []})
    with (
        patch.object(user_sync_service_module, "_lock_user_sync_source", side_effect=tracking_lock),
        patch.object(UserSyncRun.objects, "create", side_effect=tracking_create),
        patch(
            "apps.system_mgmt.services.user_sync_service.RuntimeApplicationService.execute",
            return_value=payload,
        ),
    ):
        result = execute_user_sync(source.id)

    assert result["result"] is True
    assert events.index(("lock", source.id)) < events.index(("create", UserSyncRunStatusChoices.RUNNING))


def test_execute_user_sync_refuses_when_source_missing_under_lock(ready_integration_instance):
    source = _source(ready_integration_instance, "missing-under-lock", "Missing Under Lock Root")
    with patch.object(
        user_sync_service_module,
        "_lock_user_sync_source",
        side_effect=UserSyncSource.DoesNotExist,
    ):
        result = execute_user_sync(source.id)

    assert result["result"] is False
    assert "not found" in result["message"].lower()
    assert not UserSyncRun.objects.filter(source=source, status=UserSyncRunStatusChoices.RUNNING).exists()


def test_reconcile_uses_public_lock_protocol_before_archive(ready_integration_instance):
    source = _source(ready_integration_instance, "reconcile-lock-protocol", "Reconcile Protocol Root")
    root = Group.objects.create(
        name="Reconcile Protocol Root",
        parent_id=0,
        sync_source=source,
        external_id=f"user-sync:{source.id}:0",
    )
    stale = Group.objects.create(
        name="Protocol Stale",
        parent_id=root.id,
        sync_source=source,
        external_id=f"user-sync:{source.id}:stale",
    )
    remaining = Group.objects.create(name="Protocol Remain", parent_id=0)
    User.objects.create(
        user_id=str(uuid.uuid4()),
        username="protocol-keep",
        display_name="Keep",
        email="protocol-keep@example.com",
        password=make_password(""),
        domain="domain.com",
        group_list=[stale.id, remaining.id],
        sync_source=source,
    )
    real_lock = user_sync_service_module.GroupArchiveService.lock_groups_and_overlapping_users
    calls = []

    def tracking_lock(group_ids, extra_user_ids=None):
        calls.append((set(group_ids), extra_user_ids or set()))
        return real_lock(group_ids, extra_user_ids=extra_user_ids)

    with patch.object(
        user_sync_service_module.GroupArchiveService,
        "lock_groups_and_overlapping_users",
        side_effect=tracking_lock,
    ):
        user_sync_service_module._reconcile_synced_directory(
            source=source,
            synced_usernames=["protocol-keep"],
            active_group_ids=[root.id],
            root_group_id=root.id,
        )

    assert calls
    locked_groups, _extra = calls[0]
    assert stale.id in locked_groups
    stale.refresh_from_db()
    assert stale.is_delete is True


def test_delete_source_uses_public_lock_protocol_before_archive(ready_integration_instance):
    from apps.system_mgmt.services.user_sync_service import delete_user_sync_source

    source = _source(ready_integration_instance, "delete-lock-protocol", "Delete Protocol Root")
    root = Group.objects.create(
        name="Delete Protocol Root",
        parent_id=0,
        sync_source=source,
        external_id=f"user-sync:{source.id}:0",
    )
    remaining = Group.objects.create(name="Delete Protocol Remain", parent_id=0)
    User.objects.create(
        username="delete-protocol-local",
        display_name="Local",
        email="delete-protocol-local@example.com",
        password="x",
        domain="domain.com",
        group_list=[root.id, remaining.id],
        sync_source=None,
    )
    real_lock = user_sync_service_module.GroupArchiveService.lock_groups_and_overlapping_users
    calls = []

    def tracking_lock(group_ids, extra_user_ids=None):
        calls.append(set(group_ids))
        return real_lock(group_ids, extra_user_ids=extra_user_ids)

    with patch.object(
        user_sync_service_module.GroupArchiveService,
        "lock_groups_and_overlapping_users",
        side_effect=tracking_lock,
    ):
        result = delete_user_sync_source(source)

    assert result["result"] is True
    assert calls
    assert root.id in calls[0]
    root.refresh_from_db()
    assert root.is_delete is True


def test_reconcile_archives_groups_before_deleting_stale_users(ready_integration_instance):
    source = _source(ready_integration_instance, "reconcile-lock-order", "Reconcile Lock Order Root")
    root = Group.objects.create(
        name="Reconcile Lock Order Root",
        parent_id=0,
        sync_source=source,
        external_id=f"user-sync:{source.id}:0",
    )
    stale = Group.objects.create(
        name="Stale",
        parent_id=root.id,
        sync_source=source,
        external_id=f"user-sync:{source.id}:stale",
    )
    keep_user = User.objects.create(
        user_id=str(uuid.uuid4()),
        username="keep-me",
        display_name="Keep",
        email="keep@example.com",
        password=make_password(""),
        domain="domain.com",
        group_list=[stale.id],
        sync_source=source,
    )
    stale_user = User.objects.create(
        user_id=str(uuid.uuid4()),
        username="drop-me",
        display_name="Drop",
        email="drop@example.com",
        password=make_password(""),
        domain="domain.com",
        group_list=[stale.id],
        sync_source=source,
    )
    call_order = []
    real_archive = user_sync_service_module.GroupArchiveService.archive_group_ids_keeping_membership
    original_qs_delete = QuerySet.delete

    def tracking_archive(group_ids):
        call_order.append("archive_groups")
        assert User.objects.filter(id=stale_user.id).exists()
        return real_archive(group_ids)

    def wrapped_qs_delete(self):
        if self.model is User and stale_user.id in list(self.values_list("id", flat=True)):
            call_order.append("delete_users")
            assert "archive_groups" in call_order
            assert Group.objects.filter(id=stale.id, is_delete=True).exists()
        return original_qs_delete(self)

    with (
        patch.object(
            user_sync_service_module.GroupArchiveService,
            "archive_group_ids_keeping_membership",
            side_effect=tracking_archive,
        ),
        patch.object(QuerySet, "delete", wrapped_qs_delete),
    ):
        result = user_sync_service_module._reconcile_synced_directory(
            source=source,
            synced_usernames=["keep-me"],
            active_group_ids=[root.id],
            root_group_id=root.id,
        )

    assert result["deleted_group_count"] == 1
    assert result["deleted_user_count"] == 1
    assert call_order == ["archive_groups", "delete_users"]
    stale.refresh_from_db()
    keep_user.refresh_from_db()
    assert stale.is_delete is True
    assert keep_user.group_list == [stale.id]
    assert not User.objects.filter(id=stale_user.id).exists()


def test_execute_user_sync_reports_conflicting_root_group_name(ready_integration_instance):
    Group.objects.create(name="AD用户测试", parent_id=0)
    source = _source(ready_integration_instance, "name-conflict", "AD用户测试")
    result = CapabilityExecutionResult.success_result(
        "ok",
        payload={
            "group_list": [{"id": "dept-a", "parent_id": "0", "name": "Dept A"}],
            "user_list": [],
        },
    )

    with patch(
        "apps.system_mgmt.services.user_sync_service.RuntimeApplicationService.execute",
        return_value=result,
    ):
        response = execute_user_sync(source.id)

    run = UserSyncRun.objects.get(source=source)
    assert response["result"] is False
    assert response["message"] == "group_name_conflict"
    assert run.payload["phase_progress"]["sync_groups"]["status"] == "error"
    assert run.payload["phase_error"]["error_code"] == "group_name_conflict"
    assert run.payload["phase_error"]["error_params"] == {"name": "AD用户测试"}
    assert "error_message" not in run.payload["phase_error"]


def test_archived_same_name_blocks_until_permanent_delete_then_creates_new(
    ready_integration_instance,
):
    from types import SimpleNamespace

    from apps.system_mgmt.services.group_archive_service import GroupArchiveService

    source = _source(ready_integration_instance, "archived-name-free", "Free Name Root")
    root = Group.objects.create(
        name="Free Name Root",
        parent_id=0,
        sync_source=source,
        external_id=f"user-sync:{source.id}:0",
    )
    archived = Group.objects.create(
        name="Finance",
        parent_id=root.id,
        sync_source=source,
        external_id=f"user-sync:{source.id}:old-finance",
        is_delete=True,
    )
    archived_id = archived.id
    other = Group.objects.create(name="finance-user-home", parent_id=0)
    User.objects.create(
        username="finance-archive-user",
        password=make_password("x"),
        display_name="finance-archive-user",
        email="finance-archive-user@example.com",
        domain="domain.com",
        group_list=[archived.id, other.id],
    )

    with pytest.raises(user_sync_service_module.UserSyncGroupNameConflict, match="Finance"):
        _sync_groups(
            source,
            [{"id": "new-finance", "parent_id": "0", "name": "Finance"}],
            root,
            "0",
        )

    actor = SimpleNamespace(
        is_superuser=True,
        group_list=[],
        locale="en",
        username="archive-admin",
        domain="domain.com",
    )
    deleted = GroupArchiveService.permanently_delete_archived_root(actor=actor, group_id=archived_id)
    assert deleted["result"] is True

    mapping, _ = _sync_groups(
        source,
        [{"id": "old-finance", "parent_id": "0", "name": "Finance"}],
        root,
        "0",
    )
    created = Group.objects.get(id=mapping["old-finance"])
    assert created.id != archived_id
    assert created.name == "Finance"
    assert created.is_delete is False
    assert created.external_id == f"user-sync:{source.id}:old-finance"


def test_sync_groups_reports_conflicting_child_group_name(ready_integration_instance):
    source = _source(ready_integration_instance, "child-name-conflict", "Conflict Root")
    root = Group.objects.create(
        name="Conflict Root",
        parent_id=0,
        sync_source=source,
        external_id=f"user-sync:{source.id}:0",
    )
    Group.objects.create(name="Finance", parent_id=root.id)

    with pytest.raises(user_sync_service_module.UserSyncGroupNameConflict, match="Finance"):
        _sync_groups(
            source,
            [{"id": "dept-finance", "parent_id": "0", "name": "Finance"}],
            root,
            "0",
        )


def test_reconcile_archives_complete_subtree_of_stale_parent(ready_integration_instance):
    source = _source(ready_integration_instance, "stale-subtree", "Stale Subtree Root")
    root = Group.objects.create(
        name="Stale Subtree Root",
        parent_id=0,
        sync_source=source,
        external_id=f"user-sync:{source.id}:0",
    )
    stale_parent = Group.objects.create(
        name="Stale Parent",
        parent_id=root.id,
        sync_source=source,
        external_id=f"user-sync:{source.id}:stale-parent",
    )
    nested = Group.objects.create(
        name="Nested Under Stale",
        parent_id=stale_parent.id,
        sync_source=None,
    )

    result = user_sync_service_module._reconcile_synced_directory(
        source=source,
        synced_usernames=[],
        active_group_ids=[root.id],
        root_group_id=root.id,
    )

    stale_parent.refresh_from_db()
    nested.refresh_from_db()
    assert stale_parent.is_delete is True
    assert nested.is_delete is True
    assert result["deleted_group_count"] == 2


@pytest.mark.django_db(transaction=True)
def test_delete_user_sync_source_keeps_periodic_task_if_archive_fails(ready_integration_instance):
    from django_celery_beat.models import PeriodicTask

    from apps.system_mgmt.services.user_sync_service import delete_user_sync_source

    source = _source(ready_integration_instance, "beat-rollback", "Beat Rollback Root")
    source.schedule_config = {"mode": "daily", "time": "04:00", "timezone": "Asia/Shanghai"}
    source.save(update_fields=["schedule_config"])
    source.create_sync_periodic_task()
    task_name = source.periodic_task_name()
    Group.objects.create(
        name="Beat Rollback Root",
        parent_id=0,
        sync_source=source,
        external_id=f"user-sync:{source.id}:0",
    )
    assert PeriodicTask.objects.filter(name=task_name).exists()

    with patch.object(
        user_sync_service_module.GroupArchiveService,
        "archive_group_ids_keeping_membership",
        side_effect=RuntimeError("archive boom"),
    ):
        with pytest.raises(RuntimeError, match="archive boom"):
            delete_user_sync_source(source)

    assert PeriodicTask.objects.filter(name=task_name).exists()
    assert UserSyncSource.objects.filter(id=source.id).exists()


def test_delete_source_after_reconcile_keeps_local_users(ready_integration_instance):
    from apps.system_mgmt.services.user_sync_service import delete_user_sync_source

    source = _source(ready_integration_instance, "serial-delete", "Serial Delete Root")
    root = Group.objects.create(
        name="Serial Delete Root",
        parent_id=0,
        sync_source=source,
        external_id=f"user-sync:{source.id}:0",
    )
    stale = Group.objects.create(
        name="Serial Stale",
        parent_id=root.id,
        sync_source=source,
        external_id=f"user-sync:{source.id}:stale",
    )
    local_user = User.objects.create(
        username="serial-local",
        display_name="Serial Local",
        email="serial-local@example.com",
        password="x",
        domain="domain.com",
        group_list=[stale.id],
        sync_source=None,
    )
    synced_user = User.objects.create(
        username="serial-synced",
        display_name="Serial Synced",
        email="serial-synced@example.com",
        password="x",
        domain="domain.com",
        group_list=[root.id],
        sync_source=source,
    )

    user_sync_service_module._reconcile_synced_directory(
        source=source,
        synced_usernames=["serial-synced"],
        active_group_ids=[root.id],
        root_group_id=root.id,
    )
    stale.refresh_from_db()
    assert stale.is_delete is True

    result = delete_user_sync_source(source)
    assert result["result"] is True
    assert User.objects.filter(id=local_user.id).exists()
    assert not User.objects.filter(id=synced_user.id).exists()
    root.refresh_from_db()
    assert root.is_delete is True


def test_delete_user_sync_source_stops_beat_before_archive(ready_integration_instance):
    from apps.system_mgmt.models import UserSyncSource
    from apps.system_mgmt.services.group_archive_service import GroupArchiveService
    from apps.system_mgmt.services.user_sync_service import delete_user_sync_source

    source = _source(ready_integration_instance, "beat-before-archive", "Beat Before Root")
    source.schedule_config = {"mode": "daily", "time": "04:00", "timezone": "Asia/Shanghai"}
    source.save(update_fields=["schedule_config"])
    source.create_sync_periodic_task()
    Group.objects.create(
        name="Beat Before Root",
        parent_id=0,
        sync_source=source,
        external_id=f"user-sync:{source.id}:0",
    )
    order = []
    real_delete = UserSyncSource.delete_periodic_task
    real_archive = GroupArchiveService.archive_group_ids_keeping_membership

    def tracking_delete(name):
        order.append("beat")
        return real_delete(name)

    def tracking_archive(group_ids):
        order.append("archive")
        return real_archive(group_ids)

    with patch.object(UserSyncSource, "delete_periodic_task", side_effect=tracking_delete):
        with patch.object(GroupArchiveService, "archive_group_ids_keeping_membership", side_effect=tracking_archive):
            result = delete_user_sync_source(source)

    assert result["result"] is True
    assert order == ["beat", "archive"]


def test_sync_groups_avoids_per_node_lookups(ready_integration_instance):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    source = _source(ready_integration_instance, "sync-nplusone", "Nplus Root")
    root = Group.objects.create(
        name="Nplus Root",
        parent_id=0,
        sync_source=source,
        external_id=f"user-sync:{source.id}:0",
    )
    items = [{"id": f"dept-{index}", "parent_id": "0", "name": f"Dept {index}"} for index in range(12)]
    with CaptureQueriesContext(connection) as ctx:
        mapping, _active = _sync_groups(source, items, root, "0")
    assert all(f"dept-{index}" in mapping for index in range(12))
    assert len(ctx.captured_queries) < 25
