from __future__ import annotations

import copy
from typing import Any


class CapabilityProfileError(ValueError):
    pass


def materialize_capability_contract(
    input_schema: dict[str, Any],
    ui_schema: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """MVP 不再内置业务能力方案，原子契约由原子包自身声明。"""
    return copy.deepcopy(input_schema), copy.deepcopy(ui_schema)


def resolve_capability_input_schema(catalog_item: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    del inputs
    return copy.deepcopy(catalog_item.get("input_schema") or {})


def capability_resource_snapshot(
    definition: dict[str, Any],
    atom_catalog: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    del definition, atom_catalog
    return []
