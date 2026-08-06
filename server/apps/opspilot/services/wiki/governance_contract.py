"""Wiki 目录治理在各迁移阶段的纯领域契约。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping


class DirectoryMigrationState(str, Enum):
    LEGACY = "legacy"
    BACKFILLING = "backfilling"
    READY = "ready"
    ENABLED = "enabled"


class StructureTruthSource(str, Enum):
    LEGACY_SCHEMA_CONFIG = "legacy_schema_config"
    ACTIVE_STRUCTURE_REVISION = "active_structure_revision"


class KnowledgeTruthSource(str, Enum):
    LEGACY_FLAT_CURRENT_VERSION = "legacy_flat_current_version"
    ACTIVE_GENERATION_MEMBER_VERSION_SNAPSHOT = "active_generation_member_version_snapshot"


class ReadRoute(str, Enum):
    LEGACY_FLAT_CURRENT_VERSION = "legacy_flat_current_version"
    ACTIVE_GENERATION = "active_generation"
    LEGACY_DERIVED_MIRROR = "legacy_derived_mirror"


class PublicWriteKind(str, Enum):
    STRUCTURE = "structure"
    PAGE = "page"
    BUILD = "build"


class WriteRoute(str, Enum):
    LEGACY = "legacy"
    RETRYABLE_FENCE = "retryable_fence"
    GENERATION_AWARE_CAS = "generation_aware_cas"
    INTERNAL_IDEMPOTENT_BACKFILL = "internal_idempotent_backfill"
    FORBIDDEN = "forbidden"


class DirectoryUiRoute(str, Enum):
    LEGACY_FLAT = "legacy_flat"
    LEGACY_COMPATIBILITY_MIRROR = "legacy_compatibility_mirror"
    DIRECTORY_TREE = "directory_tree"


class UnknownMigrationState(ValueError):
    pass


class InvalidMigrationStateTransition(ValueError):
    pass


@dataclass(frozen=True)
class GovernanceContract:
    state: DirectoryMigrationState
    structure_truth: StructureTruthSource
    generation_truth: KnowledgeTruthSource
    page_truth: KnowledgeTruthSource
    canonical_read_route: ReadRoute
    compatibility_read_route: ReadRoute | None
    public_write_routes: Mapping[PublicWriteKind, WriteRoute]
    internal_backfill_write_route: WriteRoute


@dataclass(frozen=True)
class DirectoryUiPresentation:
    migration_state: DirectoryMigrationState
    route: DirectoryUiRoute


def _public_routes(route: WriteRoute) -> Mapping[PublicWriteKind, WriteRoute]:
    return MappingProxyType({kind: route for kind in PublicWriteKind})


_STATE_ORDER = (
    DirectoryMigrationState.LEGACY,
    DirectoryMigrationState.BACKFILLING,
    DirectoryMigrationState.READY,
    DirectoryMigrationState.ENABLED,
)

_CONTRACTS = MappingProxyType(
    {
        DirectoryMigrationState.LEGACY: GovernanceContract(
            state=DirectoryMigrationState.LEGACY,
            structure_truth=StructureTruthSource.LEGACY_SCHEMA_CONFIG,
            generation_truth=KnowledgeTruthSource.LEGACY_FLAT_CURRENT_VERSION,
            page_truth=KnowledgeTruthSource.LEGACY_FLAT_CURRENT_VERSION,
            canonical_read_route=ReadRoute.LEGACY_FLAT_CURRENT_VERSION,
            compatibility_read_route=None,
            public_write_routes=_public_routes(WriteRoute.LEGACY),
            internal_backfill_write_route=WriteRoute.FORBIDDEN,
        ),
        DirectoryMigrationState.BACKFILLING: GovernanceContract(
            state=DirectoryMigrationState.BACKFILLING,
            structure_truth=StructureTruthSource.LEGACY_SCHEMA_CONFIG,
            generation_truth=KnowledgeTruthSource.LEGACY_FLAT_CURRENT_VERSION,
            page_truth=KnowledgeTruthSource.LEGACY_FLAT_CURRENT_VERSION,
            canonical_read_route=ReadRoute.LEGACY_FLAT_CURRENT_VERSION,
            compatibility_read_route=None,
            public_write_routes=_public_routes(WriteRoute.RETRYABLE_FENCE),
            internal_backfill_write_route=WriteRoute.INTERNAL_IDEMPOTENT_BACKFILL,
        ),
        DirectoryMigrationState.READY: GovernanceContract(
            state=DirectoryMigrationState.READY,
            structure_truth=StructureTruthSource.ACTIVE_STRUCTURE_REVISION,
            generation_truth=KnowledgeTruthSource.ACTIVE_GENERATION_MEMBER_VERSION_SNAPSHOT,
            page_truth=KnowledgeTruthSource.ACTIVE_GENERATION_MEMBER_VERSION_SNAPSHOT,
            canonical_read_route=ReadRoute.ACTIVE_GENERATION,
            compatibility_read_route=ReadRoute.LEGACY_DERIVED_MIRROR,
            public_write_routes=_public_routes(WriteRoute.GENERATION_AWARE_CAS),
            internal_backfill_write_route=WriteRoute.FORBIDDEN,
        ),
        DirectoryMigrationState.ENABLED: GovernanceContract(
            state=DirectoryMigrationState.ENABLED,
            structure_truth=StructureTruthSource.ACTIVE_STRUCTURE_REVISION,
            generation_truth=KnowledgeTruthSource.ACTIVE_GENERATION_MEMBER_VERSION_SNAPSHOT,
            page_truth=KnowledgeTruthSource.ACTIVE_GENERATION_MEMBER_VERSION_SNAPSHOT,
            canonical_read_route=ReadRoute.ACTIVE_GENERATION,
            compatibility_read_route=ReadRoute.LEGACY_DERIVED_MIRROR,
            public_write_routes=_public_routes(WriteRoute.GENERATION_AWARE_CAS),
            internal_backfill_write_route=WriteRoute.FORBIDDEN,
        ),
    }
)


def _migration_state(value: DirectoryMigrationState | str) -> DirectoryMigrationState:
    if isinstance(value, DirectoryMigrationState):
        return value
    try:
        return DirectoryMigrationState(value)
    except (TypeError, ValueError) as error:
        raise UnknownMigrationState(f"Unknown directory migration state: {value!r}") from error


def contract_for(state: DirectoryMigrationState | str) -> GovernanceContract:
    return _CONTRACTS[_migration_state(state)]


def advance_migration_state(
    current: DirectoryMigrationState | str,
    target: DirectoryMigrationState | str,
) -> DirectoryMigrationState:
    current_state = _migration_state(current)
    target_state = _migration_state(target)
    current_index = _STATE_ORDER.index(current_state)
    target_index = _STATE_ORDER.index(target_state)

    if target_index not in (current_index, current_index + 1):
        raise InvalidMigrationStateTransition(f"Cannot transition from {current_state.value} to {target_state.value}")
    return target_state


def resolve_directory_ui(
    state: DirectoryMigrationState | str,
    *,
    requested_enabled: bool,
) -> DirectoryUiPresentation:
    migration_state = _migration_state(state)
    if migration_state is DirectoryMigrationState.ENABLED and requested_enabled:
        route = DirectoryUiRoute.DIRECTORY_TREE
    elif migration_state in (DirectoryMigrationState.READY, DirectoryMigrationState.ENABLED):
        route = DirectoryUiRoute.LEGACY_COMPATIBILITY_MIRROR
    else:
        route = DirectoryUiRoute.LEGACY_FLAT
    return DirectoryUiPresentation(migration_state=migration_state, route=route)
