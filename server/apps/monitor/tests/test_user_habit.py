import pytest
from rest_framework.test import APIClient

from apps.base.models import User
from apps.core.user_habit import ALERT_CHART_HABIT_KEY
from apps.monitor.models.user_habit import UserHabit


pytestmark = pytest.mark.django_db

URL = f"/api/v1/monitor/api/user_habits/{ALERT_CHART_HABIT_KEY}/"


def test_missing_habit_returns_null(api_client):
    response = api_client.get(URL)

    assert response.status_code == 200
    assert response.json()["data"] is None


def test_user_can_save_and_reload_habit(api_client, authenticated_user):
    saved = api_client.put(URL, {"expanded": False}, format="json")
    loaded = api_client.get(URL)

    assert saved.status_code == 200
    assert saved.json()["data"] == {"expanded": False}
    assert loaded.json()["data"] == {"expanded": False}
    habit = UserHabit.objects.get(user=authenticated_user, habit_key=ALERT_CHART_HABIT_KEY)
    assert habit.habit_value == {"expanded": False}


def test_habit_rejects_non_object_value(api_client):
    response = api_client.put(URL, ["expanded"], format="json")

    assert response.status_code == 400


def test_habits_are_isolated_between_users(api_client):
    api_client.put(URL, {"expanded": False}, format="json")
    other_user = User.objects.create_user(
        username="habit-other",
        password="testpass123",
        domain="domain.com",
    )
    other_client = APIClient()
    other_client.force_authenticate(user=other_user)

    response = other_client.get(URL)

    assert response.status_code == 200
    assert response.json()["data"] is None
