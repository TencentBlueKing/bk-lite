"""把一轮对话里明确要求记下或修正的知识落成文本资料并入队。"""

from __future__ import annotations

from types import SimpleNamespace

from django.db import transaction
from django.db.models import Q

from apps.core.logger import opspilot_logger as logger
from apps.core.models.maintainer_info import maintainer_kwargs
from apps.opspilot.models import BuildRecord, CheckItem, KnowledgePage, LLMSkill, Material, PageVersion, WikiKnowledgeBase
from apps.opspilot.services.caller_identity import CALLER_IDENTITY_CONFIG_KEY
from apps.opspilot.services.wiki.material_build_queue_service import QUEUE_ITEM_TRIGGER, enqueue_material_builds
from apps.opspilot.services.wiki.material_source_service import source_metadata
from apps.system_mgmt.models import User as SystemUser
from apps.system_mgmt.models.operation_log import OperationLog

WIKI_MATERIAL_ACTOR_KEY = "wiki_material_actor"
WIKI_MATERIAL_TOOL_NAME = "wiki_material"
SAVE_WIKI_MATERIAL_TOOL_NAME = "save_wiki_material"

REPLY_SUCCESS = "正在写入，请在此等待结果"
REPLY_FAILED = "写入失败，请稍后再试"
REPLY_DENIED = "当前无权限"
REPLY_KB_DENIED = "没有权限操作该知识库，请联系管理员"
SUMMARY_CONFLICT = "这条知识与已有内容冲突，请在对话里确认"
SUMMARY_GENERATED_PREFIX = "知识已经生成："
SUMMARY_QUIET = "知识已写入，没有新的冲突"
SUMMARY_CONFIRMED = "已确认"
REPLY_SWITCH_OFF = "该智能体不能修改知识库"
REPLY_NO_KB = "没有选择知识库"
REPLY_NAME_KB = "请指定要写入的知识库"
REPLY_NOT_WRITTEN = "未写入知识库"

_BODY_EXCERPT_LEN = 50
_BODY_CAP = 4000
_CREATED_BY_MAX = 32
_SUCCEEDED_BUILD_STATUSES = frozenset({"success", "partial"})
_FAILED_BUILD_STATUSES = frozenset({"failed", "cancelled"})
_FAILED_MATERIAL_STATUSES = frozenset({"build_failed", "parse_failed", "invalid"})
_NEW_PAGE_ACTIONS = frozenset({"create", "new"})
_ACTIONS_WITH_MATERIAL = frozenset({"use_new", "edit_accept"})
_DISCARDABLE_STATUSES = frozenset({"pending", "queued"})
_ACTOR_MODES = frozenset({"system", "external", "anonymous"})
_WIKI_MATERIAL_TOOL_MARKER = f"langchain:{WIKI_MATERIAL_TOOL_NAME}"
# ChatFlow 渠道入口写进 flow_input["channel"] 的值。钉钉执行参数用 ding_talk，渠道码是 dingtalk。
_CHAT_FLOW_EXTERNAL_CHANNELS = frozenset(
    {
        "ding_talk",
        "dingtalk",
        "enterprise_wechat",
        "enterprise_wechat_aibot",
        "wechat_official_account",
        "wechat_official",
        "feishu",
    }
)

_PROMPT_WHEN_OFF = "\n\n【知识库写入】本智能体不能修改知识库。" f"如果用户要求记下、保存、写入或修正知识库中的知识，只回复「{REPLY_SWITCH_OFF}」，不要声称已经写入。"
_PROMPT_WHEN_NO_KB = "\n\n【知识库写入】本智能体没有选择知识库。" f"如果用户要求记下、保存、写入或修正知识库中的知识，只回复「{REPLY_NO_KB}」，不要声称已经写入。"
_PROMPT_WHEN_ON = (
    "\n\n【知识库写入】仅当用户在本轮明确要求记下、保存或修正知识库中的知识时，"
    f"调用 {SAVE_WIKI_MATERIAL_TOOL_NAME}。分析或排障结束、或你认为结论有价值，都不要调用。"
    "title 写知识说明的短标题，body 写整理后的知识本身，不要写用户的指令句。"
    "绑定多个知识库时，knowledge_base_name 必须是用户点名的名称；只绑定一个时可以留空。"
    "调用时 explicit_request 必须为 true。把工具返回的原文原样回复给用户，不要改写，不要声称知识页已经存在，也不要补充队列、审核或旧页是否已改。"
)


def anonymous_actor() -> dict:
    return {"mode": "anonymous", "username": "", "domain": "", "sender_id": ""}


def system_actor(username: str, domain: str) -> dict:
    return {
        "mode": "system",
        "username": (username or "").strip(),
        "domain": (domain or "").strip(),
        "sender_id": "",
    }


def external_actor(sender_id: str) -> dict:
    return {
        "mode": "external",
        "username": "",
        "domain": "",
        "sender_id": (sender_id or "").strip(),
    }


def actor_for_platform_user(user) -> dict:
    username = str(getattr(user, "username", "") or "").strip()
    domain = str(getattr(user, "domain", "") or "").strip()
    if not username or not domain:
        return anonymous_actor()
    return system_actor(username, domain)


def actor_for_caller_identity(identity) -> dict:
    if not isinstance(identity, dict):
        return anonymous_actor()
    return actor_for_platform_user(SimpleNamespace(username=identity.get("username"), domain=identity.get("domain")))


def actor_for_chat_flow_input(flow_input) -> dict:
    """平台身份优先。只有已知外部渠道才采用入口注入的发送者。"""
    if not isinstance(flow_input, dict):
        return anonymous_actor()
    caller = actor_for_caller_identity(flow_input.get(CALLER_IDENTITY_CONFIG_KEY))
    if caller["mode"] == "system":
        return caller
    channel = str(flow_input.get("channel") or "").strip()
    if channel not in _CHAT_FLOW_EXTERNAL_CHANNELS:
        return anonymous_actor()
    injected = flow_input.get(WIKI_MATERIAL_ACTOR_KEY)
    if isinstance(injected, dict) and injected.get("mode") == "external":
        return external_actor(str(injected.get("sender_id") or ""))
    sender = flow_input.get("user_id")
    if isinstance(sender, str):
        return external_actor(sender)
    return anonymous_actor()


def is_chat_sourced_material(material) -> bool:
    """只有对话写入打下的标记才放宽同主题比较。来源路径可由上传指定，不能用来分流。"""
    return bool(getattr(material, "chat_sourced", False))


def normalize_actor(value) -> dict:
    if not isinstance(value, dict) or value.get("mode") not in _ACTOR_MODES:
        return anonymous_actor()
    mode = value["mode"]
    if mode == "system":
        return system_actor(str(value.get("username") or ""), str(value.get("domain") or ""))
    if mode == "external":
        return external_actor(str(value.get("sender_id") or ""))
    return anonymous_actor()


def wiki_material_write_mode(skill_id) -> str:
    """off：开关关闭。no_kb：开关打开但没选知识库。on：可以写入。"""
    try:
        pk = int(skill_id)
    except (TypeError, ValueError):
        return "off"
    if pk <= 0:
        return "off"
    skill = LLMSkill.objects.filter(pk=pk).only("id", "allow_wiki_material_write").first()
    if skill is None or not skill.allow_wiki_material_write:
        return "off"
    if not skill.wiki_knowledge_bases.exists():
        return "no_kb"
    return "on"


def skill_allows_wiki_material_write(skill_id) -> bool:
    return wiki_material_write_mode(skill_id) == "on"


def wiki_grounded_uses_single_model_call(*, force_wiki_grounded: bool, allow_wiki_material_write: bool) -> bool:
    """强制知识库回答平时收成单次调用。允许写入时必须留出工具调用。"""
    return bool(force_wiki_grounded) and not bool(allow_wiki_material_write)


def wiki_material_tool_server() -> dict:
    return {
        "name": WIKI_MATERIAL_TOOL_NAME,
        "url": f"langchain:{WIKI_MATERIAL_TOOL_NAME}",
        "enable_auth": False,
        "auth_token": "",
        "extra_tools_prompt": "",
    }


def _is_wiki_material_tool(tool) -> bool:
    if not isinstance(tool, dict):
        return False
    if tool.get("name") == WIKI_MATERIAL_TOOL_NAME:
        return True
    url = tool.get("url")
    if isinstance(url, str) and _WIKI_MATERIAL_TOOL_MARKER in url:
        return True
    category = tool.get("category")
    if isinstance(category, str):
        return _WIKI_MATERIAL_TOOL_MARKER in category
    if isinstance(category, (list, tuple)):
        return any(isinstance(item, str) and _WIKI_MATERIAL_TOOL_MARKER in item for item in category)
    return False


def apply_wiki_material_runtime(chat_kwargs: dict, kwargs: dict) -> None:
    """按库里的开关注入提示和工具，并把服务端行动者写入 extra_config。"""
    mode = wiki_material_write_mode(kwargs.get("skill_id"))
    prompt = chat_kwargs.get("system_message_prompt") or ""
    if kwargs.get("skill_id") not in (None, ""):
        addition = {"on": _PROMPT_WHEN_ON, "no_kb": _PROMPT_WHEN_NO_KB}.get(mode, _PROMPT_WHEN_OFF)
        chat_kwargs["system_message_prompt"] = prompt + addition
    raw_tools = chat_kwargs.get("tools_servers")
    tools = [tool for tool in list(raw_tools or []) if not _is_wiki_material_tool(tool)]
    if mode == "on":
        tools.append(wiki_material_tool_server())
    if raw_tools is not None or mode == "on":
        chat_kwargs["tools_servers"] = tools

    extra = chat_kwargs.get("extra_config")
    if not isinstance(extra, dict):
        extra = {}
        chat_kwargs["extra_config"] = extra
    extra.pop(WIKI_MATERIAL_ACTOR_KEY, None)
    extra[WIKI_MATERIAL_ACTOR_KEY] = normalize_actor(kwargs.get(WIKI_MATERIAL_ACTOR_KEY))
    skill_id = kwargs.get("skill_id")
    if skill_id not in (None, ""):
        extra["skill_id"] = skill_id


def resolve_writer(actor) -> SystemUser | None:
    normalized = normalize_actor(actor)
    if normalized["mode"] == "system":
        username = normalized["username"]
        domain = normalized["domain"]
        if not username or not domain:
            return None
        return SystemUser.objects.filter(username=username, domain=domain, disabled=False).first()
    if normalized["mode"] != "external":
        return None
    sender = normalized["sender_id"]
    if not sender:
        return None
    matched = list(SystemUser.objects.filter(disabled=False).filter(Q(username=sender) | Q(user_id=sender)).order_by("id")[:2])
    if len(matched) != 1:
        return None
    return matched[0]


def _select_knowledge_base(skill: LLMSkill, raw_name: str) -> tuple[WikiKnowledgeBase | None, str | None]:
    bound = list(skill.wiki_knowledge_bases.all())
    if not bound:
        return None, REPLY_NO_KB
    if len(bound) == 1:
        return bound[0], None
    wanted = (raw_name or "").strip()
    if not wanted:
        return None, REPLY_NAME_KB
    matches = [item for item in bound if (item.name or "").strip() == wanted]
    if len(matches) != 1:
        return None, REPLY_NAME_KB
    return matches[0], None


def _discard_unbuilt_material(material_id: int) -> None:
    material = Material.objects.filter(pk=material_id).first()
    if material is None or material.status not in _DISCARDABLE_STATUSES:
        return
    BuildRecord.objects.filter(
        knowledge_base_id=material.knowledge_base_id,
        trigger=QUEUE_ITEM_TRIGGER,
        status="running",
        stage="queued",
        inputs__material_id=material.pk,
    ).delete()
    Material.objects.filter(pk=material.pk, status__in=list(_DISCARDABLE_STATUSES)).delete()


def _id_set(values) -> set[int]:
    found = set()
    for item in values or []:
        try:
            found.add(int(item))
        except (TypeError, ValueError):
            continue
    return found


def _enqueue_succeeded(material_id: int, result: dict) -> bool:
    payload = result or {}
    return material_id in _id_set(payload.get("queued")) or material_id in _id_set(payload.get("already_queued"))


def _assign_chat_source(material: Material) -> None:
    """补上构建要求的来源身份。相对路径只用于来源身份，不决定是否放宽冲突比较。"""
    metadata = source_metadata(material.knowledge_base, source_relative_path=f"chat/{material.pk}.txt")
    material.source_relative_path = metadata["source_relative_path"]
    material.source_folder_path = metadata["source_folder_path"]
    material.source_identity = metadata["source_identity"]
    material.save(update_fields=["source_relative_path", "source_folder_path", "source_identity", "updated_at"])


def _record_success_log(*, user: SystemUser, knowledge_base: WikiKnowledgeBase, material: Material, body: str) -> None:
    excerpt = body[:_BODY_EXCERPT_LEN]
    OperationLog.objects.create(
        username=user.username,
        domain=user.domain or "domain.com",
        source_ip="0.0.0.0",
        app="opspilot",
        action_type=OperationLog.ACTION_CREATE,
        summary=f"对话新增资料: {material.name}",
        target_type="wiki_material",
        target_id=str(material.id),
        detail={
            "knowledge_base_id": knowledge_base.id,
            "knowledge_base_name": knowledge_base.name,
            "material_name": material.name,
            "material_id": material.id,
            "body_excerpt": excerpt,
        },
    )


def write_chat_wiki_material(
    *,
    skill: LLMSkill | None,
    explicit_request: bool,
    title: str,
    body: str,
    knowledge_base_name: str = "",
    actor=None,
) -> str:
    """创建一条文本资料并入队。入队尚未成功时不留下资料，也不记成功日志。入队成功后即使操作日志失败也保留资料。"""
    if explicit_request is not True:
        return REPLY_NOT_WRITTEN
    cleaned_title = (title or "").strip()
    cleaned_body = (body or "").strip()
    if not cleaned_title or not cleaned_body:
        return REPLY_NOT_WRITTEN
    if skill is None or not bool(getattr(skill, "allow_wiki_material_write", False)):
        return REPLY_SWITCH_OFF

    user = resolve_writer(actor)
    if user is None:
        return REPLY_DENIED

    knowledge_base, refusal = _select_knowledge_base(skill, knowledge_base_name)
    if knowledge_base is None:
        return refusal or REPLY_NO_KB
    if not _user_can_operate_knowledge_base(user, knowledge_base):
        return REPLY_KB_DENIED

    maintainer = maintainer_kwargs(operator=user.username, domain=user.domain or "domain.com")
    maintainer["created_by"] = (maintainer.get("created_by") or "")[:_CREATED_BY_MAX]
    maintainer["updated_by"] = (maintainer.get("updated_by") or "")[:_CREATED_BY_MAX]
    material = Material.objects.create(
        knowledge_base=knowledge_base,
        name=cleaned_title[:255],
        material_type="text",
        text_content=cleaned_body,
        status="pending",
        chat_sourced=True,
        **maintainer,
    )
    try:
        _assign_chat_source(material)
        result = enqueue_material_builds(
            knowledge_base_id=knowledge_base.id,
            material_ids=[material.id],
            operator=user.username,
        )
    except Exception as exc:
        logger.warning(
            "chat wiki material enqueue failed kb_id=%s material_id=%s error_type=%s",
            knowledge_base.id,
            material.id,
            type(exc).__name__,
        )
        _discard_unbuilt_material(material.id)
        return REPLY_FAILED
    if not _enqueue_succeeded(material.id, result):
        _discard_unbuilt_material(material.id)
        return REPLY_FAILED
    _dispatch_wiki_material_write(material)
    try:
        _record_success_log(user=user, knowledge_base=knowledge_base, material=material, body=cleaned_body)
    except Exception as exc:
        logger.warning(
            "chat wiki material audit failed kb_id=%s material_id=%s error_type=%s",
            knowledge_base.id,
            material.id,
            type(exc).__name__,
        )
    return REPLY_SUCCESS


def _user_can_operate_knowledge_base(user, knowledge_base) -> bool:
    # viewsets 包的初始化会回到本模块，顶层导入形成环。
    from apps.opspilot.viewsets.wiki_team_scope import user_can_operate_knowledge_base

    return user_can_operate_knowledge_base(user, knowledge_base)


def _dispatch_wiki_material_write(material) -> None:
    # langchain 只在对话写入成功时需要。顶层导入会让资料构建在导入本模块时带上它。
    outcome = read_chat_wiki_outcome(material)
    try:
        from langchain_core.callbacks import dispatch_custom_event

        dispatch_custom_event(
            "wiki_material_write",
            {"material_id": outcome["material_id"], "phase": outcome["phase"], "summary": outcome["summary"]},
        )
    except Exception as exc:
        logger.warning(
            "chat wiki material event failed material_id=%s error_type=%s",
            material.pk,
            type(exc).__name__,
        )


def _clip_body(value) -> str:
    if not isinstance(value, str):
        return ""
    return value[:_BODY_CAP]


def _positive_id(value):
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed


def _related_material_ids(related) -> set[int]:
    if not isinstance(related, dict):
        return set()
    materials = related.get("materials")
    if not isinstance(materials, list):
        return set()
    found = set()
    for item in materials:
        raw = item.get("material_id") if isinstance(item, dict) else item
        if isinstance(item, dict) and raw in (None, ""):
            raw = item.get("id")
        parsed = _positive_id(raw)
        if parsed is not None:
            found.add(parsed)
    return found


def _related_page_id(related):
    if not isinstance(related, dict):
        return None
    pages = related.get("pages")
    if not isinstance(pages, list):
        return None
    for item in pages:
        raw = item.get("id") if isinstance(item, dict) else item
        parsed = _positive_id(raw)
        if parsed is not None:
            return parsed
    return None


def _new_count(build) -> int:
    counts = getattr(build, "counts", None)
    if not isinstance(counts, dict):
        return 0
    return _positive_id(counts.get("new")) or 0


def _page_actions(build):
    actions = getattr(build, "page_actions", None)
    if isinstance(actions, list) and actions:
        return actions
    inputs = getattr(build, "inputs", None)
    trace = inputs.get("source_trace") if isinstance(inputs, dict) else None
    nested = trace.get("page_actions") if isinstance(trace, dict) else None
    return nested if isinstance(nested, list) else []


def _new_pages(build) -> list[dict]:
    actions = _page_actions(build)
    if not isinstance(actions, list):
        return []
    pages = []
    seen = set()
    for item in actions:
        if not isinstance(item, dict) or item.get("action") not in _NEW_PAGE_ACTIONS:
            continue
        page_id = _positive_id(item.get("page_id"))
        if page_id is None or page_id in seen:
            continue
        seen.add(page_id)
        title = item.get("title") if isinstance(item.get("title"), str) else ""
        pages.append({"id": page_id, "title": title})
    return pages


def _related_checks(material):
    matched = []
    queryset = CheckItem.objects.filter(knowledge_base_id=material.knowledge_base_id).select_related("candidate_version").order_by("id")
    for check in queryset:
        if material.pk in _related_material_ids(check.related):
            matched.append(check)
    return matched


def _latest_build(material):
    return (
        BuildRecord.objects.filter(
            knowledge_base_id=material.knowledge_base_id,
            inputs__material_id=material.pk,
        )
        .order_by("-id")
        .first()
    )


def _locked_current_version(check):
    context = check.decision_context if isinstance(check.decision_context, dict) else {}
    locked_id = _positive_id(context.get("locked_current_version_id"))
    if locked_id is None:
        return None
    return PageVersion.objects.filter(pk=locked_id).first()


def _check_payload(check) -> dict:
    page_id = _related_page_id(check.related)
    page = None
    if page_id is not None:
        page = KnowledgePage.objects.select_related("current_version").filter(pk=page_id, knowledge_base_id=check.knowledge_base_id).first()
    current = _locked_current_version(check)
    if current is None and page is not None:
        current = page.current_version
    candidate = check.candidate_version
    actions = check.suggested_actions if isinstance(check.suggested_actions, list) else []
    return {
        "id": check.id,
        "page_id": page.id if page is not None else page_id,
        "page_title": page.title if page is not None else "",
        "current_body": _clip_body(getattr(current, "body", "")),
        "incoming_body": _clip_body(getattr(candidate, "body", "")),
        "actions": list(actions),
        "status": check.status,
    }


def _outcome(material, phase: str, summary: str, pages: list, checks: list) -> dict:
    return {
        "material_id": material.pk,
        "phase": phase,
        "summary": summary,
        "pages": pages,
        "checks": checks,
    }


def read_chat_wiki_outcome(material) -> dict:
    """从资料、该资料最新构建记录和相关检查项读出卡片结果。"""
    checks = _related_checks(material)
    payloads = [_check_payload(check) for check in checks]
    if any(check.status == "open" for check in checks):
        return _outcome(material, "needs_decision", SUMMARY_CONFLICT, [], payloads)
    if checks:
        return _outcome(material, "published", SUMMARY_CONFIRMED, [], payloads)
    build = _latest_build(material)
    build_status = getattr(build, "status", None)
    if material.status in _FAILED_MATERIAL_STATUSES or build_status in _FAILED_BUILD_STATUSES:
        return _outcome(material, "failed", REPLY_FAILED, [], [])
    if build_status in _SUCCEEDED_BUILD_STATUSES and _new_count(build) > 0:
        pages = _new_pages(build)
        titles = [page["title"] for page in pages if page["title"]]
        return _outcome(material, "published", SUMMARY_GENERATED_PREFIX + "、".join(titles), pages, [])
    if build_status in _SUCCEEDED_BUILD_STATUSES:
        return _outcome(material, "published", SUMMARY_QUIET, [], [])
    return _outcome(material, "writing", REPLY_SUCCESS, [], [])


def _record_decision_log(*, operator: str, domain: str, source_ip: str, material, check_id: int, action: str) -> None:
    OperationLog.objects.create(
        username=operator,
        domain=domain or "domain.com",
        source_ip=source_ip or "0.0.0.0",
        app="opspilot",
        action_type=OperationLog.ACTION_EXECUTE,
        summary=f"对话确认知识检查 {check_id}",
        target_type="wiki_check",
        target_id=str(check_id),
        detail={
            "knowledge_base_id": material.knowledge_base_id,
            "material_id": material.pk,
            "check_id": check_id,
            "action": action,
        },
    )


def decide_chat_wiki_write(*, material_id: int, check_id: int, action: str, body: str, operator: str, domain: str, source_ip: str):
    """确认这条资料相关的检查项。已经关闭的检查项再点一次，不再调用 decide_check。"""
    # 审核决策只在对话里确认时需要，避免资料构建导入本模块时带上整套检查服务。
    from apps.opspilot.services.wiki.check_service import decide_check

    with transaction.atomic():
        material = Material.objects.select_for_update().filter(pk=material_id, chat_sourced=True).first()
        if material is None:
            raise ValueError("missing write")
        check = CheckItem.objects.select_for_update().filter(pk=check_id, knowledge_base_id=material.knowledge_base_id).first()
        if check is None or material.pk not in _related_material_ids(check.related):
            raise ValueError("unknown check")
        actions = check.suggested_actions if isinstance(check.suggested_actions, list) else []
        if check.status != "open":
            if actions and action not in actions:
                raise ValueError("unknown action")
            return read_chat_wiki_outcome(material)
        if action not in actions:
            raise ValueError("unknown action")
        decide_check(
            check,
            action,
            operator=operator or "",
            body=body or "",
            material=material if action in _ACTIONS_WITH_MATERIAL else None,
        )
        _record_decision_log(
            operator=operator,
            domain=domain,
            source_ip=source_ip,
            material=material,
            check_id=check_id,
            action=action,
        )
        return read_chat_wiki_outcome(material)
