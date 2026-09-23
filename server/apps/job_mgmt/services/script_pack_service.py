"""脚本库批量导入/导出 ZIP 打包服务。

包格式（format_version=1）::

    script-pack.zip
    ├── manifest.json
    └── <safe_script_name>/
        ├── meta.json
        └── script.<ext>

加密参数导出时清空 default，只保留 is_encrypted 等元数据。
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from typing import Any, BinaryIO, Iterable

from rest_framework import serializers

from apps.core.logger import job_logger as logger
from apps.job_mgmt.constants import ScriptType
from apps.job_mgmt.models import Script
from apps.job_mgmt.serializers.script import ScriptCreateSerializer, validate_script_name_unique_in_organizations
from apps.job_mgmt.services.dangerous_checker import DangerousChecker
from apps.job_mgmt.utils.playbook_archive import get_archive_file_size

FORMAT_VERSION = 1
MANIFEST_NAME = "manifest.json"
META_NAME = "meta.json"

SCRIPT_PACK_MAX_SIZE_BYTES = 20 * 1024 * 1024
SCRIPT_PACK_MAX_MEMBERS = 500
SCRIPT_PACK_MAX_MEMBER_SIZE_BYTES = 5 * 1024 * 1024
SCRIPT_PACK_MAX_EXPANDED_SIZE_BYTES = 50 * 1024 * 1024

_SCRIPT_EXT = {
    ScriptType.SHELL: "sh",
    ScriptType.PYTHON: "py",
    ScriptType.POWERSHELL: "ps1",
    ScriptType.BAT: "bat",
}
_EXT_TO_TYPE = {ext: script_type for script_type, ext in _SCRIPT_EXT.items()}

_UNSAFE_FOLDER_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


@dataclass
class ScriptDraft:
    name: str
    description: str
    script_type: str
    timeout: int
    content: str
    params: list[dict[str, Any]]
    source_folder: str = ""


@dataclass
class ImportItem:
    name: str
    id: int | None = None
    reason: str = ""


@dataclass
class ImportResult:
    created: list[ImportItem] = field(default_factory=list)
    skipped: list[ImportItem] = field(default_factory=list)
    failed: list[ImportItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, list[dict[str, Any]]]:
        return {
            "created": [{"name": i.name, "id": i.id} for i in self.created],
            "skipped": [{"name": i.name, "reason": i.reason} for i in self.skipped],
            "failed": [{"name": i.name, "reason": i.reason} for i in self.failed],
        }


def strip_encrypted_defaults(params: list | None) -> list[dict[str, Any]]:
    """导出用：清空加密参数 default，保留其余元数据。"""
    if not params:
        return []

    result: list[dict[str, Any]] = []
    for param in params:
        if not isinstance(param, dict):
            continue
        item = dict(param)
        if item.get("is_encrypted"):
            item["default"] = ""
        result.append(item)
    return result


def sanitize_folder_name(name: str) -> str:
    cleaned = _UNSAFE_FOLDER_CHARS.sub("_", (name or "").strip())
    cleaned = cleaned.strip(". ")
    return cleaned or "script"


def script_filename(script_type: str) -> str:
    ext = _SCRIPT_EXT.get(script_type, "txt")
    return f"script.{ext}"


def _format_mb(size_bytes: int) -> str:
    return f"{size_bytes // (1024 * 1024)}MB"


def enforce_script_pack_limits(file_obj: BinaryIO) -> None:
    raw_size = get_archive_file_size(file_obj)
    if raw_size > SCRIPT_PACK_MAX_SIZE_BYTES:
        raise ValueError(f"压缩包过大，不支持处理（压缩包最大 {_format_mb(SCRIPT_PACK_MAX_SIZE_BYTES)}）")

    file_obj.seek(0)
    try:
        with zipfile.ZipFile(file_obj) as zf:
            member_count = 0
            max_member_size = 0
            total_member_size = 0
            for info in zf.infolist():
                if info.is_dir():
                    continue
                name = info.filename.replace("\\", "/")
                if ".." in name.split("/"):
                    raise ValueError("压缩包包含非法路径")
                member_count += 1
                max_member_size = max(max_member_size, info.file_size)
                total_member_size += info.file_size
    except zipfile.BadZipFile as exc:
        raise ValueError("无效的 ZIP 文件") from exc
    finally:
        file_obj.seek(0)

    if member_count > SCRIPT_PACK_MAX_MEMBERS:
        raise ValueError(f"压缩包文件数量过多，不支持处理（文件数不能超过 {SCRIPT_PACK_MAX_MEMBERS} 个）")
    if max_member_size > SCRIPT_PACK_MAX_MEMBER_SIZE_BYTES:
        raise ValueError(f"压缩包内单文件过大，不支持处理（单文件最大 {_format_mb(SCRIPT_PACK_MAX_MEMBER_SIZE_BYTES)}）")
    if total_member_size > SCRIPT_PACK_MAX_EXPANDED_SIZE_BYTES:
        raise ValueError(f"压缩包解压总量过大，不支持处理（解压总量最大 {_format_mb(SCRIPT_PACK_MAX_EXPANDED_SIZE_BYTES)}）")


class ScriptPackService:
    """脚本库 ZIP 打包与解析。"""

    @staticmethod
    def build_export_zip(scripts: Iterable[Script]) -> io.BytesIO:
        buffer = io.BytesIO()
        used_folders: set[str] = set()
        exported = 0

        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for script in scripts:
                folder = ScriptPackService._unique_folder_name(script.name, used_folders)
                meta = {
                    "format_version": FORMAT_VERSION,
                    "name": script.name,
                    "description": script.description or "",
                    "script_type": script.script_type,
                    "timeout": script.timeout,
                    "params": strip_encrypted_defaults(script.params),
                }
                zf.writestr(f"{folder}/{META_NAME}", json.dumps(meta, ensure_ascii=False, indent=2))
                zf.writestr(f"{folder}/{script_filename(script.script_type)}", script.content or "")
                exported += 1

            manifest = {
                "format_version": FORMAT_VERSION,
                "script_count": exported,
            }
            zf.writestr(MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, indent=2))

        buffer.seek(0)
        return buffer

    @staticmethod
    def parse_import_zip(file_obj: BinaryIO) -> list[ScriptDraft]:
        filename = (getattr(file_obj, "name", "") or "").lower()
        if filename and not filename.endswith(".zip"):
            raise ValueError("仅支持 .zip 格式的文件")

        enforce_script_pack_limits(file_obj)
        file_obj.seek(0)

        try:
            with zipfile.ZipFile(file_obj) as zf:
                drafts = ScriptPackService._parse_zip_members(zf)
        except zipfile.BadZipFile as exc:
            raise ValueError("无效的 ZIP 文件") from exc
        finally:
            file_obj.seek(0)

        if not drafts:
            raise ValueError("压缩包中未找到可导入的脚本")
        return drafts

    @staticmethod
    def import_scripts(
        drafts: list[ScriptDraft],
        team: list,
        *,
        username: str = "",
    ) -> ImportResult:
        result = ImportResult()
        for draft in drafts:
            try:
                validate_script_name_unique_in_organizations(draft.name, team)
            except serializers.ValidationError:
                result.skipped.append(ImportItem(name=draft.name, reason="同一组织内已存在同名脚本"))
                continue

            check_result = DangerousChecker.check_command(draft.content, team)
            if not check_result.can_execute:
                forbidden = [r["rule_name"] for r in check_result.forbidden]
                result.failed.append(ImportItem(name=draft.name, reason=f"脚本包含高危命令，禁止创建: {', '.join(forbidden)}"))
                continue

            # 导入侧再次清空加密 default，避免手工构造 draft 或旧包带入明文/密文
            params = strip_encrypted_defaults(draft.params)
            serializer = ScriptCreateSerializer(
                data={
                    "name": draft.name,
                    "description": draft.description,
                    "script_type": draft.script_type,
                    "content": draft.content,
                    "params": params,
                    "timeout": draft.timeout,
                    "team": team,
                    "is_built_in": False,
                }
            )
            if not serializer.is_valid():
                reason = ScriptPackService._format_serializer_errors(serializer.errors)
                result.failed.append(ImportItem(name=draft.name, reason=reason))
                continue

            instance = serializer.save(created_by=username, updated_by=username)
            result.created.append(ImportItem(name=instance.name, id=instance.pk))

        logger.info(
            "script_pack_import_finished created=%s skipped=%s failed=%s",
            len(result.created),
            len(result.skipped),
            len(result.failed),
        )
        return result

    @staticmethod
    def _unique_folder_name(name: str, used: set[str]) -> str:
        base = sanitize_folder_name(name)
        candidate = base
        index = 2
        while candidate in used:
            candidate = f"{base}_{index}"
            index += 1
        used.add(candidate)
        return candidate

    @staticmethod
    def _parse_zip_members(zf: zipfile.ZipFile) -> list[ScriptDraft]:
        """按 meta.json 所在目录识别脚本，兼容 macOS 重压产生的单层包装目录。"""
        files_by_path: dict[str, zipfile.ZipInfo] = {}
        for info in zf.infolist():
            path = ScriptPackService._normalize_member_path(info.filename)
            if path is None:
                continue
            files_by_path[path] = info

        meta_paths = sorted(path for path in files_by_path if path.endswith(f"/{META_NAME}") or path == META_NAME)
        drafts: list[ScriptDraft] = []
        for meta_path in meta_paths:
            if meta_path == META_NAME:
                raise ValueError("meta.json 必须放在脚本目录内，不能位于压缩包根目录")
            folder = meta_path.rsplit("/", 1)[0]
            folder_files = ScriptPackService._files_in_folder(files_by_path, folder)
            draft = ScriptPackService._draft_from_folder(zf, folder, folder_files)
            drafts.append(draft)
        return drafts

    @staticmethod
    def _normalize_member_path(filename: str) -> str | None:
        path = (filename or "").replace("\\", "/").lstrip("/")
        if not path or path.endswith("/"):
            return None
        parts = [part for part in path.split("/") if part]
        if not parts:
            return None
        if ".." in parts:
            raise ValueError("压缩包包含非法路径")
        # 忽略 macOS 资源叉与系统垃圾文件
        if parts[0] == "__MACOSX":
            return None
        if any(part == ".DS_Store" or part.startswith("._") for part in parts):
            return None
        return "/".join(parts)

    @staticmethod
    def _files_in_folder(files_by_path: dict[str, zipfile.ZipInfo], folder: str) -> dict[str, zipfile.ZipInfo]:
        prefix = f"{folder}/"
        result: dict[str, zipfile.ZipInfo] = {}
        for path, info in files_by_path.items():
            if not path.startswith(prefix):
                continue
            rest = path[len(prefix) :]
            if not rest or "/" in rest:
                continue
            result[rest] = info
        return result

    @staticmethod
    def _draft_from_folder(
        zf: zipfile.ZipFile,
        folder: str,
        files: dict[str, zipfile.ZipInfo],
    ) -> ScriptDraft:
        meta_info = files.get(META_NAME)
        if meta_info is None:
            raise ValueError(f"脚本目录 {folder} 缺少 meta.json")

        try:
            meta = json.loads(zf.read(meta_info).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"脚本目录 {folder} 的 meta.json 无效") from exc

        if not isinstance(meta, dict):
            raise ValueError(f"脚本目录 {folder} 的 meta.json 格式错误")

        script_type = str(meta.get("script_type") or "").strip()
        if script_type not in _SCRIPT_EXT:
            raise ValueError(f"脚本目录 {folder} 的 script_type 无效")

        script_info = files.get(script_filename(script_type))
        if script_info is None:
            script_info = ScriptPackService._find_script_file(files, script_type)
        if script_info is None:
            raise ValueError(f"脚本目录 {folder} 缺少脚本本体文件")

        try:
            content = zf.read(script_info).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"脚本目录 {folder} 的脚本内容不是合法 UTF-8") from exc

        name = str(meta.get("name") or "").strip()
        if not name:
            raise ValueError(f"脚本目录 {folder} 缺少 name")

        timeout = meta.get("timeout", 60)
        try:
            timeout = int(timeout)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"脚本目录 {folder} 的 timeout 无效") from exc

        params = meta.get("params") or []
        if not isinstance(params, list):
            raise ValueError(f"脚本目录 {folder} 的 params 必须是数组")

        cleaned_params: list[dict[str, Any]] = []
        for param in params:
            if not isinstance(param, dict):
                raise ValueError(f"脚本目录 {folder} 的 params 项必须是对象")
            item = dict(param)
            if item.get("is_encrypted"):
                item["default"] = ""
            cleaned_params.append(item)

        return ScriptDraft(
            name=name,
            description=str(meta.get("description") or ""),
            script_type=script_type,
            timeout=timeout,
            content=content,
            params=cleaned_params,
            source_folder=folder,
        )

    @staticmethod
    def _find_script_file(files: dict[str, zipfile.ZipInfo], script_type: str) -> zipfile.ZipInfo | None:
        expected = script_filename(script_type)
        if expected in files:
            return files[expected]
        for filename, info in files.items():
            if not filename.startswith("script."):
                continue
            ext = filename.rsplit(".", 1)[-1].lower()
            if _EXT_TO_TYPE.get(ext) == script_type:
                return info
        return None

    @staticmethod
    def _format_serializer_errors(errors: Any) -> str:
        if isinstance(errors, dict):
            parts = []
            for key, value in errors.items():
                parts.append(f"{key}: {ScriptPackService._format_serializer_errors(value)}")
            return "; ".join(parts)
        if isinstance(errors, list):
            return "; ".join(ScriptPackService._format_serializer_errors(item) for item in errors)
        return str(errors)
