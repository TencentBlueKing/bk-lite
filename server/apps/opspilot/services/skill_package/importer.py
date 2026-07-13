import logging
import os
import re
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

logger = logging.getLogger("apps.opspilot.skill_package.importer")


DEFAULT_SKILL_PACKAGE_ROOT = Path(__file__).resolve().parents[4] / ".skill" / "packages"

# SKILL.md body 必填段: deepagent 路径上 LLM 必须知道怎么用技能脚本。
# 老包 warn-only 不阻断,新包可通过 env ``OPSPILOT_REQUIRE_RUNTIME_SECTION=true`` 强制。
_RUNTIME_SECTION_RE = re.compile(r"(?m)^##\s*Runtime\b", re.IGNORECASE)
_RUNTIME_FIELDS_RE = re.compile(r"(?m)^(?:[-*]\s+)?(`?)(command|tools|artifact)\1\s*:", re.IGNORECASE)


def _check_runtime_section(skill_body: str) -> bool:
    """校验 SKILL.md body 是否含 ``## Runtime`` 段且列出 command/tools/artifact 至少一项。

    详见 Phase 3 plan:SKILL.md 必填 ``## Runtime``(命令模板 + 依赖工具 + 预期产物),
    deepagent 路径上 LLM 靠这段才知道怎么调技能脚本(否则会用内联 Python 绕过,
    写出来的产物路径跟 read_file 跨工具不可见,造成"写入成功但读取失败")。
    """
    if not _RUNTIME_SECTION_RE.search(skill_body):
        return False
    # 段存在则至少要列出 command / tools / artifact 之一
    return bool(_RUNTIME_FIELDS_RE.search(skill_body))


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
    runtime_section_present: bool = False


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
            skill_doc_member = self._find_required_member(members, "SKILL.md")
            package_root = PurePosixPath(skill_doc_member).parent
            manifest_member = self._find_optional_member(members, "skill.yaml", package_root)

            skill_markdown = archive.read(skill_doc_member).decode("utf-8")
            frontmatter, skill_body = self._split_frontmatter(skill_markdown)
            if manifest_member:
                manifest = self._load_manifest(archive.read(manifest_member).decode("utf-8"), source="skill.yaml")
            else:
                manifest = self._load_manifest(frontmatter, source="SKILL.md frontmatter") if frontmatter else {}

            inferred_id = package_root.name if package_root != PurePosixPath(".") else archive_path.stem
            skill_id = self._sanitize_id(str(manifest.get("id") or manifest.get("name") or inferred_id))
            version = self._sanitize_version(str(manifest.get("version") or "0.1.0"))

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

        runtime_present = _check_runtime_section(skill_body)
        if not runtime_present:
            # 默认 warn-only 不阻断(老包兼容);严格模式由 env 切换。
            msg = (
                f"技能包 {skill_id} 的 SKILL.md 缺少 '## Runtime' 段(含 command/tools/artifact),"
                "LLM 在 deepagent 路径上可能不知道如何调用本技能包脚本。"
                "建议在 SKILL.md 加 '## Runtime' 段并列出 command/tools/artifact 至少一项。"
            )
            if os.getenv("OPSPILOT_REQUIRE_RUNTIME_SECTION", "").lower() == "true":
                raise ValueError(msg)
            logger.warning(msg)

        return SkillPackageImportResult(
            skill_id=skill_id,
            name=str(manifest.get("name") or self._extract_markdown_title(skill_body) or skill_id),
            version=version,
            description=str(manifest.get("description") or ""),
            category=str(manifest.get("category") or ""),
            required_tools=self._string_list(manifest.get("required_tools")),
            triggers=self._string_list(manifest.get("triggers")),
            storage_path=storage_path,
            manifest=manifest,
            skill_markdown=skill_body,
            runtime_section_present=runtime_present,
        )

    def import_local_dir(self, source_dir: str | Path, organization_id: str = "default") -> SkillPackageImportResult:
        """Import a local skill package directory into the local server store.

        Expects ``source_dir`` to contain ``SKILL.md`` at the root (optionally with
        ``scripts/``、``references/``、``assets/`` 子目录;Anthropic Agent Skills 风格)。

        与 ``import_zip`` 共享同一存储布局:
        ``{storage_root}/{organization_id}/{skill_id}/{version}/extracted/``
        不复制 ``original.zip``(本地目录本身就是真相源),``storage_path`` 仍指向
        该目录的父级以便 ``hydrate_skill_packages`` 注入 ``extracted_root``。

        安全约束:
          - ``source_dir`` 必须在 ``storage_root`` 之下(防越界复制任意路径)。
          - 软链接拒绝(防 TOCTOU)。
        """
        source_dir = Path(source_dir).resolve()
        if not source_dir.is_dir():
            raise ValueError(f"技能包目录不存在: {source_dir}")

        # 防越界:source_dir 必须在 storage_root 之下。
        # 注意 storage_root 是绝对路径(默认 Path(__file__).parents[4] / ".skill" / "packages")。
        storage_root_resolved = self.storage_root.resolve()
        try:
            source_dir.relative_to(storage_root_resolved)
        except ValueError:
            raise ValueError(
                f"技能包目录必须在 {storage_root_resolved} 之下(防越界),实际: {source_dir}"
            ) from None

        # 拒绝软链接(防 TOCTOU / 路径替换)。
        if source_dir.is_symlink():
            raise ValueError(f"技能包目录不允许是软链接: {source_dir}")

        skill_md_path = source_dir / "SKILL.md"
        if not skill_md_path.is_file():
            raise ValueError(f"技能包目录缺少 SKILL.md: {skill_md_path}")

        skill_yaml_path = source_dir / "skill.yaml"

        skill_markdown = skill_md_path.read_text(encoding="utf-8")
        frontmatter, skill_body = self._split_frontmatter(skill_markdown)

        if skill_yaml_path.is_file():
            manifest = self._load_manifest(
                skill_yaml_path.read_text(encoding="utf-8"), source="skill.yaml"
            )
        else:
            manifest = (
                self._load_manifest(frontmatter, source="SKILL.md frontmatter")
                if frontmatter
                else {}
            )

        inferred_id = source_dir.name
        skill_id = self._sanitize_id(
            str(manifest.get("id") or manifest.get("name") or inferred_id)
        )
        version = self._sanitize_version(str(manifest.get("version") or "0.1.0"))

        storage_path = self.storage_root / organization_id / skill_id / version
        extracted_path = storage_path / "extracted"
        if storage_path.exists():
            shutil.rmtree(storage_path)
        extracted_path.mkdir(parents=True, exist_ok=True)

        # 复制目录树(过滤 SKILL.md / skill.yaml 之外的隐藏文件?不,anthropic/skills 有时含 .gitignore 等)。
        # 但要拒绝越界符号链接——rglob + is_file 之后再 is_symlink 单独拒。
        for src_file in sorted(source_dir.rglob("*")):
            if src_file.is_symlink():
                logger.warning("技能包目录含软链接,跳过: %s", src_file)
                continue
            if not src_file.is_file():
                continue
            try:
                rel = src_file.relative_to(source_dir)
            except ValueError:
                continue
            # 防 zip-slip 同款越界(虽然 rglob 已限 source_dir,二次校验更稳)
            if rel.parts and (".." in rel.parts or rel.is_absolute()):
                continue
            target = extracted_path / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            # 用 copy2 保留 mtime;SKILL.md 之类小文件足够快。
            shutil.copy2(src_file, target)

        runtime_present = _check_runtime_section(skill_body)
        if not runtime_present:
            # 默认 warn-only 不阻断(老包兼容);严格模式由 env 切换。
            msg = (
                f"技能包 {skill_id} 的 SKILL.md 缺少 '## Runtime' 段(含 command/tools/artifact),"
                "LLM 在 deepagent 路径上可能不知道如何调用本技能包脚本。"
                "建议在 SKILL.md 加 '## Runtime' 段并列出 command/tools/artifact 至少一项。"
            )
            if os.getenv("OPSPILOT_REQUIRE_RUNTIME_SECTION", "").lower() == "true":
                raise ValueError(msg)
            logger.warning(msg)

        return SkillPackageImportResult(
            skill_id=skill_id,
            name=str(manifest.get("name") or self._extract_markdown_title(skill_body) or skill_id),
            version=version,
            description=str(manifest.get("description") or ""),
            category=str(manifest.get("category") or ""),
            required_tools=self._string_list(manifest.get("required_tools")),
            triggers=self._string_list(manifest.get("triggers")),
            storage_path=storage_path,
            manifest=manifest,
            skill_markdown=skill_body,
            runtime_section_present=runtime_present,
        )

    @staticmethod
    def _find_required_member(members: list[zipfile.ZipInfo], filename: str) -> str:
        matches = [item.filename for item in members if PurePosixPath(item.filename).name == filename]
        if not matches:
            raise ValueError(f"技能包缺少 {filename}")
        return sorted(matches, key=lambda value: (len(PurePosixPath(value).parts), value))[0]

    @staticmethod
    def _find_optional_member(
        members: list[zipfile.ZipInfo],
        filename: str,
        package_root: PurePosixPath,
    ) -> str | None:
        matches = [
            item.filename
            for item in members
            if PurePosixPath(item.filename).name == filename and PurePosixPath(item.filename).parent == package_root
        ]
        if not matches:
            return None
        return sorted(matches)[0]

    @staticmethod
    def _load_manifest(content: str, source: str) -> dict[str, Any]:
        manifest = yaml.safe_load(content) or {}
        if not isinstance(manifest, dict):
            raise ValueError(f"{source} 必须是对象结构")
        if manifest.get("runtime", {}).get("execute_code"):
            raise ValueError("技能包第一版不允许执行代码")
        return manifest

    @staticmethod
    def _split_frontmatter(markdown: str) -> tuple[str, str]:
        if not markdown.startswith("---"):
            return "", markdown
        match = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)(.*)$", markdown, re.DOTALL)
        if not match:
            return "", markdown
        return match.group(1), match.group(2).lstrip()

    @staticmethod
    def _extract_markdown_title(markdown: str) -> str:
        for line in markdown.splitlines():
            match = re.match(r"^#\s+(.+?)\s*$", line)
            if match:
                return match.group(1)
        return ""

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
