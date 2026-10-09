"""用户悬浮 WebChat 面板偏好。"""

from django.db import models

# 与 webchat PLATFORM_DOCK_CHAT_WIDTH / MIN / MAX 对齐。未保存过时接口直接返回默认值，不写行。
DEFAULT_WEBCHAT_DOCK_WIDTH = 380
MIN_WEBCHAT_DOCK_WIDTH = 320
# 只挡异常值。正常宽度由前端按视口限制，保存时不再卡在 720。
MAX_WEBCHAT_DOCK_WIDTH = 3840


class UserWebchatPreference(models.Model):
    """按系统用户 UUID 保存悬浮对话栏宽度。"""

    user_id = models.CharField(max_length=36, unique=True, db_index=True, verbose_name="用户UUID")
    dock_width = models.PositiveIntegerField(default=DEFAULT_WEBCHAT_DOCK_WIDTH, verbose_name="悬浮对话宽度")

    class Meta:
        db_table = "opspilot_user_webchat_preference"
        verbose_name = "用户悬浮对话偏好"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"{self.user_id}:{self.dock_width}"

    @classmethod
    def clamp_width(cls, value) -> int:
        try:
            width = int(value)
        except (TypeError, ValueError):
            return DEFAULT_WEBCHAT_DOCK_WIDTH
        return max(MIN_WEBCHAT_DOCK_WIDTH, min(MAX_WEBCHAT_DOCK_WIDTH, width))

    @classmethod
    def width_for_user_id(cls, user_id: str | None) -> int:
        token = (user_id or "").strip()
        if not token:
            return DEFAULT_WEBCHAT_DOCK_WIDTH
        width = cls.objects.filter(user_id=token).values_list("dock_width", flat=True).first()
        if not isinstance(width, int) or width <= 0:
            return DEFAULT_WEBCHAT_DOCK_WIDTH
        return cls.clamp_width(width)

    @classmethod
    def save_width_for_user_id(cls, user_id: str | None, value) -> int | None:
        token = (user_id or "").strip()
        if not token:
            return None
        width = cls.clamp_width(value)
        cls.objects.update_or_create(user_id=token, defaults={"dock_width": width})
        return width
