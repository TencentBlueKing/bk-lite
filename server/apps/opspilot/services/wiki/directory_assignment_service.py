"""ORM adapter for deterministic Wiki directory assignment.

The service freezes routing against one ``WikiStructureRevision`` snapshot and
uses ``WikiDirectory`` rows only as the persistence projection returned to the
caller.  It never creates directories or knowledge candidates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from apps.opspilot.models import WikiDirectory
from apps.opspilot.services.wiki.directory_routing_contract import (
    AssignmentMode,
    DirectoryReferenceSource,
    DirectoryRouteSource,
    DirectoryRoutingDecision,
    DirectoryRoutingInvariantError,
    DirectorySnapshot,
    DirectoryStatus,
    route_directory,
)

UNCLASSIFIED_DIRECTORY_KEY = "__unclassified__"


class DirectoryAssignmentError(DirectoryRoutingInvariantError):
    """The persisted directory projection cannot represent the fixed revision."""


@dataclass(frozen=True)
class DirectoryAssignmentResult:
    directory: Any
    decision: DirectoryRoutingDecision
    assignment_mode: str
    source: str
    trace: tuple[str, ...]
    route_reason: str
    suggestion_reason: str
    confidence: float | None
    suggested_key: str | None
    suggestion_source: str
    schema_mismatch: bool
    low_confidence: bool
    redirect_chain: tuple[str, ...]
    structure_revision_id: int
    structure_revision_no: int
    structure_fingerprint: str

    @property
    def suggestion_confidence(self):
        return self.confidence

    @property
    def suggestion_schema_mismatch(self):
        return self.schema_mismatch

    def as_build_trace(self) -> dict:
        """Return JSON-safe metadata suitable for BuildRecord maintenance."""

        return {
            "directory_id": self.directory.pk,
            "directory_key": self.directory.key,
            "assignment_mode": self.assignment_mode,
            "source": self.source,
            "trace": list(self.trace),
            "route_reason": self.route_reason,
            "suggestion": {
                "key": self.suggested_key,
                "source": self.suggestion_source,
                "reason": self.suggestion_reason,
                "confidence": self.confidence,
                "schema_mismatch": self.schema_mismatch,
                "low_confidence": self.low_confidence,
            },
            "redirect_chain": list(self.redirect_chain),
            "structure_revision": {
                "id": self.structure_revision_id,
                "revision_no": self.structure_revision_no,
                "fingerprint": self.structure_fingerprint,
            },
        }


def _normalized_confidence(value):
    if value is None:
        return None
    if isinstance(value, bool):
        raise DirectoryAssignmentError("suggestion confidence must be a number between 0 and 1")
    try:
        confidence = float(value)
    except (TypeError, ValueError) as error:
        raise DirectoryAssignmentError("suggestion confidence must be a number between 0 and 1") from error
    if confidence < 0 or confidence > 1:
        raise DirectoryAssignmentError("suggestion confidence must be a number between 0 and 1")
    return confidence


def _snapshot_nodes(revision):
    snapshot = revision.structure_snapshot or {}
    directories = snapshot.get("directories")
    page_types = snapshot.get("page_types")
    if (
        snapshot.get("format_version") != 1
        or not isinstance(directories, list)
        or not isinstance(page_types, list)
        or not all(isinstance(page_type, str) and page_type for page_type in page_types)
    ):
        raise DirectoryAssignmentError("structure revision is not a complete format_version=1 snapshot")
    nodes = []
    seen_ids = set()
    seen_keys = set()
    for raw in directories:
        if not isinstance(raw, dict):
            raise DirectoryAssignmentError("structure snapshot contains a non-object directory")
        directory_id = raw.get("id")
        key = raw.get("key")
        if type(directory_id) is not int or directory_id <= 0 or not isinstance(key, str) or not key:
            raise DirectoryAssignmentError("structure snapshot contains an invalid directory identity")
        if directory_id in seen_ids or key in seen_keys:
            raise DirectoryAssignmentError("structure snapshot contains duplicate directory identities")
        seen_ids.add(directory_id)
        seen_keys.add(key)
        nodes.append(raw)
    return frozenset(page_types), nodes


def _frozen_ancestor_keys(node, nodes_by_id):
    ancestors = []
    visited = {node["id"]}
    parent = node.get("parent")
    while parent is not None:
        if not isinstance(parent, dict) or type(parent.get("id")) is not int or not isinstance(parent.get("key"), str):
            raise DirectoryAssignmentError("structure snapshot contains an invalid parent reference")
        parent_id = parent["id"]
        if parent_id in visited:
            raise DirectoryAssignmentError("structure snapshot contains a directory cycle")
        visited.add(parent_id)
        parent_node = nodes_by_id.get(parent_id)
        if parent_node is None or parent_node.get("key") != parent["key"]:
            raise DirectoryAssignmentError("structure snapshot contains a missing parent")
        ancestors.append(parent_node["key"])
        parent = parent_node.get("parent")
    ancestors.reverse()
    return tuple(ancestors)


def _row_ancestor_keys(row, rows_by_id):
    ancestors = []
    visited = {row.pk}
    parent_id = row.parent_id
    while parent_id is not None:
        if parent_id in visited:
            raise DirectoryAssignmentError("directory projection contains a cycle")
        visited.add(parent_id)
        parent = rows_by_id.get(parent_id)
        if parent is None:
            raise DirectoryAssignmentError("directory projection contains a missing parent")
        ancestors.append(parent.key)
        parent_id = parent.parent_id
    ancestors.reverse()
    return tuple(ancestors)


def _directory_snapshots(revision, rows):
    revision_page_types, nodes = _snapshot_nodes(revision)
    knowledge_base_id = revision.knowledge_base_id
    rows = list(rows)
    if any(row.knowledge_base_id != knowledge_base_id for row in rows):
        raise DirectoryAssignmentError("directory rows must belong to the revision knowledge base")
    rows_by_id = {}
    rows_by_key = {}
    for row in rows:
        if row.pk in rows_by_id or row.key in rows_by_key:
            raise DirectoryAssignmentError("directory projection contains duplicate identities")
        rows_by_id[row.pk] = row
        rows_by_key[row.key] = row

    nodes_by_id = {node["id"]: node for node in nodes}
    snapshots = {}
    type_defaults = {}
    for node in nodes:
        row = rows_by_id.get(node["id"])
        if row is None or row.key != node["key"]:
            raise DirectoryAssignmentError("fixed structure directory is missing from its ORM projection")
        try:
            status = DirectoryStatus(node.get("status", row.status))
        except ValueError as error:
            raise DirectoryAssignmentError(f"unknown directory status for {row.key!r}") from error
        rules = node.get("rules") or {}
        allowed = rules.get("allowed_page_types")
        if not isinstance(allowed, list):
            raise DirectoryAssignmentError(f"directory {row.key!r} has invalid allowed_page_types")
        defaults = rules.get("default_for_page_types")
        if not isinstance(defaults, list):
            raise DirectoryAssignmentError(f"directory {row.key!r} has invalid default_for_page_types")
        snapshots[row.key] = DirectorySnapshot(
            key=row.key,
            knowledge_base_id=knowledge_base_id,
            status=status,
            accepts_pages=row.accepts_pages,
            ancestor_keys=_frozen_ancestor_keys(node, nodes_by_id),
            merged_into_key=row.merged_into.key if row.merged_into_id else None,
            allowed_page_types=frozenset(allowed) if allowed else None,
            is_unclassified=row.key == UNCLASSIFIED_DIRECTORY_KEY,
        )
        for page_type in defaults:
            type_defaults.setdefault(page_type, []).append(row.key)

    # Retained merged keys may be absent from the current structure snapshot.
    # They are included only so the pure contract can enforce the source-aware
    # redirect boundary; they can never become defaults or roots.
    for row in rows:
        if row.key in snapshots:
            continue
        try:
            status = DirectoryStatus(row.status)
        except ValueError as error:
            raise DirectoryAssignmentError(f"unknown directory status for {row.key!r}") from error
        snapshots[row.key] = DirectorySnapshot(
            key=row.key,
            knowledge_base_id=knowledge_base_id,
            status=status,
            accepts_pages=row.accepts_pages,
            ancestor_keys=_row_ancestor_keys(row, rows_by_id),
            merged_into_key=row.merged_into.key if row.merged_into_id else None,
        )
    return revision_page_types, rows_by_id, rows_by_key, snapshots, type_defaults


def _directory_id(value, field_name):
    if value is None:
        return None
    value = getattr(value, "pk", value)
    if type(value) is not int or value <= 0:
        raise DirectoryAssignmentError(f"{field_name} must be a positive directory id")
    return value


def _route_reason(decision: DirectoryRoutingDecision, suggestion_reason: str) -> str:
    if decision.source in {DirectoryRouteSource.SUGGESTED_KEY, DirectoryRouteSource.REDIRECTED_KEY} and suggestion_reason:
        return suggestion_reason
    return decision.source.value


def resolve_page_directory(
    *,
    knowledge_base,
    structure_revision,
    page_type: str,
    assignment_mode: AssignmentMode | str = AssignmentMode.AUTO,
    current_directory=None,
    suggested_key: str | None = None,
    suggestion_source: DirectoryReferenceSource | str = DirectoryReferenceSource.LLM,
    classification_root_id=None,
    confidence=None,
    schema_mismatch: bool = False,
    suggestion_reason: str = "",
    low_confidence: bool = False,
    directory_rows: Iterable | None = None,
) -> DirectoryAssignmentResult:
    """Route one page against a fixed revision and return its ORM directory."""

    knowledge_base_id = getattr(knowledge_base, "pk", knowledge_base)
    if type(knowledge_base_id) is not int or knowledge_base_id <= 0:
        raise DirectoryAssignmentError("knowledge_base must be a persisted knowledge base")
    revision_id = getattr(structure_revision, "pk", None)
    if type(revision_id) is not int or revision_id <= 0:
        raise DirectoryAssignmentError("structure_revision must be a persisted revision")
    if structure_revision.knowledge_base_id != knowledge_base_id:
        raise DirectoryAssignmentError("structure_revision belongs to another knowledge base")
    page_type = page_type if isinstance(page_type, str) else ""
    suggested_key = suggested_key.strip() if isinstance(suggested_key, str) and suggested_key.strip() else None
    suggestion_reason = str(suggestion_reason or "").strip()
    normalized_confidence = _normalized_confidence(confidence)
    if directory_rows is None:
        directory_rows = (
            WikiDirectory.objects.filter(
                knowledge_base_id=knowledge_base_id,
            )
            .select_related("parent", "merged_into")
            .order_by("id")
        )
    revision_page_types, rows_by_id, rows_by_key, snapshots, type_defaults = _directory_snapshots(
        structure_revision,
        directory_rows,
    )
    current_id = _directory_id(current_directory, "current_directory")
    root_id = _directory_id(classification_root_id, "classification_root_id")
    current_key = rows_by_id[current_id].key if current_id in rows_by_id else None
    root_key = rows_by_id[root_id].key if root_id in rows_by_id else None
    if current_id is not None and current_key is None:
        raise DirectoryAssignmentError("current directory is missing from the ORM projection")
    if root_id is not None and root_key is None:
        raise DirectoryAssignmentError("classification root is missing from the ORM projection")

    decision = route_directory(
        knowledge_base_id=knowledge_base_id,
        page_type=page_type,
        revision_page_types=revision_page_types,
        assignment_mode=assignment_mode,
        directories=snapshots,
        current_directory_key=current_key,
        suggested_key=suggested_key,
        suggestion_source=suggestion_source,
        classification_root_key=root_key,
        type_default_keys=tuple(type_defaults.get(page_type, ())),
        unclassified_key=UNCLASSIFIED_DIRECTORY_KEY,
        suggestion_schema_mismatch=bool(schema_mismatch),
        low_confidence=bool(low_confidence),
    )
    directory = rows_by_key.get(decision.directory_key)
    if directory is None:
        raise DirectoryAssignmentError("routing decision has no ORM directory projection")
    source_value = suggestion_source.value if isinstance(suggestion_source, DirectoryReferenceSource) else str(suggestion_source)
    return DirectoryAssignmentResult(
        directory=directory,
        decision=decision,
        assignment_mode=decision.assignment_mode.value,
        source=decision.source.value,
        trace=tuple(code.value for code in decision.trace),
        route_reason=_route_reason(decision, suggestion_reason),
        suggestion_reason=suggestion_reason,
        confidence=normalized_confidence,
        suggested_key=suggested_key,
        suggestion_source=source_value,
        schema_mismatch=bool(schema_mismatch),
        low_confidence=bool(low_confidence),
        redirect_chain=decision.redirect_chain,
        structure_revision_id=structure_revision.pk,
        structure_revision_no=structure_revision.revision_no,
        structure_fingerprint=structure_revision.fingerprint,
    )


__all__ = [
    "DirectoryAssignmentError",
    "DirectoryAssignmentResult",
    "UNCLASSIFIED_DIRECTORY_KEY",
    "resolve_page_directory",
]
