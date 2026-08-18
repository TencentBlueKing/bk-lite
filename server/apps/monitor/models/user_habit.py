from apps.core.models.user_habit import UserHabitBase
from django.db import models


class UserHabit(UserHabitBase):
    class Meta:
        verbose_name = "用户习惯"
        verbose_name_plural = "用户习惯"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "habit_key"],
                name="uniq_monitor_user_habit_key",
            )
        ]
