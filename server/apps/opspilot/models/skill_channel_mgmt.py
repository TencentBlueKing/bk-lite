"""智能体渠道发布与独立会话模型。"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models.time_info import TimeInfo
from apps.opspilot.enum import SkillChannelChoices


class SkillChannel(TimeInfo):
    """智能体渠道发布绑定。

    - usage_team 为组副本：创建/更新时从 Skill.usage_team 拷入；改 Skill.usage_team 时全量同步。
    - 同 channel_type 允许多条，但同一智能体下 (channel_type, name) 唯一；对外回调与对话 URL 使用本表主键消歧。
    """

    skill = models.ForeignKey(
        "LLMSkill",
        on_delete=models.CASCADE,
        related_name="channels",
        verbose_name="智能体",
    )
    name = models.CharField(max_length=100, verbose_name=_("name"), blank=True, default="")
    channel_type = models.CharField(
        max_length=64,
        choices=SkillChannelChoices.choices,
        verbose_name=_("channel type"),
        db_index=True,
    )
    channel_config = models.JSONField(default=dict, blank=True, verbose_name=_("channel config"))
    enabled = models.BooleanField(default=False, verbose_name=_("enabled"), db_index=True)
    usage_team = models.JSONField(default=list, verbose_name="使用组织")

    class Meta:
        verbose_name = "智能体渠道绑定"
        verbose_name_plural = verbose_name
        db_table = "model_provider_mgmt_skillchannel"
        indexes = [
            models.Index(fields=["skill", "channel_type", "enabled"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["skill", "channel_type", "name"],
                name="uniq_skillchannel_skill_type_name",
            ),
        ]

    def __str__(self):
        return f"{self.skill_id}:{self.channel_type}:{self.id}"


class SkillConversation(TimeInfo):
    """智能体渠道会话元数据（独立于 Bot 会话表）。"""

    session_id = models.CharField(max_length=100, unique=True, verbose_name="会话ID", db_index=True)
    skill = models.ForeignKey(
        "LLMSkill",
        on_delete=models.CASCADE,
        related_name="conversations",
        verbose_name="智能体",
    )
    channel = models.ForeignKey(
        SkillChannel,
        on_delete=models.CASCADE,
        related_name="conversations",
        verbose_name="渠道绑定",
    )
    external_user_id = models.CharField(max_length=255, blank=True, default="", verbose_name="外部用户标识", db_index=True)
    title = models.CharField(max_length=255, blank=True, default="", verbose_name="会话标题")
    is_active = models.BooleanField(default=True, verbose_name="是否活跃")

    class Meta:
        verbose_name = "智能体会话"
        verbose_name_plural = verbose_name
        db_table = "model_provider_mgmt_skillconversation"
        indexes = [
            models.Index(fields=["skill", "-created_at"]),
            models.Index(fields=["channel", "external_user_id", "-created_at"]),
        ]

    def __str__(self):
        return self.session_id


class SkillConversationMessage(models.Model):
    """智能体会话消息。"""

    ROLE_USER = "user"
    ROLE_ASSISTANT = "assistant"
    ROLE_CHOICES = [
        (ROLE_USER, "用户"),
        (ROLE_ASSISTANT, "助手"),
    ]

    conversation = models.ForeignKey(
        SkillConversation,
        on_delete=models.CASCADE,
        related_name="messages",
        verbose_name="会话",
    )
    role = models.CharField(max_length=32, choices=ROLE_CHOICES, verbose_name="角色")
    content = models.TextField(verbose_name="内容")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间", db_index=True)

    class Meta:
        verbose_name = "智能体会话消息"
        verbose_name_plural = verbose_name
        db_table = "model_provider_mgmt_skillconversationmessage"
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["conversation", "created_at"]),
        ]
