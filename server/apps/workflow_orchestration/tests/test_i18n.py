from pathlib import Path
from string import Formatter
from types import SimpleNamespace

import yaml

from apps.workflow_orchestration.utils.i18n import workflow_message

LANGUAGE_ROOT = Path(__file__).resolve().parents[1] / "language"


def _flatten(value: dict, prefix: str = "") -> dict[str, object]:
    result = {}
    for key, item in value.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(item, dict):
            result.update(_flatten(item, path))
        else:
            result[path] = item
    return result


def _load(locale: str) -> dict[str, object]:
    with (LANGUAGE_ROOT / f"{locale}.yaml").open(encoding="utf-8") as stream:
        return _flatten(yaml.safe_load(stream) or {})


def _placeholders(value: str) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(value) if name}


def test_language_trees_and_placeholders_are_aligned():
    english = _load("en")
    chinese = _load("zh-Hans")

    assert english.keys() == chinese.keys()
    for key, english_value in english.items():
        chinese_value = chinese[key]
        assert isinstance(english_value, str)
        assert isinstance(chinese_value, str)
        assert _placeholders(english_value) == _placeholders(chinese_value)


def test_request_locale_selects_backend_message():
    request = SimpleNamespace(user=SimpleNamespace(locale="en-US"))

    assert workflow_message(request, "message.invalid_current_team", "fallback") == "Missing or invalid current_team"
    assert workflow_message(request, "message.waiting_items", "fallback", count=2) == "and 2 more"
    assert workflow_message(request, "message.report_too_large", "fallback") == "Report file exceeds the download size limit"
    assert workflow_message(request, "error.workflow_disabled", "fallback") == "Workflow is disabled"
