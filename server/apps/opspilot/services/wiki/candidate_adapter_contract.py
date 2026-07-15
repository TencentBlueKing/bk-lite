"""Pure port and eligibility contract for Wiki knowledge candidates."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Iterable, Mapping, Protocol, runtime_checkable


class CandidateDecisionType(str, Enum):
    KNOWLEDGE_CONFLICT = "knowledge_conflict"
    PAGE_IDENTITY = "page_identity"


class CandidateTrigger(str, Enum):
    HUMAN_BODY_CONFLICT = "human_body_conflict"
    MIXED_BODY_CONFLICT = "mixed_body_conflict"
    IDENTITY_AMBIGUITY = "identity_ambiguity"
    UNKNOWN_DIRECTORY_KEY = "unknown_directory_key"
    DIRECTORY_SCHEMA_MISMATCH = "directory_schema_mismatch"
    DIRECTORY_LOW_CONFIDENCE = "directory_low_confidence"
    DETERMINISTIC_UPDATE = "deterministic_update"
    NEW_AI_PAGE = "new_ai_page"


class CandidateHandling(str, Enum):
    CREATE_BODY_CONFLICT = "create_body_conflict"
    CREATE_IDENTITY_CONFLICT = "create_identity_conflict"
    BUILD_TRACE_ONLY = "build_trace_only"
    AUTO_APPLY = "auto_apply"


class UnknownCandidateTrigger(ValueError):
    pass


class InvalidCandidateHandle(ValueError):
    pass


class InvalidIdentityConflictKey(ValueError):
    pass


IDENTITY_CONFLICT_KEY_VERSION = "v1"
IDENTITY_CONFLICT_KEY_FIELDS = ("knowledge_base_id", "canonical_title_key")
IDENTITY_DIAGNOSTIC_ONLY_FIELDS = ("page_type",)


def identity_conflict_key(*, knowledge_base_id: int, canonical_title_key: str) -> str:
    """Return the stable KB-wide identity-conflict key for a canonical title."""

    if knowledge_base_id <= 0:
        raise InvalidIdentityConflictKey("knowledge_base_id must be positive")
    if not canonical_title_key.strip():
        raise InvalidIdentityConflictKey("canonical_title_key must not be blank")

    payload = json.dumps(
        [IDENTITY_CONFLICT_KEY_VERSION, knowledge_base_id, canonical_title_key],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CandidateParticipant:
    material_id: int
    content_hash: str

    def __post_init__(self) -> None:
        if self.material_id <= 0 or not self.content_hash.strip():
            raise ValueError("candidate participant requires a material id and content hash")


@dataclass(frozen=True)
class CandidateHandle:
    decision_type: CandidateDecisionType
    check_id: int
    candidate_version_id: int | None
    created: bool
    blocks_generation_activation: bool

    def __post_init__(self) -> None:
        if not isinstance(self.decision_type, CandidateDecisionType):
            raise InvalidCandidateHandle(f"unknown decision type: {self.decision_type!r}")
        if self.check_id <= 0:
            raise InvalidCandidateHandle("check_id must be positive")
        if self.decision_type is CandidateDecisionType.KNOWLEDGE_CONFLICT:
            if self.candidate_version_id is None or self.candidate_version_id <= 0:
                raise InvalidCandidateHandle("body conflict requires a non-current candidate version")
            if self.blocks_generation_activation:
                raise InvalidCandidateHandle("body conflict must not block generation activation")
        elif self.candidate_version_id is not None:
            raise InvalidCandidateHandle("identity conflict must not bind a body candidate version")
        elif not self.blocks_generation_activation:
            raise InvalidCandidateHandle("identity ambiguity must block its generation activation")


@dataclass(frozen=True)
class CandidateMethodContract:
    candidate_version_required: bool
    candidate_version_is_current: bool
    locks_current_version: bool
    mutates_current_body: bool
    auto_merges_pages: bool
    blocks_generation_activation: bool
    idempotent_open_conflict_key: bool
    stable_conflict_key_fields: tuple[str, ...] = ()
    diagnostic_only_fields: tuple[str, ...] = ()


CANDIDATE_METHOD_CONTRACTS: Mapping[CandidateDecisionType, CandidateMethodContract] = MappingProxyType(
    {
        CandidateDecisionType.KNOWLEDGE_CONFLICT: CandidateMethodContract(
            candidate_version_required=True,
            candidate_version_is_current=False,
            locks_current_version=True,
            mutates_current_body=False,
            auto_merges_pages=False,
            blocks_generation_activation=False,
            idempotent_open_conflict_key=True,
        ),
        CandidateDecisionType.PAGE_IDENTITY: CandidateMethodContract(
            candidate_version_required=False,
            candidate_version_is_current=False,
            locks_current_version=False,
            mutates_current_body=False,
            auto_merges_pages=False,
            blocks_generation_activation=True,
            idempotent_open_conflict_key=True,
            stable_conflict_key_fields=IDENTITY_CONFLICT_KEY_FIELDS,
            diagnostic_only_fields=IDENTITY_DIAGNOSTIC_ONLY_FIELDS,
        ),
    }
)


_CANDIDATE_HANDLING: Mapping[CandidateTrigger, CandidateHandling] = MappingProxyType(
    {
        CandidateTrigger.HUMAN_BODY_CONFLICT: CandidateHandling.CREATE_BODY_CONFLICT,
        CandidateTrigger.MIXED_BODY_CONFLICT: CandidateHandling.CREATE_BODY_CONFLICT,
        CandidateTrigger.IDENTITY_AMBIGUITY: CandidateHandling.CREATE_IDENTITY_CONFLICT,
        CandidateTrigger.UNKNOWN_DIRECTORY_KEY: CandidateHandling.BUILD_TRACE_ONLY,
        CandidateTrigger.DIRECTORY_SCHEMA_MISMATCH: CandidateHandling.BUILD_TRACE_ONLY,
        CandidateTrigger.DIRECTORY_LOW_CONFIDENCE: CandidateHandling.BUILD_TRACE_ONLY,
        CandidateTrigger.DETERMINISTIC_UPDATE: CandidateHandling.AUTO_APPLY,
        CandidateTrigger.NEW_AI_PAGE: CandidateHandling.AUTO_APPLY,
    }
)


def candidate_handling_for(trigger: CandidateTrigger | str) -> CandidateHandling:
    if not isinstance(trigger, CandidateTrigger):
        try:
            trigger = CandidateTrigger(trigger)
        except (TypeError, ValueError) as error:
            raise UnknownCandidateTrigger(f"unknown candidate trigger: {trigger!r}") from error
    return _CANDIDATE_HANDLING[trigger]


@runtime_checkable
class KnowledgeCandidateAdapter(Protocol):
    """Persistence port implemented by Task 5.5.

    Implementations must return the existing open conflict for the same stable
    conflict key (`created=False`) instead of creating duplicates. Identity
    conflicts must use :func:`identity_conflict_key`; ``page_type`` is diagnostic
    context only and must not affect identity or deduplication.
    """

    def create_body_conflict(
        self,
        *,
        knowledge_base_id: int,
        page_id: int,
        locked_current_version_id: int,
        candidate_body: str,
        build_record_id: int | None,
        generation_id: int,
        participants: Iterable[CandidateParticipant],
        reason: str,
        created_by: str,
    ) -> CandidateHandle:
        """Create a non-current body version without changing the current body."""

    def create_identity_conflict(
        self,
        *,
        knowledge_base_id: int,
        incoming_candidate_ref: str,
        competing_page_ids: Iterable[int],
        canonical_title_key: str,
        page_type: str,
        build_record_id: int | None,
        generation_id: int,
        reason: str,
        created_by: str,
    ) -> CandidateHandle:
        """Record KB-wide title ambiguity without binding a body or merging pages.

        ``page_type`` is diagnostic-only context. Implementations must derive the
        idempotency key from ``knowledge_base_id`` and ``canonical_title_key`` via
        :func:`identity_conflict_key`.
        """


__all__ = [
    "CANDIDATE_METHOD_CONTRACTS",
    "IDENTITY_CONFLICT_KEY_FIELDS",
    "IDENTITY_CONFLICT_KEY_VERSION",
    "IDENTITY_DIAGNOSTIC_ONLY_FIELDS",
    "CandidateDecisionType",
    "CandidateHandle",
    "CandidateHandling",
    "CandidateMethodContract",
    "CandidateParticipant",
    "CandidateTrigger",
    "InvalidCandidateHandle",
    "InvalidIdentityConflictKey",
    "KnowledgeCandidateAdapter",
    "UnknownCandidateTrigger",
    "candidate_handling_for",
    "identity_conflict_key",
]
