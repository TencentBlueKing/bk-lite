import json
from types import SimpleNamespace

import pytest
from django.test import RequestFactory

from apps.console_mgmt import views
from apps.console_mgmt.views import (
    _email_change_verified_cache_key,
    _email_code_cache_key,
    update_user_base_info,
    validate_email_code,
)
from apps.system_mgmt.models import User


pytestmark = [pytest.mark.django_db]


def _request(path, user, body):
    request = RequestFactory().post(path, data=json.dumps(body), content_type="application/json")
    request.user = SimpleNamespace(username=user.username, domain=user.domain, locale=user.locale)
    return request


def _payload(response):
    return json.loads(response.content)


@pytest.fixture
def memory_cache(monkeypatch):
    store = {}

    class MemoryCache:
        def get(self, key):
            return store.get(key)

        def set(self, key, value, timeout=None):
            store[key] = value
            return True

        def delete(self, key):
            store.pop(key, None)
            return True

    fake_cache = MemoryCache()
    monkeypatch.setattr(views, "cache", fake_cache)
    return fake_cache


def test_update_user_base_info_rejects_email_change_without_verified_code(memory_cache):
    user = User.objects.create(
        username="email_auth_alice",
        domain="domain.com",
        display_name="Alice",
        email="alice-old@example.com",
        password="!",
        locale="en",
    )

    response = update_user_base_info(
        _request(
            "/api/v1/console_mgmt/update_user_base_info/",
            user,
            {"display_name": "Alice", "email": "alice-new@example.com"},
        )
    )
    user.refresh_from_db()

    assert response.status_code == 403
    assert _payload(response)["result"] is False
    assert user.email == "alice-old@example.com"


def test_update_user_base_info_allows_profile_update_without_email_change(memory_cache):
    user = User.objects.create(
        username="email_auth_profile",
        domain="domain.com",
        display_name="Before",
        email="profile@example.com",
        password="!",
        locale="en",
    )

    response = update_user_base_info(
        _request(
            "/api/v1/console_mgmt/update_user_base_info/",
            user,
            {"display_name": "After", "email": "profile@example.com"},
        )
    )
    user.refresh_from_db()

    assert response.status_code == 200
    assert _payload(response) == {"result": True}
    assert user.display_name == "After"
    assert user.email == "profile@example.com"


def test_validate_email_code_authorizes_then_update_consumes_email_change(memory_cache):
    user = User.objects.create(
        username="email_auth_verified",
        domain="domain.com",
        display_name="Verified",
        email="verified-old@example.com",
        password="!",
        locale="en",
    )
    new_email = "verified-new@example.com"
    code_key = _email_code_cache_key(user.username, new_email)
    verified_key = _email_change_verified_cache_key(user.username, new_email)
    memory_cache.set(code_key, "123456", timeout=600)
    memory_cache.delete(verified_key)
    assert memory_cache.get(code_key) == "123456"

    validate_response = validate_email_code(
        _request(
            "/api/v1/console_mgmt/validate_email_code/",
            user,
            {"email": new_email, "input_code": "123456"},
        )
    )
    update_response = update_user_base_info(
        _request(
            "/api/v1/console_mgmt/update_user_base_info/",
            user,
            {"display_name": "Verified", "email": new_email},
        )
    )
    user.refresh_from_db()
    validate_payload = _payload(validate_response)

    assert validate_payload["result"] is True, validate_payload
    assert memory_cache.get(code_key) is None
    assert update_response.status_code == 200
    assert _payload(update_response) == {"result": True}
    assert user.email == new_email
    assert memory_cache.get(verified_key) is None


def test_email_change_authorization_is_bound_to_requested_email(memory_cache):
    user = User.objects.create(
        username="email_auth_bound",
        domain="domain.com",
        display_name="Bound",
        email="bound-old@example.com",
        password="!",
        locale="en",
    )
    memory_cache.set(_email_change_verified_cache_key(user.username, "allowed@example.com"), "1", timeout=600)

    response = update_user_base_info(
        _request(
            "/api/v1/console_mgmt/update_user_base_info/",
            user,
            {"display_name": "Bound", "email": "other@example.com"},
        )
    )
    user.refresh_from_db()

    assert response.status_code == 403
    assert _payload(response)["result"] is False
    assert user.email == "bound-old@example.com"
