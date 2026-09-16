"""Load builtin execute_parameters and UI field allowlists from support-files."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from django.conf import settings

from apps.monitor.constants.plugin import PluginConstants
from apps.node_mgmt.management.services.node_init.collector_init import COMMUNITY_PLUGIN_DIRECTORY, ENTERPRISE_PLUGIN_DIRECTORY
from apps.node_mgmt.management.services.node_init.definition_loader import load_definition_records

FLAG_RE = re.compile(r"(--[A-Za-z0-9][A-Za-z0-9._-]*)")
ENV_RE = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")
LISTEN_RE = re.compile(r"--web\.listen-address(?:\s+|=)(\S+)", re.IGNORECASE)


def _repo_path(*parts) -> Path:
    return Path(settings.BASE_DIR).joinpath(*parts)


def load_builtin_collectors(name: str) -> list[dict]:
    records = load_definition_records(COMMUNITY_PLUGIN_DIRECTORY, ENTERPRISE_PLUGIN_DIRECTORY)
    return [item for item in records if item.get("name") == name]


def _iter_plugin_dirs():
    roots = [
        _repo_path(PluginConstants.DIRECTORY),
        _repo_path(PluginConstants.ENTERPRISE_DIRECTORY),
    ]
    for root in roots:
        if not root.exists():
            continue
        for metrics in root.rglob("metrics.json"):
            yield metrics.parent


@lru_cache(maxsize=64)
def load_builtin_plugin_files(collector: str) -> dict:
    for plugin_dir in _iter_plugin_dirs():
        metrics_path = plugin_dir / "metrics.json"
        try:
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if str(metrics.get("plugin") or "") != collector and str(metrics.get("collector") or "") != collector:
            continue
        ui_path = plugin_dir / "UI.json"
        ui = {}
        if ui_path.exists():
            try:
                ui = json.loads(ui_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                ui = {}
        return {"dir": plugin_dir, "metrics": metrics, "ui": ui}
    return {}


def extract_flags(text: str) -> set[str]:
    return set(FLAG_RE.findall(text or ""))


def extract_env_vars(text: str) -> set[str]:
    return set(ENV_RE.findall(text or ""))


def _ui_transform_values(ui: dict) -> set[str]:
    values = set()
    for field in ui.get("form_fields") or []:
        for key in ("transform_on_create", "transform_on_edit"):
            mapping = (field.get(key) or {}).get("mapping") or {}
            if isinstance(mapping, dict):
                for value in mapping.values():
                    if isinstance(value, str):
                        values.add(value)
                        values.update(extract_flags(value))
                    elif isinstance(value, list):
                        for item in value:
                            if isinstance(item, str):
                                values.add(item)
                                values.update(extract_flags(item))
            to_api = ((field.get(key) or {}).get("to_api") or {}).get("mapping") or {}
            if isinstance(to_api, dict):
                for value in to_api.values():
                    if isinstance(value, str):
                        values.add(value)
                        values.update(extract_flags(value))
    return {item for item in values if item}


def builtin_allowlist(collector: str) -> dict:
    collectors = load_builtin_collectors(collector)
    plugin_files = load_builtin_plugin_files(collector)
    ui = plugin_files.get("ui") or {}
    flags = set()
    env_vars = set()
    params_by_slot = {}
    for item in collectors:
        params = item.get("execute_parameters") or ""
        flags.update(extract_flags(params))
        env_vars.update(extract_env_vars(params))
        key = (item.get("node_operating_system"), item.get("cpu_architecture") or "x86_64")
        params_by_slot[key] = params
    flags.update(extract_flags(" ".join(_ui_transform_values(ui))))
    field_names = {str(field.get("name") or "") for field in ui.get("form_fields") or [] if field.get("name")}
    return {
        "flags": flags,
        "env_vars": env_vars,
        "form_fields": field_names,
        "ui": ui,
        "params_by_slot": params_by_slot,
        "plugin_files": plugin_files,
        "collectors": collectors,
    }
