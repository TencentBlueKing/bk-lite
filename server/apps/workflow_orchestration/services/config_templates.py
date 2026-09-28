from __future__ import annotations

import copy
import json
from typing import Any

from apps.workflow_orchestration.services.atom_registry import available_atom_catalog


class AtomConfigTemplateError(ValueError):
    pass


_SKIP = object()
MAX_TEMPLATE_PARAMETERS_BYTES = 64 * 1024


def _without_sensitive_values(value: Any, schema: dict[str, Any]) -> Any:
    if schema.get("sensitive"):
        return _SKIP
    if isinstance(value, dict):
        properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        additional = schema.get("additionalProperties", True)
        result = {}
        for key, item in value.items():
            child_schema = properties.get(key)
            if not isinstance(child_schema, dict):
                child_schema = additional if isinstance(additional, dict) else {}
                if additional is False:
                    continue
            sanitized = _without_sensitive_values(item, child_schema)
            if sanitized is not _SKIP:
                result[key] = sanitized
        return result
    if isinstance(value, list):
        item_schema = schema.get("items") if isinstance(schema.get("items"), dict) else {}
        return [item for raw in value if (item := _without_sensitive_values(raw, item_schema)) is not _SKIP]
    return copy.deepcopy(value)


def sanitize_atom_template_parameters(*, team: int, atom_key: str, parameters: dict[str, Any]) -> dict[str, Any]:
    atom = available_atom_catalog(team).get(atom_key)
    if atom is None:
        raise AtomConfigTemplateError("原子不存在或当前组织无权使用")
    schema = atom.get("input_schema") if isinstance(atom.get("input_schema"), dict) else {}
    sanitized = _without_sensitive_values(parameters, schema)
    if not isinstance(sanitized, dict):
        raise AtomConfigTemplateError("配置模板参数必须是对象")
    encoded = json.dumps(sanitized, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_TEMPLATE_PARAMETERS_BYTES:
        raise AtomConfigTemplateError("配置模板参数不能超过 64 KiB")
    return sanitized
