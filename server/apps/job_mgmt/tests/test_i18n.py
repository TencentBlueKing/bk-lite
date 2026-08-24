import re
from pathlib import Path
from string import Formatter
from types import SimpleNamespace

import yaml

from apps.job_mgmt.models import JobExecution, ScheduledTask
from apps.job_mgmt.serializers.execution import JobExecutionListSerializer
from apps.job_mgmt.serializers.scheduled_task import ScheduledTaskListSerializer
from apps.job_mgmt.utils.i18n import job_message, localize_execution_name

JOB_ROOT = Path(__file__).resolve().parents[1]


def _request(locale: str):
    return SimpleNamespace(user=SimpleNamespace(locale=locale))


def _load_messages(locale: str) -> dict:
    with (JOB_ROOT / "language" / f"{locale}.yaml").open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def _flatten(value: dict, prefix: str = "") -> dict[str, object]:
    result = {}
    for key, item in value.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(item, dict):
            result.update(_flatten(item, path))
        else:
            result[path] = item
    return result


def _placeholders(value: str) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(value) if name}


def test_backend_display_language_trees_are_aligned():
    en = _flatten(_load_messages("en"))
    zh = _flatten(_load_messages("zh-Hans"))

    assert en.keys() == zh.keys()
    for key in en:
        assert isinstance(en[key], str) and en[key]
        assert isinstance(zh[key], str) and zh[key]
        assert _placeholders(en[key]) == _placeholders(zh[key]), f"placeholder mismatch for {key}"
        assert not re.search(r"[\u3400-\u9fff]", en[key]), f"untranslated English message for {key}"


def test_display_message_uses_user_locale():
    assert job_message(_request("en"), "choice.job_type.script", "fallback") == "Script Execution"
    assert job_message(_request("zh-Hans"), "choice.job_type.script", "fallback") == "脚本执行"


def test_list_display_fields_use_request_locale():
    execution = JobExecution(name="demo", job_type="script", trigger_source="manual", status="failed")
    execution_data = JobExecutionListSerializer(execution, context={"request": _request("en")}).data
    scheduled = ScheduledTask(name="demo", job_type="script", schedule_type="cron", target_list=[])
    scheduled_data = ScheduledTaskListSerializer(scheduled, context={"request": _request("en")}).data

    assert execution_data["job_type_display"] == "Script Execution"
    assert execution_data["trigger_source_display"] == "Manual Execution"
    assert scheduled_data["job_type_display"] == "Script Execution"


def test_system_generated_execution_name_is_localized_at_response_boundary():
    stored = "[手动触发] nightly cleanup"

    assert localize_execution_name(_request("en"), stored) == "[Manual trigger] nightly cleanup"
    assert localize_execution_name(_request("zh-Hans"), stored) == stored
