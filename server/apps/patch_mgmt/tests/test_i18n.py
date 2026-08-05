import ast
from pathlib import Path
from string import Formatter
from types import SimpleNamespace

import yaml

from apps.core.utils.loader import LanguageLoader
from apps.patch_mgmt.exceptions import PatchBusinessError
from apps.patch_mgmt.utils.i18n import patch_message, render_business_error


def _request(locale: str):
    return SimpleNamespace(user=SimpleNamespace(locale=locale))


PATCH_ROOT = Path(__file__).resolve().parents[1]


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader, node, deep=False):
    loader.flatten_mapping(node)
    keys = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in keys:
            raise AssertionError(f"duplicate YAML key: {key}")
        keys.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep=deep)


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _load_messages(locale: str) -> dict:
    with (PATCH_ROOT / "language" / f"{locale}.yaml").open(encoding="utf-8") as stream:
        return yaml.load(stream, Loader=_UniqueKeyLoader)


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


def test_patch_management_language_keys_exist_in_en_and_zh():
    keys = [
        "error.hosts_busy",
        "error.targets_not_pending_reboot",
        "error.patch_referenced",
        "message.baseline_assessment_name",
        "message.governance_task_name",
        "message.just_now",
        "status.task_type.install",
    ]
    for locale in ("en", "zh-Hans"):
        loader = LanguageLoader(app="patch_mgmt", default_lang=locale)
        for key in keys:
            assert loader.get(key), f"missing {locale} translation for {key}"


def test_backend_language_trees_and_placeholders_are_aligned():
    en = _flatten(_load_messages("en"))
    zh = _flatten(_load_messages("zh-Hans"))

    assert en.keys() == zh.keys()
    for key in en:
        assert isinstance(en[key], str), f"en {key} must be a string"
        assert isinstance(zh[key], str), f"zh-Hans {key} must be a string"
        assert _placeholders(en[key]) == _placeholders(zh[key]), f"placeholder mismatch for {key}"


def test_backend_static_translation_references_resolve_to_string_values():
    referenced_keys: set[str] = set()
    business_error_codes: set[str] = set()
    for directory in ("views", "serializers", "services", "utils"):
        for source in (PATCH_ROOT / directory).rglob("*.py"):
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                function_name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                if function_name in {"patch_message", "serializer_message"} and len(node.args) > 1:
                    if isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
                        referenced_keys.add(node.args[1].value)
                if function_name == "PatchBusinessError" and node.args:
                    if isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                        business_error_codes.add(node.args[0].value)

    referenced_keys.update(f"error.{code}" for code in business_error_codes)
    for locale in ("en", "zh-Hans"):
        messages = _flatten(_load_messages(locale))
        for key in referenced_keys:
            assert isinstance(messages.get(key), str), f"{locale} reference {key} is missing or is not a string"


def test_backend_dynamic_status_translation_contracts_exist():
    contracts = {
        "status.task_type": ("assess", "install", "reboot", "verify"),
        "status.compliance": (
            "compliant", "non_compliant", "pending", "evaluating", "failed",
            "unknown", "not_applicable",
        ),
    }
    for locale in ("en", "zh-Hans"):
        messages = _flatten(_load_messages(locale))
        for prefix, values in contracts.items():
            for value in values:
                assert isinstance(messages.get(f"{prefix}.{value}"), str)


def test_patch_message_uses_request_user_locale():
    assert patch_message(_request("en"), "error.task_finished_not_cancellable", "fallback") == (
        "The task has finished and cannot be cancelled"
    )
    assert patch_message(_request("zh-Hans"), "error.task_finished_not_cancellable", "fallback") == "任务已结束，不可取消"


def test_business_error_keeps_localized_summary_and_raw_diagnostic():
    error = PatchBusinessError(
        "invalid_execution_window",
        "Invalid execution-window time",
        raw_detail="S3 timeout",
    )

    assert render_business_error(_request("en"), error) == "Invalid execution-window time: S3 timeout"
    assert render_business_error(_request("zh-Hans"), error) == "执行窗口时间格式错误: S3 timeout"
