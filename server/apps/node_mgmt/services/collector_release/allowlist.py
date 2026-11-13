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


def _plugin_roots() -> list[Path]:
    roots = [
        _repo_path(PluginConstants.DIRECTORY),
        _repo_path(PluginConstants.ENTERPRISE_DIRECTORY),
    ]
    return [root for root in roots if root.exists()]


def _iter_plugin_dirs():
    for root in _plugin_roots():
        for metrics in root.rglob("metrics.json"):
            yield metrics.parent


def _load_plugin_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _metrics_names_collector(metrics: dict, collector: str) -> bool:
    return str(metrics.get("plugin") or "") == collector or str(metrics.get("collector") or "") == collector


def _plugin_under_collector_dir(plugin_dir: Path, collector: str) -> bool:
    for root in _plugin_roots():
        try:
            relative = plugin_dir.relative_to(root)
        except ValueError:
            continue
        return bool(relative.parts) and relative.parts[0] == collector
    return False


def _form_field_names(ui: dict) -> set[str]:
    return {str(field.get("name") or "") for field in ui.get("form_fields") or [] if field.get("name")}


@lru_cache(maxsize=64)
def load_builtin_plugin_files(collector: str) -> dict:
    """导出仍取第一份 metrics.plugin/collector 同名的插件，避免发行包改绑到别的 UI。"""
    for plugin_dir in _iter_plugin_dirs():
        metrics = _load_plugin_json(plugin_dir / "metrics.json")
        if not metrics:
            continue
        if not _metrics_names_collector(metrics, collector):
            continue
        return {"dir": plugin_dir, "metrics": metrics, "ui": _load_plugin_json(plugin_dir / "UI.json")}
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
    # 只有 Telegraf 包合并同目录全部内置插件。Host 等插件的 metrics.plugin 不是 Telegraf，
    # 但 UI 随 Telegraf 包导入。其他采集器仍只认第一份同名 UI。
    uis = []
    if collector == "Telegraf":
        for plugin_dir in _iter_plugin_dirs():
            metrics = _load_plugin_json(plugin_dir / "metrics.json")
            if not metrics:
                continue
            if not (_metrics_names_collector(metrics, collector) or _plugin_under_collector_dir(plugin_dir, collector)):
                continue
            uis.append(_load_plugin_json(plugin_dir / "UI.json"))
    else:
        uis.append(ui)
    field_names = set()
    for plugin_ui in uis:
        field_names.update(_form_field_names(plugin_ui))
        flags.update(extract_flags(" ".join(_ui_transform_values(plugin_ui))))
    return {
        "flags": flags,
        "env_vars": env_vars,
        "form_fields": field_names,
        "ui": ui,
        "params_by_slot": params_by_slot,
        "plugin_files": plugin_files,
        "collectors": collectors,
    }
