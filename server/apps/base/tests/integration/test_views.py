import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.base.models import UserAPISecret
from apps.base.tests.factories import UserAPISecretFactory, UserFactory


BASE_URL = "/api/v1/base/user_api_secret/"


@pytest.mark.integration
@pytest.mark.django_db
class TestUserAPISecretList:
    def test_authenticated_user_sees_own_secrets(self, api_client_with_team, user_with_permissions, user_api_secret):
        response = api_client_with_team.get(BASE_URL)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["username"] == user_with_permissions.username
        assert response.data[0]["api_secret_preview"] == f"{user_api_secret.api_secret[:4]}********"
        assert "api_secret" not in response.data[0]

    def test_user_cannot_see_other_users_secrets(self, api_client_with_team, user_with_permissions):
        # Create secret for a different user
        UserAPISecretFactory(username="otheruser", domain="domain.com", team=1)
        # Create secret for our user
        UserAPISecretFactory(
            username=user_with_permissions.username,
            domain=user_with_permissions.domain,
            team=1,
        )
        response = api_client_with_team.get(BASE_URL)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["username"] == user_with_permissions.username

    def test_unauthenticated_user_rejected(self):
        client = APIClient()
        response = client.get(BASE_URL)
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

    def test_filters_by_current_team_cookie(self, user_with_permissions):
        UserAPISecretFactory(
            username=user_with_permissions.username,
            domain=user_with_permissions.domain,
            team=1,
        )
        UserAPISecretFactory(
            username=user_with_permissions.username,
            domain=user_with_permissions.domain,
            team=2,
        )
        client = APIClient()
        client.force_authenticate(user=user_with_permissions)

        # Request with team=1
        client.cookies["current_team"] = "1"
        response = client.get(BASE_URL)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["team"] == 1

        # Request with team=2
        client.cookies["current_team"] = "2"
        response = client.get(BASE_URL)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["team"] == 2


@pytest.mark.integration
@pytest.mark.django_db
class TestUserAPISecretCreate:
    def test_create_success(self, api_client_with_team, user_with_permissions):
        response = api_client_with_team.post(BASE_URL, data={})
        assert response.status_code == status.HTTP_201_CREATED
        assert "api_secret" in response.data
        assert "api_secret_preview" not in response.data
        assert response.data["username"] == user_with_permissions.username
        assert response.data["team"] == 1


@pytest.mark.integration
@pytest.mark.django_db
class TestUserAPISecretRetrieve:
    def test_retrieve_returns_preview_only(self, api_client_with_team, user_api_secret):
        url = f"{BASE_URL}{user_api_secret.pk}/"
        response = api_client_with_team.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == user_api_secret.pk
        assert response.data["api_secret_preview"] == f"{user_api_secret.api_secret[:4]}********"
        assert "api_secret" not in response.data

    def test_duplicate_create_rejected(self, api_client_with_team, user_with_permissions, user_api_secret):
        response = api_client_with_team.post(BASE_URL, data={})
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["result"] is False

    def test_invalid_current_team_cookie(self, user_with_permissions):
        client = APIClient()
        client.force_authenticate(user=user_with_permissions)
        client.cookies["current_team"] = "abc"
        response = client.post(BASE_URL, data={})
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.integration
@pytest.mark.django_db
class TestUserAPISecretDelete:
    def test_delete_success(self, api_client_with_team, user_api_secret):
        url = f"{BASE_URL}{user_api_secret.pk}/"
        response = api_client_with_team.delete(url)
        assert response.status_code in (status.HTTP_200_OK, status.HTTP_204_NO_CONTENT)
        assert not UserAPISecret.objects.filter(pk=user_api_secret.pk).exists()


@pytest.mark.integration
@pytest.mark.django_db
class TestUserAPISecretUpdate:
    def test_put_rejected(self, api_client_with_team, user_api_secret):
        url = f"{BASE_URL}{user_api_secret.pk}/"
        response = api_client_with_team.put(url, data={"username": "new"})
        data = response.json()
        assert data["result"] is False


@pytest.mark.integration
@pytest.mark.django_db
class TestGenerateApiSecretAction:
    def test_generate_returns_valid_secret(self, api_client_with_team):
        url = f"{BASE_URL}generate_api_secret/"
        response = api_client_with_team.post(url)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["result"] is True
        assert len(data["data"]["api_secret"]) == 64
