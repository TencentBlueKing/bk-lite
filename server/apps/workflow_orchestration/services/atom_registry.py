from __future__ import annotations

import copy
import re
from typing import Any

from django.db import transaction
from django.db.models import Q

from apps.core.utils.viewset_utils import build_json_membership_query
from apps.workflow_orchestration.models import AtomDefinition

ATOM_KEY = re.compile(r"^custom\.[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")


class AtomRegistryError(ValueError):
    pass


def validate_atom_name_available(*, key: str, name: str) -> None:
    conflict = AtomDefinition.objects.filter(name__iexact=name).exclude(key=key).only("key").first()
    if conflict is not None:
        raise AtomRegistryError(f"原子名称“{name}”与 {conflict.key} 重复")

    from apps.workflow_orchestration.services.atom_packages import package_catalog_payload
    from apps.workflow_orchestration.services.system_nodes import system_node_catalog_payload

    normalized_name = name.casefold()
    conflict = next(
        (
            item
            for item in [*package_catalog_payload(), *system_node_catalog_payload()]
            if item["key"] != key and item["name"].casefold() == normalized_name
        ),
        None,
    )
    if conflict is not None:
        raise AtomRegistryError(f"原子名称“{name}”与 {conflict['key']} 重复")


def available_atom_catalog(team: int) -> dict[str, dict[str, Any]]:
    """Merge platform nodes with immutable R&D packages for one organization."""
    from apps.workflow_orchestration.services.atom_packages import package_catalog_payload

    catalog = {item["key"]: {**item, "built_in": False} for item in package_catalog_payload() if item.get("catalog_visible", True)}
    queryset = (
        AtomDefinition.objects.filter(source_type=AtomDefinition.SourceType.PACKAGE)
        .exclude(key__in=catalog)
        .filter(Q(team=[]) | build_json_membership_query(AtomDefinition.objects.all(), "team", [team]))
    )
    for atom in queryset:
        catalog[atom.key] = {
            "key": atom.key,
            "name": atom.name,
            "category": atom.category,
            "description": atom.description,
            "input_schema": copy.deepcopy(atom.input_schema),
            "output_schema": copy.deepcopy(atom.output_schema),
            "ui_schema": copy.deepcopy(atom.ui_schema),
            "driver": atom.driver,
            "execution_config": copy.deepcopy(atom.execution_config),
            "built_in": False,
            "default_timeout_seconds": atom.default_timeout_seconds,
            "retry_count": atom.retry_count,
            "retry_delay_seconds": atom.retry_delay_seconds,
            "idempotent": atom.idempotent,
            "idempotency_key": atom.idempotency_key,
            "error_types": copy.deepcopy(atom.error_types),
            "safety_level": atom.safety_level,
            "required_permissions": copy.deepcopy(atom.required_permissions),
            "resource_scope": atom.resource_scope,
            "source_type": atom.source_type,
        }
    from apps.workflow_orchestration.services.business_options import materialize_business_options
    from apps.workflow_orchestration.services.opspilot_atoms import materialize_opspilot_options

    materialize_opspilot_options(catalog, team)
    materialize_business_options(catalog, team)
    return catalog


def task_definition_from_catalog_item(item: dict[str, Any]) -> dict[str, Any]:
    if item.get("built_in"):
        raise AtomRegistryError("内置原子使用静态 Task Definition")
    return {
        "name": item["key"],
        "description": item["description"],
        "retryCount": item["retry_count"],
        "retryLogic": "FIXED",
        "retryDelaySeconds": item["retry_delay_seconds"],
        "timeoutSeconds": item["default_timeout_seconds"],
        "responseTimeoutSeconds": item["default_timeout_seconds"],
    }


@transaction.atomic
def ensure_platform_atom(
    item: dict[str, Any],
    *,
    username: str,
    domain: str,
) -> AtomDefinition:
    validate_atom_name_available(key=item["key"], name=item["name"])
    atom, _ = AtomDefinition.objects.update_or_create(
        key=item["key"],
        defaults={
            "name": item["name"],
            "category": item["category"],
            "description": item["description"],
            "driver": item["driver"],
            "built_in": False,
            "source_type": AtomDefinition.SourceType.PLATFORM,
            "team": [],
            "input_schema": copy.deepcopy(item.get("input_schema") or {}),
            "output_schema": copy.deepcopy(item.get("output_schema") or {}),
            "ui_schema": copy.deepcopy(item.get("ui_schema") or {}),
            "execution_config": copy.deepcopy(item.get("execution_config") or {}),
            "default_timeout_seconds": item.get("default_timeout_seconds", 600),
            "retry_count": item.get("retry_count", 0),
            "retry_delay_seconds": item.get("retry_delay_seconds", 5),
            "idempotent": item.get("idempotent", False),
            "idempotency_key": item.get("idempotency_key", ""),
            "error_types": item.get("error_types") or [],
            "safety_level": item.get("safety_level", "MUTATION"),
            "required_permissions": item.get("required_permissions") or [],
            "resource_scope": item.get("resource_scope", "ORGANIZATION"),
            "updated_by": username,
            "updated_by_domain": domain,
        },
    )
    return atom
