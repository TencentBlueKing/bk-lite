"""import_local_dir 单元测试(纯函数,只摸 tmp_path,不打 DB)。

覆盖:
  - 合法 anthropic/skills 风格目录(SKILL.md + scripts/)正确物化到 storage_path
  - 缺 SKILL.md 报错
  - source_dir 越界 storage_root 报错(防越界)
  - frontmatter / skill.yaml 都能读 manifest

另:enabled_skill_packages 通路(viewset 层)见 test_llm_viewset_views.py 同类断言,
  这里只覆盖 importer 的 import_local_dir。
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from apps.opspilot.services.skill_package.importer import SkillPackageImporter

pytestmark = pytest.mark.unit


@pytest.fixture
def storage_root(tmp_path: Path) -> Path:
    """临时 storage_root,importer 默认会走它。"""
    root = tmp_path / ".skill" / "packages"
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture
def importer(storage_root: Path) -> SkillPackageImporter:
    return SkillPackageImporter(storage_root=storage_root)


def _make_skill_dir(
    base: Path,
    *,
    name: str = "demo-skill",
    body: str = "# demo\n\n## When to Use\nUse this skill to demo.\n",
    frontmatter: dict | None = None,
    extra_files: dict[str, str] | None = None,
) -> Path:
    """在 base 下创建一个 anthropic/skills 风格的目录,返回其路径。

    注意:base 必须在 storage_root 之下(import_local_dir 的越界校验要求)。
    """
    skill_dir = base / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    if frontmatter is None:
        frontmatter = {"name": name, "description": f"Demo skill {name}"}
    fm_lines = "\n".join(f"{k}: {v}" for k, v in frontmatter.items())
    skill_md = f"---\n{fm_lines}\n---\n\n{body}"
    (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")
    for rel, content in (extra_files or {}).items():
        target = skill_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return skill_dir


def test_import_local_dir_copies_skill_md_and_scripts(importer, storage_root):
    """合法 skill 目录 → 物化到 storage_root/{org}/{id}/{version}/extracted/。"""
    # 模拟生产布局:storage_root/1/<skill_name>/  (organization_id = "1")
    skill_dir = _make_skill_dir(
        storage_root / "1",
        name="pdf-reader",
        body="# PDF Reader\n\nRead PDFs.\n",
        extra_files={
            "scripts/extract.py": "import sys; print(sys.argv[1])\n",
            "references/guide.md": "# Guide\n",
        },
    )

    result = importer.import_local_dir(skill_dir, organization_id="1")

    assert result.skill_id == "pdf-reader"
    assert result.name == "pdf-reader"
    assert result.version == "0.1.0"
    # storage_path 指向 .../{org}/{id}/{version}/(与 zip 导入对齐)
    assert result.storage_path == storage_root / "1" / "pdf-reader" / "0.1.0"
    extracted = result.storage_path / "extracted"
    assert (extracted / "SKILL.md").is_file()
    assert (extracted / "scripts" / "extract.py").is_file()
    assert (extracted / "references" / "guide.md").is_file()
    # manifest 从 frontmatter 读
    assert result.manifest["name"] == "pdf-reader"
    assert result.manifest["description"] == "Demo skill pdf-reader"
    # skill_markdown 不含 frontmatter(与 zip 导入行为一致)
    assert "---" not in result.skill_markdown.split("\n\n", 1)[0]
    assert "PDF Reader" in result.skill_markdown


def test_import_local_dir_missing_skill_md(importer, storage_root):
    """缺 SKILL.md → 报错。"""
    skill_dir = storage_root / "1" / "broken"
    skill_dir.mkdir(parents=True)
    (skill_dir / "README.md").write_text("# not a skill")
    with pytest.raises(ValueError, match="缺少 SKILL.md"):
        importer.import_local_dir(skill_dir)


def test_import_local_dir_rejects_outside_storage_root(importer, tmp_path):
    """source_dir 必须在 storage_root 之下,防越界复制任意路径。"""
    # 在 storage_root 之外(tmp_path 根下)建一个 skill
    outside = tmp_path / "outside"
    outside.mkdir()
    skill_dir = _make_skill_dir(outside, name="evil")
    with pytest.raises(ValueError, match="必须在"):
        importer.import_local_dir(skill_dir)


def test_import_local_dir_reads_skill_yaml_manifest(importer, storage_root):
    """存在 skill.yaml 时,manifest 优先从 skill.yaml 读;frontmatter 仅作 SKILL.md 内容来源。"""
    skill_dir = _make_skill_dir(
        storage_root / "1",
        name="with-yaml",
        body="body from SKILL.md\n",
        frontmatter={"name": "with-yaml", "description": "from frontmatter"},
        extra_files={
            "skill.yaml": "name: from-yaml\ndescription: from skill.yaml\nversion: 1.2.3\nrequired_tools:\n  - pdftotext\n",
        },
    )
    result = importer.import_local_dir(skill_dir, organization_id="default")
    assert result.manifest["name"] == "from-yaml"
    assert result.manifest["description"] == "from skill.yaml"
    assert result.manifest["version"] == "1.2.3"
    assert result.required_tools == ["pdftotext"]
    assert result.version == "1.2.3"
    # skill_markdown 用的是 SKILL.md body(剥 frontmatter 后)
    assert "body from SKILL.md" in result.skill_markdown


def test_import_local_dir_runtime_section_warning(importer, storage_root, caplog):
    """缺 ## Runtime 段 → warn-only(默认不阻断);严格模式下抛错。"""
    skill_dir = _make_skill_dir(
        storage_root / "1",
        name="no-runtime",
        body="# Just docs\nNo runtime section here.\n",
    )
    # 默认 warn-only
    with caplog.at_level("WARNING", logger="apps.opspilot.skill_package.importer"):
        result = importer.import_local_dir(skill_dir, organization_id="1")
    assert result.runtime_section_present is False
    assert any("Runtime" in rec.message for rec in caplog.records)

    # 严格模式 → 抛错
    skill_dir2 = _make_skill_dir(
        storage_root / "1", name="strict", body="# x\n"
    )
    os.environ["OPSPILOT_REQUIRE_RUNTIME_SECTION"] = "true"
    try:
        with pytest.raises(ValueError, match="Runtime"):
            importer.import_local_dir(skill_dir2, organization_id="1")
    finally:
        os.environ.pop("OPSPILOT_REQUIRE_RUNTIME_SECTION", None)


def test_import_local_dir_reimport_overwrites_storage(importer, storage_root):
    """同一 skill 二次导入:storage_path 内容被覆盖,而不是叠加。"""
    skill_dir = _make_skill_dir(
        storage_root / "1",
        name="reimport",
        body="v1\n",
        extra_files={"scripts/v1.py": "# v1\n"},
    )
    importer.import_local_dir(skill_dir, organization_id="1")

    # 同一目录,改 body 与脚本,二次导入
    (skill_dir / "SKILL.md").write_text(
        "---\nname: reimport\ndescription: desc\n---\n\nv2\n",
        encoding="utf-8",
    )
    (skill_dir / "scripts" / "v1.py").unlink()
    (skill_dir / "scripts" / "v2.py").write_text("# v2\n", encoding="utf-8")

    result = importer.import_local_dir(skill_dir, organization_id="1")
    extracted = result.storage_path / "extracted"
    assert (extracted / "SKILL.md").read_text(encoding="utf-8").endswith("v2\n")
    assert not (extracted / "scripts" / "v1.py").exists()
    assert (extracted / "scripts" / "v2.py").is_file()
