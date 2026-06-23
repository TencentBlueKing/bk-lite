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


def test_skill_package_importer_requires_skill_doc(tmp_path):
    from apps.opspilot.services.skill_package.importer import SkillPackageImporter

    archive_path = tmp_path / "broken.zip"
    archive_path.write_bytes(_build_skill_zip({"skill.yaml": "id: rca\nname: RCA\n"}).getvalue())

    importer = SkillPackageImporter(storage_root=tmp_path / ".skill")

    with pytest.raises(ValueError, match="SKILL.md"):
        importer.import_zip(archive_path, organization_id="default")


def test_skill_package_importer_accepts_skill_doc_frontmatter_without_manifest(tmp_path):
    from apps.opspilot.services.skill_package.importer import SkillPackageImporter

    archive_path = tmp_path / "claude-style.zip"
    archive_path.write_bytes(
        _build_skill_zip(
            {
                "kubernetes-specialist/SKILL.md": """---
id: kubernetes-specialist
name: Kubernetes Specialist
version: 1.2.0
description: Kubernetes 专家技能包
required_tools:
  - kubernetes
triggers:
  - k8s
---
# Kubernetes Specialist

排查 Kubernetes 工作负载、网络、存储和 Helm 问题。
""",
                "kubernetes-specialist/references/checklist.md": "排查清单",
            }
        ).getvalue()
    )

    result = SkillPackageImporter(storage_root=tmp_path / ".skill").import_zip(
        archive_path,
        organization_id="default",
    )

    assert result.skill_id == "kubernetes-specialist"
    assert result.name == "Kubernetes Specialist"
    assert result.version == "1.2.0"
    assert result.description == "Kubernetes 专家技能包"
    assert result.required_tools == ["kubernetes"]
    assert result.triggers == ["k8s"]
    assert (result.storage_path / "extracted" / "SKILL.md").exists()
    assert (result.storage_path / "extracted" / "references" / "checklist.md").exists()


def test_skill_package_importer_derives_metadata_from_skill_doc_without_frontmatter(tmp_path):
    from apps.opspilot.services.skill_package.importer import SkillPackageImporter

    archive_path = tmp_path / "plain.zip"
    archive_path.write_bytes(
        _build_skill_zip(
            {
                "plain-skill/SKILL.md": "# Plain Skill\n\n只有技能说明，没有 YAML 元数据。",
            }
        ).getvalue()
    )

    result = SkillPackageImporter(storage_root=tmp_path / ".skill").import_zip(
        archive_path,
        organization_id="default",
    )

    assert result.skill_id == "plain-skill"
    assert result.name == "Plain Skill"
    assert result.version == "0.1.0"


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


def test_skill_package_runtime_accepts_agui_message_list():
    from apps.opspilot.services.skill_package.runtime import append_matching_skill_packages_to_prompt

    prompt = append_matching_skill_packages_to_prompt(
        base_prompt="你是运维助手。",
        skill_packages=[
            {
                "name": "agent-browser-prompt-only",
                "description": "浏览器自动化问答技能",
                "triggers": ["打开网站", "浏览器自动化"],
                "skill_markdown": "已命中 OpsPilot 技能包: agent-browser-prompt-only",
            }
        ],
        user_message=[{"role": "user", "content": "帮我打开 https://example.com，并告诉我需要哪些浏览器自动化步骤"}],
        available_tool_names=set(),
    )

    assert "agent-browser-prompt-only" in prompt
    assert "已命中 OpsPilot 技能包" in prompt


def test_skill_package_runtime_adds_visible_hit_marker():
    from apps.opspilot.services.skill_package.runtime import append_matching_skill_packages_to_prompt

    prompt = append_matching_skill_packages_to_prompt(
        base_prompt="你是运维助手。",
        skill_packages=[
            {
                "id": "kubernetes-specialist",
                "name": "Kubernetes Specialist",
                "description": "Kubernetes workload troubleshooting",
                "triggers": ["K8s", "异常工作负载"],
                "skill_markdown": "Use Kubernetes troubleshooting workflow.",
            }
        ],
        user_message="查看当前 K8s 集群有哪些异常工作负载",
        available_tool_names={"kubernetes"},
    )

    assert "已命中技能包：Kubernetes Specialist" in prompt
    assert "必须在思考区或最终答复开头写明" in prompt


def test_skill_package_runtime_returns_matched_package_summaries():
    from apps.opspilot.services.skill_package.runtime import build_skill_package_prompt

    prompt, matched = build_skill_package_prompt(
        base_prompt="你是运维助手。",
        skill_packages=[
            {
                "id": "agent-browser",
                "name": "agent-browser",
                "description": "Browser automation",
                "required_tools": ["agent_browser"],
                "triggers": ["open a website"],
                "capabilities": ["browser_automation"],
                "reports": {"browser_steps": {"event": "browser_step_progress"}},
                "workflows": {"after_navigation": [{"type": "summarize"}]},
                "skill_markdown": "Use browser workflow.",
            }
        ],
        user_message="open a website",
        available_tool_names=set(),
    )

    assert "agent-browser" in prompt
    assert matched == [
        {
            "id": "agent-browser",
            "package_id": "agent-browser",
            "name": "agent-browser",
            "description": "Browser automation",
            "missing_tools": ["agent_browser"],
            "capabilities": ["browser_automation"],
            "reports": {"browser_steps": {"event": "browser_step_progress"}},
            "workflows": {"after_navigation": [{"type": "summarize"}]},
        }
    ]


def test_skill_package_runtime_normalizes_report_capabilities_from_manifest():
    from apps.opspilot.services.skill_package.runtime import build_skill_package_prompt

    _, matched = build_skill_package_prompt(
        base_prompt="你是运维助手。",
        skill_packages=[
            {
                "id": "kubernetes-specialist",
                "name": "Kubernetes Specialist",
                "description": "Kubernetes 专家技能包",
                "required_tools": ["kubernetes"],
                "triggers": ["deployment"],
                "capabilities": ["config_analysis_report", "repair_diff_report"],
                "reports": {
                    "config_analysis": {
                        "source_tool": "analyze_deployment_configurations",
                        "event": "config_analysis_report",
                    }
                },
                "workflows": {
                    "after_config_analysis": [
                        {"type": "choice", "when": "has_issues"},
                        {"type": "render_diff", "template": "repair_diff"},
                    ]
                },
                "skill_markdown": "Use Kubernetes expert audit workflow.",
            }
        ],
        user_message="检查 deployment 配置风险",
        available_tool_names={"kubernetes"},
    )

    assert matched[0]["capabilities"] == ["config_analysis_report", "repair_diff_report"]
    assert matched[0]["reports"]["config_analysis"]["source_tool"] == "analyze_deployment_configurations"
    assert matched[0]["workflows"]["after_config_analysis"][0]["type"] == "choice"


def test_skill_package_strategy_merges_capabilities_reports_and_workflows():
    from apps.opspilot.services.skill_package.runtime import build_skill_package_strategy

    strategy = build_skill_package_strategy(
        [
            {
                "capabilities": ["config_analysis_report", "repair_diff_report"],
                "reports": {"config_analysis": {"event": "config_analysis_report"}},
                "workflows": {"after_config_analysis": [{"type": "choice"}]},
            },
            {
                "capabilities": ["repair_diff_report", "browser_steps"],
                "reports": {"browser_steps": {"event": "browser_step_progress"}},
                "workflows": {"after_navigation": [{"type": "summarize"}]},
            },
        ]
    )

    assert strategy["skill_package_capabilities"] == [
        "config_analysis_report",
        "repair_diff_report",
        "browser_steps",
    ]
    assert strategy["skill_package_reports"]["config_analysis"]["event"] == "config_analysis_report"
    assert strategy["skill_package_reports"]["browser_steps"]["event"] == "browser_step_progress"
    assert strategy["skill_package_workflows"]["after_config_analysis"][0]["type"] == "choice"
