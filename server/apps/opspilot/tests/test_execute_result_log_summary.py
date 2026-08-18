"""execute 结果日志摘要:只记成功/失败与是否有数据。"""
from __future__ import annotations

import pytest

from apps.opspilot.services.skill_executor.path_rewriting_backend import (
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
