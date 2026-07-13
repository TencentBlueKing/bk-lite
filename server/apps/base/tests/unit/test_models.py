import pytest
from django.db import IntegrityError

from apps.base.models import User, UserAPISecret
from apps.base.tests.factories import UserAPISecretFactory, UserFactory


@pytest.mark.unit
class TestUserAPISecretGenerateApiSecret:
    def test_returns_64_char_hex_string(self):
        secret = UserAPISecret.generate_api_secret()
        assert len(secret) == 64
        assert all(c in "0123456789abcdef" for c in secret)

    def test_each_call_returns_different_value(self):
        secret1 = UserAPISecret.generate_api_secret()
        secret2 = UserAPISecret.generate_api_secret()
        assert secret1 != secret2

    def test_hash_api_secret_is_not_reusable_plaintext(self):
        secret = "a" * 64
        hashed = UserAPISecret.hash_api_secret(secret)

        assert hashed != secret
        assert hashed.startswith(UserAPISecret.HASH_PREFIX)
        assert UserAPISecret.hash_api_secret(hashed) == hashed


@pytest.mark.unit
@pytest.mark.django_db
class TestUserModelConstraints:
    def test_unique_together_username_domain(self):
        UserFactory(username="alice", domain="test.com")
        with pytest.raises(IntegrityError):
            UserFactory(username="alice", domain="test.com")

    def test_same_username_different_domain_allowed(self):
        UserFactory(username="alice", domain="test.com")
        user2 = UserFactory(username="alice", domain="other.com")
        assert user2.pk is not None

    def test_default_field_values(self):
        user = UserFactory(username="bob")
        assert user.domain == "domain.com"
        assert user.locale == "en"
        assert user.group_list == []
        assert user.roles == []


@pytest.mark.unit
@pytest.mark.django_db
class TestUserAPISecretModelConstraints:
    def test_unique_together_username_domain_team(self):
        UserAPISecretFactory(username="alice", domain="test.com", team=1)
        with pytest.raises(IntegrityError):
            UserAPISecretFactory(username="alice", domain="test.com", team=1)

    def test_same_username_different_team_allowed(self):
        UserAPISecretFactory(username="alice", domain="test.com", team=1)
        secret2 = UserAPISecretFactory(username="alice", domain="test.com", team=2)
        assert secret2.pk is not None

    def test_default_team_value(self):
        secret = UserAPISecretFactory(username="charlie")
        assert secret.team == 0
        assert secret.domain == "domain.com"

    def test_find_by_api_secret_matches_hashed_secret(self):
        raw_secret = UserAPISecret.generate_api_secret()
        stored = UserAPISecretFactory(api_secret=UserAPISecret.hash_api_secret(raw_secret))

        assert UserAPISecret.find_by_api_secret(raw_secret) == stored
        assert UserAPISecret.find_by_api_secret(stored.api_secret) is None

    def test_find_by_api_secret_keeps_legacy_plaintext_fallback(self):
        raw_secret = UserAPISecret.generate_api_secret()
        stored = UserAPISecretFactory(api_secret=raw_secret)

        assert UserAPISecret.find_by_api_secret(raw_secret) == stored
