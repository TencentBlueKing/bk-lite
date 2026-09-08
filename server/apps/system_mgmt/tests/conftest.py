import pytest


@pytest.fixture(autouse=True)
def use_dummy_cache_backend(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.dummy.DummyCache",
        }
    }


@pytest.fixture(autouse=True)
def stub_credential_ref_queriers(monkeypatch):
    def zeros(credential_ids, **kwargs):
        return {
            "result": True,
            "data": {"counts": {credential_id: 0 for credential_id in credential_ids or ()}},
        }

    monkeypatch.setattr(
        "apps.system_mgmt.services.credential_ref_count._live_queriers",
        lambda: (("cmdb", zeros), ("monitor", zeros)),
    )
