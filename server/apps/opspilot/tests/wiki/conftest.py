import pytest

from apps.opspilot.tests.wiki.factories import WikiFactory


@pytest.fixture
def wiki_factory():
    return WikiFactory()
