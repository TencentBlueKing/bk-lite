import io
import zipfile

import pytest


def _build_skill_zip(files: dict[str, str]) -> io.BytesIO:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    buffer.seek(0)
    return buffer


def test_skill_package_importer_requires_manifest_and_skill_doc(tmp_path):
    from apps.opspilot.services.skill_package.importer import SkillPackageImporter

    archive_path = tmp_path / "broken.zip"
    archive_path.write_bytes(_build_skill_zip({"skill.yaml": "id: rca\nname: RCA\n"}).getvalue())

    importer = SkillPackageImporter(storage_root=tmp_path / ".skill")

    with pytest.raises(ValueError, match="SKILL.md"):
        importer.import_zip(archive_path, organization_id="default")


def test_skill_package_importer_stores_zip_and_rejects_path_escape(tmp_path):
    from apps.opspilot.services.skill_package.importer import SkillPackageImporter

    archive_path = tmp_path / "unsafe.zip"
    archive_path.write_bytes(
        _build_skill_zip(
            {
                "rca/skill.yaml": """
id: rca-review
name: RCA 复盘
version: 1.0.0
description: 发现异常并输出 RCA 报告
required_tools:
  - kubernetes
triggers:
  - RCA
  - 根因
""",
                "rca/SKILL.md": "# RCA 复盘\n\n按证据链输出根因报告。",
                "rca/references/troubleshooting.md": "排查参考",
                "../escape.txt": "bad",
            }
        ).getvalue()
    )

    importer = SkillPackageImporter(storage_root=tmp_path / ".skill")

    with pytest.raises(ValueError, match="非法路径"):
        importer.import_zip(archive_path, organization_id="default")
    assert not (tmp_path / "escape.txt").exists()


def test_skill_package_importer_extracts_valid_package(tmp_path):
    from apps.opspilot.services.skill_package.importer import SkillPackageImporter

    archive_path = tmp_path / "rca.zip"
    archive_path.write_bytes(
        _build_skill_zip(
            {
                "rca/skill.yaml": """
id: rca-review
name: RCA 复盘
version: 1.0.0
description: 发现异常并输出 RCA 报告
required_tools:
  - kubernetes
  - 日志查询工具
triggers:
  - RCA
  - 根因
""",
                "rca/SKILL.md": "# RCA 复盘\n\n按证据链输出根因报告。",
            }
        ).getvalue()
    )

    result = SkillPackageImporter(storage_root=tmp_path / ".skill").import_zip(
        archive_path,
        organization_id="default",
    )

    assert result.skill_id == "rca-review"
    assert result.name == "RCA 复盘"
    assert result.required_tools == ["kubernetes", "日志查询工具"]
    assert (result.storage_path / "original.zip").exists()
    assert (result.storage_path / "extracted" / "SKILL.md").read_text(encoding="utf-8").startswith("# RCA")


def test_skill_package_runtime_selects_relevant_skill_only():
    from apps.opspilot.services.skill_package.runtime import append_matching_skill_packages_to_prompt

    prompt = append_matching_skill_packages_to_prompt(
        base_prompt="你是运维助手。",
        skill_packages=[
            {
                "name": "RCA 复盘",
                "description": "根因分析与复盘报告",
                "required_tools": ["kubernetes"],
                "triggers": ["RCA", "根因", "异常"],
                "skill_markdown": "输出事件概述、分析过程、根因结论。",
            },
            {
                "name": "修复建议",
                "description": "生成修复命令",
                "triggers": ["修复命令"],
                "skill_markdown": "只输出修复命令。",
            },
        ],
        user_message="看看当前 K8s 集群有哪些异常，并输出 RCA 复盘报告",
        available_tool_names={"kubernetes"},
    )

    assert "RCA 复盘" in prompt
    assert "输出事件概述" in prompt
    assert "修复建议" not in prompt
    assert "缺少依赖工具" not in prompt


def test_skill_package_runtime_marks_missing_required_tools():
    from apps.opspilot.services.skill_package.runtime import append_matching_skill_packages_to_prompt

    prompt = append_matching_skill_packages_to_prompt(
        base_prompt="你是运维助手。",
        skill_packages=[
            {
                "name": "RCA 复盘",
                "description": "根因分析",
                "required_tools": ["kubernetes", "日志查询工具"],
                "triggers": ["RCA"],
                "skill_markdown": "输出 RCA。",
            }
        ],
        user_message="输出 RCA",
        available_tool_names={"kubernetes"},
    )

    assert "缺少依赖工具：日志查询工具" in prompt
