import pytest


pytestmark = pytest.mark.django_db


def test_apm_no_longer_exposes_machine_token_auth(client):
    response = client.get(
        "/api/v1/apm/machine-auth/",
        HTTP_AUTHORIZATION="Bearer legacy-token",
    )

    assert response.status_code == 404
    assert "X-BK-Ingest-Source-Id" not in response.headers
