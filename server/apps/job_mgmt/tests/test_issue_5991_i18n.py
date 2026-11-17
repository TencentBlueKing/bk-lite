from pathlib import Path

from apps.job_mgmt.utils.i18n import job_message


def test_task_ids_required_keeps_single_catalog_entry():
    root = Path(__file__).resolve().parents[4]
    for relative in (
        "server/apps/job_mgmt/language/en.yaml",
        "server/apps/job_mgmt/language/zh-Hans.yaml",
    ):
        text = (root / relative).read_text(encoding="utf-8")
        assert text.count("\n  task_ids_required:") == 1
    english = type("Req", (), {"user": type("User", (), {"locale": "en"})()})()
    assert job_message(english, "error.task_ids_required", "task_ids is required") == "task_ids is required"


def test_confirmed_job_messages_follow_locale():
    english = type("Req", (), {"user": type("User", (), {"locale": "en"})()})()
    chinese = type("Req", (), {"user": type("User", (), {"locale": "zh-Hans"})()})()
    assert job_message(english, "error.script_missing", "脚本不存在") == "Script does not exist"
    assert job_message(chinese, "error.execution_source_required", "必须提供 script_id、playbook_id 或 script_content 其中之一").startswith("必须提供")
    locale = Path(__file__).resolve().parents[4] / "web/src/app/job/locales/en.json"
    snippet = locale.read_text(encoding="utf-8").split("importScriptsResult", 1)[1][:90]
    assert "{{" not in snippet
    assert "{created}" in snippet
