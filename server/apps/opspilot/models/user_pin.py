from django.db import models


class UserPin(models.Model):
    """用户置顶记录模型

    存储用户对 Bot 或 LLMSkill 的置顶状态。
    每个用户有独立的置顶列表，互不影响。
    """

    CONTENT_TYPE_BOT = "bot"
    CONTENT_TYPE_SKILL = "skill"
    CONTENT_TYPE_CHOICES = [
        (CONTENT_TYPE_BOT, "工作台"),
        (CONTENT_TYPE_SKILL, "技能"),
    ]

    username = models.CharField(max_length=150, verbose_name="用户名", db_index=True)
    domain = models.CharField(max_length=255, verbose_name="域", db_index=True)
    content_type = models.CharField(
        max_length=20,
        choices=CONTENT_TYPE_CHOICES,
        verbose_name="内容类型",
        db_index=True,
    )
    object_id = models.IntegerField(verbose_name="对象ID", db_index=True)

    class Meta:
        db_table = "opspilot_user_pin"
        verbose_name = "用户置顶"
        verbose_name_plural = "用户置顶"
        unique_together = [["username", "domain", "content_type", "object_id"]]
        indexes = [
            models.Index(fields=["username", "domain", "content_type"]),
        ]

    def __str__(self):
        return f"{self.username}@{self.domain} pinned {self.content_type}:{self.object_id}"
