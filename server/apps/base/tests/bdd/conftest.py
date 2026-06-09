import pytest
from rest_framework.test import APIClient

from apps.base.tests.factories import UserFactory


@pytest.fixture
def bdd_user(db):
    """Create a user for BDD scenarios."""
    return UserFactory(
        username="bdduser",
        group_list=[{"id": 1, "name": "Team 1"}, {"id": 2, "name": "Team 2"}],
        roles=["admin"],
        is_superuser=True,
    )


@pytest.fixture
def bdd_client(bdd_user):
    """Return an authenticated APIClient for BDD scenarios."""
    client = APIClient()
    client.force_authenticate(user=bdd_user)
    return client
