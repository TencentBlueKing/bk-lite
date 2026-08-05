"""Wiki generation CAS, staging cleanup, and rollback pure contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _positive_id(value: int, field_name: str) -> None:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")


def _optional_positive_id(value: int | None, field_name: str) -> None:
    if value is not None:
        _positive_id(value, field_name)


def _positive_version(value: int, field_name: str) -> None:
    _positive_id(value, field_name)


def _non_negative(value: int, field_name: str) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")


def _fingerprint(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 hex digest")


class GenerationStatus(str, Enum):
    PREPARING = "preparing"
    READY = "ready"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ActivationOutcome(str, Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    FAILED = "failed"


class ActivationCode(str, Enum):
    ACTIVATION_ALLOWED = "activation_allowed"
    CANDIDATE_KNOWLEDGE_BASE_MISMATCH = "candidate_knowledge_base_mismatch"
    CANDIDATE_NOT_READY = "candidate_not_ready"
    CANDIDATE_INCOMPLETE = "candidate_incomplete"
    CANDIDATE_BASE_MISMATCH = "candidate_base_generation_mismatch"
    CANDIDATE_BASE_CYCLE = "candidate_base_generation_cycle"
    CANDIDATE_STRUCTURE_MISMATCH = "candidate_structure_mismatch"
    CANDIDATE_ALREADY_ACTIVE = "candidate_already_active"
    BASE_GENERATION_CONFLICT = "base_generation_conflict"
    STRUCTURE_REVISION_CONFLICT = "structure_revision_conflict"
    STRUCTURE_VERSION_CONFLICT = "structure_version_conflict"
    STRUCTURE_FINGERPRINT_MISMATCH = "structure_fingerprint_mismatch"


@dataclass(frozen=True)
class ActivationFacts:
    """Facts read before the bounded KB-lock activation transaction.

    ``None`` is accepted for all three generation base pointers only for the
    internal first/baseline generation. Public APIs may keep requiring IDs.
    """

    knowledge_base_id: int
    candidate_generation_id: int
    candidate_knowledge_base_id: int
    candidate_status: GenerationStatus | str
    candidate_base_generation_id: int | None
    candidate_structure_revision_id: int
    candidate_structure_version: int
    candidate_structure_fingerprint: str
    requested_base_generation_id: int | None
    expected_structure_revision_id: int
    expected_structure_version: int
    active_generation_id: int | None
    active_structure_revision_id: int
    active_structure_version: int
    active_structure_fingerprint: str
    candidate_complete: bool = True

    def __post_init__(self) -> None:
        for field_name in (
            "knowledge_base_id",
            "candidate_generation_id",
            "candidate_knowledge_base_id",
            "candidate_structure_revision_id",
            "expected_structure_revision_id",
            "active_structure_revision_id",
        ):
            _positive_id(getattr(self, field_name), field_name)
        for field_name in (
            "candidate_structure_version",
            "expected_structure_version",
            "active_structure_version",
        ):
            _positive_version(getattr(self, field_name), field_name)
        for field_name in (
            "candidate_base_generation_id",
            "requested_base_generation_id",
            "active_generation_id",
        ):
            _optional_positive_id(getattr(self, field_name), field_name)
        try:
            status = GenerationStatus(self.candidate_status)
        except (TypeError, ValueError) as error:
            raise ValueError(f"unknown candidate status: {self.candidate_status!r}") from error
        object.__setattr__(self, "candidate_status", status)
        _fingerprint(self.candidate_structure_fingerprint, "candidate_structure_fingerprint")
        _fingerprint(self.active_structure_fingerprint, "active_structure_fingerprint")
        if type(self.candidate_complete) is not bool:
            raise ValueError("candidate_complete must be a boolean")


@dataclass(frozen=True)
class ActivationDecision:
    outcome: ActivationOutcome
    code: ActivationCode
    retryable: bool
    may_switch_active_pointer: bool


def _activation_decision(
    outcome: ActivationOutcome,
    code: ActivationCode,
) -> ActivationDecision:
    return ActivationDecision(
        outcome=outcome,
        code=code,
        retryable=outcome is ActivationOutcome.SUPERSEDED,
        may_switch_active_pointer=outcome is ActivationOutcome.ACTIVE,
    )


def decide_activation(facts: ActivationFacts) -> ActivationDecision:
    """Decide activation without mutating candidate or active snapshots.

    Candidate defects are terminal ``failed`` outcomes. Pointer drift is a
    retryable ``superseded`` outcome. Callers MUST re-read these facts while
    holding the knowledge-base row lock before applying the returned switch.
    """

    if facts.candidate_knowledge_base_id != facts.knowledge_base_id:
        return _activation_decision(
            ActivationOutcome.FAILED,
            ActivationCode.CANDIDATE_KNOWLEDGE_BASE_MISMATCH,
        )
    if facts.candidate_status is not GenerationStatus.READY:
        return _activation_decision(ActivationOutcome.FAILED, ActivationCode.CANDIDATE_NOT_READY)
    if not facts.candidate_complete:
        return _activation_decision(ActivationOutcome.FAILED, ActivationCode.CANDIDATE_INCOMPLETE)
    if facts.candidate_generation_id == facts.candidate_base_generation_id:
        return _activation_decision(ActivationOutcome.FAILED, ActivationCode.CANDIDATE_BASE_CYCLE)
    if facts.candidate_base_generation_id != facts.requested_base_generation_id:
        return _activation_decision(ActivationOutcome.FAILED, ActivationCode.CANDIDATE_BASE_MISMATCH)
    if (
        facts.candidate_structure_revision_id != facts.expected_structure_revision_id
        or facts.candidate_structure_version != facts.expected_structure_version
    ):
        return _activation_decision(ActivationOutcome.FAILED, ActivationCode.CANDIDATE_STRUCTURE_MISMATCH)
    if facts.candidate_generation_id == facts.active_generation_id:
        return _activation_decision(ActivationOutcome.FAILED, ActivationCode.CANDIDATE_ALREADY_ACTIVE)
    if facts.active_generation_id != facts.requested_base_generation_id:
        return _activation_decision(
            ActivationOutcome.SUPERSEDED,
            ActivationCode.BASE_GENERATION_CONFLICT,
        )
    if facts.active_structure_revision_id != facts.expected_structure_revision_id:
        return _activation_decision(
            ActivationOutcome.SUPERSEDED,
            ActivationCode.STRUCTURE_REVISION_CONFLICT,
        )
    if facts.active_structure_version != facts.expected_structure_version:
        return _activation_decision(
            ActivationOutcome.SUPERSEDED,
            ActivationCode.STRUCTURE_VERSION_CONFLICT,
        )
    if facts.candidate_structure_fingerprint != facts.active_structure_fingerprint:
        return _activation_decision(
            ActivationOutcome.FAILED,
            ActivationCode.STRUCTURE_FINGERPRINT_MISMATCH,
        )
    return _activation_decision(ActivationOutcome.ACTIVE, ActivationCode.ACTIVATION_ALLOWED)


class StagingCleanupDisposition(str, Enum):
    KEEP_NOT_OWNED = "keep_not_owned"
    KEEP_REFERENCED = "keep_referenced"
    DELETE_VERSION_ONLY = "delete_version_only"
    DELETE_VERSION_AND_PAGE_IDENTITY = "delete_version_and_page_identity"


@dataclass(frozen=True)
class StagingVersionCleanupFacts:
    """Reference counts after this generation's owned links are detached."""

    version_id: int
    cleanup_generation_id: int
    created_in_generation_id: int | None
    owned_generation_links_detached: bool
    external_generation_member_references: int = 0
    current_version_references: int = 0
    candidate_references: int = 0
    auxiliary_references: int = 0
    page_is_pure_staging_identity: bool = False
    remaining_page_versions: int = 0
    remaining_page_generation_memberships: int = 0
    remaining_page_current_version_references: int = 0
    remaining_page_candidate_references: int = 0
    remaining_page_other_references: int = 0

    def __post_init__(self) -> None:
        _positive_id(self.version_id, "version_id")
        _positive_id(self.cleanup_generation_id, "cleanup_generation_id")
        _optional_positive_id(self.created_in_generation_id, "created_in_generation_id")
        if type(self.owned_generation_links_detached) is not bool:
            raise ValueError("owned_generation_links_detached must be a boolean")
        if type(self.page_is_pure_staging_identity) is not bool:
            raise ValueError("page_is_pure_staging_identity must be a boolean")
        for field_name in (
            "external_generation_member_references",
            "current_version_references",
            "candidate_references",
            "auxiliary_references",
            "remaining_page_versions",
            "remaining_page_generation_memberships",
            "remaining_page_current_version_references",
            "remaining_page_candidate_references",
            "remaining_page_other_references",
        ):
            _non_negative(getattr(self, field_name), field_name)


@dataclass(frozen=True)
class StagingVersionCleanupDecision:
    disposition: StagingCleanupDisposition
    delete_version: bool
    delete_page_identity: bool
    version_blocking_references: tuple[str, ...]
    page_identity_blocking_references: tuple[str, ...]


def decide_staging_version_cleanup(
    facts: StagingVersionCleanupFacts,
) -> StagingVersionCleanupDecision:
    """Fail closed unless a version is both owned and completely unreferenced."""

    if facts.created_in_generation_id != facts.cleanup_generation_id:
        return StagingVersionCleanupDecision(
            disposition=StagingCleanupDisposition.KEEP_NOT_OWNED,
            delete_version=False,
            delete_page_identity=False,
            version_blocking_references=("version_not_owned_by_cleanup_generation",),
            page_identity_blocking_references=(),
        )

    blockers = []
    if not facts.owned_generation_links_detached:
        blockers.append("owned_generation_links_not_detached")
    for field_name in (
        "external_generation_member_references",
        "current_version_references",
        "candidate_references",
        "auxiliary_references",
    ):
        if getattr(facts, field_name):
            blockers.append(field_name)
    if blockers:
        return StagingVersionCleanupDecision(
            disposition=StagingCleanupDisposition.KEEP_REFERENCED,
            delete_version=False,
            delete_page_identity=False,
            version_blocking_references=tuple(blockers),
            page_identity_blocking_references=(),
        )

    page_blockers = []
    for field_name in (
        "remaining_page_versions",
        "remaining_page_generation_memberships",
        "remaining_page_current_version_references",
        "remaining_page_candidate_references",
        "remaining_page_other_references",
    ):
        if getattr(facts, field_name):
            page_blockers.append(field_name)
    delete_page_identity = facts.page_is_pure_staging_identity and not page_blockers
    if not facts.page_is_pure_staging_identity:
        page_blockers.append("page_not_pure_staging_identity")
    return StagingVersionCleanupDecision(
        disposition=(
            StagingCleanupDisposition.DELETE_VERSION_AND_PAGE_IDENTITY if delete_page_identity else StagingCleanupDisposition.DELETE_VERSION_ONLY
        ),
        delete_version=True,
        delete_page_identity=delete_page_identity,
        version_blocking_references=(),
        page_identity_blocking_references=tuple(page_blockers),
    )


class RollbackDirectoryStatus(str, Enum):
    ACTIVE = "active"
    RETIRED = "retired"
    MERGED = "merged"
    ARCHIVED = "archived"


class RollbackCompatibility(str, Enum):
    COMPATIBLE = "compatible"
    REQUIRES_STRUCTURE_RESTORE = "requires_structure_restore"
    BLOCKED = "blocked"


class RollbackIssueCode(str, Enum):
    TARGET_KNOWLEDGE_BASE_MISMATCH = "target_knowledge_base_mismatch"
    TARGET_GENERATION_NOT_RETAINED = "target_generation_not_retained"
    TARGET_GENERATION_NOT_SUCCESSFUL = "target_generation_not_successful"
    TARGET_STRUCTURE_DUPLICATE_KEY = "target_structure_duplicate_key"
    CURRENT_STRUCTURE_DUPLICATE_KEY = "current_structure_duplicate_key"
    TARGET_DIRECTORY_MISSING = "target_directory_missing"
    TARGET_DIRECTORY_KNOWLEDGE_BASE_MISMATCH = "target_directory_knowledge_base_mismatch"
    TARGET_DIRECTORY_INACTIVE = "target_directory_inactive"
    TARGET_DIRECTORY_REJECTS_PAGES = "target_directory_rejects_pages"
    CURRENT_DIRECTORY_MISSING = "current_directory_missing"
    CURRENT_DIRECTORY_KNOWLEDGE_BASE_MISMATCH = "current_directory_knowledge_base_mismatch"
    CURRENT_DIRECTORY_INACTIVE = "current_directory_inactive"
    CURRENT_DIRECTORY_REJECTS_PAGES = "current_directory_rejects_pages"
    DIRECTORY_MOVED = "directory_moved"
    DIRECTORY_DISPLAY_CHANGED = "directory_display_changed"


@dataclass(frozen=True)
class RollbackDirectorySnapshot:
    knowledge_base_id: int
    key: str
    status: RollbackDirectoryStatus | str
    accepts_pages: bool
    key_path: tuple[str, ...]
    display_path: tuple[str, ...]

    def __post_init__(self) -> None:
        _positive_id(self.knowledge_base_id, "directory.knowledge_base_id")
        if not isinstance(self.key, str) or not self.key or self.key != self.key.strip():
            raise ValueError("directory.key must be a non-blank canonical key")
        try:
            status = RollbackDirectoryStatus(self.status)
        except (TypeError, ValueError) as error:
            raise ValueError(f"unknown directory status: {self.status!r}") from error
        object.__setattr__(self, "status", status)
        if type(self.accepts_pages) is not bool:
            raise ValueError("directory.accepts_pages must be a boolean")
        if not isinstance(self.key_path, tuple) or not isinstance(self.display_path, tuple):
            raise ValueError("directory key/display paths must be immutable tuples")
        if not self.key_path or self.key_path[-1] != self.key:
            raise ValueError("directory.key_path must end with directory.key")
        if len(self.key_path) != len(self.display_path):
            raise ValueError("directory key/display paths must have the same depth")
        if any(not isinstance(part, str) or not part.strip() for part in self.key_path):
            raise ValueError("directory.key_path must contain non-blank strings")
        if any(not isinstance(part, str) or not part.strip() for part in self.display_path):
            raise ValueError("directory.display_path must contain non-blank strings")


@dataclass(frozen=True)
class RollbackStructureFacts:
    knowledge_base_id: int
    target_generation_id: int
    target_generation_knowledge_base_id: int
    target_generation_status: GenerationStatus | str
    target_generation_retained: bool
    target_structure_revision_id: int
    target_structure_version: int
    current_structure_revision_id: int
    current_structure_version: int
    referenced_directory_keys: tuple[str, ...]
    target_directories: tuple[RollbackDirectorySnapshot, ...]
    current_directories: tuple[RollbackDirectorySnapshot, ...]

    def __post_init__(self) -> None:
        for field_name in (
            "knowledge_base_id",
            "target_generation_id",
            "target_generation_knowledge_base_id",
            "target_structure_revision_id",
            "current_structure_revision_id",
        ):
            _positive_id(getattr(self, field_name), field_name)
        _positive_version(self.target_structure_version, "target_structure_version")
        _positive_version(self.current_structure_version, "current_structure_version")
        try:
            status = GenerationStatus(self.target_generation_status)
        except (TypeError, ValueError) as error:
            raise ValueError(f"unknown target generation status: {self.target_generation_status!r}") from error
        object.__setattr__(self, "target_generation_status", status)
        if type(self.target_generation_retained) is not bool:
            raise ValueError("target_generation_retained must be a boolean")
        if (
            not isinstance(self.referenced_directory_keys, tuple)
            or not isinstance(self.target_directories, tuple)
            or not isinstance(self.current_directories, tuple)
        ):
            raise ValueError("rollback structure collections must be immutable tuples")
        if any(not isinstance(key, str) or not key.strip() for key in self.referenced_directory_keys):
            raise ValueError("referenced_directory_keys must contain non-blank strings")
        if any(not isinstance(item, RollbackDirectorySnapshot) for item in self.target_directories):
            raise ValueError("target_directories must contain RollbackDirectorySnapshot values")
        if any(not isinstance(item, RollbackDirectorySnapshot) for item in self.current_directories):
            raise ValueError("current_directories must contain RollbackDirectorySnapshot values")


@dataclass(frozen=True)
class RollbackStructureIssue:
    code: RollbackIssueCode
    directory_key: str
    target_path: tuple[str, ...]
    current_path: tuple[str, ...]
    restorable: bool

    def __post_init__(self) -> None:
        try:
            code = RollbackIssueCode(self.code)
        except (TypeError, ValueError) as error:
            raise ValueError(f"unknown rollback structure issue: {self.code!r}") from error
        object.__setattr__(self, "code", code)
        if not isinstance(self.directory_key, str):
            raise ValueError("directory_key must be a string")
        if not isinstance(self.target_path, tuple) or not isinstance(self.current_path, tuple):
            raise ValueError("rollback issue paths must be immutable tuples")
        if type(self.restorable) is not bool:
            raise ValueError("restorable must be a boolean")


@dataclass(frozen=True)
class RollbackCompatibilityDecision:
    outcome: RollbackCompatibility
    knowledge_base_id: int
    target_generation_id: int
    target_structure_revision_id: int
    target_structure_version: int
    current_structure_revision_id: int
    current_structure_version: int
    issues: tuple[RollbackStructureIssue, ...]

    def __post_init__(self) -> None:
        try:
            outcome = RollbackCompatibility(self.outcome)
        except (TypeError, ValueError) as error:
            raise ValueError(f"unknown rollback compatibility outcome: {self.outcome!r}") from error
        object.__setattr__(self, "outcome", outcome)
        for field_name in (
            "knowledge_base_id",
            "target_generation_id",
            "target_structure_revision_id",
            "current_structure_revision_id",
        ):
            _positive_id(getattr(self, field_name), field_name)
        _positive_version(self.target_structure_version, "target_structure_version")
        _positive_version(self.current_structure_version, "current_structure_version")
        if not isinstance(self.issues, tuple) or any(not isinstance(issue, RollbackStructureIssue) for issue in self.issues):
            raise ValueError("issues must be an immutable tuple of RollbackStructureIssue values")

    @property
    def requires_structure_restore(self) -> bool:
        return self.outcome is RollbackCompatibility.REQUIRES_STRUCTURE_RESTORE


def _structure_index(
    snapshots: tuple[RollbackDirectorySnapshot, ...],
    duplicate_code: RollbackIssueCode,
) -> tuple[dict[str, RollbackDirectorySnapshot], list[RollbackStructureIssue]]:
    index = {}
    issues = []
    for snapshot in snapshots:
        if snapshot.key in index:
            issues.append(
                RollbackStructureIssue(
                    code=duplicate_code,
                    directory_key=snapshot.key,
                    target_path=(),
                    current_path=(),
                    restorable=False,
                )
            )
        else:
            index[snapshot.key] = snapshot
    return index, issues


def _rollback_issue(
    code: RollbackIssueCode,
    key: str = "",
    *,
    target: RollbackDirectorySnapshot | None = None,
    current: RollbackDirectorySnapshot | None = None,
    restorable: bool,
) -> RollbackStructureIssue:
    return RollbackStructureIssue(
        code=code,
        directory_key=key,
        target_path=target.display_path if target else (),
        current_path=current.display_path if current else (),
        restorable=restorable,
    )


def compare_rollback_structure(
    facts: RollbackStructureFacts,
) -> RollbackCompatibilityDecision:
    """Compare only directories referenced by the retained target generation.

    Extra current directories are compatible. Referenced nodes must preserve
    stable key, active/accepting state, ancestor-key path, and display path.
    """

    target_index, target_issues = _structure_index(
        facts.target_directories,
        RollbackIssueCode.TARGET_STRUCTURE_DUPLICATE_KEY,
    )
    current_index, current_issues = _structure_index(
        facts.current_directories,
        RollbackIssueCode.CURRENT_STRUCTURE_DUPLICATE_KEY,
    )
    issues = [*target_issues, *current_issues]
    for key in sorted(target_index):
        snapshot = target_index[key]
        if snapshot.knowledge_base_id != facts.knowledge_base_id:
            issues.append(
                _rollback_issue(
                    RollbackIssueCode.TARGET_DIRECTORY_KNOWLEDGE_BASE_MISMATCH,
                    key,
                    target=snapshot,
                    restorable=False,
                )
            )
    for key in sorted(current_index):
        snapshot = current_index[key]
        if snapshot.knowledge_base_id != facts.knowledge_base_id:
            issues.append(
                _rollback_issue(
                    RollbackIssueCode.CURRENT_DIRECTORY_KNOWLEDGE_BASE_MISMATCH,
                    key,
                    current=snapshot,
                    restorable=False,
                )
            )
    if facts.target_generation_knowledge_base_id != facts.knowledge_base_id:
        issues.append(
            _rollback_issue(
                RollbackIssueCode.TARGET_KNOWLEDGE_BASE_MISMATCH,
                restorable=False,
            )
        )
    if not facts.target_generation_retained:
        issues.append(
            _rollback_issue(
                RollbackIssueCode.TARGET_GENERATION_NOT_RETAINED,
                restorable=False,
            )
        )
    if facts.target_generation_status not in (GenerationStatus.ACTIVE, GenerationStatus.SUPERSEDED):
        issues.append(
            _rollback_issue(
                RollbackIssueCode.TARGET_GENERATION_NOT_SUCCESSFUL,
                restorable=False,
            )
        )

    for key in sorted(set(facts.referenced_directory_keys)):
        target = target_index.get(key)
        current = current_index.get(key)
        if target is None:
            issues.append(
                _rollback_issue(
                    RollbackIssueCode.TARGET_DIRECTORY_MISSING,
                    key,
                    restorable=False,
                )
            )
            continue

        if target.status is not RollbackDirectoryStatus.ACTIVE:
            issues.append(
                _rollback_issue(
                    RollbackIssueCode.TARGET_DIRECTORY_INACTIVE,
                    key,
                    target=target,
                    restorable=False,
                )
            )
            continue
        if not target.accepts_pages:
            issues.append(
                _rollback_issue(
                    RollbackIssueCode.TARGET_DIRECTORY_REJECTS_PAGES,
                    key,
                    target=target,
                    restorable=False,
                )
            )
            continue
        if current is None:
            issues.append(
                _rollback_issue(
                    RollbackIssueCode.CURRENT_DIRECTORY_MISSING,
                    key,
                    target=target,
                    restorable=True,
                )
            )
            continue

        if current.status is not RollbackDirectoryStatus.ACTIVE:
            issues.append(
                _rollback_issue(
                    RollbackIssueCode.CURRENT_DIRECTORY_INACTIVE,
                    key,
                    target=target,
                    current=current,
                    restorable=True,
                )
            )
            continue
        if not current.accepts_pages:
            issues.append(
                _rollback_issue(
                    RollbackIssueCode.CURRENT_DIRECTORY_REJECTS_PAGES,
                    key,
                    target=target,
                    current=current,
                    restorable=True,
                )
            )
            continue
        if current.key_path != target.key_path:
            issues.append(
                _rollback_issue(
                    RollbackIssueCode.DIRECTORY_MOVED,
                    key,
                    target=target,
                    current=current,
                    restorable=True,
                )
            )
            continue
        if current.display_path != target.display_path:
            issues.append(
                _rollback_issue(
                    RollbackIssueCode.DIRECTORY_DISPLAY_CHANGED,
                    key,
                    target=target,
                    current=current,
                    restorable=True,
                )
            )

    if any(not issue.restorable for issue in issues):
        outcome = RollbackCompatibility.BLOCKED
    elif issues:
        outcome = RollbackCompatibility.REQUIRES_STRUCTURE_RESTORE
    else:
        outcome = RollbackCompatibility.COMPATIBLE
    return RollbackCompatibilityDecision(
        outcome=outcome,
        knowledge_base_id=facts.knowledge_base_id,
        target_generation_id=facts.target_generation_id,
        target_structure_revision_id=facts.target_structure_revision_id,
        target_structure_version=facts.target_structure_version,
        current_structure_revision_id=facts.current_structure_revision_id,
        current_structure_version=facts.current_structure_version,
        issues=tuple(issues),
    )


class RollbackExecutionOutcome(str, Enum):
    EXECUTE = "execute"
    CONFLICT = "conflict"
    CONFIRMATION_REQUIRED = "confirmation_required"
    BLOCKED = "blocked"


class RollbackExecutionCode(str, Enum):
    ROLLBACK_ALLOWED = "rollback_allowed"
    KNOWLEDGE_BASE_MISMATCH = "knowledge_base_mismatch"
    BASE_GENERATION_CONFLICT = "base_generation_conflict"
    STRUCTURE_VERSION_CONFLICT = "structure_version_conflict"
    TARGET_IS_ACTIVE_GENERATION = "target_is_active_generation"
    TARGET_GENERATION_MISMATCH = "target_generation_mismatch"
    STRUCTURE_RESTORE_CONFIRMATION_REQUIRED = "structure_restore_confirmation_required"
    STRUCTURE_ROLLBACK_BLOCKED = "structure_rollback_blocked"


@dataclass(frozen=True)
class RollbackExecuteFacts:
    knowledge_base_id: int
    target_generation_id: int
    requested_base_generation_id: int
    active_generation_id: int
    requested_structure_version: int
    active_structure_version: int
    confirm_structure_restore: bool
    compatibility: RollbackCompatibilityDecision

    def __post_init__(self) -> None:
        for field_name in (
            "knowledge_base_id",
            "target_generation_id",
            "requested_base_generation_id",
            "active_generation_id",
        ):
            _positive_id(getattr(self, field_name), field_name)
        _positive_version(self.requested_structure_version, "requested_structure_version")
        _positive_version(self.active_structure_version, "active_structure_version")
        if type(self.confirm_structure_restore) is not bool:
            raise ValueError("confirm_structure_restore must be a boolean")
        if not isinstance(self.compatibility, RollbackCompatibilityDecision):
            raise ValueError("compatibility must be a RollbackCompatibilityDecision")


@dataclass(frozen=True)
class RollbackExecutionDecision:
    outcome: RollbackExecutionOutcome
    code: RollbackExecutionCode
    retryable: bool
    create_rollback_generation: bool
    create_structure_revision: bool
    rollback_of_generation_id: int | None
    requires_atomic_double_cas: bool


def _rollback_execution_decision(
    outcome: RollbackExecutionOutcome,
    code: RollbackExecutionCode,
    *,
    target_generation_id: int | None = None,
    restore_structure: bool = False,
) -> RollbackExecutionDecision:
    execute = outcome is RollbackExecutionOutcome.EXECUTE
    return RollbackExecutionDecision(
        outcome=outcome,
        code=code,
        retryable=outcome is RollbackExecutionOutcome.CONFLICT,
        create_rollback_generation=execute,
        create_structure_revision=execute and restore_structure,
        rollback_of_generation_id=target_generation_id if execute else None,
        requires_atomic_double_cas=execute,
    )


def decide_rollback_execute(
    facts: RollbackExecuteFacts,
) -> RollbackExecutionDecision:
    """Freeze rollback intent before creating any revision or generation row."""

    if facts.compatibility.knowledge_base_id != facts.knowledge_base_id:
        return _rollback_execution_decision(
            RollbackExecutionOutcome.BLOCKED,
            RollbackExecutionCode.KNOWLEDGE_BASE_MISMATCH,
        )
    if facts.compatibility.target_generation_id != facts.target_generation_id:
        return _rollback_execution_decision(
            RollbackExecutionOutcome.BLOCKED,
            RollbackExecutionCode.TARGET_GENERATION_MISMATCH,
        )
    if facts.active_generation_id != facts.requested_base_generation_id:
        return _rollback_execution_decision(
            RollbackExecutionOutcome.CONFLICT,
            RollbackExecutionCode.BASE_GENERATION_CONFLICT,
        )
    if (
        facts.active_structure_version != facts.requested_structure_version
        or facts.compatibility.current_structure_version != facts.requested_structure_version
    ):
        return _rollback_execution_decision(
            RollbackExecutionOutcome.CONFLICT,
            RollbackExecutionCode.STRUCTURE_VERSION_CONFLICT,
        )
    if facts.target_generation_id == facts.active_generation_id:
        return _rollback_execution_decision(
            RollbackExecutionOutcome.BLOCKED,
            RollbackExecutionCode.TARGET_IS_ACTIVE_GENERATION,
        )
    if facts.compatibility.outcome is RollbackCompatibility.BLOCKED:
        return _rollback_execution_decision(
            RollbackExecutionOutcome.BLOCKED,
            RollbackExecutionCode.STRUCTURE_ROLLBACK_BLOCKED,
        )
    if facts.compatibility.outcome is RollbackCompatibility.REQUIRES_STRUCTURE_RESTORE and not facts.confirm_structure_restore:
        return _rollback_execution_decision(
            RollbackExecutionOutcome.CONFIRMATION_REQUIRED,
            RollbackExecutionCode.STRUCTURE_RESTORE_CONFIRMATION_REQUIRED,
        )
    restore_structure = facts.compatibility.outcome is RollbackCompatibility.REQUIRES_STRUCTURE_RESTORE
    return _rollback_execution_decision(
        RollbackExecutionOutcome.EXECUTE,
        RollbackExecutionCode.ROLLBACK_ALLOWED,
        target_generation_id=facts.target_generation_id,
        restore_structure=restore_structure,
    )
