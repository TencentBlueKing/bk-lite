"""Read-only readiness audit for Wiki directory governance.

The audit intentionally uses only ORM reads.  The management command consumes
it directly; ``directory_enable_service.enable_wiki_directory`` owns the
``ready -> enabled`` transaction and knowledge-base row lock before invoking
the final readiness recheck.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from django.utils import timezone

from apps.opspilot.models import (
    BuildRecord,
    KnowledgePage,
    PageVersion,
    WikiDirectory,
    WikiGeneration,
    WikiGenerationPage,
    WikiKnowledgeBase,
    WikiStructureRevision,
)
from apps.opspilot.services.wiki.title_service import title_identity_key

REPORT_SCHEMA = "opspilot.wiki.directory-readiness/v1"
KNOWN_PAGE_STATUSES = frozenset(
    {
        "active",
        "archived",
        "pending",
        "source_invalid",
        "staging",
    }
)
KNOWN_ASSIGNMENT_MODES = frozenset({"auto", "manual"})
KNOWN_DIRECTORY_STATUSES = frozenset({"active", "retired", "merged", "archived"})
KNOWN_DIRECTORY_ORIGINS = frozenset({"system", "schema", "manual"})
ACTIVE_GENERATION_PAGE_STATUSES = frozenset({"active"})
RUNNING_BUILD_GENERATION_STATUSES = frozenset({"preparing", "ready"})
VALID_BASE_GENERATION_STATUSES = frozenset({"active", "superseded"})
UNCLASSIFIED_DIRECTORY_KEY = "__unclassified__"
UNCLASSIFIED_DIRECTORY_NAME = "待归类"
MAX_DIRECTORY_DEPTH = 8
DISPLAY_MIRROR_FIELDS = (
    "title",
    "page_type",
    "tags",
    "contribution",
    "update_method",
)


@dataclass(frozen=True)
class ReadinessIssue:
    """One stable, machine-readable readiness finding."""

    code: str
    message: str
    blocking: bool = True
    entity_type: str | None = None
    entity_id: int | str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)

    @property
    def severity(self) -> str:
        return "error" if self.blocking else "warning"

    def sort_key(self) -> tuple[str, str, str, str]:
        return (
            self.code,
            self.entity_type or "",
            str(self.entity_id) if self.entity_id is not None else "",
            json.dumps(self.details, ensure_ascii=False, sort_keys=True, default=str),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "blocking": self.blocking,
            "code": self.code,
            "details": dict(self.details),
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "message": self.message,
            "severity": self.severity,
        }


@dataclass(frozen=True)
class KnowledgeBaseReadinessResult:
    """Readiness result for one knowledge base."""

    knowledge_base_id: int
    knowledge_base_name: str
    directory_enabled: bool
    mode: str
    issues: tuple[ReadinessIssue, ...]
    scanned: Mapping[str, int] = field(default_factory=dict)

    @property
    def blocking_issue_count(self) -> int:
        return sum(issue.blocking for issue in self.issues)

    @property
    def warning_count(self) -> int:
        return len(self.issues) - self.blocking_issue_count

    @property
    def ready(self) -> bool:
        return self.blocking_issue_count == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "directory_enabled": self.directory_enabled,
            "issues": [issue.to_dict() for issue in self.issues],
            "knowledge_base_id": self.knowledge_base_id,
            "knowledge_base_name": self.knowledge_base_name,
            "mode": self.mode,
            "ready": self.ready,
            "scanned": dict(self.scanned),
            "summary": {
                "blocking_issue_count": self.blocking_issue_count,
                "issue_count": len(self.issues),
                "warning_count": self.warning_count,
            },
        }


@dataclass(frozen=True)
class ReadinessAuditReport:
    """Aggregate result with a stable JSON shape and deterministic ordering."""

    mode: str
    knowledge_bases: tuple[KnowledgeBaseReadinessResult, ...]
    missing_knowledge_base_ids: tuple[int, ...] = ()
    generated_at: str = field(default_factory=lambda: timezone.now().isoformat())
    schema: str = REPORT_SCHEMA

    @property
    def blocking_issue_count(self) -> int:
        return sum(result.blocking_issue_count for result in self.knowledge_bases) + len(self.missing_knowledge_base_ids)

    @property
    def warning_count(self) -> int:
        return sum(result.warning_count for result in self.knowledge_bases)

    @property
    def ready(self) -> bool:
        return self.blocking_issue_count == 0

    def to_dict(self) -> dict[str, Any]:
        ready_count = sum(result.ready for result in self.knowledge_bases)
        return {
            "generated_at": self.generated_at,
            "knowledge_bases": [result.to_dict() for result in self.knowledge_bases],
            "missing_knowledge_base_ids": list(self.missing_knowledge_base_ids),
            "mode": self.mode,
            "ready": self.ready,
            "schema": self.schema,
            "summary": {
                "blocked_knowledge_base_count": len(self.knowledge_bases) - ready_count,
                "blocking_issue_count": self.blocking_issue_count,
                "knowledge_base_count": len(self.knowledge_bases),
                "missing_knowledge_base_count": len(self.missing_knowledge_base_ids),
                "ready_knowledge_base_count": ready_count,
                "warning_count": self.warning_count,
            },
        }


class WikiDirectoryNotReady(RuntimeError):
    """Raised when a locked KB fails the final enable-time recheck."""

    code = "wiki_directory_not_ready"

    def __init__(self, result: KnowledgeBaseReadinessResult):
        self.result = result
        self.blocking_codes = tuple(sorted({issue.code for issue in result.issues if issue.blocking}))
        super().__init__(f"Wiki knowledge base {result.knowledge_base_id} is not directory-ready: {', '.join(self.blocking_codes)}")


def _issue(
    issues: list[ReadinessIssue],
    code: str,
    message: str,
    *,
    blocking: bool = True,
    entity_type: str | None = None,
    entity_id: int | str | None = None,
    details: Mapping[str, Any] | None = None,
) -> None:
    issues.append(
        ReadinessIssue(
            code=code,
            message=message,
            blocking=blocking,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details or {},
        )
    )


def _audit_pages(
    *,
    knowledge_base: WikiKnowledgeBase,
    strict_directory: bool,
    issues: list[ReadinessIssue],
) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
    page_rows = list(
        KnowledgePage.objects.filter(knowledge_base_id=knowledge_base.pk)
        .values(
            "id",
            "knowledge_base_id",
            "title",
            "page_type",
            "tags",
            "contribution",
            "update_method",
            "status",
            "directory_id",
            "directory_assignment_mode",
            "current_version_id",
        )
        .order_by("id")
    )
    title_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    directory_ids = {row["directory_id"] for row in page_rows if row["directory_id"] is not None}
    directory_rows = {
        row["id"]: row
        for row in WikiDirectory.objects.filter(id__in=directory_ids).values("id", "knowledge_base_id", "key", "status", "accepts_pages")
    }
    current_version_ids = {row["current_version_id"] for row in page_rows if row["current_version_id"] is not None}
    current_versions = {row["id"]: row for row in PageVersion.objects.filter(id__in=current_version_ids).values("id", "page_id")}

    for row in page_rows:
        page_id = row["id"]
        identity_key = title_identity_key(row["title"])
        if not identity_key:
            _issue(
                issues,
                "invalid_page_title",
                "Page title is empty after canonical normalization.",
                entity_type="page",
                entity_id=page_id,
                details={"status": row["status"], "title": row["title"]},
            )
        else:
            title_groups[identity_key].append(row)

        if row["status"] not in KNOWN_PAGE_STATUSES:
            _issue(
                issues,
                "invalid_page_status",
                "Page has a status outside the supported all-state namespace.",
                entity_type="page",
                entity_id=page_id,
                details={"status": row["status"]},
            )

        if row["directory_assignment_mode"] not in KNOWN_ASSIGNMENT_MODES:
            _issue(
                issues,
                "invalid_page_assignment_mode",
                "Page directory assignment mode must be auto or manual.",
                entity_type="page",
                entity_id=page_id,
                details={"assignment_mode": row["directory_assignment_mode"]},
            )

        current_version_id = row["current_version_id"]
        if current_version_id is None:
            _issue(
                issues,
                "page_current_version_missing",
                "All-state page identity has no current compatibility version.",
                entity_type="page",
                entity_id=page_id,
            )
        else:
            current_version = current_versions.get(current_version_id)
            if current_version is None:
                _issue(
                    issues,
                    "page_current_version_not_found",
                    "Page current-version pointer references a missing version.",
                    entity_type="page",
                    entity_id=page_id,
                    details={"current_version_id": current_version_id},
                )
            elif current_version["page_id"] != page_id:
                _issue(
                    issues,
                    "page_current_version_owner_mismatch",
                    "Page current-version pointer references another page's version.",
                    entity_type="page",
                    entity_id=page_id,
                    details={
                        "current_version_id": current_version_id,
                        "version_page_id": current_version["page_id"],
                    },
                )

        directory_id = row["directory_id"]
        if directory_id is None:
            _issue(
                issues,
                "page_directory_missing",
                "Page has not been assigned to a directory.",
                blocking=strict_directory,
                entity_type="page",
                entity_id=page_id,
                details={"migration_pending": not strict_directory},
            )
            continue
        directory = directory_rows.get(directory_id)
        if directory is None:
            _issue(
                issues,
                "page_directory_not_found",
                "Page references a directory that does not exist.",
                entity_type="page",
                entity_id=page_id,
                details={"directory_id": directory_id},
            )
        elif directory["knowledge_base_id"] != knowledge_base.pk:
            _issue(
                issues,
                "page_directory_cross_knowledge_base",
                "Page references a directory owned by another knowledge base.",
                entity_type="page",
                entity_id=page_id,
                details={
                    "directory_id": directory_id,
                    "directory_knowledge_base_id": directory["knowledge_base_id"],
                },
            )
        elif directory["status"] != "active" or not directory["accepts_pages"]:
            _issue(
                issues,
                "page_directory_not_assignable",
                "Page directory must be active and accept pages.",
                entity_type="page",
                entity_id=page_id,
                details={
                    "accepts_pages": directory["accepts_pages"],
                    "directory_id": directory_id,
                    "directory_status": directory["status"],
                },
            )

    for identity_key, rows in sorted(title_groups.items()):
        if len(rows) < 2:
            continue
        conflict_pages = [
            {
                "id": row["id"],
                "status": row["status"],
                "title": row["title"],
            }
            for row in sorted(rows, key=lambda item: item["id"])
        ]
        _issue(
            issues,
            "duplicate_page_title_identity",
            "Multiple all-state pages share the same canonical title identity.",
            entity_type="title_identity",
            entity_id=identity_key,
            details={"identity_key": identity_key, "pages": conflict_pages},
        )

    return page_rows, {row["id"]: row for row in page_rows}


def _audit_directory_links(
    *,
    knowledge_base: WikiKnowledgeBase,
    strict_directory: bool,
    issues: list[ReadinessIssue],
) -> dict[int, dict[str, Any]]:
    rows = list(
        WikiDirectory.objects.filter(knowledge_base_id=knowledge_base.pk)
        .values(
            "id",
            "knowledge_base_id",
            "key",
            "name",
            "description",
            "parent_id",
            "sort_order",
            "origin",
            "status",
            "accepts_pages",
            "merged_into_id",
        )
        .order_by("id")
    )
    rows_by_id = {row["id"]: row for row in rows}
    referenced_ids = {related_id for row in rows for related_id in (row["parent_id"], row["merged_into_id"]) if related_id is not None}
    referenced = {
        row["id"]: row
        for row in WikiDirectory.objects.filter(id__in=referenced_ids).values(
            "id",
            "knowledge_base_id",
            "key",
            "name",
            "parent_id",
            "status",
            "accepts_pages",
        )
    }

    for row in rows:
        if row["status"] not in KNOWN_DIRECTORY_STATUSES:
            _issue(
                issues,
                "invalid_directory_status",
                "Directory has an unsupported lifecycle status.",
                entity_type="directory",
                entity_id=row["id"],
                details={"status": row["status"]},
            )
        if row["origin"] not in KNOWN_DIRECTORY_ORIGINS:
            _issue(
                issues,
                "invalid_directory_origin",
                "Directory has an unsupported origin.",
                entity_type="directory",
                entity_id=row["id"],
                details={"origin": row["origin"]},
            )

        for field_name, code_prefix in (
            ("parent_id", "directory_parent"),
            ("merged_into_id", "directory_merge_target"),
        ):
            related_id = row[field_name]
            if related_id is None:
                continue
            target = referenced.get(related_id)
            if target is None:
                _issue(
                    issues,
                    f"{code_prefix}_not_found",
                    "Directory relationship references a missing directory.",
                    entity_type="directory",
                    entity_id=row["id"],
                    details={field_name: related_id},
                )
            elif target["knowledge_base_id"] != knowledge_base.pk:
                _issue(
                    issues,
                    f"{code_prefix}_cross_knowledge_base",
                    "Directory relationship crosses knowledge-base boundaries.",
                    entity_type="directory",
                    entity_id=row["id"],
                    details={
                        field_name: related_id,
                        "target_knowledge_base_id": target["knowledge_base_id"],
                    },
                )

        if row["status"] == "merged":
            target = referenced.get(row["merged_into_id"])
            if row["merged_into_id"] is None:
                _issue(
                    issues,
                    "merged_directory_target_missing",
                    "Merged directory must retain a redirect target.",
                    entity_type="directory",
                    entity_id=row["id"],
                )
            elif target is not None and target["knowledge_base_id"] == knowledge_base.pk:
                if target["id"] == row["id"] or target["status"] != "active" or not target["accepts_pages"]:
                    _issue(
                        issues,
                        "merged_directory_target_not_assignable",
                        "Merged directory target must be a different active directory that accepts pages.",
                        entity_type="directory",
                        entity_id=row["id"],
                        details={
                            "target_accepts_pages": target["accepts_pages"],
                            "target_directory_id": target["id"],
                            "target_status": target["status"],
                        },
                    )
        elif row["merged_into_id"] is not None:
            _issue(
                issues,
                "non_merged_directory_has_redirect",
                "Only merged directories may retain a merged-into redirect.",
                entity_type="directory",
                entity_id=row["id"],
                details={
                    "merged_into_id": row["merged_into_id"],
                    "status": row["status"],
                },
            )

    system_rows = [row for row in rows if row["origin"] == "system"]
    reserved_rows = [row for row in rows if row["key"] == UNCLASSIFIED_DIRECTORY_KEY]
    candidate_ids = sorted({row["id"] for row in (*system_rows, *reserved_rows)})
    if not candidate_ids:
        _issue(
            issues,
            "system_unclassified_directory_missing",
            "Knowledge base has no system unclassified directory.",
            blocking=strict_directory,
            entity_type="knowledge_base",
            entity_id=knowledge_base.pk,
            details={"migration_pending": not strict_directory},
        )
    elif len(system_rows) != 1 or len(reserved_rows) != 1 or system_rows[0]["id"] != reserved_rows[0]["id"]:
        _issue(
            issues,
            "system_unclassified_directory_not_unique",
            "Knowledge base must have exactly one system directory using the reserved unclassified key.",
            entity_type="knowledge_base",
            entity_id=knowledge_base.pk,
            details={
                "candidate_directory_ids": candidate_ids,
                "reserved_key_directory_ids": sorted(row["id"] for row in reserved_rows),
                "system_directory_ids": sorted(row["id"] for row in system_rows),
            },
        )
    else:
        unclassified = system_rows[0]
        expected = {
            "accepts_pages": True,
            "key": UNCLASSIFIED_DIRECTORY_KEY,
            "merged_into_id": None,
            "name": UNCLASSIFIED_DIRECTORY_NAME,
            "origin": "system",
            "parent_id": None,
            "status": "active",
        }
        invalid_fields = sorted(field_name for field_name, expected_value in expected.items() if unclassified[field_name] != expected_value)
        if invalid_fields:
            _issue(
                issues,
                "system_unclassified_directory_invalid",
                "System unclassified directory violates its immutable identity.",
                entity_type="directory",
                entity_id=unclassified["id"],
                details={"invalid_fields": invalid_fields},
            )

    active_rows = {row_id: row for row_id, row in rows_by_id.items() if row["status"] == "active"}
    for row in active_rows.values():
        current = row
        visited: list[int] = []
        while True:
            current_id = current["id"]
            if current_id in visited:
                cycle_start = visited.index(current_id)
                _issue(
                    issues,
                    "active_directory_parent_cycle",
                    "Active directory parent chain contains a cycle.",
                    entity_type="directory",
                    entity_id=row["id"],
                    details={"cycle": visited[cycle_start:] + [current_id]},
                )
                break
            visited.append(current_id)
            if len(visited) > MAX_DIRECTORY_DEPTH:
                _issue(
                    issues,
                    "active_directory_depth_exceeded",
                    "Active directory depth exceeds the supported maximum.",
                    entity_type="directory",
                    entity_id=row["id"],
                    details={
                        "depth": len(visited),
                        "maximum_depth": MAX_DIRECTORY_DEPTH,
                    },
                )
                break
            parent_id = current["parent_id"]
            if parent_id is None:
                break
            parent = referenced.get(parent_id)
            if parent is None or parent["knowledge_base_id"] != knowledge_base.pk:
                break
            if parent["status"] != "active":
                _issue(
                    issues,
                    "active_directory_parent_not_active",
                    "Active directory parent must also be active.",
                    entity_type="directory",
                    entity_id=row["id"],
                    details={"parent_id": parent_id, "parent_status": parent["status"]},
                )
                break
            current = rows_by_id[parent_id]

    return rows_by_id


def _snapshot_parent_key(entry: Mapping[str, Any]) -> str | None:
    if "parent_key" in entry:
        return entry.get("parent_key")
    parent = entry.get("parent")
    if isinstance(parent, Mapping):
        return parent.get("key")
    return None


def _audit_structure_projection(
    *,
    revision: Mapping[str, Any] | None,
    directory_rows_by_id: Mapping[int, Mapping[str, Any]],
    issues: list[ReadinessIssue],
) -> None:
    if revision is None:
        return
    snapshot = revision.get("structure_snapshot")
    if not isinstance(snapshot, dict):
        _issue(
            issues,
            "active_structure_snapshot_invalid",
            "Active structure revision snapshot must be an object.",
            entity_type="structure_revision",
            entity_id=revision["id"],
        )
        return

    canonical = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    computed_fingerprint = hashlib.sha256(canonical).hexdigest()
    if revision["fingerprint"] != computed_fingerprint:
        _issue(
            issues,
            "active_structure_snapshot_fingerprint_mismatch",
            "Active structure snapshot does not match its stored fingerprint.",
            entity_type="structure_revision",
            entity_id=revision["id"],
            details={
                "computed_fingerprint": computed_fingerprint,
                "stored_fingerprint": revision["fingerprint"],
            },
        )

    raw_entries = snapshot.get("directories")
    if not isinstance(raw_entries, list):
        _issue(
            issues,
            "active_structure_directories_invalid",
            "Active structure snapshot directories must be a list.",
            entity_type="structure_revision",
            entity_id=revision["id"],
        )
        return

    snapshot_by_key: dict[str, Mapping[str, Any]] = {}
    duplicate_keys: set[str] = set()
    invalid_indexes: list[int] = []
    for index, entry in enumerate(raw_entries):
        if not isinstance(entry, dict) or not isinstance(entry.get("key"), str) or not entry["key"].strip():
            invalid_indexes.append(index)
            continue
        key = entry["key"]
        if key in snapshot_by_key:
            duplicate_keys.add(key)
        else:
            snapshot_by_key[key] = entry
    if invalid_indexes:
        _issue(
            issues,
            "active_structure_directory_entry_invalid",
            "Active structure snapshot contains invalid directory entries.",
            entity_type="structure_revision",
            entity_id=revision["id"],
            details={"indexes": invalid_indexes},
        )
    if duplicate_keys:
        _issue(
            issues,
            "active_structure_directory_key_duplicate",
            "Active structure snapshot contains duplicate directory keys.",
            entity_type="structure_revision",
            entity_id=revision["id"],
            details={"keys": sorted(duplicate_keys)},
        )

    active_snapshot = {key: entry for key, entry in snapshot_by_key.items() if entry.get("status", "active") == "active"}
    active_projection = {row["key"]: row for row in directory_rows_by_id.values() if row["status"] == "active"}
    missing_projection_keys = sorted(set(active_snapshot).difference(active_projection))
    unexpected_projection_keys = sorted(set(active_projection).difference(active_snapshot))
    if missing_projection_keys or unexpected_projection_keys:
        _issue(
            issues,
            "active_structure_projection_membership_mismatch",
            "Active WikiDirectory projection and active revision snapshot contain different directories.",
            entity_type="structure_revision",
            entity_id=revision["id"],
            details={
                "missing_projection_keys": missing_projection_keys,
                "unexpected_projection_keys": unexpected_projection_keys,
            },
        )

    for key in sorted(set(active_snapshot).intersection(active_projection)):
        entry = active_snapshot[key]
        row = active_projection[key]
        parent = directory_rows_by_id.get(row["parent_id"])
        actual_parent_key = parent["key"] if parent is not None else None
        expected_values: dict[str, Any] = {
            "key": key,
            "name": entry.get("name"),
            "parent_key": _snapshot_parent_key(entry),
        }
        actual_values: dict[str, Any] = {
            "key": row["key"],
            "name": row["name"],
            "parent_key": actual_parent_key,
        }
        optional_fields = (
            ("id", "id"),
            ("description", "description"),
            ("order", "sort_order"),
            ("origin", "origin"),
            ("status", "status"),
            ("accepts_pages", "accepts_pages"),
        )
        for snapshot_field, projection_field in optional_fields:
            if snapshot_field in entry:
                expected_values[snapshot_field] = entry[snapshot_field]
                actual_values[snapshot_field] = row[projection_field]
        mismatches = {
            field_name: {
                "projection": actual_values[field_name],
                "snapshot": expected_value,
            }
            for field_name, expected_value in expected_values.items()
            if actual_values[field_name] != expected_value
        }
        if mismatches:
            _issue(
                issues,
                "active_structure_projection_directory_mismatch",
                "Active directory projection differs from its structure snapshot entry.",
                entity_type="directory",
                entity_id=row["id"],
                details={"key": key, "mismatches": mismatches},
            )


def _generation_identity_reasons(
    generation: Mapping[str, Any],
    *,
    knowledge_base_id: int,
    require_base_generation: bool,
    revisions: Mapping[int, Mapping[str, Any]],
    base_generations: Mapping[int, Mapping[str, Any]],
) -> list[str]:
    reasons: list[str] = []
    if generation["knowledge_base_id"] != knowledge_base_id:
        reasons.append("generation_cross_knowledge_base")
    if generation["status"] not in RUNNING_BUILD_GENERATION_STATUSES:
        reasons.append("generation_status_not_running_compatible")

    revision_id = generation["structure_revision_id"]
    revision = revisions.get(revision_id)
    if revision_id is None:
        reasons.append("missing_structure_revision")
    elif revision is None:
        reasons.append("structure_revision_missing")
    elif revision["knowledge_base_id"] != knowledge_base_id:
        reasons.append("structure_revision_cross_knowledge_base")
    elif generation["structure_fingerprint"] != revision["fingerprint"]:
        reasons.append("structure_fingerprint_mismatch")

    if not str(generation["structure_fingerprint"] or "").strip():
        reasons.append("missing_structure_fingerprint")
    if not str(generation["pipeline_version"] or "").strip():
        reasons.append("missing_pipeline_version")

    base_generation_id = generation["base_generation_id"]
    if base_generation_id is None:
        if require_base_generation:
            reasons.append("missing_base_generation")
    else:
        base_generation = base_generations.get(base_generation_id)
        if base_generation is None:
            reasons.append("base_generation_missing")
        elif base_generation["knowledge_base_id"] != knowledge_base_id:
            reasons.append("base_generation_cross_knowledge_base")
        else:
            if base_generation_id == generation["id"]:
                reasons.append("base_generation_self_reference")
            if base_generation["status"] not in VALID_BASE_GENERATION_STATUSES:
                reasons.append("base_generation_status_invalid")
    return reasons


def _audit_running_builds(
    *,
    knowledge_base: WikiKnowledgeBase,
    require_base_generation: bool,
    issues: list[ReadinessIssue],
) -> int:
    builds = list(
        BuildRecord.objects.filter(
            knowledge_base_id=knowledge_base.pk,
            status="running",
        )
        .values("id", "stage", "trigger")
        .order_by("id")
    )
    if not builds:
        return 0

    build_ids = [row["id"] for row in builds]
    generations = list(
        WikiGeneration.objects.filter(build_record_id__in=build_ids)
        .values(
            "id",
            "build_record_id",
            "knowledge_base_id",
            "structure_revision_id",
            "base_generation_id",
            "structure_fingerprint",
            "pipeline_version",
            "status",
        )
        .order_by("id")
    )
    revision_ids = {row["structure_revision_id"] for row in generations if row["structure_revision_id"] is not None}
    revisions = {row["id"]: row for row in WikiStructureRevision.objects.filter(id__in=revision_ids).values("id", "knowledge_base_id", "fingerprint")}
    base_generation_ids = {row["base_generation_id"] for row in generations if row["base_generation_id"] is not None}
    base_generations = {
        row["id"]: row for row in WikiGeneration.objects.filter(id__in=base_generation_ids).values("id", "knowledge_base_id", "status")
    }
    by_build: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for generation in generations:
        by_build[generation["build_record_id"]].append(generation)

    for build in builds:
        candidates = by_build.get(build["id"], [])
        invalid_reasons: set[str] = set()
        invalid_generation_ids: list[int] = []
        for generation in candidates:
            reasons = _generation_identity_reasons(
                generation,
                knowledge_base_id=knowledge_base.pk,
                require_base_generation=require_base_generation,
                revisions=revisions,
                base_generations=base_generations,
            )
            if reasons:
                invalid_reasons.update(reasons)
                invalid_generation_ids.append(generation["id"])
        if candidates and not invalid_generation_ids:
            continue
        if not candidates:
            invalid_reasons.add("no_generation")
        _issue(
            issues,
            "running_build_identity_missing",
            "Running build lacks a complete generation-aware identity and must be drained.",
            entity_type="build_record",
            entity_id=build["id"],
            details={
                "generation_ids": [row["id"] for row in candidates],
                "invalid_generation_ids": invalid_generation_ids,
                "reasons": sorted(invalid_reasons),
                "stage": build["stage"],
                "trigger": build["trigger"],
            },
        )
    return len(builds)


def _load_active_pointers(  # noqa: C901
    *,
    knowledge_base: WikiKnowledgeBase,
    strict_generation: bool,
    issues: list[ReadinessIssue],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    revision = None
    generation = None
    revision_id = knowledge_base.active_structure_revision_id
    generation_id = knowledge_base.active_generation_id

    if strict_generation and revision_id is None:
        _issue(
            issues,
            "active_structure_revision_missing",
            "A ready or enable-target knowledge base requires an active structure revision.",
            entity_type="knowledge_base",
            entity_id=knowledge_base.pk,
        )
    if strict_generation and generation_id is None:
        _issue(
            issues,
            "active_generation_missing",
            "A ready or enable-target knowledge base requires an active generation.",
            entity_type="knowledge_base",
            entity_id=knowledge_base.pk,
        )
    if (revision_id is None) != (generation_id is None):
        _issue(
            issues,
            "active_pointer_pair_incomplete",
            "Active structure and generation pointers must be published as a compatible pair.",
            entity_type="knowledge_base",
            entity_id=knowledge_base.pk,
            details={
                "active_generation_id": generation_id,
                "active_structure_revision_id": revision_id,
            },
        )

    if revision_id is not None:
        revision = (
            WikiStructureRevision.objects.filter(pk=revision_id)
            .values(
                "id",
                "knowledge_base_id",
                "revision_no",
                "fingerprint",
                "structure_snapshot",
            )
            .first()
        )
        if revision is None:
            _issue(
                issues,
                "active_structure_revision_not_found",
                "Active structure revision pointer references a missing row.",
                entity_type="knowledge_base",
                entity_id=knowledge_base.pk,
                details={"active_structure_revision_id": revision_id},
            )
        elif revision["knowledge_base_id"] != knowledge_base.pk:
            _issue(
                issues,
                "active_structure_revision_cross_knowledge_base",
                "Active structure revision belongs to another knowledge base.",
                entity_type="knowledge_base",
                entity_id=knowledge_base.pk,
                details={
                    "active_structure_revision_id": revision_id,
                    "revision_knowledge_base_id": revision["knowledge_base_id"],
                },
            )
        elif not str(revision["fingerprint"] or "").strip():
            _issue(
                issues,
                "active_structure_fingerprint_missing",
                "Active structure revision has no immutable fingerprint.",
                entity_type="structure_revision",
                entity_id=revision_id,
            )

    if generation_id is not None:
        generation = (
            WikiGeneration.objects.filter(pk=generation_id)
            .values(
                "id",
                "knowledge_base_id",
                "build_record_id",
                "structure_revision_id",
                "base_generation_id",
                "rollback_of_id",
                "kind",
                "structure_fingerprint",
                "pipeline_version",
                "source_fingerprints",
                "status",
            )
            .first()
        )
        if generation is None:
            _issue(
                issues,
                "active_generation_not_found",
                "Active generation pointer references a missing row.",
                entity_type="knowledge_base",
                entity_id=knowledge_base.pk,
                details={"active_generation_id": generation_id},
            )
            return revision, None
        if generation["knowledge_base_id"] != knowledge_base.pk:
            _issue(
                issues,
                "active_generation_cross_knowledge_base",
                "Active generation belongs to another knowledge base.",
                entity_type="knowledge_base",
                entity_id=knowledge_base.pk,
                details={
                    "active_generation_id": generation_id,
                    "generation_knowledge_base_id": generation["knowledge_base_id"],
                },
            )
        if generation["status"] != "active":
            _issue(
                issues,
                "active_generation_status_invalid",
                "Active generation pointer must reference a generation in active status.",
                entity_type="generation",
                entity_id=generation_id,
                details={"status": generation["status"]},
            )
        if not str(generation["pipeline_version"] or "").strip():
            _issue(
                issues,
                "active_generation_pipeline_version_missing",
                "Active generation has no pipeline version.",
                entity_type="generation",
                entity_id=generation_id,
            )
        if not str(generation["structure_fingerprint"] or "").strip():
            _issue(
                issues,
                "active_generation_structure_fingerprint_missing",
                "Active generation has no structure fingerprint.",
                entity_type="generation",
                entity_id=generation_id,
            )
        if not isinstance(generation["source_fingerprints"], list):
            _issue(
                issues,
                "active_generation_source_fingerprints_invalid",
                "Active generation source fingerprints must be a list.",
                entity_type="generation",
                entity_id=generation_id,
            )

        generation_revision_id = generation["structure_revision_id"]
        if revision_id is not None and generation_revision_id != revision_id:
            _issue(
                issues,
                "active_generation_structure_revision_mismatch",
                "Active generation and active structure pointers reference different revisions.",
                entity_type="generation",
                entity_id=generation_id,
                details={
                    "active_structure_revision_id": revision_id,
                    "generation_structure_revision_id": generation_revision_id,
                },
            )
        if revision is not None and generation["structure_fingerprint"] != revision["fingerprint"]:
            _issue(
                issues,
                "active_generation_structure_fingerprint_mismatch",
                "Active generation fingerprint differs from its active structure revision.",
                entity_type="generation",
                entity_id=generation_id,
                details={
                    "generation_fingerprint": generation["structure_fingerprint"],
                    "revision_fingerprint": revision["fingerprint"],
                },
            )

        base_generation_id = generation["base_generation_id"]
        if base_generation_id is not None:
            base_generation = WikiGeneration.objects.filter(pk=base_generation_id).values("id", "knowledge_base_id", "status").first()
            if base_generation is None:
                _issue(
                    issues,
                    "active_generation_base_not_found",
                    "Active generation references a missing base generation.",
                    entity_type="generation",
                    entity_id=generation_id,
                    details={"base_generation_id": base_generation_id},
                )
            elif base_generation["knowledge_base_id"] != knowledge_base.pk:
                _issue(
                    issues,
                    "active_generation_base_cross_knowledge_base",
                    "Active generation base belongs to another knowledge base.",
                    entity_type="generation",
                    entity_id=generation_id,
                    details={
                        "base_generation_id": base_generation_id,
                        "base_knowledge_base_id": base_generation["knowledge_base_id"],
                    },
                )
            else:
                if base_generation_id == generation_id:
                    _issue(
                        issues,
                        "active_generation_base_self_reference",
                        "Active generation cannot use itself as its base.",
                        entity_type="generation",
                        entity_id=generation_id,
                    )
                if base_generation["status"] != "superseded":
                    _issue(
                        issues,
                        "active_generation_base_status_invalid",
                        "An activated generation base must be superseded.",
                        entity_type="generation",
                        entity_id=generation_id,
                        details={
                            "base_generation_id": base_generation_id,
                            "base_status": base_generation["status"],
                        },
                    )

        rollback_of_id = generation["rollback_of_id"]
        if (generation["kind"] == "rollback") != (rollback_of_id is not None):
            _issue(
                issues,
                "active_generation_rollback_identity_invalid",
                "Rollback ownership must be present only for rollback generations.",
                entity_type="generation",
                entity_id=generation_id,
                details={"kind": generation["kind"], "rollback_of_id": rollback_of_id},
            )
        if rollback_of_id is not None:
            rollback_owner = WikiGeneration.objects.filter(pk=rollback_of_id).values_list("knowledge_base_id", flat=True).first()
            if rollback_owner is None:
                _issue(
                    issues,
                    "active_generation_rollback_target_not_found",
                    "Active rollback generation references a missing target generation.",
                    entity_type="generation",
                    entity_id=generation_id,
                    details={"rollback_of_id": rollback_of_id},
                )
            elif rollback_owner != knowledge_base.pk:
                _issue(
                    issues,
                    "active_generation_rollback_target_cross_knowledge_base",
                    "Active rollback target belongs to another knowledge base.",
                    entity_type="generation",
                    entity_id=generation_id,
                    details={
                        "rollback_of_id": rollback_of_id,
                        "rollback_target_knowledge_base_id": rollback_owner,
                    },
                )

        build_record_id = generation["build_record_id"]
        if build_record_id is not None:
            build_owner = BuildRecord.objects.filter(pk=build_record_id).values_list("knowledge_base_id", flat=True).first()
            if build_owner is None:
                _issue(
                    issues,
                    "active_generation_build_not_found",
                    "Active generation references a missing build record.",
                    entity_type="generation",
                    entity_id=generation_id,
                    details={"build_record_id": build_record_id},
                )
            elif build_owner != knowledge_base.pk:
                _issue(
                    issues,
                    "active_generation_build_cross_knowledge_base",
                    "Active generation references a build from another knowledge base.",
                    entity_type="generation",
                    entity_id=generation_id,
                    details={
                        "build_knowledge_base_id": build_owner,
                        "build_record_id": build_record_id,
                    },
                )
    return revision, generation


def _projected_directory_breadcrumb(
    directory_id: int,
    directories: Mapping[int, Mapping[str, Any]],
) -> list[dict[str, Any]] | None:
    breadcrumb: list[dict[str, Any]] = []
    current_id: int | None = directory_id
    visited: set[int] = set()
    while current_id is not None:
        if current_id in visited:
            return None
        visited.add(current_id)
        row = directories.get(current_id)
        if row is None:
            return None
        breadcrumb.append({"id": row["id"], "key": row["key"], "name": row["name"]})
        current_id = row["parent_id"]
    breadcrumb.reverse()
    return breadcrumb


def _audit_generation_members(  # noqa: C901
    *,
    knowledge_base: WikiKnowledgeBase,
    generation: Mapping[str, Any] | None,
    page_rows_by_id: Mapping[int, Mapping[str, Any]],
    directory_rows_by_id: Mapping[int, Mapping[str, Any]],
    issues: list[ReadinessIssue],
) -> int:
    if generation is None:
        return 0
    member_rows = list(
        WikiGenerationPage.objects.filter(generation_id=generation["id"])
        .values(
            "id",
            "page_id",
            "page_version_id",
            "directory_id",
            "directory_key_snapshot",
            "directory_breadcrumb_snapshot",
            "assignment_mode",
            "page_status",
            "page_display_snapshot",
        )
        .order_by("id")
    )
    member_page_ids = {row["page_id"] for row in member_rows}
    is_active_truth = generation["status"] == "active" and generation["knowledge_base_id"] == knowledge_base.pk
    if is_active_truth:
        mirror_page_ids = {page_id for page_id, row in page_rows_by_id.items() if row["status"] in ACTIVE_GENERATION_PAGE_STATUSES}
        missing_member_page_ids = sorted(mirror_page_ids.difference(member_page_ids))
        unexpected_member_page_ids = sorted(member_page_ids.difference(mirror_page_ids))
        if missing_member_page_ids or unexpected_member_page_ids:
            _issue(
                issues,
                "active_generation_member_set_mismatch",
                "Active compatibility mirror and active generation must contain the same knowledge pages.",
                entity_type="generation",
                entity_id=generation["id"],
                details={
                    "missing_member_page_ids": missing_member_page_ids,
                    "unexpected_member_page_ids": unexpected_member_page_ids,
                },
            )

    page_rows = dict(page_rows_by_id)
    missing_page_ids = member_page_ids.difference(page_rows)
    if missing_page_ids:
        page_rows.update(
            {
                row["id"]: row
                for row in KnowledgePage.objects.filter(id__in=missing_page_ids).values(
                    "id",
                    "knowledge_base_id",
                    "title",
                    "page_type",
                    "tags",
                    "contribution",
                    "update_method",
                    "status",
                    "directory_id",
                    "directory_assignment_mode",
                    "current_version_id",
                )
            }
        )

    version_ids = {row["page_version_id"] for row in member_rows}
    versions = {row["id"]: row for row in PageVersion.objects.filter(id__in=version_ids).values("id", "page_id", "created_in_generation_id")}
    directory_ids = {row["directory_id"] for row in member_rows}
    directories = dict(directory_rows_by_id)
    missing_directory_ids = directory_ids.difference(directories)
    if missing_directory_ids:
        directories.update(
            {
                row["id"]: row
                for row in WikiDirectory.objects.filter(id__in=missing_directory_ids).values(
                    "id",
                    "knowledge_base_id",
                    "key",
                    "name",
                    "parent_id",
                    "status",
                    "accepts_pages",
                )
            }
        )

    for member in member_rows:
        member_id = member["id"]
        page = page_rows.get(member["page_id"])
        version = versions.get(member["page_version_id"])
        directory = directories.get(member["directory_id"])

        if page is None:
            _issue(
                issues,
                "generation_member_page_not_found",
                "Generation member references a missing page.",
                entity_type="generation_member",
                entity_id=member_id,
                details={"page_id": member["page_id"]},
            )
        elif page["knowledge_base_id"] != knowledge_base.pk:
            _issue(
                issues,
                "generation_member_page_cross_knowledge_base",
                "Generation member page belongs to another knowledge base.",
                entity_type="generation_member",
                entity_id=member_id,
                details={
                    "page_id": member["page_id"],
                    "page_knowledge_base_id": page["knowledge_base_id"],
                },
            )

        if version is None:
            _issue(
                issues,
                "generation_member_version_not_found",
                "Generation member references a missing page version.",
                entity_type="generation_member",
                entity_id=member_id,
                details={"page_version_id": member["page_version_id"]},
            )
        elif version["page_id"] != member["page_id"]:
            _issue(
                issues,
                "generation_member_version_page_mismatch",
                "Generation member version does not belong to its page.",
                entity_type="generation_member",
                entity_id=member_id,
                details={
                    "member_page_id": member["page_id"],
                    "page_version_id": member["page_version_id"],
                    "version_page_id": version["page_id"],
                },
            )

        if directory is None:
            _issue(
                issues,
                "generation_member_directory_not_found",
                "Generation member references a missing directory.",
                entity_type="generation_member",
                entity_id=member_id,
                details={"directory_id": member["directory_id"]},
            )
        elif directory["knowledge_base_id"] != knowledge_base.pk:
            _issue(
                issues,
                "generation_member_directory_cross_knowledge_base",
                "Generation member directory belongs to another knowledge base.",
                entity_type="generation_member",
                entity_id=member_id,
                details={
                    "directory_id": member["directory_id"],
                    "directory_knowledge_base_id": directory["knowledge_base_id"],
                },
            )
        else:
            if directory["status"] != "active" or not directory["accepts_pages"]:
                _issue(
                    issues,
                    "generation_member_directory_not_assignable",
                    "Generation member directory must be active and accept pages.",
                    entity_type="generation_member",
                    entity_id=member_id,
                    details={
                        "accepts_pages": directory["accepts_pages"],
                        "directory_id": directory["id"],
                        "directory_status": directory["status"],
                    },
                )
            if member["directory_key_snapshot"] != directory["key"]:
                _issue(
                    issues,
                    "generation_member_directory_key_mismatch",
                    "Generation member directory key snapshot differs from the active projection.",
                    entity_type="generation_member",
                    entity_id=member_id,
                    details={
                        "directory_key": directory["key"],
                        "directory_key_snapshot": member["directory_key_snapshot"],
                    },
                )
            projected_breadcrumb = _projected_directory_breadcrumb(
                directory["id"],
                directory_rows_by_id,
            )
            if projected_breadcrumb is not None and member["directory_breadcrumb_snapshot"] != projected_breadcrumb:
                _issue(
                    issues,
                    "generation_member_breadcrumb_snapshot_mismatch",
                    "Generation member breadcrumb differs from the active directory projection.",
                    entity_type="generation_member",
                    entity_id=member_id,
                    details={
                        "directory_id": directory["id"],
                        "projection": projected_breadcrumb,
                        "snapshot": member["directory_breadcrumb_snapshot"],
                    },
                )

        if member["assignment_mode"] not in KNOWN_ASSIGNMENT_MODES:
            _issue(
                issues,
                "invalid_generation_member_assignment_mode",
                "Generation member assignment mode must be auto or manual.",
                entity_type="generation_member",
                entity_id=member_id,
                details={"assignment_mode": member["assignment_mode"]},
            )
        if member["page_status"] not in KNOWN_PAGE_STATUSES:
            _issue(
                issues,
                "invalid_generation_member_page_status",
                "Generation member has an unsupported page-status snapshot.",
                entity_type="generation_member",
                entity_id=member_id,
                details={"page_status": member["page_status"]},
            )
        if is_active_truth and member["page_status"] not in ACTIVE_GENERATION_PAGE_STATUSES:
            _issue(
                issues,
                "active_generation_member_status_invalid",
                "Active generation may contain only active page members.",
                entity_type="generation_member",
                entity_id=member_id,
                details={"page_status": member["page_status"]},
            )
        if not isinstance(member["directory_breadcrumb_snapshot"], list):
            _issue(
                issues,
                "generation_member_breadcrumb_snapshot_invalid",
                "Generation member breadcrumb snapshot must be a list.",
                entity_type="generation_member",
                entity_id=member_id,
            )

        display_snapshot = member["page_display_snapshot"]
        if not isinstance(display_snapshot, dict):
            _issue(
                issues,
                "generation_member_page_display_snapshot_invalid",
                "Generation member page display snapshot must be an object.",
                entity_type="generation_member",
                entity_id=member_id,
            )
        elif is_active_truth and page is not None and page["knowledge_base_id"] == knowledge_base.pk:
            display_mismatches: dict[str, dict[str, Any]] = {}
            for field_name in DISPLAY_MIRROR_FIELDS:
                mirror_value = page[field_name]
                if field_name not in display_snapshot:
                    display_mismatches[field_name] = {
                        "generation": "<missing>",
                        "mirror": mirror_value,
                    }
                elif display_snapshot[field_name] != mirror_value:
                    display_mismatches[field_name] = {
                        "generation": display_snapshot[field_name],
                        "mirror": mirror_value,
                    }
            if display_mismatches:
                _issue(
                    issues,
                    "generation_member_display_mirror_mismatch",
                    "Page display mirror differs from the active generation snapshot.",
                    entity_type="generation_member",
                    entity_id=member_id,
                    details={
                        "mismatches": display_mismatches,
                        "page_id": member["page_id"],
                    },
                )

        if is_active_truth and page is not None and page["knowledge_base_id"] == knowledge_base.pk:
            mismatches: dict[str, dict[str, Any]] = {}
            for field_name, mirror_value, snapshot_value in (
                (
                    "current_version_id",
                    page["current_version_id"],
                    member["page_version_id"],
                ),
                ("directory_id", page["directory_id"], member["directory_id"]),
                (
                    "directory_assignment_mode",
                    page["directory_assignment_mode"],
                    member["assignment_mode"],
                ),
                ("status", page["status"], member["page_status"]),
            ):
                if mirror_value != snapshot_value:
                    mismatches[field_name] = {
                        "generation": snapshot_value,
                        "mirror": mirror_value,
                    }
            if mismatches:
                _issue(
                    issues,
                    "generation_member_compatibility_mirror_mismatch",
                    "Page compatibility mirror differs from the active generation member snapshot.",
                    entity_type="generation_member",
                    entity_id=member_id,
                    details={"mismatches": mismatches, "page_id": member["page_id"]},
                )
    return len(member_rows)


def audit_knowledge_base_readiness(
    knowledge_base: WikiKnowledgeBase,
    *,
    enable_check: bool = False,
) -> KnowledgeBaseReadinessResult:
    """Audit one KB without mutations.

    ``enable_check=True`` is the strict final check.  A caller performing the
    state transition must pass the ``WikiKnowledgeBase`` instance obtained by
    ``select_for_update`` and keep the surrounding transaction open.
    """

    if knowledge_base.pk is None:
        raise ValueError("knowledge_base must be persisted")

    issues: list[ReadinessIssue] = []
    strict_generation = True
    strict_directory = True

    page_rows, page_rows_by_id = _audit_pages(
        knowledge_base=knowledge_base,
        strict_directory=strict_directory,
        issues=issues,
    )
    directory_rows_by_id = _audit_directory_links(
        knowledge_base=knowledge_base,
        strict_directory=strict_directory,
        issues=issues,
    )
    running_build_count = _audit_running_builds(
        knowledge_base=knowledge_base,
        require_base_generation=strict_generation and knowledge_base.active_generation_id is not None,
        issues=issues,
    )
    revision, generation = _load_active_pointers(
        knowledge_base=knowledge_base,
        strict_generation=strict_generation,
        issues=issues,
    )
    _audit_structure_projection(
        revision=revision,
        directory_rows_by_id=directory_rows_by_id,
        issues=issues,
    )
    member_count = _audit_generation_members(
        knowledge_base=knowledge_base,
        generation=generation,
        page_rows_by_id=page_rows_by_id,
        directory_rows_by_id=directory_rows_by_id,
        issues=issues,
    )

    return KnowledgeBaseReadinessResult(
        knowledge_base_id=knowledge_base.pk,
        knowledge_base_name=knowledge_base.name,
        directory_enabled=knowledge_base.directory_enabled,
        mode="enable",
        issues=tuple(sorted(issues, key=ReadinessIssue.sort_key)),
        scanned={
            "directory_count": len(directory_rows_by_id),
            "generation_member_count": member_count,
            "page_count": len(page_rows),
            "running_build_count": running_build_count,
        },
    )


def audit_wiki_directory_readiness(
    knowledge_bases: Iterable[WikiKnowledgeBase] | None = None,
    *,
    knowledge_base_ids: Iterable[int] | None = None,
    enable_check: bool = False,
) -> ReadinessAuditReport:
    """Audit selected or all knowledge bases and return a serializable report."""

    requested_ids = tuple(sorted({int(knowledge_base_id) for knowledge_base_id in knowledge_base_ids})) if knowledge_base_ids is not None else ()
    if knowledge_bases is None:
        queryset = WikiKnowledgeBase.objects.all()
        if requested_ids:
            queryset = queryset.filter(pk__in=requested_ids)
        knowledge_base_list = list(queryset.order_by("id"))
    else:
        knowledge_base_list = list(knowledge_bases)
        if requested_ids:
            requested_set = set(requested_ids)
            knowledge_base_list = [knowledge_base for knowledge_base in knowledge_base_list if knowledge_base.pk in requested_set]
        knowledge_base_list.sort(key=lambda knowledge_base: knowledge_base.pk)

    found_ids = {knowledge_base.pk for knowledge_base in knowledge_base_list}
    missing_ids = tuple(knowledge_base_id for knowledge_base_id in requested_ids if knowledge_base_id not in found_ids)
    results = tuple(
        audit_knowledge_base_readiness(
            knowledge_base,
            enable_check=enable_check,
        )
        for knowledge_base in knowledge_base_list
    )
    return ReadinessAuditReport(
        mode="enable",
        knowledge_bases=results,
        missing_knowledge_base_ids=missing_ids,
    )


def require_directory_enable_readiness(
    locked_knowledge_base: WikiKnowledgeBase,
) -> KnowledgeBaseReadinessResult:
    """Recheck readiness for a KB already locked by the enable transaction."""

    result = audit_knowledge_base_readiness(
        locked_knowledge_base,
        enable_check=True,
    )
    if not result.ready:
        raise WikiDirectoryNotReady(result)
    return result
