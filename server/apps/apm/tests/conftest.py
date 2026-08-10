import pytest
from rest_framework.test import APIClient

from apps.base.tests.factories import UserFactory


@pytest.fixture
def apm_user():
    user = UserFactory(
        username="apm-user",
        domain="domain.com",
        group_list=[
            {"id": 10, "name": "Team 10"},
            {"id": 20, "name": "Team 20"},
            {"id": 30, "name": "Team 30"},
        ],
        roles=[],
    )
    user.permission = {
        "apm": {
            "home-View",
            "integration_add-View",
            "integration_add-Operate",
            "applications-View",
            "applications-Operate",
            "integration_instances-View",
            "integration_instances-Operate",
            "services-View",
            "services-Operate",
            "traces-View",
            "events-View",
            "policies-View",
            "policies-Operate",
        }
    }
    return user


@pytest.fixture
def apm_api_client(apm_user):
    client = APIClient()
    client.force_authenticate(user=apm_user)
    client.cookies["current_team"] = "10"
    return client


@pytest.fixture
def apm_user_without_permissions():
    user = UserFactory(
        username="apm-no-permission",
        domain="domain.com",
        group_list=[{"id": 10, "name": "Team 10"}],
        roles=[],
    )
    user.permission = {"apm": set()}
    return user
