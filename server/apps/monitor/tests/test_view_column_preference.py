import pytest
from rest_framework.test import APIClient

from apps.base.models import User
from apps.monitor.models.monitor_object import MonitorObject


pytestmark = pytest.mark.django_db


@pytest.fixture
def monitor_object():
    return MonitorObject.objects.create(name="PreferenceHost", level="base")


def test_user_can_save_and_reload_columns_for_monitor_object(api_client, monitor_object):
    url = f"/api/v1/monitor/api/monitor_object/{monitor_object.id}/view_column_preference/"
    field_keys = ["instance_name", "time", "metric:cpu"]

    saved = api_client.put(url, {"field_keys": field_keys}, format="json")
    loaded = api_client.get(url)

    assert saved.status_code == 200
    assert saved.json()["data"] == {"field_keys": field_keys}
    assert loaded.status_code == 200
    assert loaded.json()["data"] == {"field_keys": field_keys}


@pytest.mark.parametrize(
    "field_keys",
    [None, [], ["instance_name", "instance_name"], ["instance_name", 1]],
)
def test_invalid_column_preferences_are_rejected(api_client, monitor_object, field_keys):
    url = f"/api/v1/monitor/api/monitor_object/{monitor_object.id}/view_column_preference/"

    response = api_client.put(url, {"field_keys": field_keys}, format="json")

    assert response.status_code == 400


def test_column_preferences_are_isolated_between_users(api_client, monitor_object):
    url = f"/api/v1/monitor/api/monitor_object/{monitor_object.id}/view_column_preference/"
    api_client.put(url, {"field_keys": ["instance_name"]}, format="json")
    other_user = User.objects.create_user(
        username="other-user",
        password="testpass123",
        domain="domain.com",
    )
    other_client = APIClient()
    other_client.force_authenticate(user=other_user)

    response = other_client.get(url)

    assert response.status_code == 200
    assert response.json()["data"] is None
