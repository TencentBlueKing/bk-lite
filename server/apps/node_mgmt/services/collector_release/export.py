"""Build an official layered collector release zip from builtin plugin files."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

from apps.monitor.management.utils import parse_template_filename
from apps.node_mgmt.services.collector_release.allowlist import load_builtin_collectors, load_builtin_plugin_files
from apps.node_mgmt.services.collector_release.constants import CollectorReleaseConstants as C
from apps.node_mgmt.utils.architecture import normalize_cpu_architecture


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def artifact_zip_name(os_name: str, arch: str) -> str:
    name = f"artifacts/{os_name}/{arch}"
    if os_name == "windows":
        name += ".exe"
    return name


def build_release_zip(
    *,
    collector: str,
    version: str,
    artifacts: dict[tuple[str, str], Path],
    execute_parameters: str | None = None,
) -> bytes:
    plugin_files = load_builtin_plugin_files(collector)
    if not plugin_files:
        raise ValueError(f"未找到内置插件 {collector}")
    plugin_dir: Path = plugin_files["dir"]
    collectors = load_builtin_collectors(collector)
    if not collectors:
        raise ValueError(f"未找到内置采集器 {collector}")

    metrics = plugin_files.get("metrics") or {}
    ui = plugin_files.get("ui") or {}
    collect_type = str(ui.get("collect_type") or metrics.get("collect_type") or plugin_dir.parent.name)
    params = execute_parameters
    if params is None:
        params = collectors[0].get("execute_parameters") or ""

    metrics_bytes = (plugin_dir / "metrics.json").read_bytes()
    ui_bytes = (plugin_dir / "UI.json").read_bytes() if (plugin_dir / "UI.json").exists() else b"{}"

    files_block: dict = {
        "metrics": "plugin/metrics.json",
        "ui": "plugin/ui.json",
    }
    template_payloads: list[tuple[str, bytes]] = []
    for j2 in sorted(plugin_dir.glob("*.j2")):
        type_name, config_type, file_type = parse_template_filename(j2.name)
        if not type_name or config_type not in {"child", "base"}:
            continue
        dest = f"plugin/config.{config_type}.j2"
        payload = j2.read_bytes()
        files_block[f"{config_type}_template"] = {
            "file": dest,
            "type": type_name,
            "config_type": config_type,
            "file_type": file_type,
            "sha256": _sha256_bytes(payload),
        }
        template_payloads.append((dest, payload))

    artifact_entries = []
    artifact_payloads: list[tuple[str, bytes]] = []
    for (os_name, arch), path in artifacts.items():
        os_name = str(os_name).lower()
        arch = normalize_cpu_architecture(arch)
        if os_name not in C.ALLOWED_OS or arch not in C.ALLOWED_ARCH:
            raise ValueError(f"不支持的架构 {os_name}/{arch}")
        rel = artifact_zip_name(os_name, arch)
        payload = Path(path).read_bytes()
        artifact_entries.append(
            {
                "os": os_name,
                "arch": arch,
                "file": rel,
                "sha256": _sha256_bytes(payload),
            }
        )
        artifact_payloads.append((rel, payload))

    if not artifact_entries:
        raise ValueError("至少需要一个二进制产物")

    manifest = {
        "schema_version": C.SCHEMA_VERSION,
        "collector": collector,
        "collect_type": collect_type,
        "version": version,
        "execute_parameters": params,
        "files": files_block,
        "artifacts": artifact_entries,
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        zf.writestr("plugin/metrics.json", metrics_bytes)
        zf.writestr("plugin/ui.json", ui_bytes)
        for dest, payload in template_payloads:
            zf.writestr(dest, payload)
        for rel, payload in artifact_payloads:
            zf.writestr(rel, payload)
    return buf.getvalue()
