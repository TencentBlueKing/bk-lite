"""Single active-generation read boundary for Wiki consumers."""

import logging
from dataclasses import dataclass

from django.db.models import BigIntegerField, Count, Prefetch, Subquery, Value

from apps.opspilot.models import KnowledgePage, PageRelation, PageVersion, WikiDirectory, WikiGenerationPage, WikiKnowledgeBase

READ_GENERATION_ID_ATTRIBUTE = "_wiki_read_generation_id"
logger = logging.getLogger("opspilot")


class ActiveGenerationReadError(Exception):
    def __init__(self, code, message, *, details=None):
        self.code = str(code)
        self.details = dict(details or {})
        super().__init__(message)


@dataclass(frozen=True)
class ActivePageSnapshot:
    generation_id: int | None
    page_id: int
    page_version: PageVersion | None
    directory_id: int | None
    directory_key: str
    directory_breadcrumb: tuple[dict, ...]
    assignment_mode: str
    page_status: str
    display: dict

    @property
    def page_version_id(self):
        return self.page_version.pk if self.page_version is not None else None

    @property
    def body(self):
        return self.page_version.body if self.page_version is not None else ""

    @property
    def title(self):
        return self.display.get("title", "")

    @property
    def page_type(self):
        return self.display.get("page_type", "")

    @property
    def tags(self):
        return list(self.display.get("tags") or [])

    @property
    def contribution(self):
        return self.display.get("contribution", "")


@dataclass(frozen=True)
class ActiveGenerationReadScope:
    """One immutable pointer pair shared by every query in a consumer call."""

    knowledge_base_id: int
    generation_id: int | None
    structure_revision_id: int | None
    structure_snapshot: dict


def bind_read_scope(knowledge_base):
    """Capture the active generation/structure pair in one database statement."""

    knowledge_base_id = getattr(knowledge_base, "pk", knowledge_base)
    row = (
        WikiKnowledgeBase.objects.filter(pk=knowledge_base_id)
        .values(
            "id",
            "active_generation_id",
            "active_generation__status",
            "active_generation__structure_revision_id",
            "active_structure_revision_id",
            "active_structure_revision__structure_snapshot",
        )
        .first()
    )
    if row is None:
        raise ActiveGenerationReadError(
            "knowledge_base_not_found",
            "知识库不存在",
            details={"knowledge_base_id": knowledge_base_id},
        )
    generation_id = row["active_generation_id"]
    if generation_id is None:
        raise ActiveGenerationReadError(
            "active_generation_missing",
            "已就绪知识库缺少 active generation",
            details={"knowledge_base_id": row["id"]},
        )
    if row["active_generation__status"] != "active":
        raise ActiveGenerationReadError(
            "active_generation_invalid",
            "知识库 active generation 不存在或状态非法",
            details={"knowledge_base_id": row["id"], "generation_id": generation_id, "status": row["active_generation__status"]},
        )
    generation_revision_id = row["active_generation__structure_revision_id"]
    active_revision_id = row["active_structure_revision_id"]
    if generation_revision_id is None or generation_revision_id != active_revision_id:
        logger.error(
            "wiki_active_generation_structure_mismatch kb=%s generation=%s generation_revision=%s active_revision=%s",
            row["id"],
            generation_id,
            generation_revision_id,
            active_revision_id,
        )
        raise ActiveGenerationReadError(
            "active_generation_structure_mismatch",
            "知识库 active generation 与 active structure revision 不一致",
            details={
                "knowledge_base_id": row["id"],
                "generation_id": generation_id,
                "generation_structure_revision_id": generation_revision_id,
                "active_structure_revision_id": active_revision_id,
            },
        )
    return ActiveGenerationReadScope(
        knowledge_base_id=row["id"],
        generation_id=generation_id,
        structure_revision_id=active_revision_id,
        structure_snapshot=dict(row["active_structure_revision__structure_snapshot"] or {}),
    )


def assert_read_scope_current(read_scope):
    """Fail closed if a query outlives the active generation/structure pair."""

    current = WikiKnowledgeBase.objects.filter(pk=read_scope.knowledge_base_id).values("active_generation_id", "active_structure_revision_id").first()
    if current is None:
        raise ActiveGenerationReadError(
            "knowledge_base_not_found",
            "知识库不存在",
            details={"knowledge_base_id": read_scope.knowledge_base_id},
        )
    if current["active_generation_id"] != read_scope.generation_id or current["active_structure_revision_id"] != read_scope.structure_revision_id:
        raise ActiveGenerationReadError(
            "active_generation_changed_during_query",
            "知识库内容在查询期间已更新，请重试",
            details={
                "knowledge_base_id": read_scope.knowledge_base_id,
                "expected_generation_id": read_scope.generation_id,
                "current_generation_id": current["active_generation_id"],
                "expected_structure_revision_id": read_scope.structure_revision_id,
                "current_structure_revision_id": current["active_structure_revision_id"],
                "retryable": True,
            },
        )
    return read_scope


def _read_scope(knowledge_base, read_scope=None):
    scope = read_scope or bind_read_scope(knowledge_base)
    knowledge_base_id = getattr(knowledge_base, "pk", knowledge_base)
    if scope.knowledge_base_id != knowledge_base_id:
        raise ActiveGenerationReadError(
            "read_scope_knowledge_base_mismatch",
            "读取快照不属于当前知识库",
            details={"knowledge_base_id": knowledge_base_id, "scope_knowledge_base_id": scope.knowledge_base_id},
        )
    return scope


def active_generation_id_for_read(knowledge_base):
    """Return the authoritative generation for every Wiki read."""

    return bind_read_scope(knowledge_base).generation_id


def uses_generation_truth(knowledge_base):
    return active_generation_id_for_read(knowledge_base) is not None


def active_memberships(knowledge_base, *, read_scope=None):
    generation_id = _read_scope(knowledge_base, read_scope).generation_id
    if generation_id is None:
        return WikiGenerationPage.objects.none()
    return WikiGenerationPage.objects.filter(generation_id=generation_id).select_related("page", "page_version", "directory").order_by("page_id")


def page_queryset(
    knowledge_base,
    *,
    statuses=("active",),
    directory_ids=None,
    page_type=None,
    title=None,
    read_scope=None,
):
    """Return pages scoped before pagination while prefetching the true snapshot."""

    generation_id = _read_scope(knowledge_base, read_scope).generation_id
    if isinstance(statuses, str):
        statuses = (statuses,)
    statuses = tuple(statuses or ())
    directory_ids = None if directory_ids is None else tuple(directory_ids)
    page_type = str(page_type or "").strip()
    title = str(title or "").strip()

    if generation_id is None:
        queryset = KnowledgePage.objects.filter(knowledge_base=knowledge_base)
        if statuses:
            queryset = queryset.filter(status__in=statuses)
        if directory_ids is not None:
            queryset = queryset.filter(directory_id__in=directory_ids)
        if page_type:
            queryset = queryset.filter(page_type=page_type)
        if title:
            queryset = queryset.filter(title__icontains=title)
        return queryset.select_related(
            "knowledge_base",
            "current_version",
            "directory",
        ).annotate(
            **{
                READ_GENERATION_ID_ATTRIBUTE: Value(
                    None,
                    output_field=BigIntegerField(),
                )
            }
        )

    membership_scope = WikiGenerationPage.objects.filter(generation_id=generation_id)
    if statuses:
        membership_scope = membership_scope.filter(page_status__in=statuses)
    if directory_ids is not None:
        membership_scope = membership_scope.filter(directory_id__in=directory_ids)
    if page_type:
        membership_scope = membership_scope.filter(
            page_display_snapshot__page_type=page_type,
        )
    if title:
        membership_scope = membership_scope.filter(
            page_display_snapshot__title__icontains=title,
        )

    membership_prefetch = Prefetch(
        "generation_memberships",
        queryset=WikiGenerationPage.objects.filter(generation_id=generation_id).select_related("page_version", "directory"),
        to_attr="_active_generation_memberships",
    )
    return (
        KnowledgePage.objects.filter(
            knowledge_base=knowledge_base,
            pk__in=Subquery(membership_scope.values("page_id")),
        )
        .select_related("knowledge_base")
        .annotate(
            **{
                READ_GENERATION_ID_ATTRIBUTE: Value(
                    generation_id,
                    output_field=BigIntegerField(),
                )
            }
        )
        .prefetch_related(membership_prefetch)
    )


def page_snapshot(page, *, knowledge_base=None):
    """Resolve one page without mixing compatibility and generation fields."""

    knowledge_base = knowledge_base or page.knowledge_base
    generation_id = (
        getattr(page, READ_GENERATION_ID_ATTRIBUTE) if hasattr(page, READ_GENERATION_ID_ATTRIBUTE) else active_generation_id_for_read(knowledge_base)
    )
    if generation_id is None:
        directory = getattr(page, "directory", None)
        breadcrumb = ()
        directory_key = ""
        if directory is not None:
            directory_key = directory.key
            breadcrumb = tuple(_directory_breadcrumb(directory))
        return ActivePageSnapshot(
            generation_id=None,
            page_id=page.pk,
            page_version=page.current_version,
            directory_id=page.directory_id,
            directory_key=directory_key,
            directory_breadcrumb=breadcrumb,
            assignment_mode=page.directory_assignment_mode,
            page_status=page.status,
            display={
                "title": page.title,
                "page_type": page.page_type,
                "tags": list(page.tags or []),
                "contribution": page.contribution,
                "update_method": page.update_method,
            },
        )

    memberships = getattr(page, "_active_generation_memberships", None)
    if memberships is None:
        memberships = list(
            WikiGenerationPage.objects.filter(
                generation_id=generation_id,
                page_id=page.pk,
            ).select_related("page_version", "directory")
        )
    membership_generation_ids = sorted({member.generation_id for member in memberships})
    if membership_generation_ids and membership_generation_ids != [generation_id]:
        raise ActiveGenerationReadError(
            "active_generation_membership_generation_mismatch",
            "页面成员与查询绑定的 generation 不一致",
            details={
                "knowledge_base_id": knowledge_base.pk,
                "generation_id": generation_id,
                "page_id": page.pk,
                "membership_generation_ids": membership_generation_ids,
            },
        )
    if len(memberships) != 1:
        raise ActiveGenerationReadError(
            "active_generation_membership_invalid",
            "页面在 active generation 中的成员数量非法",
            details={
                "knowledge_base_id": knowledge_base.pk,
                "generation_id": generation_id,
                "page_id": page.pk,
                "membership_count": len(memberships),
            },
        )
    member = memberships[0]
    return ActivePageSnapshot(
        generation_id=generation_id,
        page_id=page.pk,
        page_version=member.page_version,
        directory_id=member.directory_id,
        directory_key=member.directory_key_snapshot,
        directory_breadcrumb=tuple(member.directory_breadcrumb_snapshot or ()),
        assignment_mode=member.assignment_mode,
        page_status=member.page_status,
        display=dict(member.page_display_snapshot or {}),
    )


def directory_page_counts(knowledge_base, *, statuses=("active",), read_scope=None):
    """Count direct members with one grouped query from the current truth source."""

    generation_id = _read_scope(knowledge_base, read_scope).generation_id
    if isinstance(statuses, str):
        statuses = (statuses,)
    statuses = tuple(statuses or ())
    if generation_id is None:
        queryset = KnowledgePage.objects.filter(
            knowledge_base=knowledge_base,
            directory_id__isnull=False,
        )
        if statuses:
            queryset = queryset.filter(status__in=statuses)
        rows = queryset.values("directory_id").annotate(count=Count("id"))
    else:
        queryset = WikiGenerationPage.objects.filter(
            generation_id=generation_id,
        )
        if statuses:
            queryset = queryset.filter(page_status__in=statuses)
        rows = queryset.values("directory_id").annotate(count=Count("page_id"))
    return {row["directory_id"]: row["count"] for row in rows}


def relation_queryset(knowledge_base, *, read_scope=None):
    """Return only the relation set matching the page truth source."""

    generation_id = _read_scope(knowledge_base, read_scope).generation_id
    if generation_id is None:
        return PageRelation.objects.filter(
            generation__isnull=True,
            from_page__knowledge_base=knowledge_base,
            to_page__knowledge_base=knowledge_base,
        )
    return PageRelation.objects.filter(
        generation_id=generation_id,
        from_page__knowledge_base=knowledge_base,
        to_page__knowledge_base=knowledge_base,
    )


def directory_scope_ids(knowledge_base, *, directory_id=None, include_descendants=False, read_scope=None):
    """Resolve a directory subtree from the same structure snapshot as page reads."""

    if directory_id in (None, ""):
        return None
    try:
        directory_id = int(directory_id)
    except (TypeError, ValueError) as error:
        raise ActiveGenerationReadError(
            "directory_id_invalid",
            "directory_id 必须为整数",
            details={"directory_id": directory_id},
        ) from error

    scope = _read_scope(knowledge_base, read_scope)
    if scope.generation_id is None:
        rows = list(WikiDirectory.objects.filter(knowledge_base_id=scope.knowledge_base_id, status="active").values("id", "parent_id"))
    else:
        rows = []
        for node in scope.structure_snapshot.get("directories", []):
            if node.get("status", "active") != "active" or type(node.get("id")) is not int:
                continue
            parent = node.get("parent") or {}
            rows.append({"id": node["id"], "parent_id": parent.get("id")})

    directory_ids = {row["id"] for row in rows}
    if directory_id not in directory_ids:
        raise ActiveGenerationReadError(
            "directory_not_in_read_snapshot",
            "目录不属于当前知识库活动结构",
            details={"knowledge_base_id": scope.knowledge_base_id, "generation_id": scope.generation_id, "directory_id": directory_id},
        )
    if not include_descendants:
        return (directory_id,)

    children = {}
    for row in rows:
        children.setdefault(row["parent_id"], []).append(row["id"])
    result = {directory_id}
    pending = [directory_id]
    while pending:
        for child_id in children.get(pending.pop(), []):
            if child_id in result:
                continue
            result.add(child_id)
            pending.append(child_id)
    return tuple(sorted(result))


def _directory_breadcrumb(directory):
    rows = {
        row["id"]: row for row in WikiDirectory.objects.filter(knowledge_base_id=directory.knowledge_base_id).values("id", "key", "name", "parent_id")
    }
    result = []
    current_id = directory.pk
    visited = set()
    while current_id is not None:
        if current_id in visited:
            raise ActiveGenerationReadError(
                "directory_cycle",
                "目录父链存在循环",
                details={"directory_id": directory.pk},
            )
        visited.add(current_id)
        row = rows.get(current_id)
        if row is None:
            raise ActiveGenerationReadError(
                "directory_parent_missing",
                "目录父链不完整",
                details={
                    "directory_id": directory.pk,
                    "missing_directory_id": current_id,
                },
            )
        result.append({"id": row["id"], "key": row["key"], "name": row["name"]})
        current_id = row["parent_id"]
    result.reverse()
    return result
