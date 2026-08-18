"""已归档组织查询：管理端归档根列表，以及给其他模块的全量归档分页。"""

from __future__ import annotations

from django.db.models import Exists, OuterRef, Q

from apps.system_mgmt.models import Group
from apps.system_mgmt.services.group_archive_types import (
    ARCHIVED_LIST_DEFAULT_PAGE_SIZE,
    ARCHIVED_LIST_MAX_DESCENDANTS_PER_ROOT,
    ARCHIVED_LIST_MAX_PAGE_SIZE,
    ArchivedGroupRecordPage,
    ArchivedRootItem,
    ArchivedRootPage,
    capabilities_for_kind,
    classify_archived_kind,
)
from apps.system_mgmt.utils.group_filter_mixin import normalize_group_id_set


class ArchivedGroupQuery:
    @classmethod
    def _archived_roots_queryset(cls, actor_group_ids: set[int] | None):
        archived_parent = Group.objects.filter(id=OuterRef("parent_id"), is_delete=True)
        qs = Group.objects.filter(is_delete=True).filter(
            Q(parent_id=0) | Q(parent_id__isnull=True) | ~Exists(archived_parent)
        )
        if actor_group_ids is not None:
            qs = qs.filter(id__in=actor_group_ids)
        return qs.order_by("id")

    @classmethod
    def list_all_archived_groups(
        cls,
        *,
        page: int = 1,
        page_size: int = ARCHIVED_LIST_MAX_PAGE_SIZE,
    ) -> ArchivedGroupRecordPage:
        """分页返回全部已归档组织（含非根后代），供其他模块自行处理资产。"""
        page_size = min(max(page_size, 1), ARCHIVED_LIST_MAX_PAGE_SIZE)
        page = max(page, 1)
        qs = Group.objects.filter(is_delete=True).order_by("id")
        count = qs.count()
        offset = (page - 1) * page_size
        items = [
            {"id": group.id, "name": group.name, "parent_id": group.parent_id or 0}
            for group in qs[offset : offset + page_size]
        ]
        return ArchivedGroupRecordPage(items=items, count=count, page=page, page_size=page_size)

    @classmethod
    def _load_archived_descendants(cls, roots: list[Group]) -> tuple[dict[int, Group], set[int]]:
        group_by_id = {group.id: group for group in roots}
        truncated_root_ids: set[int] = set()
        for root in roots:
            frontier = [root.id]
            loaded = 0
            while frontier:
                children = list(Group.objects.filter(parent_id__in=frontier, is_delete=True).order_by("id"))
                frontier = []
                for child in children:
                    if child.id in group_by_id:
                        continue
                    if loaded >= ARCHIVED_LIST_MAX_DESCENDANTS_PER_ROOT:
                        truncated_root_ids.add(root.id)
                        frontier = []
                        break
                    group_by_id[child.id] = child
                    loaded += 1
                    frontier.append(child.id)
        return group_by_id, truncated_root_ids

    @classmethod
    def _build_readonly_children(cls, root_id: int, group_by_id: dict[int, Group]) -> list[dict]:
        children_map: dict[int, list[Group]] = {}
        for group in group_by_id.values():
            if group.parent_id in (0, None):
                continue
            children_map.setdefault(group.parent_id, []).append(group)

        def build(node_id: int) -> list[dict]:
            nodes = []
            for child in sorted(children_map.get(node_id, []), key=lambda g: g.id):
                nodes.append(
                    {
                        "id": child.id,
                        "name": child.name,
                        "parent_id": child.parent_id,
                        "children": build(child.id),
                    }
                )
            return nodes

        return build(root_id)

    @classmethod
    def list_archived_roots(
        cls,
        *,
        actor,
        page: int = 1,
        page_size: int = ARCHIVED_LIST_DEFAULT_PAGE_SIZE,
    ) -> ArchivedRootPage:
        page_size = min(max(page_size, 1), ARCHIVED_LIST_MAX_PAGE_SIZE)
        page = max(page, 1)
        actor_group_ids = None
        if not getattr(actor, "is_superuser", False):
            actor_group_ids = normalize_group_id_set(getattr(actor, "group_list", []))
            if not actor_group_ids:
                return ArchivedRootPage(items=[], count=0, page=page, page_size=page_size)

        roots_qs = cls._archived_roots_queryset(actor_group_ids)
        count = roots_qs.count()
        offset = (page - 1) * page_size
        roots = list(roots_qs[offset : offset + page_size])
        if not roots:
            return ArchivedRootPage(items=[], count=count, page=page, page_size=page_size)

        group_by_id, truncated_root_ids = cls._load_archived_descendants(roots)
        items: list[ArchivedRootItem] = []
        for group in roots:
            kind = classify_archived_kind(group)
            can_restore, can_permanently_delete = capabilities_for_kind(kind)
            items.append(
                ArchivedRootItem(
                    id=group.id,
                    name=group.name,
                    parent_id=group.parent_id or 0,
                    kind=kind,
                    can_restore=can_restore,
                    can_permanently_delete=can_permanently_delete,
                    children=cls._build_readonly_children(group.id, group_by_id),
                    children_truncated=group.id in truncated_root_ids,
                )
            )
        return ArchivedRootPage(items=items, count=count, page=page, page_size=page_size)
