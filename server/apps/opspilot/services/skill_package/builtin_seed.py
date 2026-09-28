"""从 support-files 播种内置 SkillPackage（磁盘 + DB，幂等）。"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.services.skill_package.importer import DEFAULT_SKILL_PACKAGE_ROOT, SkillPackageImporter

BUILTIN_ORG_ID = "builtin"
BUILTIN_DOMAIN = "domain.com"
DEFAULT_SUPPORT_ROOT = Path(__file__).resolve().parents[2] / "support-files" / "skill_packages"


@dataclass(frozen=True)
class BuiltinSeedResult:
    package_id: str
    version: str
    created: bool
    storage_path: Path


def list_builtin_package_dirs(support_root: Path | None = None) -> list[Path]:
    root = Path(support_root) if support_root else DEFAULT_SUPPORT_ROOT
    if not root.is_dir():
        return []
    return sorted(path for path in root.iterdir() if path.is_dir() and (path / "SKILL.md").is_file())


def _resolve_version(manifest: dict[str, Any]) -> str:
    metadata = manifest.get("metadata") if isinstance(manifest.get("metadata"), dict) else {}
    raw = manifest.get("version") or metadata.get("version") or "0.1.0"
    return SkillPackageImporter._sanitize_version(str(raw))


def _resolve_triggers(manifest: dict[str, Any]) -> list[str]:
    if manifest.get("triggers"):
        return SkillPackageImporter._string_list(manifest.get("triggers"))
    metadata = manifest.get("metadata") if isinstance(manifest.get("metadata"), dict) else {}
    raw = metadata.get("triggers")
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    return SkillPackageImporter._string_list(raw)


def _resolve_category(manifest: dict[str, Any]) -> str:
    if manifest.get("category"):
        return str(manifest.get("category"))
    metadata = manifest.get("metadata") if isinstance(manifest.get("metadata"), dict) else {}
    return str(metadata.get("domain") or metadata.get("category") or "")


def _parse_package_dir(source_dir: Path) -> dict[str, Any]:
    skill_md = (source_dir / "SKILL.md").read_text(encoding="utf-8")
    frontmatter, skill_body = SkillPackageImporter._split_frontmatter(skill_md)
    skill_yaml = source_dir / "skill.yaml"
    if skill_yaml.is_file():
        manifest = SkillPackageImporter._load_manifest(skill_yaml.read_text(encoding="utf-8"), source="skill.yaml")
    else:
        manifest = SkillPackageImporter._load_manifest(frontmatter, source="SKILL.md frontmatter") if frontmatter else {}

    package_id = SkillPackageImporter._sanitize_id(str(manifest.get("id") or manifest.get("name") or source_dir.name))
    version = _resolve_version(manifest)
    title = SkillPackageImporter._extract_markdown_title(skill_body)
    name = str(manifest.get("display_name") or title or manifest.get("name") or package_id)
    description = str(manifest.get("description") or "")
    return {
        "package_id": package_id,
        "version": version,
        "name": name,
        "description": description,
        "category": _resolve_category(manifest),
        "manifest": manifest,
        "skill_markdown": skill_body,
        "required_tools": SkillPackageImporter._string_list(manifest.get("required_tools")),
        "triggers": _resolve_triggers(manifest),
    }


def _copy_extracted(source_dir: Path, extracted_path: Path) -> None:
    if extracted_path.exists():
        shutil.rmtree(extracted_path)
    extracted_path.mkdir(parents=True, exist_ok=True)
    for src_file in sorted(source_dir.rglob("*")):
        if src_file.is_symlink() or not src_file.is_file():
            continue
        if src_file.name in {".DS_Store"} or src_file.name.startswith("._"):
            continue
        rel = src_file.relative_to(source_dir)
        if ".." in rel.parts:
            continue
        target = extracted_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, target)


def seed_builtin_skill_package(
    source_dir: Path,
    *,
    storage_root: Path | None = None,
    domain: str = BUILTIN_DOMAIN,
) -> BuiltinSeedResult:
    """把单个 support-files 技能包目录同步到存储与 SkillPackage 表。"""
    from apps.opspilot.models import SkillPackage

    source_dir = Path(source_dir).resolve()
    parsed = _parse_package_dir(source_dir)
    root = Path(storage_root) if storage_root else DEFAULT_SKILL_PACKAGE_ROOT
    storage_path = root / BUILTIN_ORG_ID / parsed["package_id"] / parsed["version"]
    extracted_path = storage_path / "extracted"
    _copy_extracted(source_dir, extracted_path)

    package, created = SkillPackage.objects.update_or_create(
        package_id=parsed["package_id"],
        version=parsed["version"],
        domain=domain,
        defaults={
            "name": parsed["name"],
            "description": parsed["description"],
            "category": parsed["category"],
            "source_type": "builtin",
            "source_url": "",
            "storage_path": str(storage_path),
            "manifest": parsed["manifest"],
            "skill_markdown": parsed["skill_markdown"],
            "required_tools": parsed["required_tools"],
            "triggers": parsed["triggers"],
            "team": [],
            "is_enabled": True,
            "is_build_in": True,
            "updated_by": "system",
            "updated_by_domain": domain,
        },
    )
    if created:
        package.created_by = "system"
        package.domain = domain
        package.save(update_fields=["created_by", "domain"])

    logger.info(
        "builtin skill package seeded package_id=%s version=%s created=%s",
        parsed["package_id"],
        parsed["version"],
        created,
    )
    return BuiltinSeedResult(
        package_id=parsed["package_id"],
        version=parsed["version"],
        created=created,
        storage_path=storage_path,
    )


def seed_all_builtin_skill_packages(
    *,
    support_root: Path | None = None,
    storage_root: Path | None = None,
    domain: str = BUILTIN_DOMAIN,
) -> list[BuiltinSeedResult]:
    results: list[BuiltinSeedResult] = []
    for package_dir in list_builtin_package_dirs(support_root):
        results.append(
            seed_builtin_skill_package(
                package_dir,
                storage_root=storage_root,
                domain=domain,
            )
        )
    return results
