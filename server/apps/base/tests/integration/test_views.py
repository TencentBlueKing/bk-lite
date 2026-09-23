import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.base.models import UserAPISecret
from apps.base.tests.factories import UserAPISecretFactory
from apps.system_mgmt.models import OperationLog

BASE_URL = "/api/v1/base/user_api_secret/"


@pytest.mark.integration
@pytest.mark.django_db
class TestUserAPISecretList:
    def test_authenticated_user_sees_own_secrets(self, api_client_with_team, user_with_permissions, user_api_secret):
        response = api_client_with_team.get(BASE_URL)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["username"] == user_with_permissions.username
        assert response.data[0]["api_secret_preview"] == "********"
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
        response = api_client_with_team.post(BASE_URL, data={"name": "first", "scope": {"mode": "all"}}, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert "api_secret" in response.data
        assert "api_secret_preview" not in response.data
        assert response.data["username"] == user_with_permissions.username
        assert response.data["team"] == 1
        stored = UserAPISecret.objects.get(username=user_with_permissions.username, domain=user_with_permissions.domain, team=1)
        assert stored.api_secret != response.data["api_secret"]
        assert stored.api_secret == UserAPISecret.hash_api_secret(response.data["api_secret"])

    def test_second_create_allowed_for_same_team(self, api_client_with_team, user_with_permissions, user_api_secret):
        response = api_client_with_team.post(BASE_URL, data={"name": "second", "scope": {"mode": "all"}}, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert "api_secret" in response.data
        assert (
            UserAPISecret.objects.filter(
                username=user_with_permissions.username,
                domain=user_with_permissions.domain,
                team=1,
            ).count()
            == 2
        )

    def test_create_accepts_name_expiry_and_scope(self, api_client_with_team, user_with_permissions):
        from datetime import timedelta

        from django.utils import timezone

        expires = timezone.now() + timedelta(days=30)
        response = api_client_with_team.post(
            BASE_URL,
            data={
                "name": "job-script",
                "expires_at": expires.isoformat(),
                "scope": {"mode": "all"},
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert response.data["name"] == "job-script"
        assert response.data["scope"] == {"mode": "all"}
        stored = UserAPISecret.objects.get(pk=response.data["id"])
        assert stored.name == "job-script"
        assert stored.scope == {"mode": "all"}
        assert stored.expires_at is not None


@pytest.mark.integration
@pytest.mark.django_db
class TestUserAPISecretRetrieve:
    def test_retrieve_returns_preview_only(self, api_client_with_team, user_api_secret):
        url = f"{BASE_URL}{user_api_secret.pk}/"
        response = api_client_with_team.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == user_api_secret.pk
        assert response.data["api_secret_preview"] == "********"
        assert "api_secret" not in response.data
        assert "name" in response.data
        assert "expires_at" in response.data
        assert "scope" in response.data

    def test_invalid_current_team_cookie(self, user_with_permissions):
        client = APIClient()
        client.force_authenticate(user=user_with_permissions)
        client.cookies["current_team"] = "abc"
        response = client.post(BASE_URL, data={"name": "first"})
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

    def test_patch_updates_metadata_without_rotating_secret(self, api_client_with_team, user_api_secret):
        original_hash = user_api_secret.api_secret
        url = f"{BASE_URL}{user_api_secret.pk}/"
        response = api_client_with_team.patch(
            url,
            data={"name": "debug", "scope": {"mode": "allowlist", "endpoints": ["GET cmdb/classifications"]}},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data["name"] == "debug"
        assert response.data["scope"] == {"mode": "allowlist", "endpoints": ["GET cmdb/classifications"]}
        assert "api_secret" not in response.data
        user_api_secret.refresh_from_db()
        assert user_api_secret.api_secret == original_hash
        assert user_api_secret.name == "debug"

    def test_create_rejects_invalid_scope(self, api_client_with_team):
        response = api_client_with_team.post(
            BASE_URL,
            data={"name": "bad", "scope": ["asset_info-View"]},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "scope" in response.data

    def test_create_requires_scope(self, api_client_with_team):
        response = api_client_with_team.post(
            BASE_URL,
            data={"name": "missing-scope"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "scope" in response.data


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
        assert not OperationLog.objects.filter(target_type="user_api_secret").exists()


def _assert_secret_log_has_no_secret(log, secret=None):
    blob = str({"summary": log.summary, "detail": log.detail, "target_id": log.target_id})
    assert "sha256$" not in blob
    if secret:
        assert secret not in blob


@pytest.mark.integration
@pytest.mark.django_db
class TestUserAPISecretOperationLog:
    def test_create_writes_operation_log_without_secret(self, api_client_with_team, user_with_permissions):
        response = api_client_with_team.post(BASE_URL, data={"name": "job-script", "scope": {"mode": "all"}}, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        log = OperationLog.objects.get(target_type="user_api_secret", action_type="create")
        assert log.username == user_with_permissions.username
        assert log.app == "system-manager"
        assert log.summary == "创建个人令牌: job-script"
        assert log.target_id == str(response.data["id"])
        assert log.detail == {"kind": "personal", "name": "job-script", "team": 1}
        _assert_secret_log_has_no_secret(log, response.data["api_secret"])

    def test_create_requires_name(self, api_client_with_team):
        response = api_client_with_team.post(BASE_URL, data={}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "name" in response.data
        assert not OperationLog.objects.filter(target_type="user_api_secret").exists()

    def test_create_rejects_duplicate_name_in_same_team(self, api_client_with_team, user_api_secret):
        response = api_client_with_team.post(BASE_URL, data={"name": user_api_secret.name, "scope": {"mode": "all"}}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "name" in response.data

    def test_patch_writes_update_operation_log(self, api_client_with_team, user_api_secret):
        url = f"{BASE_URL}{user_api_secret.pk}/"
        response = api_client_with_team.patch(url, data={"name": "debug"}, format="json")
        assert response.status_code == status.HTTP_200_OK
        log = OperationLog.objects.get(target_type="user_api_secret", action_type="update")
        assert log.summary == "更新个人令牌: debug"
        assert log.detail == {"kind": "personal", "name": "debug", "team": 1}
        _assert_secret_log_has_no_secret(log, user_api_secret.api_secret)

    def test_delete_writes_operation_log(self, api_client_with_team, user_api_secret):
        url = f"{BASE_URL}{user_api_secret.pk}/"
        response = api_client_with_team.delete(url)
        assert response.status_code in (status.HTTP_200_OK, status.HTTP_204_NO_CONTENT)
        log = OperationLog.objects.get(target_type="user_api_secret", action_type="delete")
        assert log.summary == f"删除个人令牌: {user_api_secret.name}"
        assert log.target_id == str(user_api_secret.pk)
        assert log.detail == {"kind": "personal", "name": user_api_secret.name, "team": 1}

    def test_invalid_create_does_not_write_operation_log(self, api_client_with_team):
        response = api_client_with_team.post(
            BASE_URL,
            data={"name": "bad", "scope": ["asset_info-View"]},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not OperationLog.objects.filter(target_type="user_api_secret").exists()
