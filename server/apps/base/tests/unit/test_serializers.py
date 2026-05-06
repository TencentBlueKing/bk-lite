import pytest
from django.test import RequestFactory

from apps.base.models import UserAPISecret
from apps.base.tests.factories import UserAPISecretFactory, UserFactory
from apps.base.user_api_secret_mgmt.serializers import UserAPISecretCreateSerializer, UserAPISecretSerializer


@pytest.mark.unit
@pytest.mark.django_db
class TestUserAPISecretSerializer:
    def _make_request(self, user):
        factory = RequestFactory()
        request = factory.get("/fake-url")
        request.user = user
        return request

    def test_team_name_resolved_from_group_list(self):
        user = UserFactory(
            username="alice",
            group_list=[{"id": 1, "name": "Team Alpha"}, {"id": 2, "name": "Team Beta"}],
        )
        secret = UserAPISecretFactory(username="alice", domain=user.domain, team=1)
        request = self._make_request(user)
        serializer = UserAPISecretSerializer(secret, context={"request": request})
        assert serializer.data["team_name"] == "Team Alpha"

    def test_team_name_fallback_when_no_match(self):
        user = UserFactory(
            username="bob",
            group_list=[{"id": 1, "name": "Team Alpha"}],
        )
        secret = UserAPISecretFactory(username="bob", domain=user.domain, team=999)
        request = self._make_request(user)
        serializer = UserAPISecretSerializer(secret, context={"request": request})
        assert serializer.data["team_name"] == 999

    def test_team_name_empty_when_team_is_none(self):
        user = UserFactory(
            username="charlie",
            group_list=[{"id": 1, "name": "Team Alpha"}],
        )
        secret = UserAPISecretFactory(username="charlie", domain=user.domain, team=0)
        request = self._make_request(user)
        serializer = UserAPISecretSerializer(secret, context={"request": request})
        # team=0 is falsy, so team_name should be ""
        assert serializer.data["team_name"] == ""

    def test_serializer_includes_all_fields(self):
        user = UserFactory(
            username="dave",
            group_list=[{"id": 1, "name": "Team Alpha"}],
        )
        secret = UserAPISecretFactory(username="dave", domain=user.domain, team=1)
        request = self._make_request(user)
        serializer = UserAPISecretSerializer(secret, context={"request": request})
        data = serializer.data
        assert "id" in data
        assert "username" in data
        assert "api_secret_preview" in data
        assert data["api_secret_preview"] == f"{secret.api_secret[:4]}********"
        assert "api_secret" not in data
        assert "team" in data
        assert "team_name" in data

    def test_create_serializer_includes_full_api_secret(self):
        user = UserFactory(
            username="erin",
            group_list=[{"id": 1, "name": "Team Alpha"}],
        )
        secret = UserAPISecretFactory(username="erin", domain=user.domain, team=1)
        request = self._make_request(user)
        serializer = UserAPISecretCreateSerializer(secret, context={"request": request})
        data = serializer.data

        assert data["api_secret"] == secret.api_secret
        assert "api_secret_preview" not in data
