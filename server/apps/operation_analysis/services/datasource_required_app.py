"""内置 NATS 数据源的 required_app 种子。

精确目录：apps/*/nats 里 @nats_client.register 的函数名 → 实现所在 Django app →
前端 hasAppAccess / get_client 的 app 名。目录未命中时才用受限前缀白名单。
外部源和非内置自定义 NATS 不在这里填写。
"""

from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path

NATS_SOURCE_TYPE = "nats"

# Django app 目录 → get_client 应用名。alerts 对外叫 alarm，系统管理叫 system-manager。
_DJANGO_APP_LICENSE_APP = {
    "alerts": "alarm",
    "cmdb": "cmdb",
    "monitor": "monitor",
    "log": "log",
    "node_mgmt": "node",
    "system_mgmt": "system-manager",
    "operation_analysis": "ops-analysis",
}

# rest_api 前缀 → get_client 应用名。只在精确目录未命中时使用。
_REST_API_PREFIX_LICENSE_APP = {
    "cmdb": "cmdb",
    "monitor": "monitor",
    "alert": "alarm",
    "log": "log",
    "node": "node",
    "job": "job",
    "system_mgmt": "system-manager",
}

_APPS_ROOT = Path(__file__).resolve().parents[2]


def resolve_or_seed_required_app(*, rest_api: str, source_type: str, is_build_in: bool) -> str | None:
    """内置 NATS 源返回模块许可名；推不出或非内置源返回 None。"""
    if not is_build_in or source_type != NATS_SOURCE_TYPE:
        return None
    return _resolve_builtin_nats_required_app(rest_api or "")


def _resolve_builtin_nats_required_app(rest_api: str) -> str | None:
    method = _method_name(rest_api)
    if method:
        licensed = _builtin_nats_method_license_apps().get(method)
        if licensed:
            return licensed
    prefix = _prefix(rest_api)
    if prefix:
        return _REST_API_PREFIX_LICENSE_APP.get(prefix)
    return None


def _method_name(rest_api: str) -> str:
    text = (rest_api or "").strip()
    if "/" not in text:
        return text
    return text.split("/", 1)[1].strip()


def _prefix(rest_api: str) -> str | None:
    text = (rest_api or "").strip()
    if "/" not in text:
        return None
    prefix = text.split("/", 1)[0].strip()
    return prefix or None


@lru_cache(maxsize=1)
def _builtin_nats_method_license_apps() -> dict[str, str]:
    owners: dict[str, set[str]] = {}
    for path in _iter_nats_modules():
        license_app = _license_app_for_path(path)
        if not license_app:
            continue
        for method in _registered_methods(path):
            owners.setdefault(method, set()).add(license_app)
    resolved: dict[str, str] = {}
    for method, apps in owners.items():
        if len(apps) == 1:
            resolved[method] = next(iter(apps))
    return resolved


def _iter_nats_modules():
    for nats_dir in _APPS_ROOT.glob("*/nats"):
        if not nats_dir.is_dir():
            continue
        for path in nats_dir.rglob("*.py"):
            if "tests" in path.parts or path.name == "__init__.py":
                continue
            yield path


def _license_app_for_path(path: Path) -> str | None:
    try:
        relative = path.relative_to(_APPS_ROOT)
    except ValueError:
        return None
    if not relative.parts:
        return None
    return _DJANGO_APP_LICENSE_APP.get(relative.parts[0])


def _registered_methods(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError, UnicodeError):
        return []
    methods: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            method = _decorator_method_name(decorator, node.name)
            if method:
                methods.append(method)
                break
    return methods


def _decorator_method_name(decorator: ast.AST, fallback: str) -> str | None:
    if isinstance(decorator, ast.Call):
        if not _is_nats_register(decorator.func):
            return None
        for keyword in decorator.keywords:
            if keyword.arg == "name" and isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                return keyword.value.value.strip() or fallback
        if decorator.args and isinstance(decorator.args[0], ast.Constant) and isinstance(decorator.args[0].value, str):
            explicit = decorator.args[0].value.strip()
            return explicit or fallback
        return fallback
    if _is_nats_register(decorator):
        return fallback
    return None


def _is_nats_register(node: ast.AST) -> bool:
    if isinstance(node, ast.Attribute) and node.attr == "register":
        return isinstance(node.value, ast.Name) and node.value.id == "nats_client"
    return isinstance(node, ast.Name) and node.id == "register"
