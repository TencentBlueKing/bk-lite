"""Pure directory-routing contract for Wiki governance.

The concrete service introduced later resolves ORM rows into this immutable
snapshot.  Keeping the decision table pure makes the routing order and the
merged-key boundary executable before the directory models exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Sequence


class AssignmentMode(str, Enum):
    AUTO = "auto"
    MANUAL = "manual"


class DirectoryStatus(str, Enum):
    ACTIVE = "active"
    RETIRED = "retired"
    MERGED = "merged"
    ARCHIVED = "archived"


class DirectoryReferenceSource(str, Enum):
    LLM = "llm"
    NATIVE_IMPORT = "native_import"
    HISTORICAL_LINK = "historical_link"
    AUDIT_READ = "audit_read"


class DirectoryRouteSource(str, Enum):
    MANUAL = "manual"
    SUGGESTED_KEY = "suggested_key"
    REDIRECTED_KEY = "redirected_key"
    TYPE_DEFAULT = "type_default"
    CLASSIFICATION_ROOT = "classification_root"
    UNCLASSIFIED = "unclassified"


class RoutingTraceCode(str, Enum):
    MANUAL_SUGGESTION_IGNORED = "manual_suggestion_ignored"
    LOW_CONFIDENCE = "low_confidence"
    UNKNOWN_KEY = "unknown_key"
    FOREIGN_KNOWLEDGE_BASE = "foreign_knowledge_base"
    INACTIVE_KEY = "inactive_key"
    NON_RECEIVING_KEY = "non_receiving_key"
    OUT_OF_SCOPE_KEY = "out_of_scope_key"
    SCHEMA_MISMATCH = "schema_mismatch"
    LLM_REDIRECT_FORBIDDEN = "llm_redirect_forbidden"
    MERGED_REDIRECT_FOLLOWED = "merged_redirect_followed"
    TYPE_DEFAULT_OUT_OF_SCOPE = "type_default_out_of_scope"
    TYPE_DEFAULT_INVALID = "type_default_invalid"
    CLASSIFICATION_ROOT_UNAVAILABLE = "classification_root_unavailable"


class DirectoryRoutingInvariantError(ValueError):
    """The fixed structure snapshot cannot satisfy a routing invariant."""


class UnknownAssignmentMode(DirectoryRoutingInvariantError):
    pass


class UnknownDirectoryReferenceSource(DirectoryRoutingInvariantError):
    pass


class InvalidManualDirectory(DirectoryRoutingInvariantError):
    pass


class InvalidClassificationRoot(DirectoryRoutingInvariantError):
    pass


class AmbiguousTypeDefault(DirectoryRoutingInvariantError):
    pass


class InvalidUnclassifiedDirectory(DirectoryRoutingInvariantError):
    pass


class InvalidDirectoryRedirect(DirectoryRoutingInvariantError):
    pass


@dataclass(frozen=True)
class DirectorySnapshot:
    key: str
    knowledge_base_id: int
    status: DirectoryStatus
    accepts_pages: bool
    ancestor_keys: tuple[str, ...] = ()
    merged_into_key: str | None = None
    allowed_page_types: frozenset[str] | None = None
    is_unclassified: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "ancestor_keys", tuple(self.ancestor_keys))
        if self.allowed_page_types is not None:
            object.__setattr__(self, "allowed_page_types", frozenset(self.allowed_page_types))
        if not self.key:
            raise DirectoryRoutingInvariantError("directory key must not be empty")
        if not isinstance(self.status, DirectoryStatus):
            raise DirectoryRoutingInvariantError(f"unknown directory status: {self.status!r}")
        if len(set(self.ancestor_keys)) != len(self.ancestor_keys) or self.key in self.ancestor_keys:
            raise DirectoryRoutingInvariantError(f"invalid ancestry for directory {self.key!r}")


@dataclass(frozen=True)
class DirectoryRoutingDecision:
    directory_key: str
    assignment_mode: AssignmentMode
    source: DirectoryRouteSource
    trace: tuple[RoutingTraceCode, ...] = ()
    redirect_chain: tuple[str, ...] = ()


_REDIRECT_SOURCES = frozenset(
    {
        DirectoryReferenceSource.NATIVE_IMPORT,
        DirectoryReferenceSource.HISTORICAL_LINK,
        DirectoryReferenceSource.AUDIT_READ,
    }
)


def _assignment_mode(value: AssignmentMode | str) -> AssignmentMode:
    if isinstance(value, AssignmentMode):
        return value
    try:
        return AssignmentMode(value)
    except (TypeError, ValueError) as error:
        raise UnknownAssignmentMode(f"unknown assignment mode: {value!r}") from error


def _reference_source(value: DirectoryReferenceSource | str) -> DirectoryReferenceSource:
    if isinstance(value, DirectoryReferenceSource):
        return value
    try:
        return DirectoryReferenceSource(value)
    except (TypeError, ValueError) as error:
        raise UnknownDirectoryReferenceSource(f"unknown directory reference source: {value!r}") from error


def _allows_page_type(directory: DirectorySnapshot, page_type: str) -> bool:
    return directory.allowed_page_types is None or page_type in directory.allowed_page_types


def _is_in_scope(directory: DirectorySnapshot, classification_root_key: str | None) -> bool:
    return classification_root_key is None or directory.key == classification_root_key or classification_root_key in directory.ancestor_keys


def _append_trace(trace: list[RoutingTraceCode], code: RoutingTraceCode) -> None:
    if code not in trace:
        trace.append(code)


def _suggestion_rejection(
    directory: DirectorySnapshot,
    *,
    knowledge_base_id: int,
    page_type: str,
    classification_root_key: str | None,
    schema_mismatch: bool,
) -> RoutingTraceCode | None:
    if directory.knowledge_base_id != knowledge_base_id:
        return RoutingTraceCode.FOREIGN_KNOWLEDGE_BASE
    if directory.status is not DirectoryStatus.ACTIVE:
        return RoutingTraceCode.INACTIVE_KEY
    if not directory.accepts_pages:
        return RoutingTraceCode.NON_RECEIVING_KEY
    if schema_mismatch or not _allows_page_type(directory, page_type):
        return RoutingTraceCode.SCHEMA_MISMATCH
    if not _is_in_scope(directory, classification_root_key):
        return RoutingTraceCode.OUT_OF_SCOPE_KEY
    return None


def _follow_redirect(
    start: DirectorySnapshot,
    directories: Mapping[str, DirectorySnapshot],
    *,
    knowledge_base_id: int,
) -> tuple[DirectorySnapshot, tuple[str, ...]]:
    current = start
    visited: set[str] = set()
    chain: list[str] = []
    while current.status is DirectoryStatus.MERGED:
        if current.key in visited:
            raise InvalidDirectoryRedirect(f"cyclic merged redirect at {current.key!r}")
        visited.add(current.key)
        chain.append(current.key)
        if not current.merged_into_key:
            raise InvalidDirectoryRedirect(f"merged directory {current.key!r} has no redirect target")
        target = directories.get(current.merged_into_key)
        if target is None:
            raise InvalidDirectoryRedirect(f"merged directory {current.key!r} points to missing {current.merged_into_key!r}")
        if target.knowledge_base_id != knowledge_base_id:
            raise InvalidDirectoryRedirect(f"merged directory {current.key!r} redirects across knowledge bases")
        current = target
    if current.key in visited:
        raise InvalidDirectoryRedirect(f"cyclic merged redirect at {current.key!r}")
    if current.status is not DirectoryStatus.ACTIVE:
        raise InvalidDirectoryRedirect(f"merged redirect target {current.key!r} is not active")
    if not current.accepts_pages:
        raise InvalidDirectoryRedirect(f"merged redirect target {current.key!r} does not accept pages")
    chain.append(current.key)
    return current, tuple(chain)


def _validate_manual(
    directory: DirectorySnapshot | None,
    *,
    knowledge_base_id: int,
) -> DirectorySnapshot:
    if (
        directory is None
        or directory.knowledge_base_id != knowledge_base_id
        or directory.status is not DirectoryStatus.ACTIVE
        or not directory.accepts_pages
    ):
        raise InvalidManualDirectory("manual assignment must retain an active receiving directory in the same knowledge base")
    return directory


def _validate_root(
    directory: DirectorySnapshot | None,
    *,
    knowledge_base_id: int,
) -> DirectorySnapshot:
    if directory is None or directory.knowledge_base_id != knowledge_base_id or directory.status is not DirectoryStatus.ACTIVE:
        raise InvalidClassificationRoot("classification root must be active and belong to the knowledge base")
    return directory


def _validate_unclassified(
    directory: DirectorySnapshot | None,
    *,
    knowledge_base_id: int,
    page_type: str,
) -> DirectorySnapshot:
    if (
        directory is None
        or directory.knowledge_base_id != knowledge_base_id
        or directory.status is not DirectoryStatus.ACTIVE
        or not directory.accepts_pages
        or not directory.is_unclassified
        or not _allows_page_type(directory, page_type)
    ):
        raise InvalidUnclassifiedDirectory("system unclassified directory is missing or unusable")
    return directory


def _manual_trace(
    *,
    manual: DirectorySnapshot,
    directories: Mapping[str, DirectorySnapshot],
    knowledge_base_id: int,
    page_type: str,
    suggested_key: str | None,
    source: DirectoryReferenceSource,
    classification_root_key: str | None,
    schema_mismatch: bool,
    low_confidence: bool,
) -> tuple[RoutingTraceCode, ...]:
    trace: list[RoutingTraceCode] = []
    if low_confidence:
        _append_trace(trace, RoutingTraceCode.LOW_CONFIDENCE)
    if schema_mismatch:
        _append_trace(trace, RoutingTraceCode.SCHEMA_MISMATCH)
    if suggested_key is None:
        return tuple(trace)

    if suggested_key != manual.key:
        _append_trace(trace, RoutingTraceCode.MANUAL_SUGGESTION_IGNORED)
    suggested = directories.get(suggested_key)
    if suggested is None:
        _append_trace(trace, RoutingTraceCode.UNKNOWN_KEY)
    elif suggested.knowledge_base_id != knowledge_base_id:
        _append_trace(trace, RoutingTraceCode.FOREIGN_KNOWLEDGE_BASE)
    elif suggested.status is DirectoryStatus.MERGED and source is DirectoryReferenceSource.LLM:
        _append_trace(trace, RoutingTraceCode.LLM_REDIRECT_FORBIDDEN)
    else:
        rejection = _suggestion_rejection(
            suggested,
            knowledge_base_id=knowledge_base_id,
            page_type=page_type,
            classification_root_key=classification_root_key,
            schema_mismatch=schema_mismatch,
        )
        if rejection is not None:
            _append_trace(trace, rejection)
    return tuple(trace)


def route_directory(
    *,
    knowledge_base_id: int,
    page_type: str,
    revision_page_types: frozenset[str],
    assignment_mode: AssignmentMode | str,
    directories: Mapping[str, DirectorySnapshot],
    current_directory_key: str | None,
    suggested_key: str | None,
    suggestion_source: DirectoryReferenceSource | str,
    classification_root_key: str | None,
    type_default_keys: Sequence[str],
    unclassified_key: str,
    suggestion_schema_mismatch: bool,
    low_confidence: bool,
) -> DirectoryRoutingDecision:
    """Resolve a page against one fixed structure revision.

    Invalid automatic suggestions are traceable fallbacks.  Broken manual,
    root, default-uniqueness, redirect, and system-directory invariants fail
    closed because silently changing those would alter governance truth.
    """

    mode = _assignment_mode(assignment_mode)
    source = _reference_source(suggestion_source)
    page_type_in_revision = (
        isinstance(revision_page_types, frozenset) and isinstance(page_type, str) and bool(page_type.strip()) and page_type in revision_page_types
    )
    if mode is AssignmentMode.MANUAL:
        manual = _validate_manual(
            directories.get(current_directory_key) if current_directory_key else None,
            knowledge_base_id=knowledge_base_id,
        )
        return DirectoryRoutingDecision(
            directory_key=manual.key,
            assignment_mode=AssignmentMode.MANUAL,
            source=DirectoryRouteSource.MANUAL,
            trace=_manual_trace(
                manual=manual,
                directories=directories,
                knowledge_base_id=knowledge_base_id,
                page_type=page_type,
                suggested_key=suggested_key,
                source=source,
                classification_root_key=classification_root_key,
                schema_mismatch=suggestion_schema_mismatch or not page_type_in_revision,
                low_confidence=low_confidence,
            ),
        )
    root = None
    if classification_root_key is not None:
        root = _validate_root(
            directories.get(classification_root_key),
            knowledge_base_id=knowledge_base_id,
        )

    trace: list[RoutingTraceCode] = []
    if low_confidence:
        _append_trace(trace, RoutingTraceCode.LOW_CONFIDENCE)
    if suggestion_schema_mismatch or not page_type_in_revision:
        _append_trace(trace, RoutingTraceCode.SCHEMA_MISMATCH)
    redirect_chain: tuple[str, ...] = ()

    if suggested_key is not None:
        suggested = directories.get(suggested_key)
        if suggested is None:
            _append_trace(trace, RoutingTraceCode.UNKNOWN_KEY)
        else:
            route_source = DirectoryRouteSource.SUGGESTED_KEY
            if suggested.knowledge_base_id != knowledge_base_id:
                _append_trace(trace, RoutingTraceCode.FOREIGN_KNOWLEDGE_BASE)
                suggested = None
            elif suggested.status is DirectoryStatus.MERGED:
                if source is DirectoryReferenceSource.LLM:
                    _append_trace(trace, RoutingTraceCode.LLM_REDIRECT_FORBIDDEN)
                    suggested = None
                elif source in _REDIRECT_SOURCES:
                    suggested, redirect_chain = _follow_redirect(
                        suggested,
                        directories,
                        knowledge_base_id=knowledge_base_id,
                    )
                    route_source = DirectoryRouteSource.REDIRECTED_KEY
                    _append_trace(trace, RoutingTraceCode.MERGED_REDIRECT_FOLLOWED)
            if suggested is not None:
                rejection = _suggestion_rejection(
                    suggested,
                    knowledge_base_id=knowledge_base_id,
                    page_type=page_type,
                    classification_root_key=classification_root_key,
                    schema_mismatch=suggestion_schema_mismatch or not page_type_in_revision,
                )
                if rejection is None:
                    return DirectoryRoutingDecision(
                        directory_key=suggested.key,
                        assignment_mode=AssignmentMode.AUTO,
                        source=route_source,
                        trace=tuple(trace),
                        redirect_chain=redirect_chain,
                    )
                _append_trace(trace, rejection)

    valid_defaults: list[DirectorySnapshot] = []
    seen_default_keys: set[str] = set()
    for key in type_default_keys if page_type_in_revision else ():
        if key in seen_default_keys:
            continue
        seen_default_keys.add(key)
        default = directories.get(key)
        if default is None:
            _append_trace(trace, RoutingTraceCode.TYPE_DEFAULT_INVALID)
            continue
        if not _is_in_scope(default, classification_root_key):
            _append_trace(trace, RoutingTraceCode.TYPE_DEFAULT_OUT_OF_SCOPE)
            continue
        if (
            default.knowledge_base_id != knowledge_base_id
            or default.status is not DirectoryStatus.ACTIVE
            or not default.accepts_pages
            or not _allows_page_type(default, page_type)
        ):
            _append_trace(trace, RoutingTraceCode.TYPE_DEFAULT_INVALID)
            continue
        valid_defaults.append(default)

    if len(valid_defaults) > 1:
        raise AmbiguousTypeDefault(
            f"page type {page_type!r} has multiple defaults in the effective scope: " f"{[directory.key for directory in valid_defaults]!r}"
        )
    if valid_defaults:
        return DirectoryRoutingDecision(
            directory_key=valid_defaults[0].key,
            assignment_mode=AssignmentMode.AUTO,
            source=DirectoryRouteSource.TYPE_DEFAULT,
            trace=tuple(trace),
            redirect_chain=redirect_chain,
        )

    if root is not None:
        if page_type_in_revision and root.accepts_pages and _allows_page_type(root, page_type):
            return DirectoryRoutingDecision(
                directory_key=root.key,
                assignment_mode=AssignmentMode.AUTO,
                source=DirectoryRouteSource.CLASSIFICATION_ROOT,
                trace=tuple(trace),
                redirect_chain=redirect_chain,
            )
        _append_trace(trace, RoutingTraceCode.CLASSIFICATION_ROOT_UNAVAILABLE)

    unclassified = _validate_unclassified(
        directories.get(unclassified_key),
        knowledge_base_id=knowledge_base_id,
        page_type=page_type,
    )
    return DirectoryRoutingDecision(
        directory_key=unclassified.key,
        assignment_mode=AssignmentMode.AUTO,
        source=DirectoryRouteSource.UNCLASSIFIED,
        trace=tuple(trace),
        redirect_chain=redirect_chain,
    )


__all__ = [
    "AmbiguousTypeDefault",
    "AssignmentMode",
    "DirectoryReferenceSource",
    "DirectoryRouteSource",
    "DirectoryRoutingDecision",
    "DirectoryRoutingInvariantError",
    "DirectorySnapshot",
    "DirectoryStatus",
    "InvalidClassificationRoot",
    "InvalidDirectoryRedirect",
    "InvalidManualDirectory",
    "InvalidUnclassifiedDirectory",
    "RoutingTraceCode",
    "UnknownAssignmentMode",
    "UnknownDirectoryReferenceSource",
    "route_directory",
]
