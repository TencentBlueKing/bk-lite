"""内置 PPT Master：播种触发词、原文物化、执行说明、附件编号与会话目录。"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.base.models import User
from apps.opspilot.enum import SkillChannelChoices
from apps.opspilot.metis.llm.agent.tool_execution_planner import GENERATE_ATTACHMENT_FILE_TOOL_NAME, USE_SKILLS_TOOL_NAME, ToolExecutionPlanner
from apps.opspilot.metis.llm.chain.deepagent_assembly import DeepAgentAssemblyMixin
from apps.opspilot.metis.llm.chain.skill_sandbox import SkillSandboxMixin
from apps.opspilot.models import LLMSkill, SkillChannel, SkillConversation, SkillPackage
from apps.opspilot.services.ppt_master_runtime import (
    PPT_MASTER_TRIGGERS,
    attachment_filename,
    begin_ppt_run,
    conversation_workspace,
    inspect_ppt_run,
    message_continues_ppt,
    ppt_probe_reason,
    publish_latest_export,
    quarantine_unparseable_svgs,
    quote_measurement_roles,
    release_svg_quality_gate,
    repair_svg_markup,
    session_id_from_request,
    settle_ppt_export,
)
from apps.opspilot.services.skill_channel_chat_service import delete_skill_session
from apps.opspilot.services.skill_package.builtin_seed import seed_builtin_skill_package
from apps.opspilot.services.skill_package.materializer import materialize_skill_package
from apps.opspilot.services.skill_package.runtime import select_skill_packages_for_message

pytestmark = pytest.mark.django_db

VENDORED_SKILL = Path(__file__).resolve().parents[1] / "support-files" / "skill_packages" / "ppt-master" / "SKILL.md"


class _FakeBackend:
    def __init__(self):
        self.writes = {}

    def write(self, file_path, content):
        self.writes[file_path] = content

    def upload_files(self, files):
        for path, content in files:
            self.writes[path] = content


class _Tool:
    def __init__(self, name):
        self.name = name
        self.description = name


def _mini_ppt_package(tmp_path: Path) -> Path:
    root = tmp_path / "ppt-master"
    root.mkdir()
    (root / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                "name: ppt-master",
                "description: Demo ppt package",
                "metadata:",
                '  version: "6.7.2"',
                '  copyright: "Copyright (c) 2025-2026 Hugo He"',
                "---",
                "",
                "# PPT Master Skill",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return root


def test_vendored_skill_keeps_upstream_copyright():
    text = VENDORED_SKILL.read_text(encoding="utf-8")
    assert 'copyright: "Copyright (c) 2025-2026 Hugo He"' in text
    assert "python3" in text and "attribution_guard.py" in text


def test_seed_appends_triggers_without_rewriting_skill_md(tmp_path):
    source = _mini_ppt_package(tmp_path)
    before = (source / "SKILL.md").read_text(encoding="utf-8")
    result = seed_builtin_skill_package(source, storage_root=tmp_path / "storage")
    assert result.package_id == "ppt-master"
    assert result.created is True
    pkg = SkillPackage.objects.get(package_id="ppt-master", version="6.7.2")
    assert pkg.is_build_in is True
    for word in PPT_MASTER_TRIGGERS:
        assert word in pkg.triggers
    assert (source / "SKILL.md").read_text(encoding="utf-8") == before
    assert "copyright" not in (source / "SKILL.md").read_text(encoding="utf-8").split("---", 2)[2]

    matched = select_skill_packages_for_message(
        [
            {
                "package_id": pkg.package_id,
                "name": pkg.name,
                "description": pkg.description,
                "triggers": pkg.triggers,
            }
        ],
        "做一份 PPT",
    )
    assert matched and matched[0]["package_id"] == "ppt-master"


def test_materialize_writes_original_frontmatter(tmp_path):
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    original = extracted / "SKILL.md"
    original.write_text(
        '---\nname: ppt-master\ndescription: keep\nmetadata:\n  copyright: "Copyright (c) 2025-2026 Hugo He"\n---\n\n# PPT Master Skill\n',
        encoding="utf-8",
    )
    backend = _FakeBackend()
    materialize_skill_package(
        {
            "package_id": "ppt-master",
            "name": "ppt-master",
            "description": "rewritten by the platform",
            "skill_markdown": "body only",
            "extracted_root": extracted,
        },
        backend,
    )
    written = backend.writes["/skills/ppt-master/SKILL.md"]
    assert written == original.read_text(encoding="utf-8")
    assert 'copyright: "Copyright (c) 2025-2026 Hugo He"' in written


def test_attachment_names_start_at_v1_even_when_export_is_later():
    assert attachment_filename("季度汇报", []) == "季度汇报_v1.0.pptx"
    assert attachment_filename("季度汇报", ["季度汇报_v1.0.pptx"]) == "季度汇报_v1.1.pptx"


def test_publish_registers_new_versioned_attachment(tmp_path, monkeypatch):
    monkeypatch.setenv("OPSPILOT_PPT_WORKSPACE_ROOT", str(tmp_path))
    session_id = "sess-ppt-1"
    workspace = conversation_workspace(session_id, create=True)
    export_dir = workspace / "projects" / "季度汇报" / "exports"
    export_dir.mkdir(parents=True)
    request_started = time.time() - 2
    pptx = export_dir / "季度汇报_v1.2.pptx"
    pptx.write_bytes(b"PK-fake-pptx")
    created = []

    def _create(**kwargs):
        created.append(kwargs)
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(
        "apps.opspilot.services.workflow_attachment_service.create_workflow_attachment_asset",
        _create,
    )
    request = SimpleNamespace(
        extra_config={"skill_session_id": session_id, "execution_id": "exec-1"},
        thread_id="",
        _ppt_export_since=request_started,
    )
    first = publish_latest_export(request, [])
    second = publish_latest_export(request, ["季度汇报_v1.0.pptx"])
    assert first == "季度汇报_v1.0.pptx"
    assert second == "季度汇报_v1.1.pptx"
    assert created[0]["attachment_id"] != created[1]["attachment_id"]
    assert pptx.is_file()
    stale = SimpleNamespace(
        extra_config={"skill_session_id": session_id, "execution_id": "exec-2"},
        thread_id="",
        _ppt_export_since=time.time() + 30,
    )
    assert publish_latest_export(stale, ["季度汇报_v1.0.pptx", "季度汇报_v1.1.pptx"]) == ""
    assert len(created) == 2


def test_matched_plan_drops_text_pptx_tool():
    planner = ToolExecutionPlanner(llm=None)
    tools = [_Tool(USE_SKILLS_TOOL_NAME), _Tool(GENERATE_ATTACHMENT_FILE_TOOL_NAME)]
    payload = {
        "goal": "做一份 PPT",
        "steps": [{"objective": "生成幻灯片", "tools": [USE_SKILLS_TOOL_NAME, GENERATE_ATTACHMENT_FILE_TOOL_NAME]}],
    }
    plan = planner._normalize(
        payload,
        tools,
        [{"package_id": "ppt-master"}],
        user_message="生成一个pptx文件",
        ppt_master_packages=[{"package_id": "ppt-master"}],
    )
    names = [name for step in plan.steps for name in step.tools]
    assert GENERATE_ATTACHMENT_FILE_TOOL_NAME not in names
    assert USE_SKILLS_TOOL_NAME in names

    outline_only = planner._normalize(
        {"goal": "做一份 PPT", "steps": [{"objective": "生成幻灯片", "tools": [GENERATE_ATTACHMENT_FILE_TOOL_NAME]}]},
        tools,
        [{"package_id": "ppt-master"}],
        user_message="帮我写个广州美食介绍的ppt",
        ppt_master_packages=[{"package_id": "ppt-master"}],
    )
    outline_names = [name for step in outline_only.steps for name in step.tools]
    assert outline_names == [USE_SKILLS_TOOL_NAME]

    injected = planner._normalize(
        {"goal": "写文件", "steps": [{"objective": "写正文", "tools": [USE_SKILLS_TOOL_NAME]}]},
        tools,
        [{"package_id": "ppt-master"}],
        user_message="生成一个pptx文件",
        ppt_master_packages=[],
    )
    injected_names = [name for step in injected.steps for name in step.tools]
    assert GENERATE_ATTACHMENT_FILE_TOOL_NAME in injected_names

    collapsed = planner._normalize(
        {
            "goal": "做一份 PPT",
            "steps": [
                {"objective": "读取技能说明", "tools": [USE_SKILLS_TOOL_NAME]},
                {"objective": "组织内容结构", "tools": [USE_SKILLS_TOOL_NAME]},
            ],
        },
        tools,
        [{"package_id": "ppt-master"}],
        user_message="帮我写个广州美食介绍的ppt",
        ppt_master_packages=[{"package_id": "ppt-master"}],
    )
    assert len(collapsed.steps) == 1
    assert collapsed.steps[0].tools == [USE_SKILLS_TOOL_NAME]
    assert "导出" in collapsed.steps[0].objective


def test_settle_ppt_export_runs_quick_generate(tmp_path, monkeypatch):
    svg_dir = tmp_path / "projects" / "food" / "svg_output"
    svg_dir.mkdir(parents=True)
    (svg_dir / "01.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'><text>广州</text></svg>", encoding="utf-8")
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs.get("cwd")))
        export_dir = tmp_path / "projects" / "food" / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        (export_dir / "food.pptx").write_bytes(b"PK")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("apps.opspilot.services.ppt_master_runtime.subprocess.run", fake_run)
    assert inspect_ppt_run(tmp_path) == (False, 1)
    assert settle_ppt_export(tmp_path) == "exported"
    assert calls[0][0][-2:] == ["projects/food", "--quick-generate"]
    assert calls[0][1] == str(tmp_path)
    assert inspect_ppt_run(tmp_path) == (True, 0)


def test_quarantine_unparseable_svg_keeps_valid_page(tmp_path):
    svg_dir = tmp_path / "svg_output"
    svg_dir.mkdir()
    (svg_dir / "ok.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'><text>A &amp; B</text></svg>", encoding="utf-8")
    (svg_dir / "bad.svg").write_text("<svg><text>A & B</text><notclosed>", encoding="utf-8")
    assert quarantine_unparseable_svgs(tmp_path) == 1
    assert (svg_dir / "ok.svg").is_file()
    assert not (svg_dir / "bad.svg").exists()
    assert (svg_dir / "bad.svg.broken").is_file()


def test_studio_thread_gets_a_writable_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("OPSPILOT_PPT_WORKSPACE_ROOT", str(tmp_path))
    request = SimpleNamespace(
        extra_config={"conversation_key": "thread:debug-thread-1", "execution_id": "exec-9"},
        thread_id="debug-thread-1",
    )
    session_id = session_id_from_request(request)
    assert ":" not in session_id
    workspace = conversation_workspace(session_id, create=True)
    assert workspace is not None and workspace.is_dir()
    skill_request = SimpleNamespace(extra_config={"skill_session_id": "sess-ppt-1"}, thread_id="other")
    assert session_id_from_request(skill_request) == "sess-ppt-1"


def test_execution_guidance_blocks_pdf_and_unsupported_routes():
    text = DeepAgentAssemblyMixin._skill_only_step_guidance(
        [{"package_id": "ppt-master"}],
        ppt_workspace="D:/ppt-workspaces/sess",
    )
    assert "source_to_md.py" in text
    assert "pdf_to_md.py" in text
    assert "不要 pip install" in text
    assert "旁白" in text
    assert "生图" in text
    assert "网页" in text
    assert "D:/ppt-workspaces/sess" in text
    assert "先写每一页 SVG" in text
    assert "禁止用 python-pptx" in text
    assert "禁止 &&" in text
    assert "不要执行 pwd 或 cd" in text
    assert "attribution_guard.py" in text
    assert "svg_to_pptx.py" in text
    assert "/ppt-workspace" in text
    assert "read_file /skills/ppt-master/SKILL.md" in text


def test_timestamp_directory_is_removed_after_export(tmp_path, monkeypatch):
    monkeypatch.setenv("OPSPILOT_PPT_TMP_ROOT", str(tmp_path))
    request = SimpleNamespace(extra_config={"execution_id": "exec-1"}, thread_id="")
    run = begin_ppt_run(request)
    assert run.parent == tmp_path
    assert run.name[:14].isdigit()
    assert request._ppt_run_stamp == run.name
    request._ppt_export_since = time.time() - 2
    export_dir = run / "projects" / "广州美食" / "exports"
    export_dir.mkdir(parents=True)
    (export_dir / "deck.pptx").write_bytes(b"PK-fake-pptx")

    def _create(**kwargs):
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(
        "apps.opspilot.services.workflow_attachment_service.create_workflow_attachment_asset",
        _create,
    )
    filename = publish_latest_export(request, [])
    assert filename == "广州美食_v1.0.pptx"
    assert not run.exists()


def test_quote_measurement_roles_keeps_font_family():
    command = (
        "python /skills/ppt-master/scripts/text_measure.py calibrate projects/demo "
        "--role title:Microsoft YaHei:60 --role body:Microsoft YaHei:24:bold"
    )
    quoted = quote_measurement_roles(command)
    assert '--role "title:Microsoft YaHei:60"' in quoted
    assert '--role "body:Microsoft YaHei:24:bold"' in quoted


def test_release_svg_quality_gate_clears_blocking_findings(tmp_path):
    svg_dir = tmp_path / "projects" / "demo" / "svg_output"
    svg_dir.mkdir(parents=True)
    (svg_dir / "01.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"></svg>', encoding="utf-8")
    report_path = tmp_path / "projects" / "demo" / "validation" / "svg_quality_report.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(
        json.dumps(
            {
                "schema": "ppt-master.svg-quality-report.v1",
                "stage": "final",
                "categories": {"blocking": {"count": 3, "issues": [{"file": "01.svg"}]}},
            }
        ),
        encoding="utf-8",
    )

    assert release_svg_quality_gate(tmp_path) == 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["categories"]["blocking"]["count"] == 0
    assert report["categories"]["blocking"]["issues"] == []
    assert report["source_fingerprint"]["file_count"] == 1
    assert report["stage"] == "final"


def test_release_svg_quality_gate_skips_unparseable_svg(tmp_path):
    svg_dir = tmp_path / "projects" / "demo" / "svg_output"
    svg_dir.mkdir(parents=True)
    (svg_dir / "01.svg").write_text("<svg><text>a & b</text></svg>", encoding="utf-8")

    assert release_svg_quality_gate(tmp_path) == 0
    assert not (tmp_path / "projects" / "demo" / "validation" / "svg_quality_report.json").exists()


def test_publish_records_download_event(tmp_path, monkeypatch):
    monkeypatch.setenv("OPSPILOT_PPT_TMP_ROOT", str(tmp_path))
    request = SimpleNamespace(extra_config={"execution_id": "exec-ppt"}, thread_id="thread-ppt")
    run = begin_ppt_run(request)
    export_dir = run / "projects" / "demo" / "exports"
    export_dir.mkdir(parents=True)
    (export_dir / "demo.pptx").write_bytes(b"PK-fake-pptx")

    def _create(**kwargs):
        return SimpleNamespace(id=7, **kwargs)

    monkeypatch.setattr(
        "apps.opspilot.services.workflow_attachment_service.create_workflow_attachment_asset",
        _create,
    )
    filename = publish_latest_export(request, [])
    event = request._ppt_download_event
    assert filename == "demo_v1.0.pptx"
    assert event["filename"] == filename
    assert event["file_url"].startswith("/api/proxy/opspilot/bot_mgmt/workflow_attachment/download/")
    assert event["mime_type"].endswith("presentationml.presentation")


def test_repair_svg_markup_escapes_bare_ampersand():
    import xml.etree.ElementTree as ET

    text = repair_svg_markup('<svg xmlns="http://www.w3.org/2000/svg"><text>A & B&nbsp;</text></svg>')
    ET.fromstring(text)
    assert "A &amp; B" in text
    assert "&nbsp;" not in text


def test_ppt_probe_commands_are_rejected():
    assert ppt_probe_reason("ls /ppt-workspace") == "不要探测目录。"
    assert ppt_probe_reason("ls -d /ppt-workspace") == "不要探测目录。"
    assert ppt_probe_reason("dir") == "不要探测目录。"
    assert ppt_probe_reason('python -c "print(1)"') == "不要 python -c。"
    assert ppt_probe_reason(r'D:\app\venv\bkliteserver\Scripts\python.exe -c "import os;print(os.getcwd())"') == "不要 python -c。"
    assert ppt_probe_reason("python /skills/ppt-master/scripts/icon_sync.py --help") == "不要 --help。"
    assert ppt_probe_reason("python /skills/ppt-master/scripts/svg_to_pptx.py projects/a --quick-generate") == ""


def test_short_confirmation_stays_on_ppt_master():
    assert message_continues_ppt("确认生成") is True
    assert message_continues_ppt("继续") is True
    assert message_continues_ppt("帮我写个广州美食介绍的ppt") is False
    assert message_continues_ppt("你好") is False


def test_ppt_master_requirements_are_not_pip_installed(tmp_path, monkeypatch):
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    (extracted / "requirements.txt").write_text("definitely-not-a-real-package\n", encoding="utf-8")
    calls = []

    def _run(*args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(subprocess, "run", _run)
    SkillSandboxMixin._ensure_skill_deps(
        [
            {
                "package_id": "ppt-master",
                "name": "ppt-master",
                "extracted_root": extracted,
                "required_python_packages": ["definitely-not-a-real-package"],
            }
        ]
    )
    assert calls == []


def test_delete_skill_session_removes_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("OPSPILOT_PPT_WORKSPACE_ROOT", str(tmp_path))
    session_id = "sess-ppt-del"
    workspace = conversation_workspace(session_id, create=True)
    (workspace / "marker.txt").write_text("keep", encoding="utf-8")
    user = User.objects.create_user(
        username="ppt_owner",
        password="x",
        domain="domain.com",
        locale="en",
        group_list=[{"id": 1, "name": "T1"}],
        roles=["admin"],
    )
    skill = LLMSkill.objects.create(name="ppt-skill", team=[1], usage_team=[1])
    channel = SkillChannel.objects.create(
        skill=skill,
        channel_type=SkillChannelChoices.WEB_CHAT,
        enabled=True,
        usage_team=[1],
        name="web",
    )
    owner = f"{user.username}@{user.domain}"
    SkillConversation.objects.create(session_id=session_id, skill=skill, channel=channel, external_user_id=owner)
    delete_skill_session(session_id=session_id, external_user_id=owner)
    assert not SkillConversation.objects.filter(session_id=session_id).exists()
    assert not workspace.exists()


@pytest.mark.asyncio
async def test_ppt_download_registration_leaves_the_async_loop(monkeypatch):
    import asyncio

    from apps.opspilot.metis.llm.chain.skill_sandbox import SkillSandboxMixin

    request = SimpleNamespace()
    seen = {}

    def fake_publish(graph_request, prior_filenames):
        del prior_filenames
        try:
            asyncio.get_running_loop()
            seen["in_running_loop"] = True
        except RuntimeError:
            seen["in_running_loop"] = False
        graph_request._ppt_download_event = {
            "download_id": "abc",
            "filename": "food_v1.0.pptx",
            "file_url": "/download/food",
            "mime_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        }
        return "food_v1.0.pptx"

    events = []

    async def fake_dispatch(name, event, config=None):
        del config
        events.append((name, event))

    monkeypatch.setattr("apps.opspilot.metis.llm.chain.skill_sandbox.publish_latest_export", fake_publish)
    monkeypatch.setattr("apps.opspilot.metis.llm.chain.skill_sandbox.adispatch_custom_event", fake_dispatch)
    await SkillSandboxMixin._publish_ppt_master_export(request, [], config={"configurable": {}})
    assert seen["in_running_loop"] is False
    assert events[0][0] == "report_file_download"
    assert events[0][1]["filename"] == "food_v1.0.pptx"
