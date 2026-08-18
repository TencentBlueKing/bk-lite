"""组织归档写路径：手工归档、恢复、永久删除与锁协议。"""

from __future__ import annotations

from django.core.cache import cache
from django.db import transaction
from django.db.models import Q

from apps.core.logger import system_mgmt_logger as logger
from apps.core.utils.loader import LanguageLoader
from apps.core.utils.permission_cache import clear_users_permission_cache
from apps.system_mgmt.models import Group, User
from apps.system_mgmt.services.group_archive_types import (
    KIND_LOCAL,
    ArchiveReject,
    capabilities_for_kind,
    classify_archived_kind,
)
from apps.system_mgmt.utils.group_filter_mixin import normalize_group_id_set
from apps.system_mgmt.utils.group_utils import GroupUtils
from apps.system_mgmt.utils.operation_log_utils import log_operation

_LOCK_SET_RETRIES = 3


class GroupArchiveService:
    @staticmethod
    def is_archive_root(group: Group, parent: Group | None) -> bool:
        """归档根：已归档，且父不存在 / parent_id==0 / 父为活动状态。"""
        if not group.is_delete:
            return False
        if group.parent_id in (0, None):
            return True
        if parent is None:
            return True
        return parent.is_delete is False

    @staticmethod
    def collect_subtree_ids(root_id: int) -> list[int]:
        return GroupUtils.get_group_with_descendants(root_id, include_deleted=True)

    @staticmethod
    def _loader(actor) -> LanguageLoader:
        locale = getattr(actor, "locale", None) or "en"
        return LanguageLoader(app="system_mgmt", default_lang=locale)

    @staticmethod
    def _reject(loader: LanguageLoader, reject: ArchiveReject) -> dict:
        payload = {
            "result": False,
            "message": loader.get(reject.message_key) or reject.message_key,
            "http_status": reject.http_status,
        }
        if reject.affected_users:
            payload["affected_users"] = reject.affected_users
        return payload

    @staticmethod
    def _users_overlapping_groups(subtree_ids: list[int]):
        if not subtree_ids:
            return User.objects.none()
        # group_list 为 JSONField：整数列表用 contains=int / contains=[int]；
        # overlap 在部分环境下对 jsonb 不可靠，与 update_group 一致使用 contains。
        query = Q()
        for group_id in subtree_ids:
            gid = int(group_id)
            query |= Q(group_list__contains=gid) | Q(group_list__contains=[gid])
        return User.objects.filter(query).order_by("id")

    @classmethod
    def _users_without_remaining_active(
        cls,
        users: list[User],
        subtree_id_set: set[int],
        locked_by_id: dict[int, Group] | None = None,
    ) -> list[dict]:
        remaining_by_user: list[tuple[User, set[int]]] = []
        remaining_all: set[int] = set()
        for user in users:
            remaining_ids = normalize_group_id_set(user.group_list) - subtree_id_set
            remaining_by_user.append((user, remaining_ids))
            remaining_all.update(remaining_ids)
        if locked_by_id is not None:
            active_ids = {
                group_id
                for group_id, group in locked_by_id.items()
                if group_id not in subtree_id_set and not group.is_delete
            }
        else:
            active_ids = set()
            if remaining_all:
                active_ids = set(
                    GroupUtils.active_queryset(id__in=remaining_all).values_list("id", flat=True)
                )
        affected = []
        for user, remaining_ids in remaining_by_user:
            if not remaining_ids or not remaining_ids.intersection(active_ids):
                affected.append({"username": user.username, "domain": user.domain})
        return affected

    @staticmethod
    def _is_protected_root(group: Group) -> bool:
        if group.parent_id not in (0, None):
            return False
        return group.name == "Default" or bool(group.is_virtual)

    @classmethod
    def _refresh_remaining_locks(cls, users: list[User], subtree_id_set: set[int], locked_by_id: dict[int, Group]):
        remaining = cls._remaining_group_ids(users, subtree_id_set)
        missing = remaining - set(locked_by_id)
        if missing:
            for group in cls._lock_groups_sorted(missing):
                locked_by_id[group.id] = group
        return locked_by_id

    @staticmethod
    def _lock_groups_sorted(group_ids) -> list[Group]:
        ids = sorted({int(gid) for gid in group_ids if gid not in (0, None, "")})
        if not ids:
            return []
        return list(Group.objects.select_for_update().filter(id__in=ids).order_by("id"))

    @classmethod
    def _remaining_group_ids(cls, users, subtree_id_set: set[int]) -> set[int]:
        remaining: set[int] = set()
        for user in users:
            remaining |= normalize_group_id_set(getattr(user, "group_list", [])) - subtree_id_set
        return remaining

    @classmethod
    def _collect_subtree_lock_ids(cls, group_id: int, *, include_remaining: bool) -> set[int]:
        subtree_ids = cls.collect_subtree_ids(group_id)
        lock_ids = set(subtree_ids)
        target = Group.objects.filter(id=group_id).first()
        if target is not None and target.parent_id not in (0, None):
            lock_ids.add(int(target.parent_id))
        if include_remaining and subtree_ids:
            preview = list(cls._users_overlapping_groups(subtree_ids).only("group_list"))
            lock_ids |= cls._remaining_group_ids(preview, set(subtree_ids))
        return lock_ids

    @classmethod
    def _lock_stable_group_ids(cls, collect_ids) -> list[Group]:
        locked: list[Group] = []
        for _ in range(_LOCK_SET_RETRIES):
            ids = collect_ids()
            sid = transaction.savepoint()
            locked = cls._lock_groups_sorted(ids)
            locked_ids = {group.id for group in locked}
            if collect_ids() <= locked_ids:
                return locked
            transaction.savepoint_rollback(sid)
        return cls._lock_groups_sorted(collect_ids())

    @classmethod
    def _lock_root_and_subtree(cls, group_id: int, *, include_remaining: bool = False):
        locked_groups = cls._lock_stable_group_ids(
            lambda: cls._collect_subtree_lock_ids(group_id, include_remaining=include_remaining)
        )
        locked_by_id = {group.id: group for group in locked_groups}
        locked_target = locked_by_id.get(group_id)
        if locked_target is None:
            raise Group.DoesNotExist
        parent = None
        if locked_target.parent_id not in (0, None):
            parent = locked_by_id.get(locked_target.parent_id)
        subtree_ids = cls.collect_subtree_ids(group_id)
        return locked_target, parent, subtree_ids, locked_groups, locked_by_id

    @staticmethod
    def _actor_cache_user(actor):
        """操作者清缓存行：有 username 即可；无 id 时仍清 token_info，跳过菜单键。"""
        username = getattr(actor, "username", None)
        if not username:
            return None
        row = {
            "username": username,
            "domain": getattr(actor, "domain", None) or "domain.com",
        }
        actor_id = getattr(actor, "id", None)
        if actor_id not in (None, ""):
            row["id"] = actor_id
        return row

    @classmethod
    def _cache_users_with_actor(cls, users, actor):
        """overlapping 成员 ∪ 当前操作者，按 (username, domain) 去重。"""
        cache_users = [{"id": u.id, "username": u.username, "domain": u.domain} for u in users]
        seen = {(row["username"], row["domain"]) for row in cache_users}
        actor_row = cls._actor_cache_user(actor)
        if actor_row is not None and (actor_row["username"], actor_row["domain"]) not in seen:
            cache_users.append(actor_row)
        return cache_users

    @classmethod
    def _schedule_cache_and_log(cls, *, cache_users, request, action: str, message: str):
        def _on_commit():
            try:
                if cache_users:
                    clear_users_permission_cache(cache_users)
                    cache.delete_many(
                        [f"menus-user:{user['id']}" for user in cache_users if user.get("id") not in (None, "")]
                    )
                if request is not None:
                    log_operation(request, action, "system-manager", message)
            except Exception:
                logger.exception("组织归档副作用失败")

        transaction.on_commit(_on_commit)

    @classmethod
    def lock_users_overlapping_groups(cls, subtree_ids: list[int]) -> list[User]:
        return list(cls._users_overlapping_groups(subtree_ids).select_for_update().order_by("id"))

    @classmethod
    def lock_groups_and_overlapping_users(cls, group_ids, extra_user_ids=None):
        """锁目标组织、剩余归属组织，再锁关联用户，最后按锁后快照补锁 remaining。

        调用方须已在 transaction.atomic 中，并在涉及同步源时先锁 UserSyncSource。
        extra_user_ids 与 overlapping 用户合并后按 id 排序一次加锁。
        """
        group_id_set = {int(gid) for gid in group_ids if gid not in (0, None, "")}
        extra_user_ids = {int(uid) for uid in (extra_user_ids or set()) if uid not in (0, None, "")}

        remaining = set()
        if group_id_set:
            preview_users = list(
                cls._users_overlapping_groups(list(group_id_set)).only(
                    "id", "username", "domain", "group_list"
                )
            )
            remaining = cls._remaining_group_ids(preview_users, group_id_set)

        lock_group_ids = group_id_set | remaining
        locked_by_id = {group.id: group for group in cls._lock_groups_sorted(lock_group_ids)}

        overlapping_ids = set()
        if group_id_set:
            overlapping_ids = set(
                cls._users_overlapping_groups(list(group_id_set)).values_list("id", flat=True)
            )
        all_user_ids = overlapping_ids | extra_user_ids
        users: list[User] = []
        if all_user_ids:
            users = list(
                User.objects.select_for_update().filter(id__in=sorted(all_user_ids)).order_by("id")
            )
        if group_id_set:
            locked_by_id = cls._refresh_remaining_locks(users, group_id_set, locked_by_id)
        return locked_by_id, users

    @classmethod
    def archive_subtree(cls, *, actor, group_id: int, request=None) -> dict:
        """手工归档目标组织及其完整子树。

        成功: {"result": True, "archived_ids": [...]}
        失败: {"result": False, "message": str, "affected_users": [...]?}
        """
        loader = cls._loader(actor)

        try:
            Group.objects.get(id=group_id)
        except Group.DoesNotExist:
            return cls._reject(loader, ArchiveReject("error.group_not_exist", http_status=404))

        with transaction.atomic():
            try:
                locked_target, _parent, subtree_ids, locked_groups, locked_by_id = cls._lock_root_and_subtree(
                    group_id, include_remaining=True
                )
            except Group.DoesNotExist:
                return cls._reject(loader, ArchiveReject("error.group_not_exist", http_status=404))

            if cls._is_protected_root(locked_target):
                return cls._reject(loader, ArchiveReject("error.default_group_cannot_delete"))
            if not cls._actor_authorized_for_group(actor, locked_target.id):
                return cls._reject(loader, ArchiveReject("error.no_permission_delete_group", http_status=403))

            subtree_id_set = set(subtree_ids)
            if not subtree_id_set.issubset(locked_by_id):
                return cls._reject(loader, ArchiveReject("error.group_not_exist", http_status=404))

            if any(group.sync_source_id for group in locked_groups if group.id in subtree_id_set):
                return cls._reject(loader, ArchiveReject("error.synced_groups_archive_forbidden"))

            users = cls.lock_users_overlapping_groups(subtree_ids)
            locked_by_id = cls._refresh_remaining_locks(users, subtree_id_set, locked_by_id)
            affected_users = cls._users_without_remaining_active(users, subtree_id_set, locked_by_id)
            if affected_users:
                return cls._reject(
                    loader,
                    ArchiveReject(
                        "error.group_archive_users_need_active_org",
                        affected_users=affected_users,
                    ),
                )

            Group.objects.filter(id__in=subtree_ids).update(is_delete=True)

            cache_users = cls._cache_users_with_actor(users, actor)
            cls._schedule_cache_and_log(
                cache_users=cache_users,
                request=request,
                action="delete",
                message=f"归档组织: {locked_target.name} (包含{len(subtree_ids)}个子组)",
            )

        return {"result": True, "archived_ids": subtree_ids}

    @classmethod
    def archive_group_ids_keeping_membership(cls, group_ids: list[int]) -> list[int]:
        """按 id 归档组织并保留用户 group_list。

        供同步对账 / 删源等内部路径复用锁与写状态；不做手工归档的授权、
        「剩余活动组织」或「禁止同步组织」校验（由调用方保证策略）。
        调用方须已在外层 transaction.atomic 中，并遵守锁顺序
        UserSyncSource → Group → User。
        """
        if not group_ids:
            return []
        locked = cls._lock_groups_sorted(group_ids)
        if not locked:
            return []
        locked_ids = [group.id for group in locked]
        Group.objects.filter(id__in=locked_ids).update(is_delete=True)
        return locked_ids

    @staticmethod
    def _actor_authorized_for_group(actor, group_id: int) -> bool:
        if getattr(actor, "is_superuser", False):
            return True
        return group_id in normalize_group_id_set(getattr(actor, "group_list", []))

    @staticmethod
    def _load_parent(group: Group) -> Group | None:
        if group.parent_id in (0, None):
            return None
        return Group.objects.filter(id=group.parent_id).first()

    @classmethod
    def _resolve_archived_root(cls, *, actor, group_id: int, loader: LanguageLoader):
        try:
            target = Group.objects.get(id=group_id)
        except Group.DoesNotExist:
            return None, cls._reject(loader, ArchiveReject("error.group_not_exist", http_status=404))

        parent = cls._load_parent(target)
        if not cls.is_archive_root(target, parent):
            return None, cls._reject(loader, ArchiveReject("error.archive_operation_requires_root"))

        if not cls._actor_authorized_for_group(actor, group_id):
            return None, cls._reject(loader, ArchiveReject("error.no_permission_delete_group", http_status=403))

        return target, None

    @classmethod
    def restore_archived_root(cls, *, actor, group_id: int, request=None) -> dict:
        """递归将根及其完整归档子树 is_delete=False；on_commit 清缓存 + 恢复日志。"""
        loader = cls._loader(actor)
        target, reject = cls._resolve_archived_root(actor=actor, group_id=group_id, loader=loader)
        if reject is not None:
            return reject

        kind = classify_archived_kind(target)
        can_restore, _ = capabilities_for_kind(kind)
        if not can_restore:
            return cls._reject(loader, ArchiveReject("error.group_restore_not_allowed"))

        with transaction.atomic():
            try:
                locked_target, parent, subtree_ids, _locked_groups, locked_by_id = cls._lock_root_and_subtree(
                    group_id
                )
            except Group.DoesNotExist:
                return cls._reject(loader, ArchiveReject("error.group_not_exist", http_status=404))
            subtree_id_set = set(subtree_ids)
            if not subtree_id_set.issubset(locked_by_id):
                return cls._reject(loader, ArchiveReject("error.group_not_exist", http_status=404))
            if not cls._actor_authorized_for_group(actor, locked_target.id):
                return cls._reject(loader, ArchiveReject("error.no_permission_delete_group", http_status=403))

            if not cls.is_archive_root(locked_target, parent):
                return cls._reject(loader, ArchiveReject("error.archive_operation_requires_root"))
            if classify_archived_kind(locked_target) != KIND_LOCAL:
                return cls._reject(loader, ArchiveReject("error.group_restore_not_allowed"))

            users = cls.lock_users_overlapping_groups(subtree_ids)
            Group.objects.filter(id__in=subtree_ids).update(is_delete=False)

            cache_users = cls._cache_users_with_actor(users, actor)
            cls._schedule_cache_and_log(
                cache_users=cache_users,
                request=request,
                action="update",
                message=f"恢复组织: {locked_target.name} (包含{len(subtree_ids)}个子组)",
            )

        return {"result": True, "restored_ids": subtree_ids}

    @staticmethod
    def _strip_subtree_from_group_list(group_list, subtree_id_set: set[int]):
        if not group_list:
            return group_list
        cleaned = []
        for item in group_list:
            if isinstance(item, dict):
                try:
                    gid = int(item.get("id"))
                except (TypeError, ValueError):
                    cleaned.append(item)
                    continue
                if gid not in subtree_id_set:
                    cleaned.append(item)
            else:
                try:
                    gid = int(item)
                except (TypeError, ValueError):
                    cleaned.append(item)
                    continue
                if gid not in subtree_id_set:
                    cleaned.append(item)
        return cleaned

    @classmethod
    def permanently_delete_archived_root(cls, *, actor, group_id: int, request=None) -> dict:
        """校验归档根+授权；锁后用户校验；从 group_list 移除子树；物理删除。"""
        loader = cls._loader(actor)
        target, reject = cls._resolve_archived_root(actor=actor, group_id=group_id, loader=loader)
        if reject is not None:
            return reject

        kind = classify_archived_kind(target)
        _, can_permanently_delete = capabilities_for_kind(kind)
        if not can_permanently_delete:
            return cls._reject(loader, ArchiveReject("error.group_permanent_delete_not_allowed"))

        with transaction.atomic():
            try:
                locked_target, parent, subtree_ids, _locked_groups, locked_by_id = cls._lock_root_and_subtree(
                    group_id, include_remaining=True
                )
            except Group.DoesNotExist:
                return cls._reject(loader, ArchiveReject("error.group_not_exist", http_status=404))
            subtree_id_set = set(subtree_ids)
            if not subtree_id_set.issubset(locked_by_id):
                return cls._reject(loader, ArchiveReject("error.group_not_exist", http_status=404))
            if not cls._actor_authorized_for_group(actor, locked_target.id):
                return cls._reject(loader, ArchiveReject("error.no_permission_delete_group", http_status=403))

            if not cls.is_archive_root(locked_target, parent):
                return cls._reject(loader, ArchiveReject("error.archive_operation_requires_root"))
            locked_kind = classify_archived_kind(locked_target)
            _, locked_can_delete = capabilities_for_kind(locked_kind)
            if not locked_can_delete:
                return cls._reject(loader, ArchiveReject("error.group_permanent_delete_not_allowed"))

            users = cls.lock_users_overlapping_groups(subtree_ids)
            locked_by_id = cls._refresh_remaining_locks(users, subtree_id_set, locked_by_id)
            affected_users = cls._users_without_remaining_active(users, subtree_id_set, locked_by_id)
            if affected_users:
                return cls._reject(
                    loader,
                    ArchiveReject(
                        "error.group_permanent_delete_users_need_active_org",
                        affected_users=affected_users,
                    ),
                )

            to_update = []
            for user in users:
                new_list = cls._strip_subtree_from_group_list(user.group_list, subtree_id_set)
                if new_list != user.group_list:
                    user.group_list = new_list
                    to_update.append(user)
            if to_update:
                User.objects.bulk_update(to_update, ["group_list"], batch_size=100)

            Group.objects.filter(id__in=subtree_ids).delete()

            cache_users = cls._cache_users_with_actor(users, actor)
            cls._schedule_cache_and_log(
                cache_users=cache_users,
                request=request,
                action="delete",
                message=f"永久删除组织: {locked_target.name} (包含{len(subtree_ids)}个子组)",
            )

        return {"result": True, "deleted_ids": subtree_ids}
