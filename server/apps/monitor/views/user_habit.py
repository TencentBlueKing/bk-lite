from apps.core.views.user_habit import UserHabitViewSet as BaseUserHabitViewSet
from apps.monitor.models.user_habit import UserHabit


class UserHabitViewSet(BaseUserHabitViewSet):
    habit_model = UserHabit
