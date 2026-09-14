"""智能体渠道对话记忆：读取注入、水位线计数与写入调度。"""

from datetime import timedelta

from django.db.models import Count, IntegerField, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.memory.engines.base import MemoryEntity
from apps.opspilot.memory.engines.registry import MemoryEngineRegistry
from apps.opspilot.memory.identity import split_external_user_id
from apps.opspilot.memory.truncate import truncate_memory_context
from apps.opspilot.models import LLMSkill, MemorySpace, SkillConversation, SkillConversationMessage

SKILL_MEMORY_WRITE_ROUNDS_MIN = 1
SKILL_MEMORY_WRITE_ROUNDS_MAX = 50
SKILL_MEMORY_WRITE_ROUNDS_DEFAULT = 10
SKILL_MEMORY_TITLE = "对话记忆"
SKILL_MEMORY_IDLE_MINUTES = 30
SKILL_MEMORY_READ_TOP_K = 5
SKILL_MEMORY_MESSAGE_MAX_CHARS = 4000
SKILL_MEMORY_TRANSCRIPT_MAX_CHARS = 48000
SKILL_CONVERSATION_SUMMARY_EMPTY = "EMPTY"
SKILL_CONVERSATION_SUMMARY_SYSTEM = "你负责把运维对话提炼成可复用的长期记忆。必须写下对话里出现过的专有名词、指标和阈值；禁止只输出空泛人设。"
SKILL_CONVERSATION_SUMMARY_PROMPT = """你是对话记忆助手。根据对话记录生成长期记忆，供以后排障/巡检继续使用。

## 合格标准（必须同时满足）
- 对话里出现过的集群、主机、Pod、库、告警名、指标、阈值、优先级，都要写进记忆
- 若对话包含告警分析或巡检方案，必须有「环境与资产」「结论与现状」「检查约定」三节，不能只写「用户画像」和「偏好」
- 用条目写事实，不要复制大段 SQL、脚本或整张报表

## 各节写什么
- 用户画像：职责与技术栈（一句话即可）
- 环境与资产：名称必须具体，例如集群名、Namespace、Pod、数据库类型
- 结论与现状：已确认的告警/根因/指标水位/处理结论
- 检查约定：检查项、P0/P1/P2、预警阈值、巡检频率（从表格提炼成条目）
- 未决问题：还没做完或用户要继续跟的事项
- 偏好：输出格式、详略习惯

## 不合格示例（禁止这样写）
## 用户画像
- 运维人员，关注巡检
## 偏好
- 喜欢表格

## 合格示例（风格参照，不要抄示例里的假数据）
## 用户画像
- 负责 K8s 与数据库巡检的运维
## 环境与资产
- K8s 集群 `prod-k8s-01`，Namespace `web-app`，Pod `web-xxx`
## 结论与现状
- Readiness 探针失败（Unhealthy），目标端口未监听
## 检查约定
- Oracle P0：表空间与归档空间，小时级；使用率超 80% 预警
- Oracle P1：RMAN 备份每日确认
## 偏好
- 回答先列重点，再用表格

## 不要保留
- 寒暄问好、客套、无信息量确认（如「你好」「在吗」「谢谢」「好的」）
- 工具调用过程、思考链、逐步推理
- 大段 SQL/脚本/报表原文

## 输出
- 只输出 Markdown 记忆正文或 EMPTY
- 有则写、无则省略；但只要对话里有告警/巡检，就不得省略环境、结论、检查约定
- 若完全没有可保留内容，只输出 EMPTY

## 对话记录
{transcript}
"""

_SKILL_MEMORY_PROMPT_GUIDE = (
    "以下是该用户的个人长期记忆，来自其在本平台、Web、IM 等渠道的历史对话，跨会话持续有效。"
    "本轮必须优先使用这些记忆里的环境、资产、已确认结论、检查约定与阈值："
    "只取与当前问题相关的条目，不要把其它技术栈的检查项混进来；"
    "直接复用已沉淀的检查项、优先级和阈值，不要另起一套通用清单，也不要编造记忆里没有的整段 SQL/脚本；"
    "记忆中的输出约定继续遵守，用户本轮明确要求命令时再给命令；"
    "与用户本轮表述冲突时以本轮为准，记忆没有的细节不要编造。"
)
_SKILL_MEMORY_PROMPT_FOOTER = "回答时先按上述记忆组织，再补充本轮新信息。"
_SKILL_MEMORY_READ_FAILED = "event=skill_memory_read_failed skill_id=%s memory_space_id=%s failed_stage=read error_type=%s"
_SKILL_MEMORY_INJECTED_LOG = "event=skill_memory_injected skill_id=%s memory_space_id=%s context_chars=%s"
_SKILL_MEMORY_EMPTY_LOG = "event=skill_memory_empty skill_id=%s memory_space_id=%s"


class SkillMemoryConfigError(ValueError):
    """智能体记忆体 / 写入轮数配置无效。"""


def _user_team_ids(user) -> set[int]:
    ids: set[int] = set()
    for item in getattr(user, "group_list", None) or []:
        raw = item.get("id") if isinstance(item, dict) else item
        try:
            ids.add(int(raw))
        except (TypeError, ValueError):
            continue
    return ids


def is_usable_skill_memory_space(space: MemorySpace | None) -> bool:
    return space is not None and space.scope == MemorySpace.SCOPE_PERSONAL


def skill_has_conversation_memory(skill: LLMSkill | None) -> bool:
    return is_usable_skill_memory_space(getattr(skill, "memory_space", None) if skill is not None else None)


def user_can_use_memory_space(user, space: MemorySpace) -> bool:
    if not is_usable_skill_memory_space(space):
        return False
    if user is not None and getattr(user, "is_superuser", False):
        return True
    space_teams = {int(item) for item in (space.team or []) if str(item).lstrip("-").isdigit()}
    return bool(_user_team_ids(user) & space_teams)


def normalize_memory_space_id(value) -> int | None:
    if value in (None, "", 0, "0"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise SkillMemoryConfigError("记忆体无效") from exc


def normalize_write_rounds(value, default: int = SKILL_MEMORY_WRITE_ROUNDS_DEFAULT) -> int:
    if value in (None, ""):
        return default
    try:
        rounds = int(value)
    except (TypeError, ValueError) as exc:
        raise SkillMemoryConfigError("记忆写入轮数无效") from exc
    if rounds < SKILL_MEMORY_WRITE_ROUNDS_MIN or rounds > SKILL_MEMORY_WRITE_ROUNDS_MAX:
        raise SkillMemoryConfigError("记忆写入轮数须在 1–50 之间")
    return rounds


def validate_skill_memory_binding(space_id: int | None, user=None) -> MemorySpace | None:
    if space_id is None:
        return None
    space = MemorySpace.objects.filter(id=space_id).first()
    if space is None:
        raise SkillMemoryConfigError("记忆体不存在")
    if not is_usable_skill_memory_space(space):
        raise SkillMemoryConfigError("智能体只能挂接用户自建的个人记忆体")
    if user is not None and not user_can_use_memory_space(user, space):
        raise SkillMemoryConfigError("无权使用该记忆体")
    return space


def resolve_skill_conversation_memory_space(skill: LLMSkill | None = None) -> MemorySpace | None:
    space = getattr(skill, "memory_space", None) if skill is not None else None
    if is_usable_skill_memory_space(space):
        return space
    return None


def is_empty_skill_memory_summary(text: str) -> bool:
    value = (text or "").strip()
    return (not value) or value.upper() == SKILL_CONVERSATION_SUMMARY_EMPTY


def parse_external_user_id(external_user_id: str) -> tuple[str, str]:
    return split_external_user_id(external_user_id)


def resolve_skill_write_rounds(skill: LLMSkill | None) -> int:
    return normalize_write_rounds(getattr(skill, "memory_write_rounds", None) if skill is not None else None)


def resolve_skill_memory_model_id(skill: LLMSkill, memory_space: MemorySpace | None = None):
    space = memory_space if memory_space is not None else resolve_skill_conversation_memory_space(skill)
    raw = getattr(space, "default_model", None) if space is not None else None
    if raw not in (None, ""):
        try:
            return int(raw)
        except (TypeError, ValueError):
            pass
    return getattr(skill, "llm_model_id", None)


def count_pending_memory_rounds(conversation: SkillConversation) -> int:
    watermark = conversation.memory_written_message_id or 0
    return conversation.messages.filter(role=SkillConversationMessage.ROLE_ASSISTANT, id__gt=watermark).count()


def annotate_pending_memory_rounds(queryset):
    """水位线之后的 assistant 条数。"""
    pending_sub = (
        SkillConversationMessage.objects.filter(
            conversation_id=OuterRef("pk"),
            role=SkillConversationMessage.ROLE_ASSISTANT,
            id__gt=OuterRef("memory_written_message_id"),
        )
        .values("conversation_id")
        .annotate(c=Count("id"))
        .values("c")
    )
    return queryset.annotate(pending_count=Coalesce(Subquery(pending_sub, output_field=IntegerField()), Value(0)))


def pending_rounds_for_conversation(conversation: SkillConversation, pending_count: int | None = None) -> int:
    if not skill_has_conversation_memory(getattr(conversation, "skill", None)):
        return 0
    if pending_count is not None:
        return int(pending_count)
    return count_pending_memory_rounds(conversation)


def load_messages_after_watermark(conversation: SkillConversation):
    watermark = conversation.memory_written_message_id or 0
    return list(conversation.messages.filter(id__gt=watermark).order_by("created_at", "id"))


def snapshot_pending_messages(conversation: SkillConversation) -> list[dict]:
    return [{"id": msg.id, "role": msg.role, "content": msg.content or ""} for msg in load_messages_after_watermark(conversation)]


def _clip_transcript_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    head = max(0, (max_chars * 2) // 3)
    tail = max(0, max_chars - head - 16)
    if tail <= 0:
        return text[:max_chars] + "\n…(已截断)"
    return f"{text[:head]}\n…(中间已截断)…\n{text[-tail:]}"


def _transcript_message_text(role: str, content: str) -> str:
    text = content or ""
    if role == SkillConversationMessage.ROLE_ASSISTANT:
        # 循环依赖：skill_channel_chat_service 顶层导入本模块
        from apps.opspilot.services.skill_channel_chat_service import visible_assistant_text

        text = visible_assistant_text(text)
    return _clip_transcript_text(text, SKILL_MEMORY_MESSAGE_MAX_CHARS)


def format_conversation_transcript(messages) -> str:
    """把待写消息编成摘要用的对话记录：助手取可见正文，超长保留首条与近轮。"""
    blocks = []
    for item in messages:
        role = item.role if hasattr(item, "role") else item.get("role")
        content = item.content if hasattr(item, "content") else item.get("content") or ""
        label = "用户" if role == SkillConversationMessage.ROLE_USER else "助手"
        text = _transcript_message_text(role, content)
        if text.strip():
            blocks.append(f"{label}：{text}")
    joined = "\n\n".join(blocks)
    if len(joined) <= SKILL_MEMORY_TRANSCRIPT_MAX_CHARS:
        return joined
    head = [_clip_transcript_text(blocks[0], SKILL_MEMORY_TRANSCRIPT_MAX_CHARS)]
    total = len(head[0])
    tail = []
    for block in reversed(blocks[1:]):
        extra = len(block) + 2
        if total + extra > SKILL_MEMORY_TRANSCRIPT_MAX_CHARS:
            break
        tail.append(block)
        total += extra
    tail.reverse()
    return "\n\n".join(head + tail).strip()


def append_skill_memory_block(prompt: str, block: str) -> str:
    """把用户记忆块放到 system prompt 末尾，避免 Wiki / 技能包把它挤到中间。"""
    memory_block = (block or "").strip()
    if not memory_block:
        return prompt or ""
    remainder = (prompt or "").replace(memory_block, "", 1).strip()
    return f"{remainder}\n\n{memory_block}" if remainder else memory_block


def build_skill_memory_prompt_block(skill: LLMSkill, external_user_id: str, user_message: str) -> str:
    memory_space = resolve_skill_conversation_memory_space(skill)
    if memory_space is None:
        return ""
    query = user_message if isinstance(user_message, str) else ""
    try:
        engine = MemoryEngineRegistry.get_engine(memory_space.id)
        result = engine.read(
            entity=MemoryEntity(user_id=external_user_id or ""),
            query=query,
            top_k=SKILL_MEMORY_READ_TOP_K,
        )
    except Exception as exc:
        logger.exception(_SKILL_MEMORY_READ_FAILED, skill.id, memory_space.id, type(exc).__name__)
        return ""
    context = (getattr(result, "context", None) or "").strip()
    if not context:
        logger.debug(_SKILL_MEMORY_EMPTY_LOG, skill.id, memory_space.id)
        return ""
    truncated = truncate_memory_context(context)
    logger.debug(_SKILL_MEMORY_INJECTED_LOG, skill.id, memory_space.id, len(truncated))
    return f"## 用户记忆\n{_SKILL_MEMORY_PROMPT_GUIDE}\n\n{truncated}\n\n{_SKILL_MEMORY_PROMPT_FOOTER}"


def inject_skill_memory_prompt(params: dict, skill: LLMSkill, external_user_id: str, user_message: str) -> dict:
    block = build_skill_memory_prompt_block(skill, external_user_id, user_message)
    if not block:
        return params
    params["skill_memory_block"] = block
    params["skill_prompt"] = append_skill_memory_block(params.get("skill_prompt") or "", block)
    return params


def maybe_schedule_skill_memory_write(conversation: SkillConversation) -> bool:
    skill = getattr(conversation, "skill", None)
    if skill is None or getattr(skill, "memory_space", None) is None:
        conversation = SkillConversation.objects.select_related("skill", "skill__memory_space").filter(id=conversation.id).first()
        if conversation is None:
            return False
        skill = conversation.skill
    if not skill_has_conversation_memory(skill):
        return False
    pending = count_pending_memory_rounds(conversation)
    if pending < resolve_skill_write_rounds(skill):
        return False
    from apps.opspilot.tasks.memory import write_skill_conversation_memory

    write_skill_conversation_memory.delay(conversation.id)
    logger.debug("event=skill_memory_write_scheduled conversation_id=%s pending_rounds=%s", conversation.id, pending)
    return True


def iter_idle_skill_conversation_ids(*, idle_minutes: int = SKILL_MEMORY_IDLE_MINUTES) -> list[int]:
    cutoff = timezone.now() - timedelta(minutes=idle_minutes)
    qs = (
        SkillConversation.objects.filter(
            is_active=True,
            skill__memory_space_id__isnull=False,
            skill__memory_space__scope=MemorySpace.SCOPE_PERSONAL,
        )
        .annotate(
            last_msg_at=Subquery(
                SkillConversationMessage.objects.filter(conversation_id=OuterRef("pk")).order_by("-created_at", "-id").values("created_at")[:1]
            )
        )
        .filter(last_msg_at__lte=cutoff)
        .annotate(
            pending_count=Coalesce(
                Subquery(
                    SkillConversationMessage.objects.filter(
                        conversation_id=OuterRef("pk"),
                        role=SkillConversationMessage.ROLE_ASSISTANT,
                        id__gt=OuterRef("memory_written_message_id"),
                    )
                    .values("conversation_id")
                    .annotate(c=Count("id"))
                    .values("c"),
                    output_field=IntegerField(),
                ),
                Value(0),
            )
        )
        .filter(pending_count__gt=0)
        .order_by("id")
        .values_list("id", flat=True)
    )
    return list(qs)
