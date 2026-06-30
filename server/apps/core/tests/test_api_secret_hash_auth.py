import pytest

from apps.base.models import User, UserAPISecret
from apps.core.backends import APISecretAuthBackend


@pytest.mark.django_db
def test_api_secret_authenticates_with_raw_token_against_hashed_storage(monkeypatch):
    raw_secret = UserAPISecret.generate_api_secret()
    user = User.objects.create(username="alice", domain="domain.com")
    UserAPISecret.objects.create(
        username=user.username,
        domain=user.domain,
        team=7,
        api_secret=UserAPISecret.hash_api_secret(raw_secret),
    )
    monkeypatch.setattr(APISecretAuthBackend, "_populate_user_permissions", lambda self, user, team: None)

    authenticated = APISecretAuthBackend().authenticate(api_token=raw_secret)

    assert authenticated == user
    assert authenticated.group_list == [7]


@pytest.mark.django_db
def test_api_secret_auth_rejects_leaked_stored_digest(monkeypatch):
    raw_secret = UserAPISecret.generate_api_secret()
    stored_digest = UserAPISecret.hash_api_secret(raw_secret)
    user = User.objects.create(username="bob", domain="domain.com")
    UserAPISecret.objects.create(
        username=user.username,
        domain=user.domain,
        team=3,
        api_secret=stored_digest,
    )
    monkeypatch.setattr(APISecretAuthBackend, "_populate_user_permissions", lambda self, user, team: None)

    assert APISecretAuthBackend().authenticate(api_token=stored_digest) is None
