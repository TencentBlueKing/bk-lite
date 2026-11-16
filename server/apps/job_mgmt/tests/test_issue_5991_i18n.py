from pathlib import Path

from apps.job_mgmt.utils.i18n import job_message


def test_confirmed_job_messages_follow_locale():
    english = type("Req", (), {"user": type("User", (), {"locale": "en"})()})()
    chinese = type("Req", (), {"user": type("User", (), {"locale": "zh-Hans"})()})()
    assert job_message(english, "error.script_missing", "脚本不存在") == "Script does not exist"
    assert job_message(chinese, "error.execution_source_required", "必须提供 script_id、playbook_id 或 script_content 其中之一").startswith("必须提供")
    locale = Path(__file__).resolve().parents[4] / "web/src/app/job/locales/en.json"
    snippet = locale.read_text(encoding="utf-8").split("importScriptsResult", 1)[1][:90]
    assert "{{" not in snippet
    assert "{created}" in snippet
