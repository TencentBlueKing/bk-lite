"""PPT Master 平台侧集成：路径无关的纯函数与沙箱物化契约。"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.opspilot.metis.llm.chain.deepagent_assembly import DeepAgentAssemblyMixin
from apps.opspilot.metis.llm.chain.entity import ExtraConfig
from apps.opspilot.metis.llm.chain.skill_sandbox import SkillSandboxMixin
from apps.opspilot.services.ppt_master_runtime import (
    apply_ppt_continuation_packages,
    begin_ppt_run,
    discard_ppt_run,
    message_continues_ppt,
    packages_include_ppt_master,
    ppt_probe_reason,
    publish_latest_export,
    release_svg_quality_gate,
    repair_svg_markup,
    safe_session_id,
)

pytestmark = pytest.mark.unit


def test_safe_session_id_strips_path_and_windows_separators():
    assert safe_session_id("") == ""
    assert safe_session_id("..") == ""
    assert safe_session_id("../etc") == "etc"
    assert safe_session_id("skill:abc") == "skill_abc"
    assert safe_session_id("ok.session-1") == "ok.session-1"
    folded = safe_session_id("a:b/c")
    assert ":" not in folded
    assert "/" not in folded


def test_repair_svg_markup_drops_illegal_xml_characters():
    assert repair_svg_markup("<svg>\x00ok\x1f</svg>") == "<svg>ok</svg>"


def test_message_continues_ppt_accepts_short_confirmation_only():
    assert message_continues_ppt("确认生成") is True
    assert message_continues_ppt("继续") is True
    assert message_continues_ppt("帮我写个广州美食介绍的ppt") is False
    assert message_continues_ppt("你好") is False


def test_ppt_probe_reason_blocks_file_commands():
    assert ppt_probe_reason("ls /ppt-workspace") == "不要探测目录。"
    assert ppt_probe_reason("cat /ppt-workspace/../../etc/passwd") == "不要 cat/head/tail/cp/rm。"
    assert ppt_probe_reason("head -n 5 notes.txt") == "不要 cat/head/tail/cp/rm。"
    assert ppt_probe_reason("tail notes.txt") == "不要 cat/head/tail/cp/rm。"
    assert ppt_probe_reason("cp a b") == "不要 cat/head/tail/cp/rm。"
    assert ppt_probe_reason("rm page.svg") == "不要 cat/head/tail/cp/rm。"
    assert ppt_probe_reason(r"C:\Windows\System32\cat.exe notes.txt") == "不要 cat/head/tail/cp/rm。"
    assert ppt_probe_reason("python /skills/ppt-master/scripts/svg_to_pptx.py projects/a --quick-generate") == ""


def test_release_svg_quality_gate_keeps_original_summary(tmp_path, caplog):
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
                "summary": {"total": 1, "errors": 3, "passed": 0},
                "categories": {"blocking": {"count": 3, "issues": [{"file": "01.svg"}]}},
            }
        ),
        encoding="utf-8",
    )

    with caplog.at_level("WARNING", logger="opspilot"):
        assert release_svg_quality_gate(tmp_path) == 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["categories"]["blocking"]["count"] == 0
    assert report["summary"]["errors"] == 3
    assert report["summary"]["passed"] == 0
    assert report["platform_override"]["released"] is True
    assert report["platform_override"]["previous_blocking_count"] == 3
    assert "ppt svg quality gate overridden previous_blocking=3" in caplog.text


def test_confirmation_rewrites_matched_packages_to_enabled_ppt():
    ppt_pkg = {"package_id": "ppt-master", "name": "ppt-master"}
    other = {"package_id": "notes", "name": "notes"}
    extra = {"matched_skill_packages": [other], "enabled_skill_packages": [ppt_pkg, other]}
    model = ExtraConfig.from_raw(extra)
    matched = apply_ppt_continuation_packages(extra, "确认生成", model=model)
    assert [item["package_id"] for item in matched] == ["ppt-master"]
    assert extra["matched_skill_packages"] == [ppt_pkg]
    assert model.matched_skill_packages == [ppt_pkg]
    kept = apply_ppt_continuation_packages(
        {"matched_skill_packages": [other], "enabled_skill_packages": [ppt_pkg]},
        "你好",
    )
    assert kept == [other]
    only_enabled = {"matched_skill_packages": [], "enabled_skill_packages": [ppt_pkg]}
    assert apply_ppt_continuation_packages(only_enabled, "确认生成") == [ppt_pkg]
    assert only_enabled["matched_skill_packages"] == [ppt_pkg]


def test_publish_skips_empty_execution_id(tmp_path, monkeypatch):
    monkeypatch.setenv("OPSPILOT_PPT_TMP_ROOT", str(tmp_path))
    request = SimpleNamespace(extra_config={}, thread_id="", _ppt_export_since=time.time() - 5)
    run = begin_ppt_run(request)
    (run / "deck.pptx").write_bytes(b"PK")
    assert publish_latest_export(request, []) == ""
    assert run.is_dir()


def test_publish_skips_pptx_outside_export_window(tmp_path, monkeypatch):
    monkeypatch.setenv("OPSPILOT_PPT_TMP_ROOT", str(tmp_path))
    request = SimpleNamespace(extra_config={"execution_id": "exec-window"}, thread_id="")
    run = begin_ppt_run(request)
    (run / "deck.pptx").write_bytes(b"PK")
    request._ppt_export_since = time.time() + 60
    assert publish_latest_export(request, []) == ""
    assert run.is_dir()


def test_begin_ppt_run_sweeps_expired_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("OPSPILOT_PPT_TMP_ROOT", str(tmp_path))
    old = tmp_path / "20000101010101"
    old.mkdir()
    stale = time.time() - (24 * 60 * 60) - 30
    os.utime(old, (stale, stale))
    recent = tmp_path / "recent"
    recent.mkdir()
    request = SimpleNamespace(extra_config={}, thread_id="")
    run = begin_ppt_run(request)
    assert run.is_dir()
    assert not old.exists()
    assert recent.is_dir()
    discard_ppt_run(request)


def test_confirmation_materializes_and_binds_ppt_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("OPSPILOT_PPT_TMP_ROOT", str(tmp_path / "runs"))
    ppt_pkg = {"package_id": "ppt-master", "name": "ppt-master", "skill_markdown": "# PPT Master\n"}
    other = {"package_id": "notes", "name": "notes", "skill_markdown": "# notes\n"}
    extra = {
        "matched_skill_packages": [other],
        "enabled_skill_packages": [ppt_pkg],
        "execution_id": "exec-confirm",
    }
    request = SimpleNamespace(extra_config=extra, thread_id="")
    model = ExtraConfig.from_raw(extra)
    matched = apply_ppt_continuation_packages(extra, "确认生成", model=model)
    assert packages_include_ppt_master(matched)
    node = SkillSandboxMixin()
    monkeypatch.setattr(
        SkillSandboxMixin,
        "_load_skill_package_runtime_params",
        lambda self, graph_request, packages: ({}, []),
    )
    backend, sources, sandbox_dir = node._build_skill_backend_and_sources(request)
    try:
        assert sources == ["/skills/"]
        assert backend is not None
        assert backend._ppt_workspace is not None and backend._ppt_workspace.is_dir()
        link = Path(sandbox_dir) / "ppt-workspace"
        assert link.is_symlink()
        assert link.resolve() == backend._ppt_workspace.resolve()
        assert (Path(sandbox_dir) / "skills" / "ppt-master" / "SKILL.md").is_file()
        assert not (Path(sandbox_dir) / "skills" / "notes").exists()
        resolved = node._resolve_skill_packages(request)
        text = DeepAgentAssemblyMixin._skill_only_step_guidance(resolved, ppt_workspace=str(backend._ppt_workspace))
        assert "【ppt-master】" in text
        assert str(backend._ppt_workspace) in text
    finally:
        node._cleanup_sandbox(sandbox_dir)
        discard_ppt_run(request)


def test_failed_sandbox_build_discards_ppt_run(tmp_path, monkeypatch):
    monkeypatch.setenv("OPSPILOT_PPT_TMP_ROOT", str(tmp_path))
    request = SimpleNamespace(
        extra_config={"matched_skill_packages": [{"package_id": "ppt-master", "name": "ppt-master", "skill_markdown": "# x\n"}]},
        thread_id="",
    )
    node = SkillSandboxMixin()
    monkeypatch.setattr(
        SkillSandboxMixin,
        "_load_skill_package_runtime_params",
        lambda self, graph_request, packages: ({}, []),
    )

    class _Boom:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr("apps.opspilot.services.skill_executor.PathRewritingBackend", _Boom)
    backend, sources, sandbox_dir = node._build_skill_backend_and_sources(request)
    assert backend is None and sources == [] and sandbox_dir is None
    assert getattr(request, "_ppt_run_dir", None) is None
    assert not any(path.is_dir() for path in tmp_path.iterdir())
