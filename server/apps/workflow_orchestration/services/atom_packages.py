from __future__ import annotations

import copy
import importlib
import json
import re
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from django.db import transaction
from jsonschema import Draft202012Validator, SchemaError

from apps.workflow_orchestration.models import AtomDefinition
from apps.workflow_orchestration.services.capability_profiles import materialize_capability_contract

CUSTOM_KEY = re.compile(r"^custom\.[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
PLATFORM_KEY = re.compile(r"^bklite_[a-z][a-z0-9_]*$")
DEFAULT_PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "atom_packages"


class AtomPackageError(ValueError):
    pass


PACKAGE_HANDLERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {}
PACKAGE_MANIFESTS: dict[str, dict[str, Any]] = {}


def _json_file(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AtomPackageError(f"{label} 无法读取") from error
    if not isinstance(value, dict):
        raise AtomPackageError(f"{label} 必须是 JSON 对象")
    return value


def _package_file(package_dir: Path, value: str, label: str) -> Path:
    base = package_dir.resolve()
    candidate = (package_dir / value).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as error:
        raise AtomPackageError(f"{label} 必须位于原子包目录内") from error
    return candidate


def _schema(package_dir: Path, value: Any, label: str) -> dict[str, Any]:
    schema = _json_file(_package_file(package_dir, value, label), label) if isinstance(value, str) else value
    if not isinstance(schema, dict):
        raise AtomPackageError(f"{label} 必须是 JSON Schema 对象")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as error:
        raise AtomPackageError(f"{label} 非法") from error
    return schema


def _object(package_dir: Path, value: Any, label: str) -> dict[str, Any]:
    result = _json_file(_package_file(package_dir, value, label), label) if isinstance(value, str) else value
    if not isinstance(result, dict):
        raise AtomPackageError(f"{label} 必须是 JSON 对象")
    return result


def _handler(value: Any) -> Callable[[dict[str, Any]], dict[str, Any]]:
    module_name, separator, attribute = str(value or "").partition(":")
    if not separator or not module_name.startswith("apps.") or not attribute:
        raise AtomPackageError("WORKER handler 必须是 apps.*:callable")
    try:
        candidate = getattr(importlib.import_module(module_name), attribute)
    except (ImportError, AttributeError) as error:
        raise AtomPackageError("WORKER handler 不存在") from error
    if not callable(candidate):
        raise AtomPackageError("WORKER handler 必须可调用")
    return candidate


def _http_config(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise AtomPackageError("HTTP 配置必须是 JSON 对象")
    url = str(value.get("url") or "").strip()
    method = str(value.get("method") or "GET").strip().upper()
    parsed = urlparse(url)
    if not url or len(url) > 2000 or parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise AtomPackageError("HTTP 原子必须声明 method 和绝对 URL")
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        raise AtomPackageError("HTTP method 非法")
    return {"url": url, "method": method}


def _bounded_string(value: Any, *, label: str, maximum: int, required: bool = True) -> str:
    normalized = str(value or "").strip()
    if (required and not normalized) or len(normalized) > maximum:
        raise AtomPackageError(f"{label} 非法")
    return normalized


def _string_list(value: Any, *, label: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 50 or not all(isinstance(item, str) and item.strip() and len(item) <= 100 for item in value):
        raise AtomPackageError(f"{label} 必须是有界字符串数组")
    return list(dict.fromkeys(item.strip() for item in value))


def _normalize_manifest(path: Path, *, allow_platform: bool) -> dict[str, Any]:  # noqa: C901
    manifest = _json_file(path, "bk-atom.json")
    source_type = str(manifest.get("source_type") or AtomDefinition.SourceType.PACKAGE).upper()
    if source_type not in {AtomDefinition.SourceType.PLATFORM, AtomDefinition.SourceType.PACKAGE}:
        raise AtomPackageError("source_type 只能是 PLATFORM 或 PACKAGE")
    if source_type == AtomDefinition.SourceType.PLATFORM and not allow_platform:
        raise AtomPackageError("PLATFORM 原子只能来自内置原子包目录")
    key = str(manifest.get("key") or "").strip()
    key_pattern = PLATFORM_KEY if source_type == AtomDefinition.SourceType.PLATFORM else CUSTOM_KEY
    if not key_pattern.fullmatch(key):
        expected = "bklite_*" if source_type == AtomDefinition.SourceType.PLATFORM else "custom.*"
        raise AtomPackageError(f"key 必须是 {expected} 稳定标识")
    driver = str(manifest.get("driver") or "").strip().upper()
    if driver not in {"WORKER", "HTTP"}:
        raise AtomPackageError("driver 只能是 WORKER 或 HTTP")
    input_schema = _schema(path.parent, manifest.get("input_schema"), "input_schema")
    output_schema = _schema(path.parent, manifest.get("output_schema"), "output_schema")
    ui_schema = _object(path.parent, manifest.get("ui_schema", {}), "ui_schema")
    try:
        input_schema, ui_schema = materialize_capability_contract(input_schema, ui_schema)
    except ValueError as error:
        raise AtomPackageError(str(error)) from error
    handler_path = str(manifest.get("handler") or "").strip()
    handler = _handler(handler_path) if driver == "WORKER" else None
    http = _http_config(manifest.get("http")) if driver == "HTTP" else None
    name = _bounded_string(manifest.get("name"), label="name", maximum=120)
    category = _bounded_string(manifest.get("category"), label="category", maximum=80)
    description = _bounded_string(manifest.get("description"), label="description", maximum=500, required=False)
    timeout = manifest.get("timeout_seconds", 600)
    retry_count = manifest.get("retry_count", 0)
    retry_delay = manifest.get("retry_delay_seconds", 5)
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 3900:
        raise AtomPackageError("timeout_seconds 必须在 1 到 3900 之间")
    if isinstance(retry_count, bool) or not isinstance(retry_count, int) or not 0 <= retry_count <= 5:
        raise AtomPackageError("retry_count 必须在 0 到 5 之间")
    if isinstance(retry_delay, bool) or not isinstance(retry_delay, int) or not 0 <= retry_delay <= 120:
        raise AtomPackageError("retry_delay_seconds 必须在 0 到 120 之间")
    safety_level = str(manifest.get("safety_level") or "READ_ONLY").upper()
    if safety_level not in {"READ_ONLY", "MUTATION"}:
        raise AtomPackageError("safety_level 非法")
    resource_scope = str(manifest.get("resource_scope") or "ORGANIZATION").upper()
    if resource_scope not in {"ORGANIZATION", "NODE_INPUT"}:
        raise AtomPackageError("resource_scope 非法")
    trusted_context = manifest.get("trusted_context", False)
    if not isinstance(trusted_context, bool):
        raise AtomPackageError("trusted_context 必须是布尔值")
    catalog_visible = manifest.get("catalog_visible", True)
    if not isinstance(catalog_visible, bool):
        raise AtomPackageError("catalog_visible 必须是布尔值")
    normalized = {
        "key": key,
        "name": name,
        "category": category,
        "description": description,
        "source_type": source_type,
        "trusted_context": trusted_context,
        "catalog_visible": catalog_visible,
        "driver": driver,
        "handler": handler_path if driver == "WORKER" else "",
        "handler_callable": handler,
        "http": http,
        "input_schema": input_schema,
        "output_schema": output_schema,
        "ui_schema": ui_schema,
        "timeout_seconds": timeout,
        "retry_count": retry_count,
        "retry_delay_seconds": retry_delay,
        "idempotent": bool(manifest.get("idempotent", False)),
        "idempotency_key": _bounded_string(manifest.get("idempotency_key"), label="idempotency_key", maximum=200, required=False),
        "safety_level": safety_level,
        "resource_scope": resource_scope,
        "required_permissions": _string_list(manifest.get("required_permissions"), label="required_permissions"),
        "error_types": _string_list(manifest.get("error_types"), label="error_types"),
    }
    return normalized


def _discover(root: Path | str | None = None) -> list[dict[str, Any]]:
    package_root = Path(root or DEFAULT_PACKAGE_ROOT).resolve()
    if not package_root.exists():
        return []
    allow_platform = package_root == DEFAULT_PACKAGE_ROOT.resolve()
    manifests = [_normalize_manifest(path, allow_platform=allow_platform) for path in sorted(package_root.glob("*/bk-atom.json"))]
    identities: set[str] = set()
    names: dict[str, str] = {}
    for item in manifests:
        identity = item["key"]
        if identity in identities:
            raise AtomPackageError(f"原子 {item['key']} 重复")
        identities.add(identity)
        normalized_name = item["name"].casefold()
        other = names.get(normalized_name)
        if other is not None and other != item["key"]:
            raise AtomPackageError(f"原子名称“{item['name']}”与 {other} 重复")
        names[normalized_name] = item["key"]
    return manifests


def _cache_manifests(manifests: list[dict[str, Any]]) -> None:
    PACKAGE_MANIFESTS.update({item["key"]: item for item in manifests})
    PACKAGE_HANDLERS.update({item["key"]: item["handler_callable"] for item in manifests if item["handler_callable"] is not None})


def load_package_handlers(root: Path | str | None = None) -> dict[str, Callable]:
    manifests = _discover(root)
    _cache_manifests(manifests)
    return {item["key"]: item["handler_callable"] for item in manifests if item["handler_callable"] is not None}


def package_catalog_payload(root: Path | str | None = None) -> list[dict[str, Any]]:
    manifests = _discover(root)
    _cache_manifests(manifests)
    return [
        {
            "key": item["key"],
            "name": item["name"],
            "category": item["category"],
            "description": item["description"],
            "input_schema": copy.deepcopy(item["input_schema"]),
            "output_schema": copy.deepcopy(item["output_schema"]),
            "ui_schema": copy.deepcopy(item["ui_schema"]),
            "driver": item["driver"],
            "execution_config": {
                "handler": item["handler"],
                "http": copy.deepcopy(item["http"]),
            },
            "default_timeout_seconds": item["timeout_seconds"],
            "retry_count": item["retry_count"],
            "retry_delay_seconds": item["retry_delay_seconds"],
            "idempotent": item["idempotent"],
            "idempotency_key": item["idempotency_key"],
            "error_types": copy.deepcopy(item["error_types"]),
            "safety_level": item["safety_level"],
            "required_permissions": copy.deepcopy(item["required_permissions"]),
            "resource_scope": item["resource_scope"],
            "source_type": item["source_type"],
            "catalog_visible": item["catalog_visible"],
            "built_in": False,
        }
        for item in sorted(manifests, key=lambda value: (value["category"], value["name"], value["key"]))
    ]


def package_task_definitions(root: Path | str | None = None) -> list[dict[str, Any]]:
    return [
        {
            "name": item["key"],
            "description": item["description"],
            "retryCount": item["retry_count"],
            "retryLogic": "FIXED",
            "retryDelaySeconds": item["retry_delay_seconds"],
            "timeoutSeconds": item["default_timeout_seconds"],
            "responseTimeoutSeconds": item["default_timeout_seconds"],
        }
        for item in package_catalog_payload(root)
    ]


def execute_package_atom(task_type: str, inputs: dict[str, Any]) -> dict[str, Any]:
    if not PACKAGE_MANIFESTS:
        load_package_handlers()
    manifest = PACKAGE_MANIFESTS.get(task_type)
    payload = copy.deepcopy(inputs)
    handler = PACKAGE_HANDLERS.get(task_type)
    if handler is not None:
        return handler(payload)
    if manifest is not None and manifest["driver"] == "HTTP":
        from apps.workflow_orchestration.atom_packages.http_runtime import execute_http

        return execute_http(payload, fixed=manifest["http"])
    atom = AtomDefinition.objects.filter(key=task_type).first()
    if atom is not None and atom.driver == "HTTP":
        from apps.workflow_orchestration.atom_packages.http_runtime import execute_http

        http = atom.execution_config.get("http")
        if not isinstance(http, dict):
            raise ValueError(f"原子执行配置非法: {task_type}")
        return execute_http(payload, fixed=http)
    raise ValueError(f"原子执行能力未注册: {task_type}")


def atom_requires_trusted_context(task_type: str) -> bool:
    if task_type not in PACKAGE_MANIFESTS:
        load_package_handlers()
    return bool((PACKAGE_MANIFESTS.get(task_type) or {}).get("trusted_context"))


def register_atom_packages(root: Path | str | None = None) -> dict[str, int]:
    """扫描受信任代码目录，幂等同步原子当前兼容契约。"""
    package_root = Path(root or DEFAULT_PACKAGE_ROOT).resolve()
    manifests = _discover(package_root)
    if package_root != DEFAULT_PACKAGE_ROOT.resolve():
        platform_names = {item["name"].casefold(): item["key"] for item in package_catalog_payload()}
        for item in manifests:
            conflict_key = platform_names.get(item["name"].casefold())
            if conflict_key is not None and conflict_key != item["key"]:
                raise AtomPackageError(f"原子名称“{item['name']}”与 {conflict_key} 重复")
    created_atoms = 0
    updated_atoms = 0
    handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {}
    with transaction.atomic():
        for item in manifests:
            conflict = AtomDefinition.objects.filter(name__iexact=item["name"]).exclude(key=item["key"]).first()
            if conflict is not None:
                raise AtomPackageError(f"原子名称“{item['name']}”与 {conflict.key} 重复")
            existing = AtomDefinition.objects.filter(key=item["key"]).only("built_in", "source_type").first()
            if existing is not None and (existing.built_in or existing.source_type != item["source_type"]):
                raise AtomPackageError(f"原子 key 与现有能力冲突: {item['key']}")
            atom, created = AtomDefinition.objects.update_or_create(
                key=item["key"],
                defaults={
                    "name": item["name"],
                    "category": item["category"],
                    "description": item["description"],
                    "driver": item["driver"],
                    "built_in": False,
                    "team": [],
                    "input_schema": item["input_schema"],
                    "output_schema": item["output_schema"],
                    "ui_schema": item["ui_schema"],
                    "execution_config": {
                        "handler": item["handler"],
                        "http": copy.deepcopy(item["http"]),
                    },
                    "default_timeout_seconds": item["timeout_seconds"],
                    "retry_count": item["retry_count"],
                    "retry_delay_seconds": item["retry_delay_seconds"],
                    "idempotent": item["idempotent"],
                    "idempotency_key": item["idempotency_key"],
                    "error_types": item["error_types"],
                    "safety_level": item["safety_level"],
                    "required_permissions": item["required_permissions"],
                    "resource_scope": item["resource_scope"],
                    "source_type": item["source_type"],
                    "created_by": "package-registry",
                    "updated_by": "package-registry",
                },
            )
            created_atoms += int(created)
            updated_atoms += int(not created)
            if item["handler_callable"] is not None:
                handlers[item["key"]] = item["handler_callable"]
    PACKAGE_HANDLERS.update(handlers)
    _cache_manifests(manifests)
    return {
        "packages": len(manifests),
        "created_atoms": created_atoms,
        "updated_atoms": updated_atoms,
    }
