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


def test_skill_package_runtime_lists_all_enabled_packages():
    """所有已启用的技能包都进 prompt,让 LLM 看完整列表后挑相关的用。

    之前 substring match 只显示 match 上的(导致"都展示误区"或"全不展示")。
    新行为列全部启用 + prompt 写"挑相关用,不要全用上",LLM 看着上下文
    决定调哪些。

    这里启用了"修复建议"包,虽然用户消息"输出 RCA 复盘"不匹配它的 trigger,
    但它仍进 prompt 让 LLM 知道有这工具(LLM 自己判断是否调用)。
    """
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

    # 所有已启用的包都进 prompt
    assert "RCA 复盘" in prompt
    assert "输出事件概述" in prompt
    assert "修复建议" in prompt
    assert "只输出修复命令" in prompt
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


def test_skill_package_runtime_matches_required_tool_by_display_name():
    from apps.opspilot.services.skill_package.runtime import build_skill_package_prompt

    prompt, matched = build_skill_package_prompt(
        base_prompt="你是运维助手。",
        skill_packages=[
            {
                "id": "kubernetes-specialist",
                "name": "Kubernetes Specialist",
                "description": "Kubernetes 专家技能包",
                "required_tools": ["kubernetes"],
                "triggers": ["k8s"],
                "skill_markdown": "Use Kubernetes workflow.",
            }
        ],
        user_message="k8s 集群下所有工作负载有什么问题",
        available_tool_names={"Kubernetes工具"},
    )

    assert "缺少依赖工具" not in prompt
    assert matched[0]["missing_tools"] == []


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

    # 新文案:"已采用技能包" 替代 "已命中技能包"
    assert "已采用技能包：Kubernetes Specialist" in prompt
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


def test_manifest_overlay_reads_skill_md_frontmatter_to_activate_capabilities(tmp_path):
    """SKILL.md frontmatter 里的 capabilities 应当覆盖 DB manifest,让 chain 路径热生效。"""
    from types import SimpleNamespace

    from apps.opspilot.services.skill_package.runtime import _manifest_with_storage_overlay

    extracted = tmp_path / "extracted"
    extracted.mkdir()
    (extracted / "SKILL.md").write_text(
        "---\n"
        "name: k8s-pack\n"
        "description: K8s 专家技能包\n"
        "capabilities:\n"
        "  - config_analysis_report\n"
        "  - repair_diff_report\n"
        "reports:\n"
        "  config_analysis:\n"
        "    event: config_analysis_report\n"
        "workflows:\n"
        "  after_config_analysis:\n"
        "    - type: choice\n"
        "---\n\n"
        "# body\n",
        encoding="utf-8",
    )

    # DB manifest 故意留空(模拟:用户重导过 ZIP 但那次没声明 capabilities)
    stored = SimpleNamespace(
        manifest={},
        storage_path=str(tmp_path),
    )

    overlay = _manifest_with_storage_overlay(stored)

    assert overlay["capabilities"] == ["config_analysis_report", "repair_diff_report"]
    assert overlay["reports"]["config_analysis"]["event"] == "config_analysis_report"
    assert overlay["workflows"]["after_config_analysis"][0]["type"] == "choice"


def test_manifest_overlay_skill_md_overrides_skill_yaml_and_db_manifest(tmp_path):
    """SKILL.md frontmatter > skill.yaml > DB manifest,后两者都不能盖过 SKILL.md。"""
    from types import SimpleNamespace

    from apps.opspilot.services.skill_package.runtime import _manifest_with_storage_overlay

    extracted = tmp_path / "extracted"
    extracted.mkdir()
    # skill.yaml 声明旧的 capabilities
    (extracted / "skill.yaml").write_text(
        "name: k8s-pack\n"
        "capabilities:\n"
        "  - browser_steps\n",
        encoding="utf-8",
    )
    # SKILL.md 声明新的 capabilities(用户最新编辑)
    (extracted / "SKILL.md").write_text(
        "---\n"
        "name: k8s-pack\n"
        "capabilities:\n"
        "  - config_analysis_report\n"
        "  - repair_diff_report\n"
        "---\n\n"
        "# body\n",
        encoding="utf-8",
    )

    stored = SimpleNamespace(
        manifest={"capabilities": ["legacy_capability"]},  # DB 里有更老的
        storage_path=str(tmp_path),
    )

    overlay = _manifest_with_storage_overlay(stored)

    # SKILL.md 的 capabilities 胜出
    assert overlay["capabilities"] == ["config_analysis_report", "repair_diff_report"]


def test_manifest_overlay_falls_back_to_db_when_skill_md_lacks_strategy_field(tmp_path):
    """SKILL.md frontmatter 没声明 capabilities 时,沿用 DB manifest(不删能力)。"""
    from types import SimpleNamespace

    from apps.opspilot.services.skill_package.runtime import _manifest_with_storage_overlay

    extracted = tmp_path / "extracted"
    extracted.mkdir()
    (extracted / "SKILL.md").write_text(
        "---\n"
        "name: k8s-pack\n"
        "description: 没声明 capabilities\n"
        "---\n\n"
        "# body\n",
        encoding="utf-8",
    )

    stored = SimpleNamespace(
        manifest={"capabilities": ["config_analysis_report"]},
        storage_path=str(tmp_path),
    )

    overlay = _manifest_with_storage_overlay(stored)

    assert overlay["capabilities"] == ["config_analysis_report"]


def test_manifest_overlay_returns_manifest_when_storage_path_is_empty(tmp_path):
    """storage_path 为空时直接返回 DB manifest,不能崩。"""
    from types import SimpleNamespace

    from apps.opspilot.services.skill_package.runtime import _manifest_with_storage_overlay

    stored = SimpleNamespace(
        manifest={"capabilities": ["config_analysis_report"]},
        storage_path="",
    )

    overlay = _manifest_with_storage_overlay(stored)

    assert overlay == {"capabilities": ["config_analysis_report"]}


def test_manifest_overlay_tolerates_malformed_skill_md(tmp_path):
    """SKILL.md 解析失败时不能崩,要安静回退到 DB manifest。"""
    from types import SimpleNamespace

    from apps.opspilot.services.skill_package.runtime import _manifest_with_storage_overlay

    extracted = tmp_path / "extracted"
    extracted.mkdir()
    (extracted / "SKILL.md").write_text(
        "---\n"
        "name: broken\n"
        "capabilities: [unclosed\n",  # YAML 解析会失败
        encoding="utf-8",
    )

    stored = SimpleNamespace(
        manifest={"capabilities": ["config_analysis_report"]},
        storage_path=str(tmp_path),
    )

    overlay = _manifest_with_storage_overlay(stored)

    assert overlay["capabilities"] == ["config_analysis_report"]


def test_skill_package_runtime_does_not_match_enabled_package_for_unrelated_message():
    """无关消息不能把已启用技能包显示为命中。"""
    from apps.opspilot.services.skill_package.runtime import build_skill_package_prompt

    prompt, matched = build_skill_package_prompt(
        base_prompt="你是运维助手。",
        skill_packages=[
            {
                "id": "kubernetes-specialist",
                "name": "Kubernetes Specialist",
                "description": "K8s 专家",
                "triggers": ["deployment", "pod"],
                "skill_markdown": "K8s.",
            }
        ],
        # "今天天气" 跟 k8s 完全无关 — 但启用了的包仍要进 prompt
        user_message="今天天气怎么样",
        available_tool_names=set(),
    )

    assert matched == []
    # prompt 用"已启用"这个新标签,不用"当前可用"
    assert "## 已启用的技能包" in prompt
    assert "## 当前可用技能包" not in prompt
    assert "Kubernetes Specialist" in prompt
    # 没有"命中标记"(老 wording 已废弃)
    assert "命中标记" not in prompt


def test_skill_package_runtime_uses_explicit_skill_request_as_strong_match():
    """用户明确要求使用某技能时,即使任务词弱也应强命中该技能。"""
    from apps.opspilot.services.skill_package.runtime import build_skill_package_prompt

    prompt, matched = build_skill_package_prompt(
        base_prompt="你是运维助手。",
        skill_packages=[
            {
                "id": "kubernetes-specialist",
                "name": "Kubernetes Specialist",
                "description": "K8s 工具",
                "triggers": ["kubernetes"],
                "skill_markdown": "K8s.",
            },
            {
                "id": "markitdown",
                "name": "Markitdown",
                "description": "Office 转 markdown",
                "triggers": ["markdown"],
                "skill_markdown": "Markitdown.",
            },
        ],
        user_message="使用 Kubernetes Specialist 技能帮我看一下",
        available_tool_names=set(),
    )

    assert [p["id"] for p in matched] == ["kubernetes-specialist"]
    assert "Kubernetes Specialist" in prompt
    assert "Markitdown" in prompt
    # 使用规则明确告诉 LLM"挑相关用,不要全用上"
    assert "挑 1 个或几个最相关的用" in prompt
    assert "已采用技能包" in prompt


def test_skill_package_runtime_matches_kubernetes_semantics_without_explicit_skill_request():
    """K8s 语义问题即使没写“使用xx技能”,也应自动命中 Kubernetes 技能包。"""
    from apps.opspilot.services.skill_package.runtime import build_skill_package_prompt

    _, matched = build_skill_package_prompt(
        base_prompt="你是运维助手。",
        skill_packages=[
            {
                "id": "kubernetes-specialist",
                "name": "Kubernetes Specialist",
                "description": "Kubernetes workload troubleshooting",
                "triggers": ["异常工作负载"],
                "skill_markdown": "Use Kubernetes troubleshooting workflow.",
            },
            {
                "id": "markitdown",
                "name": "Markitdown",
                "description": "Office 转 markdown",
                "triggers": ["markdown"],
                "skill_markdown": "Markitdown.",
            },
        ],
        user_message="查看 k8s 集群下所有的工作负载有没有配置问题",
        available_tool_names=set(),
    )

    assert [p["id"] for p in matched] == ["kubernetes-specialist"]
