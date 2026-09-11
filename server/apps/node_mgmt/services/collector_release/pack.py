"""Parse and validate a collector release zip without using research directory identity."""

from __future__ import annotations

import hashlib
import json
import posixpath
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from apps.node_mgmt.services.collector_release.constants import CollectorReleaseConstants as C
from apps.node_mgmt.services.collector_release.errors import (
    ARCH_INVALID,
    ARTIFACT_EMPTY,
    FILE_MISSING,
    FILE_UNDECLARED,
    HINT_REMOVE_EXTRA,
    HINT_REPACK,
    HINT_SIZE,
    LEVEL_ERROR,
    MANIFEST_FIELD,
    MANIFEST_INVALID,
    MANIFEST_MISSING,
    MANIFEST_SCHEMA,
    PACK_BOMB,
    PACK_FILE_TOO_LARGE,
    PACK_LAYOUT_INVALID,
    PACK_NESTED_ARCHIVE,
    PACK_NOT_ZIP,
    PACK_SYMLINK,
    PACK_TOO_LARGE,
    PACK_TOO_MANY_ENTRIES,
    PACK_UNCOMPRESSED_TOO_LARGE,
    PACK_ZIP_SLIP,
    PLUGIN_NAME_MISMATCH,
    SHA256_MISMATCH,
    PackIssue,
    issue,
)
from apps.node_mgmt.utils.architecture import normalize_cpu_architecture

VERSION_RE = re.compile(C.VERSION_PATTERN)
UNIX_SYMLINK_MASK = 0o170000
UNIX_SYMLINK_TYPE = 0o120000


@dataclass
class ArtifactSpec:
    os: str
    arch: str
    file: str
    sha256: str
    size: int
    computed_sha256: str


@dataclass
class TemplateSpec:
    file: str
    type: str
    config_type: str
    file_type: str
    content: str
    computed_sha256: str


@dataclass
class ParsedPack:
    collector: str
    collect_type: str
    version: str
    execute_parameters: str
    executable_path: str
    schema_version: int
    metrics: dict
    ui: dict
    metrics_sha256: str
    ui_sha256: str
    child_template: TemplateSpec | None = None
    base_template: TemplateSpec | None = None
    artifacts: list[ArtifactSpec] = field(default_factory=list)
    files: dict[str, bytes] = field(default_factory=dict)
    wrapping_prefix: str = ""


def _format_mb(num_bytes: int) -> str:
    return f"{num_bytes / (1024 * 1024):.1f}MB"


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    return ((info.external_attr >> 16) & UNIX_SYMLINK_MASK) == UNIX_SYMLINK_TYPE


def _normalize_zip_name(name: str) -> str:
    return name.replace("\\", "/").lstrip("/")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _detect_wrap_prefix(names: list[str]) -> str:
    tops = set()
    for name in names:
        if not name or name.endswith("/"):
            continue
        parts = name.split("/")
        if parts:
            tops.add(parts[0])
    if len(tops) == 1:
        top = next(iter(tops))
        if top not in {"plugin", "artifacts", "manifest.json"}:
            prefixed = [name for name in names if name == f"{top}/manifest.json" or name.startswith(f"{top}/")]
            if any(name == f"{top}/manifest.json" for name in prefixed):
                return f"{top}/"
    return ""


def _strip_prefix(name: str, prefix: str) -> str:
    if prefix and name.startswith(prefix):
        return name[len(prefix) :]
    return name


def _declared_file_entry(value, default_path: str) -> tuple[str, str]:
    if not value:
        return default_path, ""
    if isinstance(value, str):
        return value, ""
    if isinstance(value, dict):
        return str(value.get("file") or default_path), str(value.get("sha256") or "").strip().lower()
    return default_path, ""


def _layout_violation_paths(paths: list[str]) -> list[str]:
    bad = []
    research_dirs = {"exporter", "guide", "language"}
    for path in paths:
        parts = [part for part in path.split("/") if part]
        if any(part in research_dirs for part in parts):
            bad.append(path)
            continue
        if path == "manifest.json":
            continue
        if path.startswith("plugin/"):
            if path.count("/") != 1:
                bad.append(path)
            continue
        if path.startswith("artifacts/"):
            segs = path.split("/")
            if len(segs) != 3 or segs[1] not in C.ALLOWED_OS:
                bad.append(path)
            continue
        bad.append(path)
    return bad


def _check_declared_hash(issues: list[PackIssue], path: str, payload: bytes, declared_hash: str) -> str:
    computed = _sha256_bytes(payload)
    if declared_hash and declared_hash != computed:
        issues.append(
            issue(
                SHA256_MISMATCH,
                f"{path} 的 sha256 与清单不一致。",
                details={"file": path},
            )
        )
    return computed


def parse_release_zip(source, compressed_size: int | None = None) -> tuple[list[PackIssue], ParsedPack | None]:
    issues: list[PackIssue] = []
    if compressed_size is not None and compressed_size > C.MAX_COMPRESSED_BYTES:
        issues.append(
            issue(
                PACK_TOO_LARGE,
                f"压缩包 {_format_mb(compressed_size)}，超过上限 {_format_mb(C.MAX_COMPRESSED_BYTES)}。",
                hint=HINT_SIZE,
                details={"size": compressed_size, "limit": C.MAX_COMPRESSED_BYTES},
            )
        )
        return issues, None

    try:
        zf = zipfile.ZipFile(source)
    except (zipfile.BadZipFile, OSError, ValueError):
        issues.append(issue(PACK_NOT_ZIP, "不是 zip 或文件已损坏。", hint="请重新打包为 zip 后再导入。"))
        return issues, None

    with zf:
        return _parse_open_zip(zf, compressed_size or 0, issues)


def _has_pack_structure_error(issues: list[PackIssue]) -> bool:
    return any(item.level == LEVEL_ERROR and item.code.startswith("PACK_") for item in issues)


def _collect_zip_file_infos(infos: list[zipfile.ZipInfo], compressed_size: int, issues: list[PackIssue]) -> list[zipfile.ZipInfo] | None:
    if len(infos) > C.MAX_ENTRIES:
        issues.append(
            issue(
                PACK_TOO_MANY_ENTRIES,
                f"包内条目 {len(infos)} 个，超过上限 {C.MAX_ENTRIES}。",
                hint=HINT_REPACK,
                details={"count": len(infos), "limit": C.MAX_ENTRIES},
            )
        )

    claimed_total = 0
    file_infos = []
    for info in infos:
        name = _normalize_zip_name(info.filename)
        if not name or name.endswith("/"):
            continue
        if ".." in name.split("/") or name.startswith("/") or posixpath.isabs(name):
            issues.append(issue(PACK_ZIP_SLIP, f"路径非法: {name}", details={"file": name}))
            continue
        if _is_symlink(info):
            issues.append(issue(PACK_SYMLINK, f"不允许符号链接: {name}", details={"file": name}))
            continue
        lower = name.lower()
        if lower.endswith(C.NESTED_ARCHIVE_SUFFIXES) and not lower.endswith(".json"):
            issues.append(issue(PACK_NESTED_ARCHIVE, f"不允许嵌套压缩包: {name}", details={"file": name}))
            continue
        if info.file_size > C.MAX_FILE_BYTES:
            issues.append(
                issue(
                    PACK_FILE_TOO_LARGE,
                    f"文件 {name} 为 {_format_mb(info.file_size)}，超过上限 {_format_mb(C.MAX_FILE_BYTES)}。",
                    hint=HINT_SIZE,
                    details={"file": name, "size": info.file_size, "limit": C.MAX_FILE_BYTES},
                )
            )
        claimed_total += info.file_size
        file_infos.append(info)

    if claimed_total > C.MAX_UNCOMPRESSED_BYTES:
        issues.append(
            issue(
                PACK_UNCOMPRESSED_TOO_LARGE,
                f"解压后合计 {_format_mb(claimed_total)}，超过上限 {_format_mb(C.MAX_UNCOMPRESSED_BYTES)}。",
                hint=HINT_SIZE,
                details={"size": claimed_total, "limit": C.MAX_UNCOMPRESSED_BYTES},
            )
        )
    if compressed_size and claimed_total and claimed_total / max(compressed_size, 1) > C.BOMB_RATIO and claimed_total > 10 * 1024 * 1024:
        issues.append(issue(PACK_BOMB, "压缩比异常，已拒绝解压。", hint="请检查 zip 是否被异常压缩。"))
    if _has_pack_structure_error(issues):
        return None
    return file_infos


def _extract_zip_contents(zf: zipfile.ZipFile, file_infos: list[zipfile.ZipInfo], issues: list[PackIssue]) -> tuple[dict[str, bytes], str] | None:
    names = [_normalize_zip_name(info.filename) for info in file_infos]
    prefix = _detect_wrap_prefix(names)
    contents: dict[str, bytes] = {}
    actual_total = 0
    for info in file_infos:
        raw_name = _normalize_zip_name(info.filename)
        rel = _strip_prefix(raw_name, prefix)
        payload = zf.read(info)
        actual_total += len(payload)
        if actual_total > C.MAX_UNCOMPRESSED_BYTES:
            issues.append(
                issue(
                    PACK_UNCOMPRESSED_TOO_LARGE,
                    f"解压后合计超过上限 {_format_mb(C.MAX_UNCOMPRESSED_BYTES)}。",
                    hint=HINT_SIZE,
                    details={"limit": C.MAX_UNCOMPRESSED_BYTES},
                )
            )
            return None
        if info.file_size and len(payload) > info.file_size * 2:
            issues.append(issue(PACK_BOMB, f"文件 {rel} 实际大小与声明不符。", details={"file": rel}))
            return None
        contents[rel] = payload
    return contents, prefix


def _load_manifest(contents: dict[str, bytes], issues: list[PackIssue]) -> dict | None:
    if "manifest.json" not in contents:
        if any(path.endswith("/metrics.json") or path == "metrics.json" for path in contents):
            issues.append(
                issue(
                    PACK_LAYOUT_INVALID,
                    "包布局无效：缺少根目录 manifest.json，或使用了研发插件目录。",
                    hint=HINT_REPACK,
                )
            )
        else:
            issues.append(issue(MANIFEST_MISSING, "缺少 manifest.json。", hint=HINT_REPACK))
        return None
    try:
        manifest = json.loads(contents["manifest.json"].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        issues.append(issue(MANIFEST_INVALID, f"manifest.json 无法解析: {exc}", hint="请检查 JSON 语法。"))
        return None
    if not isinstance(manifest, dict):
        issues.append(issue(MANIFEST_INVALID, "manifest.json 必须是对象。"))
        return None
    return manifest


def _read_manifest_identity(manifest: dict, issues: list[PackIssue]) -> tuple[str, str, str, str, str, int]:
    schema_version = manifest.get("schema_version", C.SCHEMA_VERSION)
    if schema_version != C.SCHEMA_VERSION:
        issues.append(
            issue(
                MANIFEST_SCHEMA,
                f"不支持的 schema_version: {schema_version}。",
                details={"schema_version": schema_version},
            )
        )
    collector = str(manifest.get("collector") or "").strip()
    collect_type = str(manifest.get("collect_type") or "").strip()
    version = str(manifest.get("version") or "").strip()
    execute_parameters = str(manifest.get("execute_parameters") or "")
    executable_path = str(manifest.get("executable_path") or "").strip()
    if not collector:
        issues.append(issue(MANIFEST_FIELD, "缺少 collector。", details={"field": "collector"}))
    if not collect_type:
        issues.append(issue(MANIFEST_FIELD, "缺少 collect_type。", details={"field": "collect_type"}))
    if not version or not VERSION_RE.match(version):
        issues.append(issue(MANIFEST_FIELD, "version 必须是 x.y.z。", details={"field": "version", "value": version}))
    return collector, collect_type, version, execute_parameters, executable_path, schema_version


def _declare_template_files(child_spec, base_spec, declared: set[str], issues: list[PackIssue]) -> None:
    for key, spec in (("child_template", child_spec), ("base_template", base_spec)):
        if not spec:
            continue
        if isinstance(spec, str):
            spec = {"file": spec}
        if not isinstance(spec, dict) or not spec.get("file"):
            issues.append(issue(MANIFEST_FIELD, f"{key} 格式无效。", details={"field": key}))
            continue
        declared.add(spec["file"])
        missing = [field for field in ("type", "config_type", "file_type") if not spec.get(field)]
        if missing:
            issues.append(issue(MANIFEST_FIELD, f"{key} 缺少 {', '.join(missing)}。", details={"field": key}))


def _parse_artifact_specs(artifacts_block, declared: set[str], issues: list[PackIssue]) -> list[ArtifactSpec]:
    if not isinstance(artifacts_block, list) or not artifacts_block:
        issues.append(issue(MANIFEST_FIELD, "artifacts 不能为空。", details={"field": "artifacts"}))
        artifacts_block = []
    artifact_specs: list[ArtifactSpec] = []
    for item in artifacts_block:
        if not isinstance(item, dict):
            issues.append(issue(MANIFEST_FIELD, "artifact 必须是对象。"))
            continue
        os_name = str(item.get("os") or "").strip().lower()
        arch = normalize_cpu_architecture(item.get("arch"))
        rel = str(item.get("file") or "").strip()
        if os_name not in C.ALLOWED_OS or arch not in C.ALLOWED_ARCH:
            issues.append(
                issue(
                    ARCH_INVALID,
                    f"不支持的架构 {os_name}/{item.get('arch')}。",
                    details={"os": os_name, "arch": item.get("arch")},
                )
            )
            continue
        if not rel:
            issues.append(issue(MANIFEST_FIELD, "artifact.file 不能为空。", details={"os": os_name, "arch": arch}))
            continue
        expected_prefix = f"artifacts/{os_name}/"
        if not rel.startswith(expected_prefix):
            issues.append(
                issue(
                    PACK_LAYOUT_INVALID,
                    f"二进制路径必须位于 {expected_prefix} 下，实际为 {rel}。",
                    hint=HINT_REPACK,
                    details={"file": rel, "os": os_name, "arch": arch},
                )
            )
        declared.add(rel)
        artifact_specs.append(
            ArtifactSpec(
                os=os_name,
                arch=arch,
                file=rel,
                sha256=str(item.get("sha256") or "").strip().lower(),
                size=0,
                computed_sha256="",
            )
        )
    return artifact_specs


def _report_undeclared_and_layout(contents: dict[str, bytes], declared: set[str], issues: list[PackIssue]) -> None:
    extra = sorted(path for path in contents if path not in declared)
    if extra:
        issues.append(
            issue(
                FILE_UNDECLARED,
                f"包内有清单未声明的文件: {', '.join(extra)}。",
                hint=HINT_REMOVE_EXTRA,
                details={"files": extra},
            )
        )
    layout_bad = _layout_violation_paths(list(contents))
    if layout_bad:
        issues.append(
            issue(
                PACK_LAYOUT_INVALID,
                "包布局无效：根目录堆了文件，或出现了研发插件目录。",
                hint=HINT_REPACK,
                details={"files": layout_bad},
            )
        )


def _require_pack_file(contents: dict[str, bytes], path: str, label: str, declared_hash: str, issues: list[PackIssue]) -> bytes | None:
    payload = contents.get(path)
    if payload is None:
        issues.append(issue(FILE_MISSING, f"缺少 {label}: {path}", hint=HINT_REPACK, details={"file": path}))
        return None
    _check_declared_hash(issues, path, payload, declared_hash)
    return payload


def _load_plugin_jsons(
    contents: dict[str, bytes],
    metrics_path: str,
    metrics_hash: str,
    ui_path: str,
    ui_hash: str,
    collector: str,
    collect_type: str,
    issues: list[PackIssue],
) -> tuple[dict, dict, bytes | None, bytes | None]:
    metrics_bytes = _require_pack_file(contents, metrics_path, "metrics.json", metrics_hash, issues)
    ui_bytes = _require_pack_file(contents, ui_path, "ui.json", ui_hash, issues)
    metrics_data: dict = {}
    ui_data: dict = {}
    if metrics_bytes is not None:
        try:
            metrics_data = json.loads(metrics_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            issues.append(issue(MANIFEST_INVALID, f"{metrics_path} 无法解析: {exc}", details={"file": metrics_path}))
            metrics_data = {}
        else:
            plugin_name = str(metrics_data.get("plugin") or "").strip()
            if plugin_name and collector and plugin_name != collector:
                issues.append(
                    issue(
                        PLUGIN_NAME_MISMATCH,
                        f"metrics.json 的 plugin 为 {plugin_name}，与 manifest.collector {collector} 不一致。",
                        details={"plugin": plugin_name, "collector": collector},
                    )
                )
            elif not plugin_name and collector:
                metrics_data["plugin"] = collector
            metrics_data["collector"] = collector
            metrics_data["collect_type"] = collect_type
    if ui_bytes is not None:
        try:
            ui_data = json.loads(ui_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            issues.append(issue(MANIFEST_INVALID, f"{ui_path} 无法解析: {exc}", details={"file": ui_path}))
            ui_data = {}
        else:
            if isinstance(ui_data, dict):
                ui_data["collector"] = collector
                ui_data["collect_type"] = collect_type
    return metrics_data, ui_data, metrics_bytes, ui_bytes


def _load_template_spec(spec, contents: dict[str, bytes], issues: list[PackIssue]) -> TemplateSpec | None:
    if not spec:
        return None
    if isinstance(spec, str):
        spec = {"file": spec}
    path = spec.get("file")
    payload = contents.get(path)
    if payload is None:
        issues.append(issue(FILE_MISSING, f"缺少 {path}", hint=HINT_REPACK, details={"file": path}))
        return None
    declared_hash = str(spec.get("sha256") or "").strip().lower()
    computed = _sha256_bytes(payload)
    if declared_hash and declared_hash != computed:
        issues.append(
            issue(
                SHA256_MISMATCH,
                f"{path} 的 sha256 与清单不一致。",
                details={"file": path},
            )
        )
    return TemplateSpec(
        file=path,
        type=str(spec.get("type") or ""),
        config_type=str(spec.get("config_type") or ""),
        file_type=str(spec.get("file_type") or ""),
        content=payload.decode("utf-8"),
        computed_sha256=computed,
    )


def _load_artifact_binaries(artifact_specs: list[ArtifactSpec], contents: dict[str, bytes], issues: list[PackIssue]) -> list[ArtifactSpec]:
    loaded_artifacts: list[ArtifactSpec] = []
    for spec in artifact_specs:
        payload = contents.get(spec.file)
        if payload is None:
            issues.append(issue(FILE_MISSING, f"缺少二进制: {spec.file}", details={"file": spec.file, "os": spec.os, "arch": spec.arch}))
            continue
        if not payload:
            issues.append(
                issue(
                    ARTIFACT_EMPTY,
                    f"{spec.os}/{spec.arch} 二进制为空。",
                    details={"os": spec.os, "arch": spec.arch, "file": spec.file},
                )
            )
            continue
        computed = _sha256_bytes(payload)
        if spec.sha256 and spec.sha256 != computed:
            issues.append(
                issue(
                    SHA256_MISMATCH,
                    f"{spec.file} 的 sha256 与清单不一致。",
                    details={"file": spec.file, "os": spec.os, "arch": spec.arch},
                )
            )
        spec.computed_sha256 = computed
        spec.size = len(payload)
        loaded_artifacts.append(spec)
    return loaded_artifacts


def _parse_open_zip(zf: zipfile.ZipFile, compressed_size: int, issues: list[PackIssue]) -> tuple[list[PackIssue], ParsedPack | None]:
    file_infos = _collect_zip_file_infos(zf.infolist(), compressed_size, issues)
    if file_infos is None:
        return issues, None
    extracted = _extract_zip_contents(zf, file_infos, issues)
    if extracted is None:
        return issues, None
    contents, prefix = extracted
    manifest = _load_manifest(contents, issues)
    if manifest is None:
        return issues, None

    collector, collect_type, version, execute_parameters, executable_path, schema_version = _read_manifest_identity(manifest, issues)
    files_block = manifest.get("files") or {}
    if not isinstance(files_block, dict):
        issues.append(issue(MANIFEST_FIELD, "files 必须是对象。", details={"field": "files"}))
        files_block = {}
    metrics_path, metrics_hash = _declared_file_entry(files_block.get("metrics"), "plugin/metrics.json")
    ui_path, ui_hash = _declared_file_entry(files_block.get("ui"), "plugin/ui.json")
    child_spec = files_block.get("child_template")
    base_spec = files_block.get("base_template")
    declared = {"manifest.json", metrics_path, ui_path}
    _declare_template_files(child_spec, base_spec, declared, issues)
    artifact_specs = _parse_artifact_specs(manifest.get("artifacts") or [], declared, issues)
    _report_undeclared_and_layout(contents, declared, issues)

    identity_errors = {PACK_LAYOUT_INVALID, MANIFEST_FIELD, MANIFEST_SCHEMA, ARCH_INVALID}
    if any(item.code in identity_errors and item.level == LEVEL_ERROR for item in issues) and not collector:
        return issues, None

    metrics_data, ui_data, metrics_bytes, ui_bytes = _load_plugin_jsons(
        contents, metrics_path, metrics_hash, ui_path, ui_hash, collector, collect_type, issues
    )
    child_template = _load_template_spec(child_spec, contents, issues)
    base_template = _load_template_spec(base_spec, contents, issues)
    loaded_artifacts = _load_artifact_binaries(artifact_specs, contents, issues)
    if not collector or not version:
        return issues, None
    return issues, ParsedPack(
        collector=collector,
        collect_type=collect_type,
        version=version,
        execute_parameters=execute_parameters,
        executable_path=executable_path,
        schema_version=schema_version,
        metrics=metrics_data,
        ui=ui_data,
        metrics_sha256=_sha256_bytes(metrics_bytes or b""),
        ui_sha256=_sha256_bytes(ui_bytes or b""),
        child_template=child_template,
        base_template=base_template,
        artifacts=loaded_artifacts,
        files=contents,
        wrapping_prefix=prefix,
    )


def parse_release_path(path: str | Path) -> tuple[list[PackIssue], ParsedPack | None]:
    file_path = Path(path)
    size = file_path.stat().st_size if file_path.exists() else None
    with file_path.open("rb") as handle:
        return parse_release_zip(handle, compressed_size=size)
