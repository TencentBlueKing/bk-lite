import pytest
from apps.alerts.enrichment.providers.base import (
    EnrichmentProvider, register_provider, get_provider,
)


def test_register_and_get_provider():
    @register_provider
    class FakeProvider(EnrichmentProvider):
        provider_type = "fake_xyz"

        def fetch_batch(self, keys, config):
            return {k: [{"ok": 1}] for k in keys}

    p = get_provider("fake_xyz")
    assert isinstance(p, EnrichmentProvider)
    assert p.fetch_batch([("a",)], {}) == {("a",): [{"ok": 1}]}


def test_get_unknown_provider_raises():
    with pytest.raises(KeyError):
        get_provider("does_not_exist")
