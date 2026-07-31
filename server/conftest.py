import pydantic.root_model  # noqa: F401
import pytest


@pytest.fixture(autouse=True)
def use_dummy_cache_backend(settings):
    """Replace Django cache with DummyCache for all tests."""
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.dummy.DummyCache",
        }
    }


@pytest.fixture(autouse=True)
def disable_auth_middleware(settings):
    """Remove custom auth middleware so DRF force_authenticate() works in tests."""
    settings.MIDDLEWARE = tuple(
        m for m in settings.MIDDLEWARE
        if m not in (
            "apps.core.middlewares.auth_middleware.AuthMiddleware",
            "apps.core.middlewares.api_middleware.APISecretMiddleware",
        )
    )


@pytest.fixture
def authenticated_user(db):
    """Create an authenticated User with sensible defaults."""
    from apps.base.models import User

    user = User.objects.create_user(
        username="testuser",
        password="testpass123",
        domain="domain.com",
        locale="en",
        group_list=[{"id": 1, "name": "Default Team"}],
        roles=["admin"],
    )
    return user


@pytest.fixture
def api_client(authenticated_user):
    """Return a DRF APIClient authenticated as the default test user."""
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_authenticate(user=authenticated_user)
    return client


@pytest.fixture
def request_factory():
    """Return a Django RequestFactory instance."""
    from django.test import RequestFactory

    return RequestFactory()
