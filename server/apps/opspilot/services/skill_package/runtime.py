import json
from pathlib import Path
from typing import Any, Iterable

import yaml


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
    user_message: Any,
    limit: int = 3,
) -> list[dict[str, Any]]:
    packages = normalize_skill_packages(skill_packages)
    if not packages:
        return []

    message = _message_to_text(user_message).casefold()
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
    user_message: Any,
    available_tool_names: Iterable[str] | None = None,
) -> str:
    prompt, _ = build_skill_package_prompt(
        base_prompt=base_prompt,
        skill_packages=skill_packages,
        user_message=user_message,
        available_tool_names=available_tool_names,
    )
    return prompt


def build_skill_package_prompt(
    base_prompt: str,
    skill_packages: Any,
    user_message: Any,
    available_tool_names: Iterable[str] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    selected = select_skill_packages_for_message(skill_packages, user_message)
    if not selected:
        return base_prompt or "", []

    available = {str(item) for item in (available_tool_names or [])}
    blocks = ["\n\n---\n\n## 当前可用技能包\n"]
    matched_packages: list[dict[str, Any]] = []
    for package in selected:
        package_name = _package_display_name(package)
        missing_tools = _missing_required_tools(package, available)
        matched_packages.append(
            {
                "id": str(package.get("id") or package.get("package_id") or package_name),
                "name": package_name,
                "package_id": str(package.get("package_id") or package.get("id") or ""),
                "description": str(package.get("description") or ""),
                "missing_tools": missing_tools,
                "capabilities": _as_list(package.get("capabilities")),
                "reports": _as_dict(package.get("reports")),
                "workflows": _as_dict(package.get("workflows")),
            }
        )
        missing_notice = f"\n- 缺少依赖工具：{'、'.join(missing_tools)}" if missing_tools else ""
        blocks.append(
            "\n".join(
                [
                    f"### {package_name}",
                    f"- 命中标记：已命中技能包：{package_name}",
                    f"- 说明：{package.get('description') or '无'}",
                    f"- 触发词：{_join_list(package.get('triggers')) or '无'}",
                    f"- 依赖工具：{_join_list(package.get('required_tools')) or '无'}{missing_notice}",
                    "",
                    str(package.get("skill_markdown") or package.get("content") or "").strip(),
                ]
            )
        )
    blocks.append(
        "\n使用规则：仅在用户问题命中技能包能力边界时采用对应技能包；如果采用技能包方法，必须在思考区或最终答复开头写明 `已命中技能包：<技能包名称>`；技能包不是工具调用，不要把技能包写成已调用工具；技能包提供任务方法和输出约束，事实数据必须来自工具或上下文。"
    )
    return (base_prompt or "") + "\n".join(blocks), matched_packages


def build_skill_package_strategy(matched_skill_packages: Any) -> dict[str, Any]:
    matched = normalize_skill_packages(matched_skill_packages)
    capabilities = []
    seen = set()
    reports: dict[str, Any] = {}
    workflows: dict[str, Any] = {}
    for package in matched:
        for capability in _as_list(package.get("capabilities")):
            if capability in seen:
                continue
            seen.add(capability)
            capabilities.append(capability)
        reports.update(_as_dict(package.get("reports")))
        workflows.update(_as_dict(package.get("workflows")))
    return {
        "skill_package_capabilities": capabilities,
        "skill_package_reports": reports,
        "skill_package_workflows": workflows,
    }


def hydrate_skill_packages(skill_packages: Any) -> list[dict[str, Any]]:
    packages = normalize_skill_packages(skill_packages)
    ids = [item.get("id") for item in packages if item.get("id")]
    if not ids:
        return packages

    try:
        from apps.opspilot.models import SkillPackage
    except Exception:
        return packages

    try:
        stored_packages = {item.id: item for item in SkillPackage.objects.filter(id__in=ids, is_enabled=True)}
    except Exception:
        return packages
    hydrated: list[dict[str, Any]] = []
    for item in packages:
        stored = stored_packages.get(item.get("id"))
        if not stored:
            hydrated.append(item)
            continue
        manifest = _manifest_with_storage_overlay(stored)
        snapshot = dict(item)
        snapshot.update(
            {
                "id": stored.id,
                "package_id": stored.package_id,
                "name": stored.name,
                "version": stored.version,
                "description": stored.description,
                "category": stored.category,
                "required_tools": stored.required_tools,
                "triggers": stored.triggers,
                "capabilities": manifest.get("capabilities", []),
                "reports": manifest.get("reports", {}),
                "workflows": manifest.get("workflows", {}),
                "skill_markdown": stored.skill_markdown,
            }
        )
        hydrated.append(snapshot)
    return hydrated


def _manifest_with_storage_overlay(stored_package) -> dict[str, Any]:
    manifest = dict(getattr(stored_package, "manifest", None) or {})
    missing_strategy_fields = any(key not in manifest for key in ("capabilities", "reports", "workflows"))
    storage_path = getattr(stored_package, "storage_path", "")
    if not missing_strategy_fields or not storage_path:
        return manifest

    manifest_path = Path(storage_path) / "extracted" / "skill.yaml"
    if not manifest_path.exists():
        return manifest
    try:
        file_manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return manifest
    if not isinstance(file_manifest, dict):
        return manifest
    for key in ("capabilities", "reports", "workflows"):
        if key not in manifest and key in file_manifest:
            manifest[key] = file_manifest[key]
    return manifest


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


def _package_display_name(package: dict[str, Any]) -> str:
    return str(package.get("name") or package.get("package_id") or package.get("id") or "未命名技能包")


def _message_to_text(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        content = value.get("content")
        if isinstance(content, list):
            return " ".join(_message_to_text(item) for item in content)
        if content is not None:
            return str(content)
        return " ".join(str(item) for item in value.values() if item)
    if isinstance(value, list):
        return " ".join(_message_to_text(item) for item in value)
    return str(value)


def _missing_required_tools(package: dict[str, Any], available_tool_names: set[str]) -> list[str]:
    if not available_tool_names:
        return _as_list(package.get("required_tools"))
    normalized_available = [_normalize_tool_key(tool) for tool in available_tool_names]
    missing = []
    for tool in _as_list(package.get("required_tools")):
        normalized_tool = _normalize_tool_key(tool)
        if not normalized_tool or not any(_tool_key_matches(normalized_tool, available) for available in normalized_available):
            missing.append(tool)
    return missing


def _normalize_tool_key(value: Any) -> str:
    return "".join(char for char in str(value or "").casefold() if char.isalnum())


def _tool_key_matches(required: str, available: str) -> bool:
    if not required or not available:
        return False
    return required == available or required in available or available in required


def _as_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _join_list(value: Any) -> str:
    return "、".join(_as_list(value))
