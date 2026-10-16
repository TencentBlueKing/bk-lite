"""内置工具、技能包、MCP 的系统标签与用户标签。

系统标签是稳定标识，按工具集或播种数据整组替换。用户标签按输入保存。
"""

from __future__ import annotations

BUILTIN_TOOL_SYSTEM_TAGS: dict[str, tuple[str, ...]] = {
    "monitor": ("monitoring_alert", "platform_app"),
    "alerts": ("monitoring_alert", "platform_app"),
    "log": ("log", "platform_app"),
    "cmdb": ("asset", "platform_app"),
    "mysql": ("database",),
    "oracle": ("database",),
    "mssql": ("database",),
    "postgres": ("database",),
    "redis": ("database",),
    "elasticsearch": ("database",),
    "kubernetes": ("container",),
    "kubernetes_data_collection": ("container",),
    "jenkins": ("release",),
    "ssh": ("host_identity",),
    "shell": ("host_identity",),
    "activedirectory": ("host_identity",),
    "duckduckgo": ("retrieval",),
    "fetch": ("retrieval",),
    "github": ("retrieval",),
    "browser_use": ("retrieval",),
    "agent_browser": ("retrieval",),
    "current_time": ("general",),
    "python": ("general",),
    "attachment_file": ("general",),
    "ops_analysis_dashboard": ("general", "platform_app"),
}


def system_tags_for_tool(tool_name: str) -> list[str]:
    return list(BUILTIN_TOOL_SYSTEM_TAGS.get(str(tool_name or ""), ()))


def normalize_user_tags(raw) -> list[str]:
    """去首尾空白、丢掉空词，并按出现顺序去重。"""
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        return []
    seen: set[str] = set()
    result: list[str] = []
    for item in raw:
        if item is None:
            continue
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def normalize_system_tags(raw) -> list[str]:
    return normalize_user_tags(raw)


def system_tags_removed(current, requested) -> bool:
    """请求里的系统标签少了当前任一标识时，视为试图删除系统标签。"""
    current_tags = normalize_system_tags(current)
    requested_tags = set(normalize_system_tags(requested))
    return any(tag not in requested_tags for tag in current_tags)


def system_tags_from_manifest(manifest: dict | None) -> list[str]:
    """只读播种数据里写明的 system_tags，不从 category 推导。"""
    if not isinstance(manifest, dict):
        return []
    raw = manifest.get("system_tags")
    if raw is None:
        metadata = manifest.get("metadata")
        if isinstance(metadata, dict):
            raw = metadata.get("system_tags")
    return normalize_system_tags(raw)


def apply_fallback_tool_tags(item: dict) -> dict:
    """尚未入库的内置工具兜底项带上系统标签，用户标签为空。"""
    system_tags = system_tags_for_tool(item.get("name") or "")
    item["system_tags"] = system_tags
    item["user_tags"] = []
    item["tags"] = list(system_tags)
    return item
