"""对话里整理技能包成稿，确认卡点选后才新建一条技能包。

模型输出只进入缓存快照。写入使用快照和数据库里已保存的管理分组，
不采用请求里的未保存分组，也不改智能体已选技能包。
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from apps.core.logger import opspilot_logger as logger
from apps.core.models.maintainer_info import maintainer_kwargs
from apps.opspilot.metis.llm.middleware.terminal_user_choice import finalize_user_choice
from apps.opspilot.models import LLMSkill, SkillPackage
from apps.opspilot.utils.pending_question import (
    consume_pending_question,
    peek_pending_question,
    resolve_conversation_key,
    resolve_conversation_key_from_mapping,
    save_pending_question,
)

PREPARE_CONVERSATION_SKILL_PACKAGE_TOOL = "prepare_conversation_skill_package"
AUTHORING_EXTRA_KEY = "conversation_skill_package_authoring"
CONFIRM_OPTION = "确认写入"
ABANDON_OPTION = "放弃"
SOURCE_CONVERSATION = "conversation"
PACKAGE_VERSION = "0.1.0"
ENTRY_SKILL_TEST = "skill_test"
ALLOWED_ENTRIES = frozenset({ENTRY_SKILL_TEST, "platform", "web_chat"})
ADD_PERMISSION = "tool_list-Add"

AUTHORING_PROMPT_SUFFIX = (
    "\n\n【技能包制作】只有用户明确要求做成技能包、保存成技能包或生成技能包时，"
    "才调用 prepare_conversation_skill_package。"
    "调用时给出名称、何时使用的说明、至少一条触发词，以及包含步骤、需要用户提供什么、怎样算做完的正文。"
    "正文写成谁勾上都能照着做的步骤，不要写死某个工具，不要声明依赖工具或必填变量。"
    "缺了任何一项就先追问，不要调用工具。"
    "工具只会发出确认卡；用户没点确认就不要说已经写入。"
    "普通问答不要调用这个工具，也不要主动提议做成技能包。"
)

_EXPLICIT_PHRASES = (
    "做成技能包",
    "保存成技能包",
    "生成技能包",
    "制作技能包",
    "创建技能包",
    "做成技能",
    "存成技能包",
    "make a skill package",
    "save as a skill package",
    "create a skill package",
)
_USER_ROLES = frozenset({"user", "human"})
_FIELD_LABELS = (
    ("name", "名称"),
    ("description", "何时使用的说明"),
    ("triggers", "触发词"),
    ("skill_markdown", "正文"),
)

_SAVED_LOG = "event=conversation_skill_package_saved skill_id=%s package_id=%s"
_REJECTED_LOG = "event=conversation_skill_package_rejected reason=%s skill_id=%s"

_STALE_REPLY = "这次确认已经失效，没有写入技能包。需要的话请重新生成成稿。"
_ABANDON_REPLY = "已放弃，没有写入技能包。"
_PERMISSION_REPLY = "没有工具管理的新增权限，没有写入技能包。"
_ENTRY_REPLY = "当前入口不能写入技能包。"
_TEAM_REPLY = "这个智能体还没有已保存的管理分组，请先保存管理分组，再做成技能包。"
_SKILL_REPLY = "找不到这个智能体，没有写入技能包。"
_DUPLICATE_WARNING = "这些管理分组里已有同名技能包，确认后会再增加一条。"
_CARD_TITLE = "确认写入这条技能包？"
_CARD_FOOTER = "请点「确认写入」或「放弃」。只有点确认写入才会保存；在输入框里打字不会写入。"


def user_can_add_skill_package(user) -> bool:
    """与技能包导入相同：超级用户，或 opspilot 的 tool_list-Add。外部身份不能写入。"""
    if user is None or getattr(user, "is_authenticated", None) is False:
        return False
    if getattr(user, "id", None) is None:
        return False
    if not str(getattr(user, "username", "") or "").strip():
        return False
    if getattr(user, "is_superuser", False):
        return True
    permission = getattr(user, "permission", None)
    if isinstance(permission, dict):
        perms = permission.get("opspilot") or set()
    elif isinstance(permission, (set, list, tuple)):
        perms = permission
    else:
        perms = set()
    if isinstance(perms, (list, tuple)):
        perms = set(perms)
    return ADD_PERMISSION in perms


def authoring_context(user, entry: str) -> dict[str, Any]:
    """服务端覆盖客户端传入的制作开关。入口不在允许列表时 enabled 为假。"""
    entry_name = str(entry or "")
    enabled = entry_name in ALLOWED_ENTRIES
    return {
        "enabled": enabled,
        "entry": entry_name,
        "can_add": bool(enabled and user_can_add_skill_package(user)),
        "username": str(getattr(user, "username", "") or ""),
        "domain": str(getattr(user, "domain", "") or ""),
    }


def user_requested_skill_package(user_message: str = "", conversation_messages=None) -> bool:
    """当前这句话或更早的用户发言里有明确制作要求。不看助手回复和系统提示。"""
    texts = [str(user_message or "")]
    for message in conversation_messages or []:
        role, text = _role_and_text(message)
        if role in _USER_ROLES and text:
            texts.append(text)
    blob = "\n".join(texts).casefold()
    return any(phrase.casefold() in blob for phrase in _EXPLICIT_PHRASES)


def skill_package_request_needs_planner(tools, user_message: str = "", conversation_messages=None) -> bool:
    """制作工具不算业务工具；用户明确要求时仍要进入规划，避免被轻量直答吞掉。"""
    if not any(getattr(tool, "name", "") == PREPARE_CONVERSATION_SKILL_PACKAGE_TOOL for tool in (tools or [])):
        return False
    return user_requested_skill_package(user_message, conversation_messages)


def saved_management_team_ids(team) -> list[int]:
    """智能体已保存的管理分组。0 和无法转成整数的值不算。"""
    if isinstance(team, str):
        return []
    if not isinstance(team, (list, tuple)):
        return []
    ids: list[int] = []
    for item in team:
        try:
            value = int(item)
        except (TypeError, ValueError):
            continue
        if value > 0 and value not in ids:
            ids.append(value)
    return ids


def prepare_conversation_skill_package(
    *,
    name: str,
    description: str,
    triggers,
    skill_markdown: str,
    graph_request,
    config,
) -> dict[str, Any]:
    """校验成稿。通过时返回待发出的确认内容，不写缓存、不落库。"""
    authoring = _authoring(graph_request)
    skill_id = _skill_id(graph_request)
    if not authoring.get("enabled") or str(authoring.get("entry") or "") not in ALLOWED_ENTRIES:
        return _rejected("entry", skill_id, _ENTRY_REPLY)
    if not authoring.get("can_add"):
        return _rejected("permission", skill_id, _PERMISSION_REPLY)
    if not user_requested_skill_package(_user_message(graph_request), _history(graph_request)):
        return _rejected("not_requested", skill_id, "用户没有明确要求做成技能包，不要调用这个工具。")
    if not _conversation_key(graph_request, config):
        return _rejected("conversation_key", skill_id, "当前对话无法保存确认，请重试。")

    fields = _draft_fields(name, description, triggers, skill_markdown)
    missing = [label for key, label in _FIELD_LABELS if not fields[key]]
    if missing:
        return _rejected("missing_fields", skill_id, f"成稿还不完整，还缺：{'、'.join(missing)}。补全后再整理。")
    if len(fields["name"]) > 255:
        return _rejected("name_too_long", skill_id, "名称超过 255 个字，请缩短后再整理。")

    skill = LLMSkill.objects.filter(id=skill_id).only("id", "team").first() if skill_id else None
    team_ids = saved_management_team_ids(getattr(skill, "team", None))
    if skill is None:
        return _rejected("missing_skill", skill_id, _SKILL_REPLY)
    if not team_ids:
        return _rejected("missing_team", skill_id, _TEAM_REPLY)

    duplicate = _same_name_exists(name=fields["name"], domain=_actor_domain(authoring), team_ids=team_ids)
    draft_text = _render_draft(fields, duplicate=duplicate)
    visible = f"{draft_text}\n\n{_CARD_FOOTER}"
    return {
        "ok": True,
        "text": visible,
        "question": _CARD_TITLE,
        "description": draft_text,
        "options": [CONFIRM_OPTION, ABANDON_OPTION],
        "draft": {
            "skill_id": skill.id,
            "name": fields["name"],
            "description": fields["description"],
            "triggers": fields["triggers"],
            "skill_markdown": fields["skill_markdown"],
            "confirm_option": CONFIRM_OPTION,
        },
    }


def publish_conversation_skill_package_choice(prepared: dict[str, Any], *, graph_request, config, messages, tool_call_id: str):
    """校验已通过后发出确认卡，并把成稿快照放进待答标记。"""
    visible, tool_message = finalize_user_choice(
        question=prepared["question"],
        question_type="single_select",
        options=prepared["options"],
        config=_config_with_conversation_key(graph_request, config),
        messages=messages,
        tool_call_id=tool_call_id,
        description=prepared["description"],
        skill_package_draft=prepared["draft"],
        visible_text=prepared["text"],
        tool_name=PREPARE_CONVERSATION_SKILL_PACKAGE_TOOL,
        tool_result="已向用户发出技能包确认，本轮结束。",
    )
    return visible, tool_message


def try_commit_conversation_skill_package(params) -> str | None:
    """确认点击按快照新建技能包。没有成稿标记时返回 None，交给原来的对话。"""
    if not isinstance(params, dict):
        return None
    key = resolve_conversation_key(
        conversation_key=params.get("conversation_key"),
        bot_id=params.get("bot_id"),
        session_id=params.get("session_id"),
        thread_id=params.get("thread_id"),
        skill_session_id=params.get("skill_session_id"),
    )
    if not key:
        return _STALE_REPLY if _is_confirm_click(params) else None

    pending = peek_pending_question(key)
    draft = pending.get("skill_package_draft") if isinstance(pending, dict) else None
    if not isinstance(draft, dict):
        if _is_confirm_click(params):
            logger.info(_REJECTED_LOG, "stale", _param_skill_id(params))
            return _STALE_REPLY
        return None

    consumed = consume_pending_question(key)
    if not isinstance(consumed, dict) or not isinstance(consumed.get("skill_package_draft"), dict):
        if _is_confirm_click(params):
            logger.info(_REJECTED_LOG, "stale", _param_skill_id(params))
            return _STALE_REPLY
        return None
    draft = consumed["skill_package_draft"]
    skill_id = draft.get("skill_id")

    choice_id = str(params.get("choice_id") or "").strip()
    option = str(params.get("choice_option") or "").strip()
    if not choice_id or choice_id != str(draft.get("choice_id") or ""):
        logger.info(_REJECTED_LOG, "not_card_click", skill_id or "-")
        return None
    if option == ABANDON_OPTION:
        logger.info(_REJECTED_LOG, "abandoned", skill_id or "-")
        return _ABANDON_REPLY
    if option != CONFIRM_OPTION:
        logger.info(_REJECTED_LOG, "not_card_click", skill_id or "-")
        return None

    authoring = params.get(AUTHORING_EXTRA_KEY)
    if not isinstance(authoring, dict) or not authoring.get("enabled") or str(authoring.get("entry") or "") not in ALLOWED_ENTRIES:
        logger.info(_REJECTED_LOG, "entry", skill_id or "-")
        return _ENTRY_REPLY
    if not authoring.get("can_add"):
        logger.info(_REJECTED_LOG, "permission", skill_id or "-")
        return _PERMISSION_REPLY

    fields = _draft_fields(draft.get("name"), draft.get("description"), draft.get("triggers"), draft.get("skill_markdown"))
    if not all(fields[key] for key, _label in _FIELD_LABELS):
        logger.info(_REJECTED_LOG, "missing_fields", skill_id or "-")
        return "成稿已不完整，没有写入。请重新生成。"

    skill = LLMSkill.objects.filter(id=skill_id).only("id", "team", "skill_packages").first()
    if skill is None:
        logger.info(_REJECTED_LOG, "missing_skill", skill_id or "-")
        return _SKILL_REPLY
    team_ids = saved_management_team_ids(skill.team)
    if not team_ids:
        logger.info(_REJECTED_LOG, "missing_team", skill.id)
        return _TEAM_REPLY

    try:
        package = SkillPackage.objects.create(
            package_id=uuid.uuid4().hex,
            name=fields["name"],
            version=PACKAGE_VERSION,
            description=fields["description"],
            category="",
            source_type=SOURCE_CONVERSATION,
            source_url="",
            storage_path="",
            manifest={},
            skill_markdown=fields["skill_markdown"],
            required_tools=[],
            triggers=fields["triggers"],
            team=team_ids,
            system_tags=[],
            user_tags=[],
            is_enabled=True,
            is_build_in=False,
            **maintainer_kwargs(operator=str(authoring.get("username") or ""), domain=_actor_domain(authoring)),
        )
    except Exception:
        save_pending_question(key, consumed)
        raise
    logger.info(_SAVED_LOG, skill.id, package.package_id)
    return f"已写入技能包「{package.name}」。请刷新智能体配置页，在「添加技能包」里勾选。默认不会自动勾上。"


def _rejected(reason: str, skill_id, text: str) -> dict[str, Any]:
    logger.info(_REJECTED_LOG, reason, skill_id or "-")
    return {"ok": False, "text": text}


def _draft_fields(name, description, triggers, skill_markdown) -> dict[str, Any]:
    return {
        "name": " ".join(str(name or "").split()),
        "description": str(description or "").strip(),
        "triggers": _normalize_triggers(triggers),
        "skill_markdown": str(skill_markdown or "").strip(),
    }


def _normalize_triggers(raw) -> list[str]:
    if isinstance(raw, str):
        parts = re.split(r"[,，、\n]", raw)
    elif isinstance(raw, (list, tuple)):
        parts = []
        for item in raw:
            if isinstance(item, str):
                parts.extend(re.split(r"[,，、\n]", item))
            elif item is not None:
                parts.append(str(item))
    else:
        return []
    seen: list[str] = []
    for part in parts:
        text = str(part or "").strip()
        if text and text not in seen:
            seen.append(text)
    return seen


def _render_draft(fields: dict[str, Any], *, duplicate: bool) -> str:
    lines = []
    if duplicate:
        lines.append(_DUPLICATE_WARNING)
        lines.append("")
    lines.append(f"名称：{fields['name']}")
    lines.append(f"何时使用：{fields['description']}")
    lines.append("触发词：" + "、".join(fields["triggers"]))
    lines.append("正文：")
    lines.append(fields["skill_markdown"])
    return "\n".join(lines)


def _same_name_exists(*, name: str, domain: str, team_ids: list[int]) -> bool:
    wanted = set(team_ids)
    rows = SkillPackage.objects.filter(name=name, domain=domain).only("team")
    for row in rows:
        if wanted & set(saved_management_team_ids(row.team)):
            return True
    return False


def _authoring(graph_request) -> dict[str, Any]:
    extra = getattr(graph_request, "extra_config", None) or {}
    if not isinstance(extra, dict):
        return {}
    raw = extra.get(AUTHORING_EXTRA_KEY)
    return raw if isinstance(raw, dict) else {}


def _skill_id(graph_request):
    extra = getattr(graph_request, "extra_config", None) or {}
    if not isinstance(extra, dict):
        return None
    try:
        value = int(extra.get("skill_id"))
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _user_message(graph_request) -> str:
    return str(getattr(graph_request, "user_message", "") or getattr(graph_request, "graph_user_message", "") or "")


def _history(graph_request):
    history = getattr(graph_request, "chat_history", None)
    return history if isinstance(history, (list, tuple)) else []


def _config_with_conversation_key(graph_request, config) -> dict[str, Any]:
    merged = dict(config) if isinstance(config, dict) else {}
    configurable = dict(merged.get("configurable") or {})
    key = _conversation_key(graph_request, merged)
    if key:
        configurable["conversation_key"] = key
    if graph_request is not None and configurable.get("graph_request") is None:
        configurable["graph_request"] = graph_request
    merged["configurable"] = configurable
    return merged


def _conversation_key(graph_request, config) -> str:
    configurable = {}
    if isinstance(config, dict):
        raw = config.get("configurable")
        if isinstance(raw, dict):
            configurable = raw
    key = resolve_conversation_key_from_mapping(configurable)
    if key:
        return key
    extra = getattr(graph_request, "extra_config", None) or {}
    if not isinstance(extra, dict):
        extra = {}
    return resolve_conversation_key(
        conversation_key=extra.get("conversation_key"),
        bot_id=extra.get("bot_id"),
        session_id=extra.get("session_id"),
        thread_id=getattr(graph_request, "thread_id", None) or extra.get("thread_id"),
        skill_session_id=extra.get("skill_session_id"),
    )


def _actor_domain(authoring: dict[str, Any]) -> str:
    return str(authoring.get("domain") or "").strip() or "domain.com"


def _is_confirm_click(params: dict) -> bool:
    return bool(str(params.get("choice_id") or "").strip()) and str(params.get("choice_option") or "").strip() == CONFIRM_OPTION


def _param_skill_id(params: dict):
    try:
        return int(params.get("skill_id"))
    except (TypeError, ValueError):
        return "-"


def _role_and_text(message) -> tuple[str, str]:
    if isinstance(message, dict):
        role = str(message.get("event") or message.get("role") or message.get("type") or "")
        text = message.get("message", message.get("content", ""))
    else:
        role = str(getattr(message, "event", "") or getattr(message, "type", "") or getattr(message, "role", "") or "")
        text = getattr(message, "message", None)
        if text is None:
            text = getattr(message, "content", "") or ""
    if not isinstance(text, str):
        text = ""
    return role.casefold(), text
