from types import MappingProxyType

import pytest

from apps.opspilot.services.wiki.governance_contract import (
    DirectoryMigrationState,
    DirectoryUiRoute,
    InvalidMigrationStateTransition,
    KnowledgeTruthSource,
    PublicWriteKind,
    ReadRoute,
    StructureTruthSource,
    UnknownMigrationState,
    WriteRoute,
    advance_migration_state,
    contract_for,
    resolve_directory_ui,
)


@pytest.mark.parametrize(
    ("state", "structure_truth", "knowledge_truth", "canonical_read", "write_route"),
    [
        (
            DirectoryMigrationState.LEGACY,
            StructureTruthSource.LEGACY_SCHEMA_CONFIG,
            KnowledgeTruthSource.LEGACY_FLAT_CURRENT_VERSION,
            ReadRoute.LEGACY_FLAT_CURRENT_VERSION,
            WriteRoute.LEGACY,
        ),
        (
            DirectoryMigrationState.BACKFILLING,
            StructureTruthSource.LEGACY_SCHEMA_CONFIG,
            KnowledgeTruthSource.LEGACY_FLAT_CURRENT_VERSION,
            ReadRoute.LEGACY_FLAT_CURRENT_VERSION,
            WriteRoute.RETRYABLE_FENCE,
        ),
        (
            DirectoryMigrationState.READY,
            StructureTruthSource.ACTIVE_STRUCTURE_REVISION,
            KnowledgeTruthSource.ACTIVE_GENERATION_MEMBER_VERSION_SNAPSHOT,
            ReadRoute.ACTIVE_GENERATION,
            WriteRoute.GENERATION_AWARE_CAS,
        ),
        (
            DirectoryMigrationState.ENABLED,
            StructureTruthSource.ACTIVE_STRUCTURE_REVISION,
            KnowledgeTruthSource.ACTIVE_GENERATION_MEMBER_VERSION_SNAPSHOT,
            ReadRoute.ACTIVE_GENERATION,
            WriteRoute.GENERATION_AWARE_CAS,
        ),
    ],
)
def test_state_contract_freezes_truth_reads_and_all_public_write_routes(
    state,
    structure_truth,
    knowledge_truth,
    canonical_read,
    write_route,
):
    contract = contract_for(state)

    assert contract.structure_truth is structure_truth
    assert contract.generation_truth is knowledge_truth
    assert contract.page_truth is knowledge_truth
    assert contract.canonical_read_route is canonical_read
    assert contract.public_write_routes == {
        PublicWriteKind.STRUCTURE: write_route,
        PublicWriteKind.PAGE: write_route,
        PublicWriteKind.BUILD: write_route,
    }
    assert isinstance(contract.public_write_routes, MappingProxyType)


def test_only_legacy_allows_legacy_public_writes():
    assert all(route is WriteRoute.LEGACY for route in contract_for(DirectoryMigrationState.LEGACY).public_write_routes.values())

    for state in (
        DirectoryMigrationState.BACKFILLING,
        DirectoryMigrationState.READY,
        DirectoryMigrationState.ENABLED,
    ):
        assert WriteRoute.LEGACY not in contract_for(state).public_write_routes.values()


def test_backfilling_fences_public_writes_but_allows_only_internal_idempotent_backfill():
    backfilling = contract_for(DirectoryMigrationState.BACKFILLING)

    assert set(backfilling.public_write_routes.values()) == {WriteRoute.RETRYABLE_FENCE}
    assert backfilling.internal_backfill_write_route is WriteRoute.INTERNAL_IDEMPOTENT_BACKFILL

    for state in (
        DirectoryMigrationState.LEGACY,
        DirectoryMigrationState.READY,
        DirectoryMigrationState.ENABLED,
    ):
        assert contract_for(state).internal_backfill_write_route is WriteRoute.FORBIDDEN


@pytest.mark.parametrize("state", [DirectoryMigrationState.READY, DirectoryMigrationState.ENABLED])
def test_generation_states_expose_legacy_flat_reads_only_as_a_derived_mirror(state):
    contract = contract_for(state)

    assert contract.canonical_read_route is ReadRoute.ACTIVE_GENERATION
    assert contract.compatibility_read_route is ReadRoute.LEGACY_DERIVED_MIRROR
    assert contract.compatibility_read_route is not contract.canonical_read_route


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (DirectoryMigrationState.LEGACY, DirectoryMigrationState.LEGACY),
        (DirectoryMigrationState.LEGACY, DirectoryMigrationState.BACKFILLING),
        (DirectoryMigrationState.BACKFILLING, DirectoryMigrationState.BACKFILLING),
        (DirectoryMigrationState.BACKFILLING, DirectoryMigrationState.READY),
        (DirectoryMigrationState.READY, DirectoryMigrationState.READY),
        (DirectoryMigrationState.READY, DirectoryMigrationState.ENABLED),
        (DirectoryMigrationState.ENABLED, DirectoryMigrationState.ENABLED),
    ],
)
def test_migration_state_allows_only_same_state_or_next_state(current, target):
    assert advance_migration_state(current, target) is target


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (DirectoryMigrationState.LEGACY, DirectoryMigrationState.READY),
        (DirectoryMigrationState.LEGACY, DirectoryMigrationState.ENABLED),
        (DirectoryMigrationState.BACKFILLING, DirectoryMigrationState.ENABLED),
        (DirectoryMigrationState.BACKFILLING, DirectoryMigrationState.LEGACY),
        (DirectoryMigrationState.READY, DirectoryMigrationState.BACKFILLING),
        (DirectoryMigrationState.ENABLED, DirectoryMigrationState.READY),
    ],
)
def test_migration_state_rejects_skips_and_regressions(current, target):
    with pytest.raises(InvalidMigrationStateTransition):
        advance_migration_state(current, target)


def test_disabling_directory_ui_keeps_enabled_truth_and_writes_monotonic():
    presentation = resolve_directory_ui(DirectoryMigrationState.ENABLED, requested_enabled=False)

    assert presentation.migration_state is DirectoryMigrationState.ENABLED
    assert presentation.route is DirectoryUiRoute.LEGACY_COMPATIBILITY_MIRROR
    assert contract_for(presentation.migration_state).canonical_read_route is ReadRoute.ACTIVE_GENERATION
    assert set(contract_for(presentation.migration_state).public_write_routes.values()) == {WriteRoute.GENERATION_AWARE_CAS}


def test_directory_tree_ui_is_available_only_for_enabled_state_with_the_toggle_on():
    assert resolve_directory_ui(DirectoryMigrationState.ENABLED, requested_enabled=True).route is DirectoryUiRoute.DIRECTORY_TREE
    assert resolve_directory_ui(DirectoryMigrationState.READY, requested_enabled=True).route is DirectoryUiRoute.LEGACY_COMPATIBILITY_MIRROR


def test_unknown_states_fail_closed_instead_of_falling_back_to_legacy():
    with pytest.raises(UnknownMigrationState):
        contract_for("unknown")

    with pytest.raises(UnknownMigrationState):
        advance_migration_state("unknown", DirectoryMigrationState.LEGACY)


def test_public_write_route_mapping_is_immutable():
    routes = contract_for(DirectoryMigrationState.LEGACY).public_write_routes

    with pytest.raises(TypeError):
        routes[PublicWriteKind.PAGE] = WriteRoute.GENERATION_AWARE_CAS
