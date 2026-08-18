from apps.core.views.user_habit import UserHabitViewSet as BaseUserHabitViewSet
from apps.log.models.user_habit import UserHabit


class UserHabitViewSet(BaseUserHabitViewSet):
    habit_model = UserHabit
