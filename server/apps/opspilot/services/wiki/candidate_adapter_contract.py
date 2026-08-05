"""Pure port and eligibility contract for Wiki knowledge candidates."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Iterable, Mapping, Protocol


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


class InvalidBodyConflictKey(ValueError):
    pass


class InvalidIdentityConflictKey(ValueError):
    pass


BODY_CONFLICT_KEY_VERSION = "v1"
BODY_CONFLICT_KEY_FIELDS = (
    "knowledge_base_id",
    "page_id",
    "locked_current_version_id",
    "content_contract_fingerprint",
    "participants",
)
IDENTITY_CONFLICT_KEY_VERSION = "v1"
IDENTITY_CONFLICT_KEY_FIELDS = ("knowledge_base_id", "normalized_title_key")
IDENTITY_DIAGNOSTIC_ONLY_FIELDS = ("page_type",)


def normalize_title_identity_key(title: str) -> str:
    """Apply the one title-identity algorithm frozen by the OpenSpec."""

    if not isinstance(title, str):
        raise InvalidIdentityConflictKey("title identity input must be a string")
    normalized = " ".join(unicodedata.normalize("NFKC", title).split()).casefold()
    if not normalized:
        raise InvalidIdentityConflictKey("title identity input must not be blank")
    return normalized


@dataclass(frozen=True)
class IdentityConflictKey:
    knowledge_base_id: int
    normalized_title_key: str

    def __post_init__(self) -> None:
        if type(self.knowledge_base_id) is not int or self.knowledge_base_id <= 0:
            raise InvalidIdentityConflictKey("knowledge_base_id must be a positive integer")
        normalized = normalize_title_identity_key(self.normalized_title_key)
        if normalized != self.normalized_title_key:
            raise InvalidIdentityConflictKey("normalized_title_key must already use the shared title identity algorithm")

    @property
    def digest(self) -> str:
        payload = json.dumps(
            [
                IDENTITY_CONFLICT_KEY_VERSION,
                self.knowledge_base_id,
                self.normalized_title_key,
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def identity_conflict_key(*, knowledge_base_id: int, normalized_title_key: str) -> IdentityConflictKey:
    """Build a validated KB-wide identity key without silently normalizing."""

    return IdentityConflictKey(
        knowledge_base_id=knowledge_base_id,
        normalized_title_key=normalized_title_key,
    )


@dataclass(frozen=True)
class CandidateParticipant:
    material_id: int
    content_hash: str

    def __post_init__(self) -> None:
        if self.material_id <= 0 or not self.content_hash.strip():
            raise ValueError("candidate participant requires a material id and content hash")


@dataclass(frozen=True)
class BodyConflictKey:
    knowledge_base_id: int
    page_id: int
    locked_current_version_id: int
    content_contract_fingerprint: str
    participants: tuple[CandidateParticipant, ...]

    def __post_init__(self) -> None:
        identifiers = (
            ("knowledge_base_id", self.knowledge_base_id),
            ("page_id", self.page_id),
            ("locked_current_version_id", self.locked_current_version_id),
        )
        for field_name, value in identifiers:
            if type(value) is not int or value <= 0:
                raise InvalidBodyConflictKey(f"{field_name} must be a positive integer")
        fingerprint = self.content_contract_fingerprint
        if not isinstance(fingerprint, str) or not fingerprint or fingerprint != fingerprint.strip():
            raise InvalidBodyConflictKey("content_contract_fingerprint must be a non-blank canonical string")
        if type(self.participants) is not tuple or not self.participants:
            raise InvalidBodyConflictKey("participants must be a non-empty canonical tuple")
        for participant in self.participants:
            if not isinstance(participant, CandidateParticipant):
                raise InvalidBodyConflictKey("participants must contain CandidateParticipant values")
            if type(participant.material_id) is not int or participant.material_id <= 0:
                raise InvalidBodyConflictKey("participant material_id must be a positive integer")
            if (
                not isinstance(participant.content_hash, str)
                or not participant.content_hash
                or participant.content_hash != participant.content_hash.strip()
            ):
                raise InvalidBodyConflictKey("participant content_hash must be a non-blank canonical string")
        canonical = tuple(
            sorted(
                set(self.participants),
                key=lambda participant: (participant.material_id, participant.content_hash),
            )
        )
        if canonical != self.participants:
            raise InvalidBodyConflictKey("participants must already be sorted and unique")

    @property
    def digest(self) -> str:
        payload = json.dumps(
            {
                "content_contract_fingerprint": self.content_contract_fingerprint,
                "knowledge_base_id": self.knowledge_base_id,
                "locked_current_version_id": self.locked_current_version_id,
                "page_id": self.page_id,
                "participants": [[participant.material_id, participant.content_hash] for participant in self.participants],
                "version": BODY_CONFLICT_KEY_VERSION,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def body_conflict_key(
    *,
    knowledge_base_id: int,
    page_id: int,
    locked_current_version_id: int,
    content_contract_fingerprint: str,
    participants: Iterable[CandidateParticipant],
) -> BodyConflictKey:
    """Build the stable open-conflict identity and canonicalize participants."""

    try:
        participant_values = tuple(participants)
    except TypeError as error:
        raise InvalidBodyConflictKey("participants must be iterable") from error
    if any(not isinstance(participant, CandidateParticipant) for participant in participant_values):
        raise InvalidBodyConflictKey("participants must contain CandidateParticipant values")
    canonical_participants = tuple(
        sorted(
            set(participant_values),
            key=lambda participant: (participant.material_id, participant.content_hash),
        )
    )
    return BodyConflictKey(
        knowledge_base_id=knowledge_base_id,
        page_id=page_id,
        locked_current_version_id=locked_current_version_id,
        content_contract_fingerprint=content_contract_fingerprint,
        participants=canonical_participants,
    )


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
            stable_conflict_key_fields=BODY_CONFLICT_KEY_FIELDS,
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


class KnowledgeCandidateAdapter(Protocol):
    """Persistence port implemented by Task 5.5.

    Implementations must return the existing open conflict for the same stable
    conflict key (`created=False`) instead of creating duplicates. Body and
    identity conflicts receive the strict value objects produced by
    :func:`body_conflict_key` and :func:`identity_conflict_key`. ``page_type`` is
    recorded outside this port as diagnostic context and cannot participate in
    adapter deduplication.
    """

    def create_body_conflict(
        self,
        *,
        conflict_key: BodyConflictKey,
        candidate_body: str,
        build_record_id: int | None,
        generation_id: int,
        reason: str,
        created_by: str,
    ) -> CandidateHandle:
        """Create a non-current body version without changing the current body.

        Implementations must deduplicate on ``conflict_key.digest`` before they
        create a PageVersion. Retry-only fields cannot change that identity.
        """

    def create_identity_conflict(
        self,
        *,
        conflict_key: IdentityConflictKey,
        incoming_candidate_ref: str,
        competing_page_ids: Iterable[int],
        build_record_id: int | None,
        generation_id: int,
        reason: str,
        created_by: str,
    ) -> CandidateHandle:
        """Record KB-wide title ambiguity without binding a body or merging pages.

        Implementations must use ``conflict_key.digest`` as the open-conflict
        idempotency key. Page type is deliberately absent from this persistence
        boundary and belongs in BuildRecord diagnostics.
        """


class DjangoKnowledgeCandidateAdapter:
    """Django ORM implementation of the frozen candidate persistence port."""

    @staticmethod
    def _handle(check, decision_type, *, created, blocks):
        return CandidateHandle(
            decision_type=decision_type,
            check_id=check.pk,
            candidate_version_id=check.candidate_version_id,
            created=created,
            blocks_generation_activation=blocks,
        )

    def create_body_conflict(
        self,
        *,
        conflict_key: BodyConflictKey,
        candidate_body: str,
        build_record_id: int | None,
        generation_id: int,
        reason: str,
        created_by: str,
    ) -> CandidateHandle:
        """Create a stable non-current candidate compatible with decide_check."""

        from django.db import transaction

        from apps.opspilot.models import (
            BuildRecord,
            CheckItem,
            KnowledgePage,
            Material,
            MaterialVersion,
            PageVersion,
            WikiGeneration,
            WikiKnowledgeBase,
        )
        from apps.opspilot.services.wiki.check_service import _body_hash, create_candidate
        from apps.opspilot.services.wiki.decision_service import compute_schema_fingerprint, subject_key_for_page
        from apps.opspilot.services.wiki.title_service import canonical_title

        with transaction.atomic():
            knowledge_base = WikiKnowledgeBase.objects.select_for_update().get(pk=conflict_key.knowledge_base_id)
            generation = WikiGeneration.objects.select_for_update().get(
                pk=generation_id,
                knowledge_base=knowledge_base,
            )
            if generation.status not in {"preparing", "ready"}:
                raise ValueError("body conflict generation must still be preparing or ready")
            page = (
                KnowledgePage.objects.select_for_update()
                .select_related("current_version")
                .get(
                    pk=conflict_key.page_id,
                    knowledge_base=knowledge_base,
                )
            )
            if page.current_version_id != conflict_key.locked_current_version_id:
                raise ValueError("body conflict current version changed before persistence")
            build_record = None
            if build_record_id is not None:
                build_record = BuildRecord.objects.get(pk=build_record_id, knowledge_base=knowledge_base)
                if build_record.generation_id not in {None, generation.pk}:
                    raise ValueError("build record belongs to another generation")

            existing = (
                CheckItem.objects.select_for_update()
                .select_related("candidate_version")
                .filter(
                    knowledge_base=knowledge_base,
                    check_type__in=("cannot_merge", "material_update"),
                    decision_key=conflict_key.digest,
                    status="open",
                )
                .order_by("id")
                .first()
            )
            if existing is not None:
                if existing.candidate_version_id is None:
                    raise InvalidCandidateHandle("stable body conflict has no candidate version")
                return self._handle(
                    existing,
                    CandidateDecisionType.KNOWLEDGE_CONFLICT,
                    created=False,
                    blocks=False,
                )

            participants = [
                {
                    "material_id": participant.material_id,
                    "content_hash": participant.content_hash,
                }
                for participant in conflict_key.participants
            ]
            evidence_material_ids = set(page.evidences.values_list("material_id", flat=True))
            incoming_participant = next(
                (participant for participant in conflict_key.participants if participant.material_id not in evidence_material_ids),
                conflict_key.participants[0],
            )
            incoming_material = Material.objects.filter(
                pk=incoming_participant.material_id,
                knowledge_base=knowledge_base,
            ).first()
            incoming_version = None
            if incoming_material is not None:
                incoming_version = (
                    MaterialVersion.objects.filter(
                        material=incoming_material,
                        content_hash=incoming_participant.content_hash,
                    )
                    .order_by("-id")
                    .first()
                )
                if incoming_version is None:
                    current = getattr(incoming_material, "current_version", None)
                    current_hash = getattr(current, "content_hash", "") or incoming_material.content_hash or ""
                    if current_hash != incoming_participant.content_hash:
                        incoming_material = None

            open_ids_before = set(
                CheckItem.objects.filter(
                    knowledge_base=knowledge_base,
                    check_type__in=("cannot_merge", "material_update"),
                    status="open",
                ).values_list("id", flat=True)
            )
            related = {
                "pages": [page.pk],
                "build_record_id": build_record_id,
                "generation_id": generation.pk,
                "candidate_adapter": "body_conflict_v1",
                "conflict_key": conflict_key.digest,
            }
            check = create_candidate(
                page,
                candidate_body,
                reason,
                check_type="cannot_merge",
                build_record=build_record,
                created_by=created_by,
                related=related,
                suggested_actions=["edit_accept", "keep_current", "use_new"],
                change_type="candidate",
                meta_snapshot={
                    "candidate_adapter": "body_conflict_v1",
                    "conflict_key": conflict_key.digest,
                    "generation_id": generation.pk,
                },
                incoming_material=incoming_material,
                incoming_material_version=incoming_version,
            )
            if check.pk in open_ids_before:
                last = page.page_versions.order_by("-no").first()
                candidate = PageVersion.objects.create(
                    page=page,
                    no=(last.no + 1) if last else 1,
                    body=candidate_body,
                    change_type="candidate",
                    build_record=build_record,
                    created_in_generation=generation,
                    is_current=False,
                    created_by=created_by or "",
                    meta_snapshot={
                        "candidate_adapter": "body_conflict_v1",
                        "conflict_key": conflict_key.digest,
                        "generation_id": generation.pk,
                    },
                )
                check = CheckItem.objects.create(
                    knowledge_base=knowledge_base,
                    check_type="cannot_merge",
                    status="open",
                    related=related,
                    candidate_version=candidate,
                    suggested_actions=["edit_accept", "keep_current", "use_new"],
                    decision_key=conflict_key.digest,
                    created_by=created_by or "",
                    updated_by=created_by or "",
                )
            else:
                candidate = check.candidate_version
            if candidate is None:
                raise InvalidCandidateHandle("create_candidate returned no body candidate version")
            if candidate.created_in_generation_id not in {None, generation.pk}:
                raise ValueError("candidate version already belongs to another generation")
            candidate.created_in_generation = generation
            candidate.build_record = build_record
            candidate.is_current = False
            candidate.save(update_fields=["created_in_generation", "build_record", "is_current", "updated_at"])

            incoming = {
                "material_id": incoming_participant.material_id,
                "material_version_id": getattr(incoming_version, "pk", None),
                "content_hash": incoming_participant.content_hash,
            }
            context = dict(check.decision_context or {})
            context.update(
                {
                    "locked_current_version_id": conflict_key.locked_current_version_id,
                    "decision_type": CandidateDecisionType.KNOWLEDGE_CONFLICT.value,
                    "subject_key": context.get("subject_key")
                    or subject_key_for_page(
                        page_type=page.page_type or "concept",
                        canonical_title=canonical_title(knowledge_base, page.title),
                    ),
                    "schema_fingerprint": context.get("schema_fingerprint") or compute_schema_fingerprint(knowledge_base),
                    "participants": participants,
                    "incoming": incoming,
                    "current_body_hash": _body_hash(page.current_version.body),
                    "candidate_body_hash": _body_hash(candidate_body),
                    "candidate_version_id": candidate.pk,
                    "reason": reason or "",
                    "page_identity": context.get("page_identity")
                    or {
                        "page_id": page.pk,
                        "title": page.title,
                        "canonical_title": canonical_title(knowledge_base, page.title),
                        "page_type": page.page_type,
                    },
                    "candidate_adapter": {
                        "contract": "body_conflict_v1",
                        "conflict_key": conflict_key.digest,
                        "content_contract_fingerprint": conflict_key.content_contract_fingerprint,
                        "generation_id": generation.pk,
                        "build_record_id": build_record_id,
                    },
                }
            )
            check.decision_key = conflict_key.digest
            check.decision_context = context
            check.related = related
            check.candidate_version = candidate
            check.save(
                update_fields=[
                    "decision_key",
                    "decision_context",
                    "related",
                    "candidate_version",
                    "updated_at",
                ]
            )
            return self._handle(
                check,
                CandidateDecisionType.KNOWLEDGE_CONFLICT,
                created=True,
                blocks=False,
            )

    def create_identity_conflict(
        self,
        *,
        conflict_key: IdentityConflictKey,
        incoming_candidate_ref: str,
        competing_page_ids: Iterable[int],
        build_record_id: int | None,
        generation_id: int,
        reason: str,
        created_by: str,
    ) -> CandidateHandle:
        """Persist a normalized-title conflict without a body candidate."""

        from django.db import transaction

        from apps.opspilot.models import BuildRecord, CheckItem, KnowledgePage, WikiGeneration, WikiKnowledgeBase
        from apps.opspilot.services.wiki.decision_service import build_page_identity_snapshot, compute_schema_fingerprint

        candidate_ref = str(incoming_candidate_ref or "").strip()
        if not candidate_ref:
            raise ValueError("incoming_candidate_ref must not be blank")
        try:
            raw_page_ids = tuple(competing_page_ids)
        except TypeError as error:
            raise ValueError("competing_page_ids must contain positive integers") from error
        if not raw_page_ids or any(type(page_id) is not int or page_id <= 0 for page_id in raw_page_ids):
            raise ValueError("competing_page_ids must contain positive integers")
        page_ids = tuple(sorted(set(raw_page_ids)))

        with transaction.atomic():
            knowledge_base = WikiKnowledgeBase.objects.select_for_update().get(pk=conflict_key.knowledge_base_id)
            generation = WikiGeneration.objects.select_for_update().get(
                pk=generation_id,
                knowledge_base=knowledge_base,
            )
            if generation.status not in {"preparing", "ready"}:
                raise ValueError("identity conflict generation must still be preparing or ready")
            if build_record_id is not None:
                build_record = BuildRecord.objects.get(pk=build_record_id, knowledge_base=knowledge_base)
                if build_record.generation_id not in {None, generation.pk}:
                    raise ValueError("build record belongs to another generation")
            pages = list(KnowledgePage.objects.select_for_update().filter(pk__in=page_ids, knowledge_base=knowledge_base).order_by("id"))
            if tuple(page.pk for page in pages) != page_ids:
                raise ValueError("competing page is missing or belongs to another knowledge base")
            if any(normalize_title_identity_key(page.title) != conflict_key.normalized_title_key for page in pages):
                raise ValueError("competing page title does not match the normalized title conflict key")

            existing = (
                CheckItem.objects.select_for_update()
                .filter(
                    knowledge_base=knowledge_base,
                    check_type__in=("conflict", "duplicate"),
                    decision_key=conflict_key.digest,
                    status="open",
                )
                .order_by("id")
                .first()
            )
            if existing is not None:
                return self._handle(
                    existing,
                    CandidateDecisionType.PAGE_IDENTITY,
                    created=False,
                    blocks=True,
                )

            identities = [build_page_identity_snapshot(knowledge_base, page) for page in pages]
            related = {
                "pages": list(page_ids),
                "normalized_title_key": conflict_key.normalized_title_key,
                "incoming_candidate_ref": candidate_ref,
                "build_record_id": build_record_id,
                "generation_id": generation.pk,
                "candidate_adapter": "identity_conflict_v1",
            }
            context = {
                "decision_type": CandidateDecisionType.PAGE_IDENTITY.value,
                "subject_key": f"title::{conflict_key.normalized_title_key}",
                "schema_fingerprint": compute_schema_fingerprint(knowledge_base),
                "page_identities": identities,
                "target_identity": identities[0],
                "incoming_candidate_ref": candidate_ref,
                "reason": reason or "",
                "candidate_adapter": {
                    "contract": "identity_conflict_v1",
                    "conflict_key": conflict_key.digest,
                    "generation_id": generation.pk,
                    "build_record_id": build_record_id,
                },
            }
            check = CheckItem.objects.create(
                knowledge_base=knowledge_base,
                check_type="conflict",
                status="open",
                related=related,
                candidate_version=None,
                suggested_actions=["keep_separate", "merge"] if len(page_ids) == 2 else [],
                action_type="page_identity",
                decision_key=conflict_key.digest,
                decision_context=context,
                created_by=created_by or "",
                updated_by=created_by or "",
            )
            return self._handle(
                check,
                CandidateDecisionType.PAGE_IDENTITY,
                created=True,
                blocks=True,
            )


__all__ = [
    "BODY_CONFLICT_KEY_FIELDS",
    "BODY_CONFLICT_KEY_VERSION",
    "CANDIDATE_METHOD_CONTRACTS",
    "IDENTITY_CONFLICT_KEY_FIELDS",
    "IDENTITY_CONFLICT_KEY_VERSION",
    "IDENTITY_DIAGNOSTIC_ONLY_FIELDS",
    "BodyConflictKey",
    "CandidateDecisionType",
    "CandidateHandle",
    "CandidateHandling",
    "CandidateMethodContract",
    "CandidateParticipant",
    "CandidateTrigger",
    "IdentityConflictKey",
    "InvalidBodyConflictKey",
    "InvalidCandidateHandle",
    "InvalidIdentityConflictKey",
    "KnowledgeCandidateAdapter",
    "DjangoKnowledgeCandidateAdapter",
    "UnknownCandidateTrigger",
    "body_conflict_key",
    "candidate_handling_for",
    "identity_conflict_key",
    "normalize_title_identity_key",
]
