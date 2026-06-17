import json
from typing import Any, Iterable


def normalize_skill_packages(raw_packages: Any) -> list[dict[str, Any]]:
    if not raw_packages:
        return []
    if isinstance(raw_packages, str):
        try:
            raw_packages = json.loads(raw_packages)
        except json.JSONDecodeError:
            return []
    if not isinstance(raw_packages, list):
        return []
    return [item for item in raw_packages if isinstance(item, dict)]


def select_skill_packages_for_message(
    skill_packages: Any,
    user_message: str,
    limit: int = 3,
) -> list[dict[str, Any]]:
    packages = normalize_skill_packages(skill_packages)
    if not packages:
        return []

    message = (user_message or "").casefold()
    scored: list[tuple[int, int, dict[str, Any]]] = []
    for index, package in enumerate(packages):
        score = _match_score(package, message)
        if score > 0:
            scored.append((score, -index, package))

    scored.sort(reverse=True)
    return [package for _, _, package in scored[:limit]]


def append_matching_skill_packages_to_prompt(
    base_prompt: str,
    skill_packages: Any,
    user_message: str,
    available_tool_names: Iterable[str] | None = None,
) -> str:
    selected = select_skill_packages_for_message(skill_packages, user_message)
    if not selected:
        return base_prompt or ""

    available = {str(item) for item in (available_tool_names or [])}
    blocks = ["\n\n---\n\n## 当前可用技能包\n"]
    for package in selected:
        missing_tools = _missing_required_tools(package, available)
        missing_notice = f"\n- 缺少依赖工具：{'、'.join(missing_tools)}" if missing_tools else ""
        blocks.append(
            "\n".join(
                [
                    f"### {package.get('name') or package.get('id') or '未命名技能包'}",
                    f"- 说明：{package.get('description') or '无'}",
                    f"- 触发词：{_join_list(package.get('triggers')) or '无'}",
                    f"- 依赖工具：{_join_list(package.get('required_tools')) or '无'}{missing_notice}",
                    "",
                    str(package.get("skill_markdown") or package.get("content") or "").strip(),
                ]
            )
        )
    blocks.append(
        "\n使用规则：仅在用户问题命中技能包能力边界时采用对应技能包；技能包提供任务方法和输出约束，事实数据必须来自工具或上下文。"
    )
    return (base_prompt or "") + "\n".join(blocks)


def _match_score(package: dict[str, Any], message: str) -> int:
    if not message:
        return 0
    score = 0
    searchable_fields = [
        package.get("name"),
        package.get("description"),
        package.get("category"),
        package.get("id"),
    ]
    for field in searchable_fields:
        text = str(field or "").casefold()
        if text and text in message:
            score += 2
    for trigger in _as_list(package.get("triggers")):
        text = str(trigger).casefold()
        if text and text in message:
            score += 5
    return score


def _missing_required_tools(package: dict[str, Any], available_tool_names: set[str]) -> list[str]:
    if not available_tool_names:
        return _as_list(package.get("required_tools"))
    return [tool for tool in _as_list(package.get("required_tools")) if tool not in available_tool_names]


def _as_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return []


def _join_list(value: Any) -> str:
    return "、".join(_as_list(value))
