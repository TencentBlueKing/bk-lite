from dataclasses import dataclass, field
from typing import Iterable, Optional


@dataclass(frozen=True)
class ChoiceOptionGuard:
    target_label: str
    allowed_options: list[str]
    allowed_aliases: set[str] = field(default_factory=set)
    single_option_message: str = ""
    block_message: str = ""


def _option_matches_allowed(option: str, allowed_options: Iterable[str], allowed_aliases: set[str]) -> bool:
    value = option.strip()
    if value in allowed_aliases:
        return True
    return any(name and (value == name or name in value) for name in allowed_options)


def validate_user_choice_options(
    *,
    question_type: str,
    options: Optional[list[str]],
    guard: Optional[ChoiceOptionGuard],
) -> str:
    if not guard or question_type not in {"single_select", "multi_select"}:
        return ""

    if guard.block_message:
        return guard.block_message

    normalized_options = options or []
    if not normalized_options:
        return ""

    allowed_options = [option for option in guard.allowed_options if option]
    if not allowed_options:
        return ""

    if len(allowed_options) == 1 and guard.single_option_message:
        return guard.single_option_message

    invalid_options = [
        option for option in normalized_options
        if not _option_matches_allowed(option, allowed_options, guard.allowed_aliases)
    ]
    if not invalid_options:
        return ""

    allowed = "、".join(allowed_options)
    invalid = "、".join(invalid_options)
    return (
        f"检测到 {guard.target_label}选择项不是来自真实配置，已阻止向用户展示。"
        f"真实可用{guard.target_label}只有：{allowed}。无效选项：{invalid}。"
        "请先调用工具查询真实目标位置，或仅使用真实名称重新发起选择。"
    )
