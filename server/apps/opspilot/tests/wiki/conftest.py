import pytest

from apps.opspilot.tests.wiki.factories import WikiFactory


@pytest.fixture(autouse=True)
def grant_wiki_function_permissions(request):
    """API tests opt into the same Wiki function permissions used by the UI."""

    if "api_client" not in request.fixturenames:
        return
    user = request.getfixturevalue("authenticated_user")
    user.permission = {
        "opspilot": {
            "wiki_list-View",
            "wiki_list-Add",
            "wiki_list-Edit",
            "wiki_list-Delete",
        }
    }


@pytest.fixture
def wiki_factory():
    return WikiFactory()
