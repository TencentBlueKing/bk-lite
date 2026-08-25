from rest_framework.decorators import action
from rest_framework.viewsets import ViewSet

from apps.core.user_habit import InvalidHabitKey, InvalidHabitValue, validate_habit_key, validate_habit_value
from apps.core.utils.web_utils import WebUtils


class UserHabitViewSet(ViewSet):
    """按 key 读写当前用户在本应用下的习惯。子类必须设置 habit_model。"""

    habit_model = None

    def _handle(self, request, habit_key: str):
        try:
            key = validate_habit_key(habit_key)
        except InvalidHabitKey as exc:
            return WebUtils.response_error(error_message=str(exc))

        if request.method == "GET":
            habit = self.habit_model.objects.filter(user=request.user, habit_key=key).first()
            return WebUtils.response_success(None if habit is None else habit.habit_value)

        try:
            value = validate_habit_value(request.data)
        except InvalidHabitValue as exc:
            return WebUtils.response_error(error_message=str(exc))

        self.habit_model.objects.update_or_create(
            user=request.user,
            habit_key=key,
            defaults={"habit_value": value},
        )
        return WebUtils.response_success(value)

    @action(methods=["get", "put"], detail=False, url_path=r"(?P<habit_key>[\w.-]+)")
    def by_key(self, request, habit_key=None):
        return self._handle(request, habit_key)
