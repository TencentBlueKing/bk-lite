from django.conf import settings
from django.db import models

from apps.core.models.time_info import TimeInfo


class UserHabitBase(TimeInfo):
    """各应用用户习惯表的同构抽象。"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="%(app_label)s_user_habits",
        verbose_name="用户",
    )
    habit_key = models.CharField(max_length=100, verbose_name="习惯键")
    habit_value = models.JSONField(default=dict, verbose_name="习惯值")

    class Meta:
        abstract = True
