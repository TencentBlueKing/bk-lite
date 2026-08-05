from inspect import Parameter, signature
from types import MappingProxyType

import pytest

from apps.opspilot.services.wiki import candidate_adapter_contract as candidate_contract
from apps.opspilot.services.wiki.candidate_adapter_contract import (
    CANDIDATE_METHOD_CONTRACTS,
    IDENTITY_CONFLICT_KEY_FIELDS,
    IDENTITY_DIAGNOSTIC_ONLY_FIELDS,
    CandidateDecisionType,
    CandidateHandle,
    CandidateHandling,
    CandidateTrigger,
    IdentityConflictKey,
    InvalidCandidateHandle,
    InvalidIdentityConflictKey,
    KnowledgeCandidateAdapter,
    UnknownCandidateTrigger,
    candidate_handling_for,
    identity_conflict_key,
    normalize_title_identity_key,
)
from apps.opspilot.services.wiki.directory_routing_contract import (
    AmbiguousTypeDefault,
    AssignmentMode,
    DirectoryReferenceSource,
    DirectoryRouteSource,
    DirectorySnapshot,
    DirectoryStatus,
    InvalidClassificationRoot,
    InvalidDirectoryRedirect,
    InvalidManualDirectory,
    InvalidUnclassifiedDirectory,
    RoutingTraceCode,
    route_directory,
)

KB_ID = 7
OTHER_KB_ID = 8


def _directory(
    key,
    *,
    knowledge_base_id=KB_ID,
    status=DirectoryStatus.ACTIVE,
    accepts_pages=True,
    ancestor_keys=(),
    merged_into_key=None,
    allowed_page_types=None,
    is_unclassified=False,
):
    return DirectorySnapshot(
        key=key,
        knowledge_base_id=knowledge_base_id,
        status=status,
        accepts_pages=accepts_pages,
        ancestor_keys=tuple(ancestor_keys),
        merged_into_key=merged_into_key,
        allowed_page_types=None if allowed_page_types is None else frozenset(allowed_page_types),
        is_unclassified=is_unclassified,
    )


def _directories(*items):
    unclassified = _directory("__unclassified__", is_unclassified=True)
    return {directory.key: directory for directory in (*items, unclassified)}


def _route(directories, **overrides):
    options = {
        "knowledge_base_id": KB_ID,
        "page_type": "procedure",
        "revision_page_types": frozenset({"concept", "procedure", "faq"}),
        "assignment_mode": AssignmentMode.AUTO,
        "directories": directories,
        "current_directory_key": None,
        "suggested_key": None,
        "suggestion_source": DirectoryReferenceSource.LLM,
        "classification_root_key": None,
        "type_default_keys": (),
        "unclassified_key": "__unclassified__",
        "suggestion_schema_mismatch": False,
        "low_confidence": False,
    }
    options.update(overrides)
    return route_directory(**options)


def test_manual_directory_wins_even_outside_classification_root():
    manual = _directory("manual_outside")
    root = _directory("batch_root", accepts_pages=True)
    suggested = _directory("suggested", ancestor_keys=(root.key,))
    default = _directory("default", ancestor_keys=(root.key,))

    decision = _route(
        _directories(manual, root, suggested, default),
        assignment_mode=AssignmentMode.MANUAL,
        current_directory_key=manual.key,
        suggested_key=suggested.key,
        classification_root_key=root.key,
        type_default_keys=(default.key,),
    )

    assert decision.directory_key == manual.key
    assert decision.assignment_mode is AssignmentMode.MANUAL
    assert decision.source is DirectoryRouteSource.MANUAL
    assert decision.trace == (RoutingTraceCode.MANUAL_SUGGESTION_IGNORED,)


def test_manual_route_preserves_invalid_suggestion_and_confidence_trace():
    manual = _directory("manual")

    decision = _route(
        _directories(manual),
        assignment_mode=AssignmentMode.MANUAL,
        current_directory_key=manual.key,
        suggested_key="missing",
        suggestion_schema_mismatch=True,
        low_confidence=True,
    )

    assert decision.directory_key == manual.key
    assert RoutingTraceCode.MANUAL_SUGGESTION_IGNORED in decision.trace
    assert RoutingTraceCode.LOW_CONFIDENCE in decision.trace
    assert RoutingTraceCode.SCHEMA_MISMATCH in decision.trace
    assert RoutingTraceCode.UNKNOWN_KEY in decision.trace


@pytest.mark.parametrize(
    "manual",
    [
        None,
        _directory("foreign", knowledge_base_id=OTHER_KB_ID),
        _directory("retired", status=DirectoryStatus.RETIRED),
        _directory("non_receiving", accepts_pages=False),
    ],
)
def test_invalid_manual_directory_fails_closed_instead_of_becoming_auto(manual):
    directories = _directories(*(tuple() if manual is None else (manual,)))

    with pytest.raises(InvalidManualDirectory):
        _route(
            directories,
            assignment_mode=AssignmentMode.MANUAL,
            current_directory_key=None if manual is None else manual.key,
        )


def test_valid_llm_key_wins_and_low_confidence_is_trace_only():
    target = _directory("target")

    decision = _route(
        _directories(target),
        suggested_key=target.key,
        low_confidence=True,
    )

    assert decision.directory_key == target.key
    assert decision.source is DirectoryRouteSource.SUGGESTED_KEY
    assert decision.trace == (RoutingTraceCode.LOW_CONFIDENCE,)


def test_directory_snapshot_copies_mutable_scope_inputs():
    ancestors = ["root"]
    allowed_page_types = {"procedure"}

    snapshot = DirectorySnapshot(
        key="child",
        knowledge_base_id=KB_ID,
        status=DirectoryStatus.ACTIVE,
        accepts_pages=True,
        ancestor_keys=ancestors,
        allowed_page_types=allowed_page_types,
    )
    ancestors.append("later")
    allowed_page_types.add("concept")

    assert snapshot.ancestor_keys == ("root",)
    assert snapshot.allowed_page_types == frozenset({"procedure"})


@pytest.mark.parametrize(
    ("suggested", "suggested_key", "extra", "expected_trace"),
    [
        (None, "missing", {}, RoutingTraceCode.UNKNOWN_KEY),
        (
            _directory("foreign", knowledge_base_id=OTHER_KB_ID),
            "foreign",
            {},
            RoutingTraceCode.FOREIGN_KNOWLEDGE_BASE,
        ),
        (
            _directory("retired", status=DirectoryStatus.RETIRED),
            "retired",
            {},
            RoutingTraceCode.INACTIVE_KEY,
        ),
        (
            _directory("non_receiving", accepts_pages=False),
            "non_receiving",
            {},
            RoutingTraceCode.NON_RECEIVING_KEY,
        ),
        (
            _directory("wrong_type", allowed_page_types={"concept"}),
            "wrong_type",
            {},
            RoutingTraceCode.SCHEMA_MISMATCH,
        ),
        (
            _directory("schema_flag"),
            "schema_flag",
            {"suggestion_schema_mismatch": True},
            RoutingTraceCode.SCHEMA_MISMATCH,
        ),
    ],
)
def test_invalid_llm_key_records_reason_and_falls_back_to_type_default(
    suggested,
    suggested_key,
    extra,
    expected_trace,
):
    default = _directory("default")
    directories = _directories(default, *(tuple() if suggested is None else (suggested,)))

    decision = _route(
        directories,
        suggested_key=suggested_key,
        type_default_keys=(default.key,),
        **extra,
    )

    assert decision.directory_key == default.key
    assert decision.source is DirectoryRouteSource.TYPE_DEFAULT
    assert expected_trace in decision.trace


@pytest.mark.parametrize("page_type", ["", "   ", "unknown"])
def test_unknown_revision_page_type_skips_unrestricted_routes_and_uses_unclassified(page_type):
    root = _directory("root")
    suggested = _directory("suggested", ancestor_keys=(root.key,))
    default = _directory("default", ancestor_keys=(root.key,))

    decision = _route(
        _directories(root, suggested, default),
        page_type=page_type,
        revision_page_types=frozenset({"procedure"}),
        suggested_key=suggested.key,
        classification_root_key=root.key,
        type_default_keys=(default.key,),
    )

    assert decision.directory_key == "__unclassified__"
    assert decision.source is DirectoryRouteSource.UNCLASSIFIED
    assert RoutingTraceCode.SCHEMA_MISMATCH in decision.trace


def test_unknown_revision_page_type_keeps_manual_directory_and_records_mismatch():
    manual = _directory("manual")

    decision = _route(
        _directories(manual),
        page_type="unknown",
        revision_page_types=frozenset({"procedure"}),
        assignment_mode=AssignmentMode.MANUAL,
        current_directory_key=manual.key,
    )

    assert decision.directory_key == manual.key
    assert decision.source is DirectoryRouteSource.MANUAL
    assert RoutingTraceCode.SCHEMA_MISMATCH in decision.trace


def test_empty_suggested_key_is_traced_as_unknown_in_auto_mode():
    decision = _route(_directories(), suggested_key="")

    assert decision.source is DirectoryRouteSource.UNCLASSIFIED
    assert RoutingTraceCode.UNKNOWN_KEY in decision.trace


def test_out_of_scope_llm_key_and_default_fall_back_to_receiving_root():
    root = _directory("root")
    outside_suggestion = _directory("outside_suggestion")
    outside_default = _directory("outside_default")

    decision = _route(
        _directories(root, outside_suggestion, outside_default),
        suggested_key=outside_suggestion.key,
        classification_root_key=root.key,
        type_default_keys=(outside_default.key,),
    )

    assert decision.directory_key == root.key
    assert decision.source is DirectoryRouteSource.CLASSIFICATION_ROOT
    assert RoutingTraceCode.OUT_OF_SCOPE_KEY in decision.trace
    assert RoutingTraceCode.TYPE_DEFAULT_OUT_OF_SCOPE in decision.trace


def test_multiple_valid_type_defaults_are_a_structure_invariant_error():
    first = _directory("first")
    second = _directory("second")

    with pytest.raises(AmbiguousTypeDefault):
        _route(
            _directories(first, second),
            type_default_keys=(first.key, second.key),
        )


def test_no_classification_root_skips_root_fallback_and_uses_unclassified():
    decision = _route(_directories())

    assert decision.directory_key == "__unclassified__"
    assert decision.assignment_mode is AssignmentMode.AUTO
    assert decision.source is DirectoryRouteSource.UNCLASSIFIED


@pytest.mark.parametrize(
    "unclassified",
    [
        None,
        _directory("__unclassified__", is_unclassified=False),
        _directory("__unclassified__", status=DirectoryStatus.RETIRED, is_unclassified=True),
        _directory("__unclassified__", accepts_pages=False, is_unclassified=True),
        _directory("__unclassified__", knowledge_base_id=OTHER_KB_ID, is_unclassified=True),
    ],
)
def test_missing_or_invalid_system_unclassified_directory_fails_closed(unclassified):
    directories = {} if unclassified is None else {unclassified.key: unclassified}

    with pytest.raises(InvalidUnclassifiedDirectory):
        _route(directories)


def test_invalid_classification_root_fails_closed_for_auto_routing():
    root = _directory("root", status=DirectoryStatus.RETIRED)

    with pytest.raises(InvalidClassificationRoot):
        _route(_directories(root), classification_root_key=root.key)


def test_non_receiving_classification_root_scopes_candidates_but_falls_back_to_unclassified():
    root = _directory("root", accepts_pages=False)

    decision = _route(_directories(root), classification_root_key=root.key)

    assert decision.source is DirectoryRouteSource.UNCLASSIFIED
    assert RoutingTraceCode.CLASSIFICATION_ROOT_UNAVAILABLE in decision.trace


def test_llm_merged_key_never_follows_redirect_and_uses_fallback():
    merged = _directory(
        "old",
        status=DirectoryStatus.MERGED,
        merged_into_key="new",
    )
    target = _directory("new")
    default = _directory("default")

    decision = _route(
        _directories(merged, target, default),
        suggested_key=merged.key,
        suggestion_source=DirectoryReferenceSource.LLM,
        type_default_keys=(default.key,),
    )

    assert decision.directory_key == default.key
    assert decision.redirect_chain == ()
    assert RoutingTraceCode.LLM_REDIRECT_FORBIDDEN in decision.trace


@pytest.mark.parametrize(
    "source",
    [
        DirectoryReferenceSource.NATIVE_IMPORT,
        DirectoryReferenceSource.HISTORICAL_LINK,
        DirectoryReferenceSource.AUDIT_READ,
    ],
)
def test_only_persisted_reference_sources_follow_merged_redirect_with_trace(source):
    first = _directory("old", status=DirectoryStatus.MERGED, merged_into_key="middle")
    middle = _directory("middle", status=DirectoryStatus.MERGED, merged_into_key="new")
    target = _directory("new")

    decision = _route(
        _directories(first, middle, target),
        suggested_key=first.key,
        suggestion_source=source,
    )

    assert decision.directory_key == target.key
    assert decision.source is DirectoryRouteSource.REDIRECTED_KEY
    assert decision.redirect_chain == ("old", "middle", "new")
    assert RoutingTraceCode.MERGED_REDIRECT_FOLLOWED in decision.trace


@pytest.mark.parametrize(
    ("target", "expected_rejection"),
    [
        (_directory("target", allowed_page_types={"concept"}), RoutingTraceCode.SCHEMA_MISMATCH),
        (_directory("target"), RoutingTraceCode.OUT_OF_SCOPE_KEY),
    ],
)
def test_persisted_redirect_to_active_context_mismatch_uses_fallback(target, expected_rejection):
    root = _directory("root")
    merged = _directory("old", status=DirectoryStatus.MERGED, merged_into_key=target.key)
    default = _directory("default", ancestor_keys=(root.key,))

    decision = _route(
        _directories(root, merged, target, default),
        suggested_key=merged.key,
        suggestion_source=DirectoryReferenceSource.NATIVE_IMPORT,
        classification_root_key=root.key,
        type_default_keys=(default.key,),
    )

    assert decision.directory_key == default.key
    assert decision.redirect_chain == (merged.key, target.key)
    assert RoutingTraceCode.MERGED_REDIRECT_FOLLOWED in decision.trace
    assert expected_rejection in decision.trace


def test_foreign_merged_key_cannot_redirect_back_into_the_current_knowledge_base():
    foreign = _directory(
        "foreign_old",
        knowledge_base_id=OTHER_KB_ID,
        status=DirectoryStatus.MERGED,
        merged_into_key="local_target",
    )
    local_target = _directory("local_target")
    default = _directory("default")

    decision = _route(
        _directories(foreign, local_target, default),
        suggested_key=foreign.key,
        suggestion_source=DirectoryReferenceSource.NATIVE_IMPORT,
        type_default_keys=(default.key,),
    )

    assert decision.directory_key == default.key
    assert decision.redirect_chain == ()
    assert RoutingTraceCode.FOREIGN_KNOWLEDGE_BASE in decision.trace


@pytest.mark.parametrize(
    "directories",
    [
        _directories(_directory("old", status=DirectoryStatus.MERGED, merged_into_key="missing")),
        _directories(
            _directory("a", status=DirectoryStatus.MERGED, merged_into_key="b"),
            _directory("b", status=DirectoryStatus.MERGED, merged_into_key="a"),
        ),
        _directories(
            _directory("old", status=DirectoryStatus.MERGED, merged_into_key="retired"),
            _directory("retired", status=DirectoryStatus.RETIRED),
        ),
        _directories(
            _directory("old", status=DirectoryStatus.MERGED, merged_into_key="non_receiving"),
            _directory("non_receiving", accepts_pages=False),
        ),
    ],
)
def test_dangling_or_cyclic_redirect_fails_closed(directories):
    suggested_key = "old" if "old" in directories else "a"

    with pytest.raises(InvalidDirectoryRedirect):
        _route(
            directories,
            suggested_key=suggested_key,
            suggestion_source=DirectoryReferenceSource.NATIVE_IMPORT,
        )


@pytest.mark.parametrize(
    ("trigger", "handling"),
    [
        (CandidateTrigger.HUMAN_BODY_CONFLICT, CandidateHandling.CREATE_BODY_CONFLICT),
        (CandidateTrigger.MIXED_BODY_CONFLICT, CandidateHandling.CREATE_BODY_CONFLICT),
        (CandidateTrigger.IDENTITY_AMBIGUITY, CandidateHandling.CREATE_IDENTITY_CONFLICT),
        (CandidateTrigger.UNKNOWN_DIRECTORY_KEY, CandidateHandling.BUILD_TRACE_ONLY),
        (CandidateTrigger.DIRECTORY_SCHEMA_MISMATCH, CandidateHandling.BUILD_TRACE_ONLY),
        (CandidateTrigger.DIRECTORY_LOW_CONFIDENCE, CandidateHandling.BUILD_TRACE_ONLY),
        (CandidateTrigger.DETERMINISTIC_UPDATE, CandidateHandling.AUTO_APPLY),
        (CandidateTrigger.NEW_AI_PAGE, CandidateHandling.AUTO_APPLY),
    ],
)
def test_candidate_eligibility_separates_business_ambiguity_from_directory_trace(trigger, handling):
    assert candidate_handling_for(trigger) is handling


def test_unknown_candidate_trigger_fails_closed():
    with pytest.raises(UnknownCandidateTrigger):
        candidate_handling_for("generic_review")


def test_candidate_adapter_method_shapes_are_keyword_only_and_stable():
    body_parameters = signature(KnowledgeCandidateAdapter.create_body_conflict).parameters
    identity_parameters = signature(KnowledgeCandidateAdapter.create_identity_conflict).parameters

    assert tuple(body_parameters) == (
        "self",
        "conflict_key",
        "candidate_body",
        "build_record_id",
        "generation_id",
        "reason",
        "created_by",
    )
    assert tuple(identity_parameters) == (
        "self",
        "conflict_key",
        "incoming_candidate_ref",
        "competing_page_ids",
        "build_record_id",
        "generation_id",
        "reason",
        "created_by",
    )
    assert all(parameter.kind is Parameter.KEYWORD_ONLY for name, parameter in body_parameters.items() if name != "self")
    assert all(parameter.kind is Parameter.KEYWORD_ONLY for name, parameter in identity_parameters.items() if name != "self")
    with pytest.raises(TypeError):
        isinstance(object(), KnowledgeCandidateAdapter)


def test_candidate_method_semantics_are_immutable_and_keep_directory_issues_out():
    assert isinstance(CANDIDATE_METHOD_CONTRACTS, MappingProxyType)
    body = CANDIDATE_METHOD_CONTRACTS[CandidateDecisionType.KNOWLEDGE_CONFLICT]
    identity = CANDIDATE_METHOD_CONTRACTS[CandidateDecisionType.PAGE_IDENTITY]

    assert body.candidate_version_required is True
    assert body.candidate_version_is_current is False
    assert body.locks_current_version is True
    assert body.mutates_current_body is False
    assert body.auto_merges_pages is False
    assert body.blocks_generation_activation is False
    assert body.idempotent_open_conflict_key is True
    assert body.stable_conflict_key_fields == (
        "knowledge_base_id",
        "page_id",
        "locked_current_version_id",
        "content_contract_fingerprint",
        "participants",
    )

    assert identity.candidate_version_required is False
    assert identity.locks_current_version is False
    assert identity.mutates_current_body is False
    assert identity.auto_merges_pages is False
    assert identity.blocks_generation_activation is True
    assert identity.idempotent_open_conflict_key is True
    assert identity.stable_conflict_key_fields == IDENTITY_CONFLICT_KEY_FIELDS
    assert identity.diagnostic_only_fields == IDENTITY_DIAGNOSTIC_ONLY_FIELDS
    assert IDENTITY_CONFLICT_KEY_FIELDS == ("knowledge_base_id", "normalized_title_key")
    assert IDENTITY_DIAGNOSTIC_ONLY_FIELDS == ("page_type",)

    with pytest.raises(TypeError):
        CANDIDATE_METHOD_CONTRACTS[CandidateDecisionType.PAGE_IDENTITY] = body


def test_body_conflict_key_is_canonical_and_independent_of_runtime_attempts():
    factory = getattr(candidate_contract, "body_conflict_key", None)
    key_type = getattr(candidate_contract, "BodyConflictKey", None)
    fields = getattr(candidate_contract, "BODY_CONFLICT_KEY_FIELDS", None)

    assert callable(factory)
    assert key_type is not None
    assert fields == (
        "knowledge_base_id",
        "page_id",
        "locked_current_version_id",
        "content_contract_fingerprint",
        "participants",
    )
    assert tuple(signature(factory).parameters) == fields

    participant_a = candidate_contract.CandidateParticipant(material_id=7, content_hash="hash-a")
    participant_b = candidate_contract.CandidateParticipant(material_id=9, content_hash="hash-b")
    key = factory(
        knowledge_base_id=KB_ID,
        page_id=31,
        locked_current_version_id=47,
        content_contract_fingerprint="schema-v3",
        participants=(participant_b, participant_a, participant_b),
    )
    retried = factory(
        knowledge_base_id=KB_ID,
        page_id=31,
        locked_current_version_id=47,
        content_contract_fingerprint="schema-v3",
        participants=(participant_a, participant_b),
    )

    assert isinstance(key, key_type)
    assert key.participants == (participant_a, participant_b)
    assert len(key.digest) == 64
    assert retried.digest == key.digest


def test_body_conflict_key_rejects_incomplete_or_noncanonical_identity():
    factory = getattr(candidate_contract, "body_conflict_key", None)
    error_type = getattr(candidate_contract, "InvalidBodyConflictKey", None)

    assert callable(factory)
    assert isinstance(error_type, type)

    valid = {
        "knowledge_base_id": KB_ID,
        "page_id": 31,
        "locked_current_version_id": 47,
        "content_contract_fingerprint": "schema-v3",
        "participants": (candidate_contract.CandidateParticipant(material_id=7, content_hash="hash-a"),),
    }
    invalid_overrides = (
        {"knowledge_base_id": True},
        {"page_id": 0},
        {"locked_current_version_id": "47"},
        {"content_contract_fingerprint": " schema-v3"},
        {"participants": ()},
    )

    for override in invalid_overrides:
        with pytest.raises(error_type):
            factory(**(valid | override))


def test_title_identity_normalization_is_exact_and_does_not_use_legacy_compaction():
    assert normalize_title_identity_key(" Ａ\u00a0 Guide\t") == "a guide"
    assert normalize_title_identity_key("Straße") == "strasse"
    assert normalize_title_identity_key("a-b") == "a-b"
    assert normalize_title_identity_key("a-b") != normalize_title_identity_key("ab")

    for invalid in (None, 7, " \u2003 "):
        with pytest.raises(InvalidIdentityConflictKey):
            normalize_title_identity_key(invalid)


def test_identity_conflict_key_requires_normalized_title_and_excludes_page_type():
    key = identity_conflict_key(
        knowledge_base_id=KB_ID,
        normalized_title_key="installation guide",
    )

    assert isinstance(key, IdentityConflictKey)
    assert key.knowledge_base_id == KB_ID
    assert key.normalized_title_key == "installation guide"
    assert len(key.digest) == 64
    assert key == identity_conflict_key(
        knowledge_base_id=KB_ID,
        normalized_title_key="installation guide",
    )
    assert key != identity_conflict_key(
        knowledge_base_id=OTHER_KB_ID,
        normalized_title_key="installation guide",
    )
    assert key != identity_conflict_key(
        knowledge_base_id=KB_ID,
        normalized_title_key="another guide",
    )

    for invalid_title in ("", " Installation Guide", "Ａ  Guide", "Straße"):
        with pytest.raises(InvalidIdentityConflictKey):
            identity_conflict_key(
                knowledge_base_id=KB_ID,
                normalized_title_key=invalid_title,
            )

    for invalid_kb_id in (0, -1, True, 7.5, "7"):
        with pytest.raises(InvalidIdentityConflictKey):
            identity_conflict_key(
                knowledge_base_id=invalid_kb_id,
                normalized_title_key="installation guide",
            )


def test_candidate_handle_enforces_body_and_identity_result_shapes():
    body = CandidateHandle(
        decision_type=CandidateDecisionType.KNOWLEDGE_CONFLICT,
        check_id=11,
        candidate_version_id=22,
        created=True,
        blocks_generation_activation=False,
    )
    identity = CandidateHandle(
        decision_type=CandidateDecisionType.PAGE_IDENTITY,
        check_id=33,
        candidate_version_id=None,
        created=False,
        blocks_generation_activation=True,
    )

    assert body.candidate_version_id == 22
    assert identity.candidate_version_id is None

    with pytest.raises(InvalidCandidateHandle):
        CandidateHandle(
            decision_type=CandidateDecisionType.KNOWLEDGE_CONFLICT,
            check_id=1,
            candidate_version_id=None,
            created=True,
            blocks_generation_activation=False,
        )
    with pytest.raises(InvalidCandidateHandle):
        CandidateHandle(
            decision_type=CandidateDecisionType.PAGE_IDENTITY,
            check_id=1,
            candidate_version_id=2,
            created=True,
            blocks_generation_activation=True,
        )
