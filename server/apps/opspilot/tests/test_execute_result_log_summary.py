"""execute 结果日志摘要:只记成功/失败与是否有数据。"""
from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from apps.opspilot.services.skill_executor.path_rewriting_backend import (
    _sandbox_deny_result,
    _summarize_execute_output,
    list_skill_scripts_for_command,
    skill_execute_result_guidance,
)

pytestmark = pytest.mark.unit


def test_summarize_skill_ok_with_entries():
    text = '{"ok":true,"data":{"type":"user","query":"*","count":10,"entries":[{"sAMAccountName":"a"}]}}'
    summary = _summarize_execute_output(text, 0)
    assert summary == {"ok": True, "has_data": True, "detail": "count=1"}


def test_summarize_skill_ok_empty_entries():
    text = '{"ok":true,"data":{"type":"user","query":"missing","count":0,"entries":[]}}'
    summary = _summarize_execute_output(text, 0)
    assert summary == {"ok": True, "has_data": False, "detail": "count=0"}


def test_summarize_skill_error_code_only():
    text = '{"ok":false,"error":{"code":6,"message":"Cannot reach host"}}'
    summary = _summarize_execute_output(text, 6)
    assert summary["ok"] is False
    assert summary["has_data"] is False
    assert summary["detail"] == "error_code=6"


def test_summarize_does_not_embed_business_fields():
    text = (
        '{"ok":true,"data":{"count":2,"entries":['
        '{"sAMAccountName":"Administrator","mail":"Administrator@bktest.com.cn"},'
        '{"sAMAccountName":"Guest","mail":"Guest@bktest.com.cn"}]}}'
    )
    summary = _summarize_execute_output(text, 0)
    blob = str(summary)
    assert "Administrator" not in blob
    assert "bktest.com.cn" not in blob
    assert summary["detail"] == "count=2"


def test_skill_result_guidance_stops_on_empty_success():
    cmd = "python3 /skills/ad-domain-ops/scripts/ad_search.py --query '*' --type user"
    text = '{"ok":true,"data":{"count":0,"entries":[]}}'
    hint = skill_execute_result_guidance(cmd, text, 0)
    assert "[OPSPILOT_SKILL_RESULT]" in hint
    assert "空结果" in hint
    assert "不要重试" in hint
    assert "read_file" in hint


def test_skill_result_guidance_stops_on_success_with_data():
    cmd = "python3 /skills/ad-domain-ops/scripts/ad_search.py --query admin --type user"
    text = '{"ok":true,"data":{"count":1,"entries":[{"sAMAccountName":"a"}]}}'
    hint = skill_execute_result_guidance(cmd, text, 0)
    assert "最终结果" in hint
    assert "禁止再次 execute" in hint


def test_skill_result_guidance_limits_retry_on_failure():
    cmd = "python3 /skills/ad-domain-ops/scripts/ad_search.py --query x --type user"
    text = '{"ok":false,"error":{"code":6,"message":"Cannot reach"}}'
    hint = skill_execute_result_guidance(cmd, text, 6)
    assert "最多" in hint and "1 次" in hint


def test_skill_result_guidance_skips_non_skill_commands():
    hint = skill_execute_result_guidance('python3 -c "print(1)"', "1", 0)
    assert hint == ""


def test_skill_result_guidance_skips_ls_of_scripts_dir():
    hint = skill_execute_result_guidance("ls -la /skills/ad-domain-ops/scripts/", "dir listing", 1)
    assert hint == ""


def test_skill_result_guidance_missing_script_lists_real_files():
    cmd = "python3 /skills/ad-domain-ops/scripts/query_users.py 10"
    text = "can't open file 'C:\\\\tmp\\\\query_users.py': [Errno 2] No such file or directory"
    hint = skill_execute_result_guidance(
        cmd,
        text,
        2,
        available_scripts=["/skills/ad-domain-ops/scripts/ad_search.py"],
    )
    assert "脚本不存在" in hint
    assert "ad_search.py" in hint
    assert "query_users.py" not in hint or "改跑" in hint
    assert "ls/glob" in hint


def test_list_skill_scripts_for_command_skips_private_modules(tmp_path):
    scripts = tmp_path / "skills" / "ad-domain-ops" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "ad_search.py").write_text("print(1)\n", encoding="utf-8")
    (scripts / "_lib.py").write_text("x=1\n", encoding="utf-8")
    listed = list_skill_scripts_for_command(
        "python3 /skills/ad-domain-ops/scripts/query_users.py",
        tmp_path,
    )
    assert listed == ["/skills/ad-domain-ops/scripts/ad_search.py"]


def test_skill_result_guidance_argparse_usage_tells_exact_retry():
    cmd = "python3 /skills/ad-domain-ops/scripts/ad_search.py --limit 10 --field samAccountName"
    text = "ad_search.py: error: the following arguments are required: --query"
    hint = skill_execute_result_guidance(cmd, text, 2)
    assert "参数错误" in hint
    assert "--query" in hint
    assert "--attrs" in hint
    assert "禁止 read_file" in hint


def test_skill_result_guidance_forbids_retry_on_auth_failure():
    cmd = "python3 /skills/ad-domain-ops/scripts/ad_search.py --query '*' --type user"
    text = '{"ok":false,"error":"invalid credentials"}'
    hint = skill_execute_result_guidance(cmd, text, 1)
    assert "禁止重试" in hint
    assert "最多修正参数" not in hint


def test_ppt_script_success_does_not_tell_the_model_to_stop():
    cmd = "python /skills/ppt-master/scripts/project_manager.py init guangzhou-food"
    hint = skill_execute_result_guidance(cmd, "initialized\n", 0)
    assert "继续" in hint
    assert "write_file" in hint
    assert "最终结果" not in hint
    assert "ad-domain-ops" not in hint


def test_ppt_workspace_cwd_applies_to_export_command(tmp_path):
    from unittest.mock import MagicMock

    from apps.opspilot.services.skill_executor.path_rewriting_backend import PathRewritingBackend

    inner = MagicMock()
    inner.execute.return_value = SimpleNamespace(output="ok\n", exit_code=0, truncated=False)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    backend = PathRewritingBackend(inner, tmp_path / "sandbox", ppt_workspace=workspace)
    backend.execute("python /skills/ppt-master/scripts/svg_to_pptx.py projects/demo --quick-generate")
    command = inner.execute.call_args.args[0]
    assert str(workspace) in command
    assert command.lower().startswith("cd")


def test_ppt_workspace_virtual_path_is_relative_to_cwd(tmp_path):
    from unittest.mock import MagicMock

    from apps.opspilot.services.skill_executor.path_rewriting_backend import PathRewritingBackend

    inner = MagicMock()
    inner.execute.return_value = SimpleNamespace(output="ok\n", exit_code=0, truncated=False)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    backend = PathRewritingBackend(inner, tmp_path / "sandbox", ppt_workspace=workspace)
    backend.execute(
        'python /skills/ppt-master/scripts/text_measure.py calibrate /ppt-workspace/projects/guangzhou-food --role "title:Microsoft YaHei:44"'
    )
    command = inner.execute.call_args.args[0]
    assert "/ppt-workspace/" not in command
    assert "projects/guangzhou-food" in command
    assert str(workspace) in command


def test_ppt_workspace_rejects_directory_probe(tmp_path):
    from unittest.mock import MagicMock

    from apps.opspilot.services.skill_executor.path_rewriting_backend import PathRewritingBackend

    inner = MagicMock()
    workspace = tmp_path / "ws"
    workspace.mkdir()
    backend = PathRewritingBackend(inner, tmp_path / "sandbox", ppt_workspace=workspace)
    result = backend.execute("ls /ppt-workspace")
    inner.execute.assert_not_called()
    assert "不要探测目录" in result.output
    assert "write_file" in result.output
    assert str(workspace) in result.output

    inline = backend.execute(r'D:\app\venv\bkliteserver\Scripts\python.exe -c "import os;print(os.getcwd())"')
    inner.execute.assert_not_called()
    assert "不要 python -c" in inline.output
    assert "write_file" in inline.output


def test_successful_svg_export_marks_ready(tmp_path):
    from unittest.mock import MagicMock

    from apps.opspilot.services.skill_executor.path_rewriting_backend import PathRewritingBackend

    inner = MagicMock()
    inner.execute.return_value = SimpleNamespace(output="exported\n", exit_code=0, truncated=False)
    workspace = tmp_path / "ws"
    export_dir = workspace / "projects" / "demo" / "exports"
    export_dir.mkdir(parents=True)
    (export_dir / "demo.pptx").write_bytes(b"PK")
    ready = {"called": False}

    def _mark() -> None:
        ready["called"] = True

    backend = PathRewritingBackend(inner, tmp_path / "sandbox", ppt_workspace=workspace, on_ppt_exported=_mark)
    backend.execute("python /skills/ppt-master/scripts/svg_to_pptx.py projects/demo --quick-generate")
    assert ready["called"] is True


def test_ppt_export_finish_skips_next_model_call():
    from apps.opspilot.metis.llm.middleware.tool_runtime import PptExportFinishMiddleware

    waiting = SimpleNamespace(_ppt_export_ready=False)
    assert PptExportFinishMiddleware(waiting).before_model({}, None) is None
    ready = SimpleNamespace(_ppt_export_ready=True)
    finished = PptExportFinishMiddleware(ready).before_model({}, None)
    assert finished["jump_to"] == "end"
    assert "PPT 已导出" in finished["messages"][0].content


def test_ppt_sandbox_deny_points_back_to_ppt_master():
    denied = _sandbox_deny_result(PermissionError("[sandbox] 禁止重定向/管道/命令串联"), ppt=True)
    assert "ppt-master" in denied.output
    assert "ad-domain-ops" not in denied.output
    assert "write_file" in denied.output


def test_ppt_workspace_write_lands_in_timestamp_dir(tmp_path):
    import os

    from deepagents.backends.local_shell import LocalShellBackend

    from apps.opspilot.services.skill_executor.path_rewriting_backend import PathRewritingBackend

    sandbox = tmp_path / "sandbox"
    workspace = tmp_path / "20261026181500"
    sandbox.mkdir()
    workspace.mkdir()
    os.symlink(workspace, sandbox / "ppt-workspace", target_is_directory=True)
    inner = LocalShellBackend(root_dir=str(sandbox), virtual_mode=True, inherit_env=False, env={})
    backend = PathRewritingBackend(inner, sandbox, ppt_workspace=workspace)

    result = backend.write("/ppt-workspace/projects/demo/svg_output/01.svg", "<svg>广州</svg>")
    assert result.error is None, result.error
    written = workspace / "projects" / "demo" / "svg_output" / "01.svg"
    assert written.read_text(encoding="utf-8") == "<svg>广州</svg>"
    edited = backend.edit("/ppt-workspace/projects/demo/svg_output/01.svg", "广州", "深圳")
    assert edited.error is None, edited.error
    assert written.read_text(encoding="utf-8") == "<svg>深圳</svg>"

    listed = backend.ls("/ppt-workspace/projects/demo/svg_output")
    assert listed.entries
    assert any(str(item.get("path", "")).endswith("01.svg") for item in listed.entries)
    read = backend.read("/ppt-workspace/projects/demo/svg_output/01.svg")
    assert read.error is None
    assert "深圳" in read.file_data["content"]

    # write/read 把 PermissionError 收成 error；_resolve_path 本身仍抛出。
    denied = backend.write("/ppt-workspace/../outside.txt", "no")
    assert denied.error
    assert "ppt 工作目录" in denied.error
    assert not (tmp_path / "outside.txt").exists()
    with pytest.raises(PermissionError, match="ppt 工作目录"):
        inner._resolve_path("/ppt-workspace/../outside.txt")

    inside = backend.write("/hello.txt", "hi")
    assert inside.error is None, inside.error
    assert (sandbox / "hello.txt").read_text(encoding="utf-8") == "hi"
    assert not (workspace / "hello.txt").exists()


def test_bind_utf8_execute_only_wraps_real_local_shell(tmp_path):
    from unittest.mock import MagicMock

    from deepagents.backends.local_shell import LocalShellBackend

    from apps.opspilot.services.skill_executor.utf8_local_shell import bind_utf8_execute

    fake = MagicMock()
    original = fake.execute
    bind_utf8_execute(fake)
    assert fake.execute is original

    class _Subclass(LocalShellBackend):
        pass

    subclassed = _Subclass(root_dir=str(tmp_path), virtual_mode=True, inherit_env=False, env={})
    bind_utf8_execute(subclassed)
    assert "execute" not in subclassed.__dict__

    backend = LocalShellBackend(root_dir=str(tmp_path), virtual_mode=True, inherit_env=False, env={})
    bind_utf8_execute(backend)
    assert "execute_utf8" in backend.__dict__["execute"].__code__.co_names


def test_shell_execute_decodes_utf8_instead_of_gbk(tmp_path):
    from deepagents.backends.local_shell import LocalShellBackend

    from apps.opspilot.services.skill_executor.utf8_local_shell import bind_utf8_execute

    script = tmp_path / "emit_utf8.py"
    script.write_text(
        "import sys\n" "sys.stdout.buffer.write('没有 SVG：质量检查未通过 — ©\\n'.encode('utf-8'))\n" "sys.stdout.buffer.write(bytes([0xFF]))\n",
        encoding="utf-8",
    )
    backend = LocalShellBackend(root_dir=str(tmp_path), virtual_mode=True, inherit_env=True)
    bind_utf8_execute(backend)
    result = backend.execute(f'"{sys.executable}" "{script}"')
    assert result.exit_code == 0, result.output
    assert "没有 SVG：质量检查未通过" in result.output
    assert "—" in result.output
    assert "\ufffd" in result.output
