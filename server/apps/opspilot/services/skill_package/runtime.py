import json
import re
from pathlib import Path
from typing import Any, Iterable

import yaml

# SKILL.md frontmatter 提取正则(与 importer._split_frontmatter 保持一致)
_SKILL_MD_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)
# 策略字段:由 SKILL.md frontmatter / skill.yaml 决定,覆盖 DB manifest
_STRATEGY_FIELDS = ("capabilities", "reports", "workflows")
_DOMAIN_MATCH_ALIASES = (
    (
        ("kubernetes", "k8s"),
        ("kubernetes", "k8s", "集群", "工作负载", "pod", "pods", "deployment", "namespace", "命名空间"),
    ),
)


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
    # 列出所有已启用的技能包(不靠 keyword 匹配筛,避免"今天天气" 也强塞包)。
    # LLM 看到完整列表后按用户问题挑相关的 1+ 个用,而不是"显示的都用上"。
    enabled = normalize_skill_packages(skill_packages)
    if not enabled:
        return base_prompt or "", []

    available = {str(item) for item in (available_tool_names or [])}
    blocks = ["\n\n---\n\n## 已启用的技能包\n"]
    matched = select_skill_packages_for_message(enabled, user_message)
    matched_ids = {_package_match_key(package) for package in matched}
    matched_packages: list[dict[str, Any]] = []
    for package in enabled:
        package_name = _package_display_name(package)
        missing_tools = _missing_required_tools(package, available)
        if _package_match_key(package) in matched_ids:
            matched_packages.append(_package_summary(package, missing_tools))
        missing_notice = f"\n- 缺少依赖工具：{'、'.join(missing_tools)}" if missing_tools else ""
        blocks.append(
            "\n".join(
                [
                    f"### {package_name}",
                    f"- 已采用技能包：{package_name}",
                    f"- 说明：{package.get('description') or '无'}",
                    f"- 触发词：{_join_list(package.get('triggers')) or '无'}",
                    f"- 依赖工具：{_join_list(package.get('required_tools')) or '无'}{missing_notice}",
                    "",
                    str(package.get("skill_markdown") or package.get("content") or "").strip(),
                ]
            )
        )
    blocks.append(
        "\n使用规则：以下技能包**已启用**(可被调用),但**仅当用户问题与某个技能包的能力边界相关时才采用**;用户明说「使用xx」时,直接调用对应那个,其他技能包忽略;用户没明说时,根据问题**挑 1 个或几个最相关的用**,不要「列出来的全用上」。如采用技能包方法,必须在思考区或最终答复开头写明 `已采用技能包:<技能包名称>`。技能包不是工具调用,不要把技能包写成已调用工具;技能包提供任务方法和输出约束,事实数据必须来自工具或上下文。"
        "\n运行规则：当用户要求你实际获取、访问、转换、读取、生成或处理外部内容时，不要只输出安装步骤或示例代码；必须优先调用当前可用工具完成任务。DeepAgent 沙箱提供 `execute`、`read_file`、`write_file` 等工具时，应使用这些工具运行技能包中的 CLI 或脚本，并基于工具返回的真实结果回答。只有工具不可用或执行失败时，才说明失败原因并给出人工执行步骤。"
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
        # 同步 ORM 查询,调用方须在 sync 上下文(用 ThreadPoolExecutor 包一层)。
        stored_list = list(SkillPackage.objects.filter(id__in=ids, is_enabled=True))
        # key 统一转 str:LangGraph configurable 跨节点序列化会把 int id 转 str,
        # 后续 stored_packages.get(item.get("id")) 也用 str 查,保持一致。
        stored_packages = {str(item.id): item for item in stored_list}
    except Exception as e:
        logger.debug("技能包查询失败: %r", e)
        return packages
    hydrated: list[dict[str, Any]] = []
    for item in packages:
        # 兼容 str/int id(参见上面 stored_packages 的 key 处理)。
        item_id = item.get("id")
        stored = stored_packages.get(item_id) or stored_packages.get(str(item_id) if item_id is not None else None)
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
        # 注入物化所需的 extracted_root + asset_roots(流式路径)。
        # 真相源仍是磁盘上的 extracted_path;materalizer 用 Path.rglob 扫描读盘,
        # 不在 snapshot 里复制文件内容,避免 mb 级包占用内存。
        # 仅当 storage_path 非空时添加,空字符串保持后向兼容(走旧 dict 路径)。
        storage_path_text = str(getattr(stored, "storage_path", "") or "")
        if storage_path_text:
            extracted_root = Path(storage_path_text) / "extracted"
            snapshot["extracted_root"] = extracted_root
            asset_roots: dict[str, Path | None] = {}
            for asset_dir in ("scripts", "references", "assets"):
                sub = extracted_root / asset_dir
                asset_roots[asset_dir] = sub if sub.is_dir() else None
            snapshot["asset_roots"] = asset_roots
        hydrated.append(snapshot)
    return hydrated


def _manifest_with_storage_overlay(stored_package) -> dict[str, Any]:
    """从 DB manifest 出发,叠加磁盘上 skill.yaml / SKILL.md frontmatter 的策略字段。

    优先级(由低到高): DB manifest → skill.yaml → SKILL.md frontmatter。

    设计原因:用户编辑磁盘上的 SKILL.md 后希望能立即热生效,而不用每次都重导 ZIP。
    - DB manifest 是导入时落盘的快照,可能落后于磁盘文件。
    - skill.yaml 与 SKILL.md frontmatter 同时存在时,SKILL.md frontmatter 优先
      (用户改 SKILL.md 比改 skill.yaml 频繁,且 SKILL.md 是 deepagent 沙箱的真相源)。
    - 磁盘文件不存在 / 不含某策略字段时,沿用 DB manifest 的值
      (后向兼容历史数据,避免删 skill.yaml 后能力丢失)。
    """
    manifest = dict(getattr(stored_package, "manifest", None) or {})
    storage_path = getattr(stored_package, "storage_path", "")
    if not storage_path:
        return manifest

    extracted_dir = Path(storage_path) / "extracted"
    if not extracted_dir.is_dir():
        return manifest

    # 1) skill.yaml 中间层(比 DB 新,但比 SKILL.md 旧)
    skill_yaml_path = extracted_dir / "skill.yaml"
    if skill_yaml_path.is_file():
        try:
            file_manifest = yaml.safe_load(skill_yaml_path.read_text(encoding="utf-8")) or {}
        except Exception:
            file_manifest = None
        if isinstance(file_manifest, dict):
            for key in _STRATEGY_FIELDS:
                if key in file_manifest:
                    manifest[key] = file_manifest[key]

    # 2) SKILL.md frontmatter 最高优先级(用户编辑磁盘文件 → 立即热生效)
    skill_md_path = extracted_dir / "SKILL.md"
    if skill_md_path.is_file():
        try:
            skill_md = skill_md_path.read_text(encoding="utf-8")
        except Exception:
            skill_md = ""
        if skill_md:
            match = _SKILL_MD_FRONTMATTER_RE.match(skill_md)
            if match:
                try:
                    frontmatter = yaml.safe_load(match.group(1)) or {}
                except Exception:
                    frontmatter = None
                if isinstance(frontmatter, dict):
                    for key in _STRATEGY_FIELDS:
                        if key in frontmatter:
                            manifest[key] = frontmatter[key]

    return manifest


def _match_score(package: dict[str, Any], message: str) -> int:
    if not message:
        return 0
    score = 0
    package_text = _package_search_text(package)
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
    for package_aliases, message_aliases in _DOMAIN_MATCH_ALIASES:
        if any(alias in package_text for alias in package_aliases) and any(alias in message for alias in message_aliases):
            score += 4
    return score


def _package_search_text(package: dict[str, Any]) -> str:
    parts = [
        package.get("name"),
        package.get("description"),
        package.get("category"),
        package.get("id"),
        package.get("package_id"),
        package.get("skill_markdown"),
        package.get("content"),
    ]
    parts.extend(_as_list(package.get("triggers")))
    parts.extend(_as_list(package.get("required_tools")))
    parts.extend(_as_list(package.get("capabilities")))
    return " ".join(str(part or "") for part in parts).casefold()


def _package_match_key(package: dict[str, Any]) -> str:
    return str(package.get("id") or package.get("package_id") or _package_display_name(package))


def _package_summary(package: dict[str, Any], missing_tools: list[str]) -> dict[str, Any]:
    package_name = _package_display_name(package)
    return {
        "id": str(package.get("id") or package.get("package_id") or package_name),
        "name": package_name,
        "package_id": str(package.get("package_id") or package.get("id") or ""),
        "description": str(package.get("description") or ""),
        "missing_tools": missing_tools,
        "capabilities": _as_list(package.get("capabilities")),
        "reports": _as_dict(package.get("reports")),
        "workflows": _as_dict(package.get("workflows")),
    }


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
