"""组织归档的常量、返回结构与 kind 判定。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from apps.system_mgmt.models import Group

_USER_SYNC_EXTERNAL_ID_RE = re.compile(r"^user-sync:\d+:")

KIND_LOCAL = "local"
KIND_SYNCED_ACTIVE = "synced_active_source"
KIND_SYNCED_DELETED = "synced_deleted_source"

ARCHIVED_LIST_DEFAULT_PAGE_SIZE = 50
ARCHIVED_LIST_MAX_PAGE_SIZE = 100
ARCHIVED_LIST_MAX_DESCENDANTS_PER_ROOT = 200


@dataclass(frozen=True)
class ArchiveReject:
    message_key: str
    affected_users: list[dict] = field(default_factory=list)
    http_status: int = 400


@dataclass(frozen=True)
class ArchivedRootItem:
    id: int
    name: str
    parent_id: int
    kind: str  # local | synced_active_source | synced_deleted_source
    can_restore: bool
    can_permanently_delete: bool
    children: list[dict]  # 只读子树节点
    children_truncated: bool = False


@dataclass(frozen=True)
class ArchivedRootPage:
    items: list[ArchivedRootItem]
    count: int
    page: int
    page_size: int


@dataclass(frozen=True)
class ArchivedGroupRecordPage:
    items: list[dict]
    count: int
    page: int
    page_size: int


def classify_archived_kind(group: Group) -> str:
    if group.sync_source_id:
        return KIND_SYNCED_ACTIVE
    external_id = group.external_id or ""
    if _USER_SYNC_EXTERNAL_ID_RE.match(external_id):
        return KIND_SYNCED_DELETED
    return KIND_LOCAL


def capabilities_for_kind(kind: str) -> tuple[bool, bool]:
    if kind == KIND_LOCAL:
        return True, True
    # 同步对账归档与删源残留：不可手工恢复；可永久删除以释放 (name, parent_id)。
    # 永久删除后同一外部组织再出现，按新建处理，不再复用原 ID。
    return False, True
