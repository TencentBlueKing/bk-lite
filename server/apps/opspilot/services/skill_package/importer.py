import re
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import yaml


DEFAULT_SKILL_PACKAGE_ROOT = Path(__file__).resolve().parents[4] / ".skill" / "packages"


@dataclass(frozen=True)
class SkillPackageImportResult:
    skill_id: str
    name: str
    version: str
    description: str
    category: str
    required_tools: list[str]
    triggers: list[str]
    storage_path: Path
    manifest: dict[str, Any]
    skill_markdown: str


class SkillPackageImporter:
    """Import a zip skill package into the local server skill package store."""

    def __init__(self, storage_root: str | Path | None = None):
        self.storage_root = Path(storage_root) if storage_root else DEFAULT_SKILL_PACKAGE_ROOT

    def import_zip(self, archive_path: str | Path, organization_id: str = "default") -> SkillPackageImportResult:
        archive_path = Path(archive_path)
        if not archive_path.exists():
            raise ValueError("技能包文件不存在")

        with zipfile.ZipFile(archive_path) as archive:
            members = [item for item in archive.infolist() if not item.is_dir()]
            self._validate_members(members)
            manifest_member = self._find_required_member(members, "skill.yaml")
            skill_doc_member = self._find_required_member(members, "SKILL.md")

            manifest = self._load_manifest(archive.read(manifest_member).decode("utf-8"))
            skill_markdown = archive.read(skill_doc_member).decode("utf-8")
            skill_id = self._sanitize_id(str(manifest.get("id") or manifest.get("name") or "skill-package"))
            version = self._sanitize_version(str(manifest.get("version") or "0.1.0"))

            package_root = PurePosixPath(manifest_member).parent
            storage_path = self.storage_root / organization_id / skill_id / version
            extracted_path = storage_path / "extracted"
            if storage_path.exists():
                shutil.rmtree(storage_path)
            extracted_path.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(archive_path, storage_path / "original.zip")

            for member in members:
                relative_name = self._relative_member_name(member.filename, package_root)
                if not relative_name:
                    continue
                target = extracted_path / relative_name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(member))

        return SkillPackageImportResult(
            skill_id=skill_id,
            name=str(manifest.get("name") or skill_id),
            version=version,
            description=str(manifest.get("description") or ""),
            category=str(manifest.get("category") or ""),
            required_tools=self._string_list(manifest.get("required_tools")),
            triggers=self._string_list(manifest.get("triggers")),
            storage_path=storage_path,
            manifest=manifest,
            skill_markdown=skill_markdown,
        )

    @staticmethod
    def _find_required_member(members: list[zipfile.ZipInfo], filename: str) -> str:
        matches = [item.filename for item in members if PurePosixPath(item.filename).name == filename]
        if not matches:
            raise ValueError(f"技能包缺少 {filename}")
        return sorted(matches, key=lambda value: (len(PurePosixPath(value).parts), value))[0]

    @staticmethod
    def _load_manifest(content: str) -> dict[str, Any]:
        manifest = yaml.safe_load(content) or {}
        if not isinstance(manifest, dict):
            raise ValueError("skill.yaml 必须是对象结构")
        if manifest.get("runtime", {}).get("execute_code"):
            raise ValueError("技能包第一版不允许执行代码")
        return manifest

    @staticmethod
    def _validate_members(members: list[zipfile.ZipInfo]) -> None:
        for member in members:
            path = PurePosixPath(member.filename)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"技能包包含非法路径: {member.filename}")

    @staticmethod
    def _relative_member_name(filename: str, package_root: PurePosixPath) -> str:
        path = PurePosixPath(filename)
        if package_root != PurePosixPath("."):
            try:
                path = path.relative_to(package_root)
            except ValueError:
                return ""
        return path.as_posix()

    @staticmethod
    def _sanitize_id(value: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip()).strip("-")
        return normalized or "skill-package"

    @staticmethod
    def _sanitize_version(value: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip()).strip("-")
        return normalized or "0.1.0"

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if not value:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [str(item) for item in value if item]
        return []
